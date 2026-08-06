from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import requests
from network.RequestWorker import async_request
from models.User import User, SecuredUser


class UserRequests:
    @async_request
    def getAllUsers(loggedUser: User) -> tuple[str, dict[str, SecuredUser]]:
        response = None
        try:
            response = requests.get(f'{SERVER_URL}/users', auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
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
            response = requests.post(f'{SERVER_URL}/users', json=newUser.__dict__, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
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
            response = requests.put(f'{SERVER_URL}/users', json=user_dict, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
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
            response = requests.patch(f'{SERVER_URL}/users/theme', json={'username': loggedUser.getUsername(), 'theme': theme}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
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
            response = requests.patch(f'{SERVER_URL}/users/active', json={'username': username, 'is_active': is_active}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
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
            response = requests.delete(f'{SERVER_URL}/users', json={'username': username}, auth=(loggedUser.getUsername(), loggedUser.getPassword()), timeout=TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete user\n{err}"

        if not data.get("success"):
            err = response.json().get("error", response.text) or response.json().get("message", response.text) if response is not None else str(e)
            return f"Failed to delete user!\n{err}"

