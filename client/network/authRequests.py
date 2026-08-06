from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import requests
from network.RequestWorker import async_request
from models.User import User


class AuthRequests:
    @async_request
    def login(username, password) -> tuple[str, User]:
        response = None
        try:
            response = requests.post(f'{SERVER_URL}/login', auth=(username, password), timeout=TIMEOUT)
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
                f'{SERVER_URL}/reset-password-request',
                json={'username': username},
                timeout=TIMEOUT
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
                f'{SERVER_URL}/reset-password',
                json={'username': username, 'new-password': newPassword, 'verification-code': verificationCode},
                timeout=TIMEOUT
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

