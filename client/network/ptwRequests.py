"""PTW endpoint wrappers: fetch, create, update, delete, approve, and drive the
run/hold/close request-and-confirm cycles, plus PTW attachments.

Mixed into ``ClientRequests`` (see ``network/clientRequests.py``).
"""

from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import requests
import tempfile
from network.RequestWorker import async_request
from helper.utils import dictToObj, objToDict
from models.User import User, UserDepartments
from models.PTW import PTW, Attachment


class PTWRequests:
    """Mixin providing PTW lifecycle and attachment endpoints.

    Combined with the other ``*Requests`` mixins into ``ClientRequests``.
    """

    @async_request
    def getAllPTWs(loggedUser: User, department: UserDepartments = None, requestorUsername: str = None) -> tuple[str, dict[int, PTW]]:
        """Fetch all visible PTWs via GET /ptws, optionally filtered by department/requestor.

        Returns ``(None, {id: PTW})`` on success, or ``(err, {})`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ptws',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department, 'requestor': requestorUsername},
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch PTWs\n{err}", {}

        if data.get("success"):
            ptws = [PTW().setAll(namespace=dictToObj(ptwDict)) for ptwDict in data["ptws"]]
            return None, {ptw.id: ptw for ptw in ptws}
        else:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch PTWs\n{err}", {}

    @async_request
    def getPTWById(loggedUser: User, ptwId) -> tuple[str, PTW]:
        """Single-record lookup used for SSE-driven targeted refreshes. A 404 means the PTW
        no longer exists or isn't visible to this user — returned as (None, None), not an error."""
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ptws/{ptwId}',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            if response.status_code == 404:
                return None, None
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch PTW #{ptwId}\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch PTW #{ptwId}\n{err}", None

        return None, PTW().setAll(namespace=dictToObj(data["ptw"]))

    @async_request
    def getArchivedPTWs(loggedUser: User, department: UserDepartments = None) -> tuple[str, dict[int, PTW]]:
        """Fetch all archived PTWs via GET /ptws/archive, optionally filtered by department.

        Returns ``(None, {id: PTW})`` on success, or ``(err, {})`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ptws/archive',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch archived PTWs\n{err}", {}

        if data.get("success"):
            ptws = [PTW().setAll(namespace=dictToObj(ptwDict)) for ptwDict in data["ptws"]]
            return None, {ptw.id: ptw for ptw in ptws}
        else:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch archived PTWs\n{err}", {}

    @async_request
    def addPTW(loggedUser: User, ptw: PTW) -> tuple[str, str]:
        """Create a new PTW via POST /ptws.

        Returns ``(None, ptw-id)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws',
                json=objToDict(ptw),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add PTW\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add PTW\n{err}", None
        return None, data.get('ptw-id')

    @async_request
    def updatePTW(loggedUser: User, ptw: PTW) -> str:
        """Update an existing PTW via PUT /ptws (e.g. edit-and-resubmit a returned PTW).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.put(f'{SERVER_URL}/ptws', json=objToDict(ptw), auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update PTW\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update PTW\n{err}"

        return None

    @async_request
    def addPtwAttachments(loggedUser: User, ptwId: str, attachments: list[Attachment]) -> str:
        """Upload files to a PTW via POST /ptws/attachments.

        If ``attachments`` is empty, delegates to ``deleteAllPtwAttachments`` to
        clear any existing ones instead of sending an empty upload. Returns an
        error string, or None on success.
        """
        if not attachments:
            return PTWRequests.deleteAllPtwAttachments(loggedUser, ptwId)

        files = {}
        opened = []
        for attach in attachments:
            f = open(attach.localPath, 'rb')
            files[attach.remoteName] = (attach.remoteName, f)
            opened.append(f)

        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/attachments',
                data={'ptw-id': ptwId},
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
    def getPtwAttachmentNames(loggedUser: User, ptwId: str) -> tuple[str, list[str]]:
        """List a PTW's attachment filenames via GET /ptws/attachments.

        Returns ``(None, [filename, ...])`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ptws/attachments',
                json={'ptw-id': ptwId},
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
    def getPtwAttachment(loggedUser: User, ptwId: str, filename: str):
        """Download one PTW attachment via GET /ptws/attachments and save it to a temp file.

        Returns ``(None, local_temp_path)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/ptws/attachments',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'ptw-id': ptwId, 'filename': filename},
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to download attachment file {filename}\n{err}", None

        try:
            with tempfile.NamedTemporaryFile(delete=False, prefix=f'attach-{ptwId}-{filename}-', suffix='.pdf') as f:
                f.write(response.content)
                return None, f.name
        except Exception as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to save attachment file {filename}\n{err}", None

    @async_request
    def deleteAllPtwAttachments(loggedUser: User, ptwId: str, keepFilenames: list[str] = []) -> str:
        """Delete a PTW's attachments via DELETE /ptws/attachments, keeping any in ``keepFilenames``.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.delete(
                f'{SERVER_URL}/ptws/attachments',
                json={'ptw-id': ptwId, 'keep-filenames': keepFilenames},
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
    def copyPtwAttachments(loggedUser: User, sourcePtwId: str, targetPtwId: str) -> str:
        """Copy attachments from one PTW to another via POST /ptws/attachments/copy.

        Also additively copies the source PTW's risk assessment onto the target
        (server-side behavior). Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/attachments/copy',
                json={'source-ptw-id': sourcePtwId, 'target-ptw-id': targetPtwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to copy some of the attachments\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to copy attachments\n{err}"
        return None

    @async_request
    def deletePTW(loggedUser: User, ptwId: str) -> str:
        """Delete a PTW via DELETE /ptws. Returns an error string, or None on success."""
        response = None
        try:
            response = requests.delete(f'{SERVER_URL}/ptws', json={'ptw-id': ptwId}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete PTW\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete PTW\n{err}"

        return None

    @async_request
    def returnPTW(loggedUser: User, ptwId: str, comment: str) -> str:
        """Return a PTW to the requestor for corrections via POST /ptws/return, with a comment.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/return',
                json={'ptw-id': ptwId, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to return PTW\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to return PTW\n{err}"

        return None

    @async_request
    def updateApprovalPTW(loggedUser: User, ptwId: str, approval: PTW.Approval) -> str:
        """Submit an approval action on a PTW's approval chain via POST /ptws/approvals.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/approvals',
                json={'ptw-id': ptwId, 'approval': approval.__dict__},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update PTW approvals\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update PTW approvals\n{err}"

        return None

    @async_request
    def archivePTWs(loggedUser: User, ptwIds: list[str]) -> str:
        """Archive one or more closed PTWs via POST /ptws/archive.

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(f'{SERVER_URL}/ptws/archive', json={'ptw-ids': ptwIds}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to archive PTW\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to archive PTW\n{err}"

        return None

    @async_request
    def requestToRunPTW(loggedUser: User, ptwId: str, pa: str, ts: str):
        """Submit a run request for a PTW via POST /ptws/run-request (Performing Authority).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/run-request',
                json={'ptw-id': ptwId, 'pa': pa, 'timestamp': ts},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Request to run PTW {ptwId} failed\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Request to run PTW {ptwId} failed\n{err}"

        return None

    @async_request
    def runResponsePTW(loggedUser: User, ptwId: str, ia: str, ts: str, accepted: bool, comment: str = None) -> str:
        """Accept or reject a PTW's run request via POST /ptws/run (Issuing Authority).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/run',
                json={'ptw-id': ptwId, 'ia': ia, 'timestamp': ts, 'response': accepted, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to {'run' if accepted else 'reject'} PTW {ptwId}\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to {'run' if accepted else 'reject'} PTW {ptwId}\n{err}"

        return None

    @async_request
    def requestToHldPTW(loggedUser: User, ptwId: str, pa: str, ts: str, comment: str = None, heldICs: list[str] = []):
        """Submit a hold request for a running PTW via POST /ptws/hold-request (Performing Authority).

        ``heldICs`` lists which linked ICs should remain held for this cycle.
        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/hold-request',
                json={'ptw-id': ptwId, 'pa': pa, 'timestamp': ts, 'comment': comment, 'held-ics': heldICs},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Request to hold PTW {ptwId} failed\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Request to hold PTW {ptwId} failed\n{err}"

        return None

    @async_request
    def hldResponsePTW(loggedUser: User, ptwId: str, ia: str, ts: str, accepted: bool, comment: str = None) -> str:
        """Accept or reject a PTW's hold request via POST /ptws/hold (Issuing Authority).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/hold',
                json={'ptw-id': ptwId, 'ia': ia, 'timestamp': ts, 'response': accepted, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to {'hold' if accepted else 'reject hold for'} PTW {ptwId}\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to {'hold' if accepted else 'reject hold for'} PTW {ptwId}\n{err}"

        return None

    @async_request
    def requestToClsPTW(loggedUser: User, ptwId: str, pa: str, ts: str, comment: str = None):
        """Submit a close request for a PTW via POST /ptws/close-request (Performing Authority).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/close-request',
                json={'ptw-id': ptwId, 'pa': pa, 'timestamp': ts, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Request to close PTW {ptwId} failed\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Request to close PTW {ptwId} failed\n{err}"

        return None

    @async_request
    def clsResponsePTW(loggedUser: User, ptwId: str, ia: str, ts: str, accepted: bool, comment: str = None) -> str:
        """Accept or reject a PTW's close request via POST /ptws/close (Issuing Authority).

        Returns an error string, or None on success.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/ptws/close',
                json={'ptw-id': ptwId, 'ia': ia, 'timestamp': ts, 'response': accepted, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to {'close' if accepted else 'reject'} PTW {ptwId}\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to {'close' if accepted else 'reject'} PTW {ptwId}\n{err}"

        return None

