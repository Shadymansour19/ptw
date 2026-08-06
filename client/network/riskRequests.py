from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT
import requests
from network.RequestWorker import async_request
from helper.utils import dictToObj, objToDict
from models.User import User
from models.PTW import PTW, RiskAssessment


class RiskRequests:
    @async_request
    def getAllRiskAssessments(loggedUser: User) -> tuple[str, dict[str, RiskAssessment]]:
        response = None
        try:
            response = requests.get(
                f'{SERVER_URL}/risks',
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
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
                f'{SERVER_URL}/risks/ptw',
                json={'ptw_id': ptw_id},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
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
                f'{SERVER_URL}/risks',
                json=objToDict(riskAssessment),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
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
                f'{SERVER_URL}/risks',
                json=objToDict(riskAssessment),
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
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
                f'{SERVER_URL}/risks',
                json={'title': riskTitle, 'ptw_id': ptw_id},
                auth=(loggedUser.getUsername(), loggedUser.getPassword()),
                timeout=TIMEOUT
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

