"""IC (Isolation Certificate) endpoint wrappers: fetch, create, approve, drive the
isolate/de-isolate request-confirm-execute cycles, PTW linkage, and IC attachments.

Mixed into ``ClientRequests`` (see ``network/clientRequests.py``).
"""

from network.requestConfig import SERVER_URL, VERIFY, TIMEOUT, FILE_TIMEOUT, extractError
import os
import requests
import tempfile
from network.RequestWorker import async_request
from helper.utils import dictToObj, objToDict
from models.User import User, UserDepartments
from models.PTW import PTW, Attachment
from models.Isolation import IC


class ICRequests:
    """Mixin providing IC (Isolation Certificate) lifecycle and attachment endpoints.

    Combined with the other ``*Requests`` mixins into ``ClientRequests``.
    """

    @async_request
    def getAllICs(loggedUser: User, department: UserDepartments = None):
        """Fetch all visible ICs via GET /ics, optionally filtered by department.

        Returns ``(None, {id: IC})`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to get ICs\n{err}", None

        if not data.get("success"):
            err = extractError(response)
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
                verify=VERIFY, timeout=TIMEOUT
            )
            if response.status_code == 404:
                return None, None
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to fetch IC #{icId}\n{err}", None

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to fetch IC #{icId}\n{err}", None

        return None, IC().setAll(namespace=dictToObj(data["ic"]))

    @async_request
    def addIC(loggedUser: User, ic: IC) -> tuple[str, str]:
        """Create a new IC via POST /ics.

        Returns ``(None, ic-id)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics',
                json=objToDict(ic),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to add IC\n{err}", None

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to add IC\n{err}", None
        return None, data.get('ic-id')

    @async_request
    def addIcAttachments(loggedUser: User, icId: str, attachments: list[Attachment]) -> str:
        """Upload P&ID/wiring files to an IC via POST /ics/attachments.

        If ``attachments`` is empty, delegates to ``deleteAllIcAttachments`` to
        clear any existing ones instead of sending an empty upload. Returns an
        error string, or None on success.
        """
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
                verify=VERIFY, timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            for f in opened:
                f.close()
            err = extractError(response, e)
            return f"Failed to add attachment\n{err}"

        for f in opened:
            f.close()

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to add attachment\n{err}"
        return None

    @async_request
    def getIcAttachmentNames(loggedUser: User, icId: str) -> tuple[str, list[str]]:
        """List an IC's P&ID/wiring attachment filenames via GET /ics/attachments.

        Returns ``(None, [filename, ...])`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics/attachments',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to get attachments\n{err}", None

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to get attachments\n{err}", None

        return None, data.get("attachments", [])

    @async_request
    def getIcAttachment(loggedUser: User, icId: str, filename: str):
        """Download one IC P&ID/wiring attachment via GET /ics/attachments and save it to a temp file.

        Returns ``(None, local_temp_path)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ics/attachments',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'ic-id': icId, 'filename': filename},
                verify=VERIFY, timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to download attachment file {filename}\n{err}", None

        try:
            suffix = os.path.splitext(filename)[1] or '.pdf'
            with tempfile.NamedTemporaryFile(delete=False, prefix=f'attach-{icId}-{filename}-', suffix=suffix) as f:
                f.write(response.content)
                return None, f.name
        except Exception as e:
            # response.content here is the already-downloaded binary PDF, not JSON - the
            # failure is local (e.g. disk full/permission denied writing the temp file),
            # so use e's own message directly rather than trying (and failing) to parse it.
            return f"Failed to save attachment file {filename}\n{e}", None

    @async_request
    def deleteAllIcAttachments(loggedUser: User, icId: str, keepFilenames: list[str] = []) -> str:
        """Delete an IC's P&ID/wiring attachments via DELETE /ics/attachments, keeping any in ``keepFilenames``.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.delete(
                f'{SERVER_URL}/ics/attachments',
                json={'ic-id': icId, 'keep-filenames': keepFilenames},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to delete attachments\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to delete attachments\n{err}"
        return None

    @async_request
    def updateApprovalIC(loggedUser: User, icId, approval: IC.Approval, mark_psic: bool = False, psic_terms: dict = None) -> str:
        """Submit an approval action on an IC's approval chain via POST /ics/approvals.

        `mark_psic` is only meaningful for Issuing's own approval (flags the IC as a PSIC);
        `psic_terms` is only meaningful for Coordinator's own approval of a PSIC (the
        reasons/MOC number/description fields their approval doubles as writing - see
        DialogDefinePsicTerms.getTerms()). Neither has any effect for any other role/stage.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/approvals',
                json={'ic-id': icId, 'approval': approval.__dict__, 'mark_psic': mark_psic, 'psic_terms': psic_terms},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to update IC approvals\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to update IC approvals\n{err}"

        return None

    @async_request
    def requestIsolateIC(loggedUser: User, icId) -> str:
        """Request that an approved IC's isolation be carried out via POST /ics/isolate-request.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/isolate-request',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to request isolation\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to request isolation\n{err}"

        return None

    @async_request
    def confirmIsolateIC(loggedUser: User, icId, response: bool) -> str:
        """Issuing confirms or returns an isolate request via POST /ics/isolate-confirm.

        Returns an error string, or None on success.
        """
        resp = None
        try:
            resp = requests.post(
                f'{SERVER_URL}/ics/isolate-confirm',
                json={'ic-id': icId, 'response': response},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
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
        """Isolator carries out the isolation via POST /ics/isolate-execute, with optional per-item lock #/lock box # data.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/isolate-execute',
                json={'ic-id': icId, 'items': objToDict(items or [])},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to execute isolation\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to execute isolation\n{err}"

        return None

    @async_request
    def requestDeisolateIC(loggedUser: User, icId) -> str:
        """Request de-isolation of an active IC via POST /ics/deisolate-request.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/deisolate-request',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to request de-isolation\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to request de-isolation\n{err}"

        return None

    @async_request
    def confirmDeisolateIC(loggedUser: User, icId, response: bool) -> str:
        """Issuing confirms or returns a de-isolate request via POST /ics/deisolate-confirm.

        Returns an error string, or None on success.
        """
        resp = None
        try:
            resp = requests.post(
                f'{SERVER_URL}/ics/deisolate-confirm',
                json={'ic-id': icId, 'response': response},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
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
        """Isolator carries out the de-isolation via POST /ics/deisolate-execute, closing the IC.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/deisolate-execute',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to execute de-isolation\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to execute de-isolation\n{err}"

        return None

    @async_request
    def linkPTWToIC(loggedUser: User, icId, ptwId) -> str:
        """Link a PTW to an IC via POST /ics/link-ptw (symmetric write to both records).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/link-ptw',
                json={'ic-id': icId, 'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to link PTW\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to link PTW\n{err}"

        return None

    @async_request
    def unlinkPTWFromIC(loggedUser: User, icId, ptwId) -> str:
        """Unlink a PTW from an IC via POST /ics/unlink-ptw (symmetric write to both records).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ics/unlink-ptw',
                json={'ic-id': icId, 'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to unlink PTW\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to unlink PTW\n{err}"

        return None

