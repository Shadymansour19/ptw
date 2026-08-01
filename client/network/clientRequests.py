import os
import re
import requests
from models.User import User, SecuredUser, UserDepartments
from models.PTW import PTW, RiskAssessment, Attachment
from models.Isolation import IC
from helper.utils import dictToObj, objToDict
from typing import Iterable
import tempfile
from network.RequestWorker import async_request

class ClientRequests:
    SERVER_URL = 'http://localhost:5000'
    TIMEOUT = 15        # seconds; generic request timeout
    FILE_TIMEOUT = 60   # seconds; upload/download endpoints transferring file content

    @async_request
    def login(username, password) -> tuple[str, User]:
        response = None
        try:
            response = requests.post(f'{ClientRequests.SERVER_URL}/login', auth=(username, password), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) if response is not None else str(e)
            return f"Login request failed\n{err}\n", None

        if data.get("success"):
            user = User().setAll(data.get('user'))
            user.setPassword(password)
            return None, user
        else:
            err = response.json().get("error", response.text) if response is not None else str(e)
            return f"Login Failed! Incorrect username or password\n{err}", None

    @async_request
    def requestResetPassword(username: str):
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/reset-password-request',
                json={'username': username},
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Password reset request failed\n{err}\nPlease check your connection and try again."

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return data.get("message", f"Password reset request failed\n{err}")
        return None


    @async_request
    def resetPassword(username: str, newPassword: str, verificationCode: str) -> str:
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/reset-password',
                json={'username': username, 'new-password': newPassword, 'verification-code': verificationCode},
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Password reset failed\n{err}\nPlease check your connection and try again."

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return data.get("message", f"Password reset failed!\n{err}")
        return None

    @async_request
    def getAllUsers(loggedUser: User) -> tuple[str, dict[str, SecuredUser]]:
        response = None
        try:
            response = requests.get(f'{ClientRequests.SERVER_URL}/users', auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch users\n{err}", None

        if data.get("success"):
            allUsers = {}
            for d in data.get('all-users').values():
                user = SecuredUser().setAll(d)
                allUsers[user.getUsername()] = user
            return None, allUsers
        else:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch users\n{err}", None

    @async_request
    def addNewUser(loggedUser: User, newUser: User):
        response = None
        try:
            response = requests.post(f'{ClientRequests.SERVER_URL}/users', json=newUser.__dict__, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to register user\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to register user!\n{err}"

    @async_request
    def updateUser(loggedUser: User, user: User):
        response = None
        try:
            user_dict = {k: v for k, v in user.__dict__.items() if not (k == 'password' and not v)}
            response = requests.put(f'{ClientRequests.SERVER_URL}/users', json=user_dict, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update user\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update user!\n{err}"

    @async_request
    def updateTheme(loggedUser: User, theme: str | None):
        response = None
        try:
            response = requests.patch(f'{ClientRequests.SERVER_URL}/users/theme', json={'username': loggedUser.getUsername(), 'theme': theme}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) if response is not None else str(e)
            return f"Failed to update theme\n{err}"
        if not data.get("success"):
            return data.get("error", "Failed to update theme")

    @async_request
    def setUserActive(loggedUser: User, username: str, is_active: bool):
        response = None
        try:
            response = requests.patch(f'{ClientRequests.SERVER_URL}/users/active', json={'username': username, 'is_active': is_active}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) if response is not None else str(e)
            return f"Failed to update active status\n{err}"
        if not data.get("success"):
            return data.get("error", "Failed to update active status")

    @async_request
    def deleteUser(loggedUser: User, username: str):
        response = None
        try:
            response = requests.delete(f'{ClientRequests.SERVER_URL}/users', json={'username': username}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete user\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete user!\n{err}"

    @async_request
    def getAllPTWs(loggedUser: User, department: UserDepartments = None, requestorUsername: str = None) -> tuple[str, Iterable[PTW]]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/ptws',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department, 'requestor': requestorUsername},
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch PTWs\n{err}", []

        if data.get("success"):
            return None, [PTW().setAll(namespace=dictToObj(ptwDict)) for ptwDict in data["ptws"]]
        else:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch PTWs\n{err}", []

    @async_request
    def getArchivedPTWs(loggedUser: User, department: UserDepartments = None) -> tuple[str, Iterable[PTW]]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/ptws/archive',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch archived PTWs\n{err}", []

        if data.get("success"):
            return None, [PTW().setAll(namespace=dictToObj(ptwDict)) for ptwDict in data["ptws"]]
        else:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to fetch archived PTWs\n{err}", []

    @async_request
    def addPTW(loggedUser: User, ptw: PTW) -> tuple[str, str]:
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws',
                json=objToDict(ptw),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.put(f'{ClientRequests.SERVER_URL}/ptws', json=objToDict(ptw), auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
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
        if not attachments:
            return ClientRequests.deleteAllPtwAttachments(loggedUser, ptwId)

        files = {}
        opened = []
        for attach in attachments:
            f = open(attach.localPath, 'rb')
            files[attach.remoteName] = (attach.remoteName, f)
            opened.append(f)

        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/attachments',
                data={'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                files=files,
                timeout=ClientRequests.FILE_TIMEOUT
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
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/ptws/attachments',
                json={'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/ptws/attachments',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'ptw-id': ptwId, 'filename': filename},
                timeout=ClientRequests.FILE_TIMEOUT
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
        response = None
        try:
            response = requests.delete(
                f'{ClientRequests.SERVER_URL}/ptws/attachments',
                json={'ptw-id': ptwId, 'keep-filenames': keepFilenames},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/attachments/copy',
                json={'source-ptw-id': sourcePtwId, 'target-ptw-id': targetPtwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.FILE_TIMEOUT
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
        response = None
        try:
            response = requests.delete(f'{ClientRequests.SERVER_URL}/ptws', json={'ptw-id': ptwId}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/return',
                json={'ptw-id': ptwId, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/approvals',
                json={'ptw-id': ptwId, 'approval': approval.__dict__},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(f'{ClientRequests.SERVER_URL}/ptws/archive', json={'ptw-ids': ptwIds}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=ClientRequests.TIMEOUT)
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/run-request',
                json={'ptw-id': ptwId, 'pa': pa, 'timestamp': ts},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/run',
                json={'ptw-id': ptwId, 'ia': ia, 'timestamp': ts, 'response': accepted, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/hold-request',
                json={'ptw-id': ptwId, 'pa': pa, 'timestamp': ts, 'comment': comment, 'held-ics': heldICs},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/hold',
                json={'ptw-id': ptwId, 'ia': ia, 'timestamp': ts, 'response': accepted, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/close-request',
                json={'ptw-id': ptwId, 'pa': pa, 'timestamp': ts, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ptws/close',
                json={'ptw-id': ptwId, 'ia': ia, 'timestamp': ts, 'response': accepted, 'comment': comment},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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


    @async_request
    def getAllICs(loggedUser: User, department: UserDepartments = None):
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/ics',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                timeout=ClientRequests.TIMEOUT
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
    def addIC(loggedUser: User, ic: IC) -> tuple[str, str]:
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ics',
                json=objToDict(ic),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
            return ClientRequests.deleteAllIcAttachments(loggedUser, icId)

        files = {}
        opened = []
        for attach in attachments:
            f = open(attach.localPath, 'rb')
            files[attach.remoteName] = (attach.remoteName, f)
            opened.append(f)

        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/ics/attachments',
                data={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                files=files,
                timeout=ClientRequests.FILE_TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/attachments',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/attachments',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'ic-id': icId, 'filename': filename},
                timeout=ClientRequests.FILE_TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/attachments',
                json={'ic-id': icId, 'keep-filenames': keepFilenames},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/approvals',
                json={'ic-id': icId, 'approval': approval.__dict__},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/isolate-request',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/isolate-confirm',
                json={'ic-id': icId, 'response': response},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/isolate-execute',
                json={'ic-id': icId, 'items': objToDict(items or [])},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/deisolate-request',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/deisolate-confirm',
                json={'ic-id': icId, 'response': response},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/deisolate-execute',
                json={'ic-id': icId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/link-ptw',
                json={'ic-id': icId, 'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/ics/unlink-ptw',
                json={'ic-id': icId, 'ptw-id': ptwId},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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


    @async_request
    def getAllRiskAssessments(loggedUser: User) -> tuple[str, dict[str, RiskAssessment]]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/risks',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get risks\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get risks\n{err}", None

        return None, {title: RiskAssessment().setAll(riskAssessmentDict) for title, riskAssessmentDict in data["risks"].items()}

    @async_request
    def getPTWSpecificRiskAssessment(loggedUser: User, ptw_id: int) -> tuple[str, RiskAssessment]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/risks/ptw',
                json={'ptw_id': ptw_id},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get PTW-specific risk\n{err}", None

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get PTW-specific risk\n{err}", None

        return None, RiskAssessment().setAll(data["risk"]) if data.get("risk") else None

    @async_request
    def addNewRiskAssessment(loggedUser: User, riskAssessment: RiskAssessment) ->  str:
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/risks',
                json=objToDict(riskAssessment),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add risk\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to add risk\n{err}"
        return None

    @async_request
    def updateRiskAssessment(loggedUser: User, riskAssessment: RiskAssessment) ->  str:
        response = None
        try:
            response = requests.put(
                f'{ClientRequests.SERVER_URL}/risks',
                json=objToDict(riskAssessment),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update risk\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to update risk\n{err}"
        return None


    @async_request
    def deleteRiskAssessment(loggedUser: User, riskTitle: str, ptw_id: int = None) ->  str:
        response = None
        try:
            response = requests.delete(
                f'{ClientRequests.SERVER_URL}/risks',
                json={'title': riskTitle, 'ptw_id': ptw_id},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete risk\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete risk\n{err}"
        return None


    @async_request
    def getMIWI(loggedUser: User, filename: str, department: UserDepartments = None) -> tuple[str, str]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/miwi',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'filename': filename, 'department': department},
                timeout=ClientRequests.FILE_TIMEOUT
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
                f'{ClientRequests.SERVER_URL}/miwis',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'department': department},
                timeout=ClientRequests.TIMEOUT
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
                    f'{ClientRequests.SERVER_URL}/miwi',
                    auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                    files=files,
                    data={'department': loggedUser.getDepartment()},
                    timeout=ClientRequests.FILE_TIMEOUT
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

    @async_request
    def getLogFiles(loggedUser: User) -> tuple[str, list[str]]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/logs',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/logs',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                json={'filename': filename},
                timeout=ClientRequests.TIMEOUT
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to get log file '{filename}'\n{err}", None

        return None, response.text

    @async_request
    def getBackups(loggedUser: User) -> tuple[str, dict]:
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/backups',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.post(
                f'{ClientRequests.SERVER_URL}/backups',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.FILE_TIMEOUT
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
        response = None
        try:
            response = requests.delete(
                f'{ClientRequests.SERVER_URL}/backups',
                json={'name': name},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.TIMEOUT
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
        response = None
        try:
            response = requests.get(
                f'{ClientRequests.SERVER_URL}/backups',
                json={'name': name, 'which': which},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=ClientRequests.FILE_TIMEOUT
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
