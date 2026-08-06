from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import requests
import tempfile
from network.RequestWorker import async_request
from models.User import User, UserDepartments


class DocumentRequests:
    @async_request
    def getMIWI(loggedUser: User, filename: str, department: UserDepartments = None) -> tuple[str, str]:
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/miwi',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'filename': filename, 'department': department},
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to download MIWI file\n{err}", None

        try:
            with tempfile.NamedTemporaryFile(delete=False, prefix=f'miwi-{filename}-', suffix='.pdf') as f:
                f.write(response.content)
                return None, f.name
        except Exception as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to save MIWI file\n{err}", None

    @async_request
    def getAllMIWIs(loggedUser: User, department: UserDepartments = None) -> tuple[str, list[str]]:
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/miwis',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get MIWIs\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get MIWIs\n{err}", None

        return None, data["miwis"]

    @async_request
    def uploadMIWI(loggedUser: User, filePath: str, savename: str = None) -> str:
        response = None
        try:
            with open(filePath, 'rb') as f:
                files = {'miwi': (savename, f, 'application/pdf')}
                response = requests.post(
                    f'{SERVER_URL}/miwi',
                    auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                    files=files,
                    data={'department': loggedUser.getDepartment()},
                    timeout=FILE_TIMEOUT
                )
                response.raise_for_status()
                data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to upload MIWI file\n{err}"
        except Exception as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to read MIWI file\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to upload MIWI file\n{err}"

        return None

