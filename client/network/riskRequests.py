"""Risk assessment endpoint wrappers: fetch generic and PTW-specific risk
assessments, and create/update/delete them.

Mixed into ``ClientRequests`` (see ``network/clientRequests.py``).
"""

from network.requestConfig import SERVER_URL, TIMEOUT, FILE_TIMEOUT, extractError
import requests
from network.RequestWorker import async_request
from helper.utils import dictToObj, objToDict
from models.User import User
from models.PTW import PTW, RiskAssessment


class RiskRequests:
    """Mixin providing risk-assessment endpoints.

    Combined with the other ``*Requests`` mixins into ``ClientRequests``.
    """

    @async_request
    def getAllRiskAssessments(loggedUser: User) -> tuple[str, dict[str, RiskAssessment]]:
        """Fetch all generic risk assessments via GET /risks.

        Returns ``(None, {title: RiskAssessment})`` on success, or ``(err, None)`` on failure.
        """
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
            err = extractError(response, e)
            return f"Failed to get risks\n{err}", None

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to get risks\n{err}", None

        return None, {title: RiskAssessment().setAll(riskAssessmentDict) for title, riskAssessmentDict in data["risks"].items()}

    @async_request
    def getPTWSpecificRiskAssessment(loggedUser: User, ptw_id: int) -> tuple[str, RiskAssessment]:
        """Fetch one PTW's specific risk assessment via GET /risks/ptw.

        Returns ``(None, RiskAssessment or None)`` on success, or ``(err, None)`` on failure.
        """
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
            err = extractError(response, e)
            return f"Failed to get PTW-specific risk\n{err}", None

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to get PTW-specific risk\n{err}", None

        return None, RiskAssessment().setAll(data["risk"]) if data.get("risk") else None

    @async_request
    def addNewRiskAssessment(loggedUser: User, riskAssessment: RiskAssessment) ->  str:
        """Create a risk assessment via POST /risks (generic or a PTW's own, per its ``ptw_id``).

        Returns an error string, or None on success.
        """
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
            err = extractError(response, e)
            return f"Failed to add risk\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to add risk\n{err}"
        return None

    @async_request
    def updateRiskAssessment(loggedUser: User, riskAssessment: RiskAssessment) ->  str:
        """Update a risk assessment via PUT /risks.

        Returns an error string, or None on success.
        """
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
            err = extractError(response, e)
            return f"Failed to update risk\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to update risk\n{err}"
        return None

    @async_request
    def deleteRiskAssessment(loggedUser: User, riskTitle: str, ptw_id: int = None) ->  str:
        """Delete a risk assessment via DELETE /risks, identified by title (and PTW id if not generic).

        Returns an error string, or None on success.
        """
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
            err = extractError(response, e)
            return f"Failed to delete risk\n{err}"

        if not data.get("success"):
            err = extractError(response)
            return f"Failed to delete risk\n{err}"
        return None

