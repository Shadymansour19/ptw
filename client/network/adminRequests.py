"""Admin-only endpoint wrappers: server log files and on-demand database/file backups.

Mixed into ``ClientRequests`` (see ``network/clientRequests.py``).
"""

from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import re
import requests
from network.RequestWorker import async_request
from models.User import User


class AdminRequests:
    """Mixin providing admin-only endpoints for logs and backups.

    Combined with the other ``*Requests`` mixins into ``ClientRequests``.
    """

    @async_request
    def getLogFiles(loggedUser: User) -> tuple[str, list[str]]:
        """List server log filenames via GET /logs (no request body).

        Returns ``(None, [filename, ...])`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/logs',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get log files\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get log files\n{err}", None

        return None, data["logs"]

    @async_request
    def getLog(loggedUser: User, filename: str) -> tuple[str, str]:
        """Download a specific log file's contents via GET /logs.

        Returns ``(None, file_text)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/logs',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'filename': filename},
                timeout=TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get log file '{filename}'\n{err}", None

        return None, response.text

    @async_request
    def getBackups(loggedUser: User) -> tuple[str, dict]:
        """List existing backups via GET /backups (no request body).

        Returns ``(None, {"backups": [...], "retentionDays": ..., "freeBytes": ..., "lastBackupAt": ...})``
        on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/backups',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get backups\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get backups\n{err}", None

        return None, data

    @async_request
    def createBackup(loggedUser: User) -> tuple[str, dict]:
        """Create an on-demand backup now via POST /backups.

        Returns ``(None, backup_row_dict)`` on success, or ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.post(
                f'{SERVER_URL}/backups',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to create backup\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to create backup\n{err}", None

        return None, data["backup"]

    @async_request
    def deleteBackup(loggedUser: User, name: str) -> str:
        """Delete a backup by its timestamp name via DELETE /backups.

        Returns an error string, or None (implicitly) on success.
        """
        response = None
        try:
            response = requests.delete(
                f'{SERVER_URL}/backups',
                json={'name': name},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete backup\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete backup\n{err}"

    @async_request
    def downloadBackupFile(loggedUser: User, name: str, which: str) -> tuple[str, dict]:
        """Download one backup's dump or files archive via GET /backups (``which`` is ``"dump"`` or ``"files"``).

        Reads the real filename from the response's Content-Disposition header
        rather than guessing it client-side. Returns
        ``(None, {"filename": ..., "content": bytes})`` on success, or
        ``(err, None)`` on failure.
        """
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/backups',
                json={'name': name, 'which': which},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=FILE_TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to download backup file '{which}' for '{name}'\n{err}", None

        # Trust the server's Content-Disposition for the real filename (e.g. the actual
        # <dbname>.dump) rather than guessing it client-side.
        match = re.search(r'filename="?([^";]+)"?', response.headers.get('Content-Disposition', ''))
        filename = match.group(1) if match else which
        return None, {'filename': filename, 'content': response.content}

