from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import os
import requests
import tempfile
from network.RequestWorker import async_request
from helper.utils import dictToObj, objToDict
from models.User import User, UserDepartments
from models.PTW import PTW, Attachment
from models.Isolation import IC


class ICRequests:
    @async_request
    def getAllICs(loggedUser: User, department: UserDepartments = None):
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get ICs\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get ICs\n{err}", None

        return None, {ic['id']: IC().setAll(namespace=dictToObj(ic)) for ic in data.get("ics", [])}

    @async_request
    def getICById(loggedUser: User, icId) -> tuple[str, IC]:
        """Single-record lookup used for SSE-driven targeted refreshes. A 404 means the IC
        no longer exists or isn't visible to this user — returned as (None, None), not an error."""
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics/{icId}',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            if response.status_code == 404:
                return None, None
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch IC #{icId}\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch IC #{icId}\n{err}", None

        return None, IC().setAll(namespace=dictToObj(data["ic"]))

    @async_request
    def addIC(loggedUser: User, ic: IC) -> tuple[str, str]:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics',
                json=objToDict(ic),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add IC\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add IC\n{err}", None
        return None, data.get('ic-id')

    @async_request
    def addIcAttachments(loggedUser: User, icId: str, attachments: list[Attachment]) -> str:
        if not attachments:
            return ICRequests.deleteAllIcAttachments(loggedUser, icId)

        files = {}
        opened = []
        for attach in attachments:
            f = open(attach.localPath, 'rb')
            files[attach.remoteName] = (attach.remoteName, f)
            opened.append(f)

        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/attachments',
                data={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                files=files,
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            for f in opened:
                f.close()
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add attachment\n{err}"

        for f in opened:
            f.close()

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add attachment\n{err}"
        return None

    @async_request
    def getIcAttachmentNames(loggedUser: User, icId: str) -> tuple[str, list[str]]:
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics/attachments',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get attachments\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get attachments\n{err}", None

        return None, data.get("attachments", [])

    @async_request
    def getIcAttachment(loggedUser: User, icId: str, filename: str):
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics/attachments',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'ic-id': icId, 'filename': filename},
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to download attachment file {filename}\n{err}", None

        try:
            suffix = os.path.splitext(filename)[1] or '.pdf'
            with tempfile.NamedTemporaryFile(delete=False, prefix=f'attach-{icId}-{filename}-', suffix=suffix) as f:
                f.write(response.content)
                return None, f.name
        except Exception as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to save attachment file {filename}\n{err}", None

    @async_request
    def deleteAllIcAttachments(loggedUser: User, icId: str, keepFilenames: list[str] = []) -> str:
        response = None
        try:
            response = requests.delete(
                f'{SERVER_URL}/ics/attachments',
                json={'ic-id': icId, 'keep-filenames': keepFilenames},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete attachments\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete attachments\n{err}"
        return None

    @async_request
    def updateApprovalIC(loggedUser: User, icId, approval: IC.Approval) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/approvals',
                json={'ic-id': icId, 'approval': approval.__dict__},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update IC approvals\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update IC approvals\n{err}"

        return None

    @async_request
    def requestIsolateIC(loggedUser: User, icId) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/isolate-request',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to request isolation\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to request isolation\n{err}"

        return None

    @async_request
    def confirmIsolateIC(loggedUser: User, icId, response: bool) -> str:
        resp = None
        try:
            resp = requests.post(
                f'{SERVER_URL}/ics/isolate-confirm',
                json={'ic-id': icId, 'response': response},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            err = resp.json().get("error", resp.text) or resp.json().get("message", resp.text) if resp is not None else str(e)
            return f"Failed to confirm isolation\n{err}"

        if not data.get("success"):
            err = resp.json().get("error", resp.text) or resp.json().get("message", resp.text) if resp is not None else str(e)
            return f"Failed to confirm isolation\n{err}"

        return None

    @async_request
    def executeIsolateIC(loggedUser: User, icId, items: list = None) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/isolate-execute',
                json={'ic-id': icId, 'items': objToDict(items or [])},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to execute isolation\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to execute isolation\n{err}"

        return None

    @async_request
    def requestDeisolateIC(loggedUser: User, icId) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/deisolate-request',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to request de-isolation\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to request de-isolation\n{err}"

        return None

    @async_request
    def confirmDeisolateIC(loggedUser: User, icId, response: bool) -> str:
        resp = None
        try:
            resp = requests.post(
                f'{SERVER_URL}/ics/deisolate-confirm',
                json={'ic-id': icId, 'response': response},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.RequestException as e:
            err = resp.json().get("error", resp.text) or resp.json().get("message", resp.text) if resp is not None else str(e)
            return f"Failed to confirm de-isolation\n{err}"

        if not data.get("success"):
            err = resp.json().get("error", resp.text) or resp.json().get("message", resp.text) if resp is not None else str(e)
            return f"Failed to confirm de-isolation\n{err}"

        return None

    @async_request
    def executeDeisolateIC(loggedUser: User, icId) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/deisolate-execute',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to execute de-isolation\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to execute de-isolation\n{err}"

        return None

    @async_request
    def linkPTWToIC(loggedUser: User, icId, ptwId) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/link-ptw',
                json={'ic-id': icId, 'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to link PTW\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to link PTW\n{err}"

        return None

    @async_request
    def unlinkPTWFromIC(loggedUser: User, icId, ptwId) -> str:
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/unlink-ptw',
                json={'ic-id': icId, 'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to unlink PTW\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to unlink PTW\n{err}"

        return None

