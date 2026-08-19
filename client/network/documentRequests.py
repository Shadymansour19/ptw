"""MIWI (Maintenance and Work Instructions) document endpoint wrappers: list,
download, and upload.

Mixed into ``ClientRequests`` (see ``network/clientRequests.py``).
"""

from network.requestConfig import SERVER_URL, VERIFY, TIMEOUT, FILE_TIMEOUT, extractError
import requests
import tempfile
from network.RequestWorker import async_request
from models.User import User, UserDepartments


class DocumentRequests:
    """Mixin providing MIWI document endpoints.

    Combined with the other ``*Requests`` mixins into ``ClientRequests``.
    """

    @async_request
    def getMIWI(loggedUser: User, filename: str, department: UserDepartments = None) -> tuple[str, str]:
        """Download a MIWI PDF via GET /miwi and save it to a temp file.

        Returns ``(None, local_temp_path)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/miwi',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'filename': filename, 'department': department},
                verify=VERIFY, timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to download MIWI file\n{err}", None

        try:
            with tempfile.NamedTemporaryFile(delete=False, prefix=f'miwi-{filename}-', suffix='.pdf') as f:
                f.write(response.content)
                return None, f.name
        except Exception as e:
            # response.content here is the already-downloaded binary PDF, not JSON - the
            # failure is local (e.g. disk full/permission denied writing the temp file),
            # so use e's own message directly rather than trying (and failing) to parse it.
            return f"Failed to save MIWI file\n{e}", None

    @async_request
    def getAllMIWIs(loggedUser: User, department: UserDepartments = None) -> tuple[str, list[str]]:
        """List MIWI filenames via GET /miwis, optionally scoped by department.

        Returns ``(None, [filename, ...])`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/miwis',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                verify=VERIFY, timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to get MIWIs\n{err}", None

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to get MIWIs\n{err}", None

        return None, data["miwis"]

    @async_request
    def uploadMIWI(loggedUser: User, filePath: str, savename: str = None) -> str:
        """Upload a new MIWI PDF via POST /miwi, into the logged-in user's own department.

        Returns an error string, or None on success.
        """
        response = None
        try:
            with open(filePath, 'rb') as f:
                files = {'miwi': (savename, f, 'application/pdf')}
                response = requests.post(
                    f'{SERVER_URL}/miwi',
                    auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                    files=files,
                    data={'department': loggedUser.getDepartment()},
                    verify=VERIFY, timeout=FILE_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
        except requests.exceptions.RequestException as e:
            err = extractError(response, e)
            return f"Failed to upload MIWI file\n{err}"
        except Exception as e:
            err = extractError(response, e)
            return f"Failed to read MIWI file\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to upload MIWI file\n{err}"

        return None

