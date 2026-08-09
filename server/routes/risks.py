"""Flask blueprint for risk assessments.

Covers CRUD for the generic risk-assessment library (Safety role only,
``ptw_id`` is ``None``) and for a PTW's own materialized risk-item row set
(any authenticated user, ``ptw_id`` set) — the server distinguishes the two
by checking whether ``ptw_id`` is present, not by trusting a client-declared
role.
"""

from flask import Blueprint, request, jsonify

from core import log, ptwDB, risksDB
from models.User import UserRoles
from routes.auth import getVerifiedUser
from utils import objToDict

risksBp = Blueprint("risks", __name__)


@risksBp.route("/risks", methods=["GET"])
def getAllRiskAssessments():
    """Return every generic risk assessment (``ptw_id IS NULL``).

    GET /risks. Requires any authenticated user; no role restriction.
    Responds with ``{"success": True, "risks": [...]}``, or a 400 with an
    error message if the lookup fails.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /risks unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        risks = risksDB.getAllRiskAssessments()
        log.debug("GET /risks: %d assessments returned to user='%s'", len(risks), user.getUsername())
        return jsonify({"success": True, "risks": objToDict(risks)})
    except Exception as e:
        log.error("GET /risks failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@risksBp.route("/risks/ptw", methods=["GET"])
def getPTWSpecificRiskAssessment():
    """Return one PTW's materialized risk assessment row set.

    GET /risks/ptw. Requires any authenticated user, any department. Body:
    ``{"ptw_id": <int>}``; 400 if missing/invalid, 404 if the PTW doesn't
    exist. Responds with ``{"success": True, "risk": <RiskAssessment or
    None>}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /risks/ptw unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptw_id = payload.get('ptw_id')
    if ptw_id is None:
        log.warning("GET /risks/ptw: missing ptw_id (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        ptw_id = int(ptw_id)
    except (TypeError, ValueError):
        log.warning("GET /risks/ptw: invalid ptw_id=%r (user='%s')", ptw_id, user.getUsername())
        return jsonify({"success": False, "error": "Invalid PTW id"}), 400
    ptw = ptwDB.getPTWById(ptw_id)
    if ptw is None:
        log.warning("GET /risks/ptw: PTW #%s not found (user='%s')", ptw_id, user.getUsername())
        return jsonify({"success": False, "error": "PTW not found"}), 404
    try:
        risk = risksDB.getPTWSpecificRiskAssessment(ptw_id)
        log.debug("GET /risks/ptw: PTW #%s risk returned to user='%s'", ptw_id, user.getUsername())
        return jsonify({"success": True, "risk": objToDict(risk) if risk else None})
    except Exception as e:
        log.error("GET /risks/ptw failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@risksBp.route("/risks", methods=["POST"])
def addNewRiskAssessment():
    """Create a risk assessment.

    POST /risks. Requires an authenticated user; only the Safety role may
    create a generic assessment (``ptw_id`` absent) — any user may create
    their own PTW-specific row set (``ptw_id`` set), 401 otherwise. Body is
    the risk assessment dict. Responds with ``{"success": True, "error":
    <db result>}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /risks unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    riskAssessmentDict = request.get_json(silent=True) or {}
    title = riskAssessmentDict.get('title', '')
    ptw_id = riskAssessmentDict.get('ptw_id')
    # Non-safety users may only create PTW-specific risks (ptw_id set)
    if user.getRole() != UserRoles.SAFETY and ptw_id is None:
        log.warning("POST /risks unauthorized: requester='%s' tried to create non-PTW risk (ip=%s)", user.getUsername(), request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        result = risksDB.addRiskAssessmentFromDict(riskAssessmentDict)
        log.info("Risk assessment created: title='%s' by='%s'", title, user.getUsername())
        return jsonify({"success": True, "error": result})
    except Exception as e:
        log.error("POST /risks failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@risksBp.route("/risks", methods=["PUT"])
def updateRiskAssessment():
    """Update a risk assessment.

    PUT /risks. Requires an authenticated user; only the Safety role may
    update a generic assessment (``ptw_id`` absent) — any user may update
    their own PTW-specific row set (``ptw_id`` set), 401 otherwise. Body is
    the risk assessment dict. Responds with ``{"success": True, "error":
    <db result>}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("PUT /risks unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    riskAssessmentDict = request.get_json(silent=True) or {}
    title = riskAssessmentDict.get('title', '')
    ptw_id = riskAssessmentDict.get('ptw_id')
    # Non-safety users may only update PTW-specific risks (ptw_id set)
    if user.getRole() != UserRoles.SAFETY and ptw_id is None:
        log.warning("PUT /risks unauthorized: requester='%s' tried to update non-PTW risk (ip=%s)", user.getUsername(), request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        result = risksDB.updateRiskAssessmentFromDict(riskAssessmentDict)
        log.info("Risk assessment updated: title='%s' by='%s'", title, user.getUsername())
        return jsonify({"success": True, "error": result})
    except Exception as e:
        log.error("PUT /risks failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@risksBp.route("/risks", methods=["DELETE"])
def deleteRiskAssessment():
    """Delete a risk assessment by title.

    DELETE /risks. Requires an authenticated user; only the Safety role may
    delete a generic assessment (``ptw_id`` absent) — any user may delete
    their own PTW-specific row set (``ptw_id`` set), 401 otherwise. Body:
    ``{"title": <str>, "ptw_id": <optional>}``. Responds with
    ``{"success": True, "error": <db result>}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("DELETE /risks unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        title = data['title']
        ptw_id = data.get('ptw_id')
        # Non-safety users may only delete PTW-specific risks (ptw_id set)
        if user.getRole() != UserRoles.SAFETY and ptw_id is None:
            log.warning("DELETE /risks unauthorized: requester='%s' tried to delete non-PTW risk (ip=%s)", user.getUsername(), request.remote_addr)
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        result = risksDB.deleteRiskAssessment(title)
        log.info("Risk assessment deleted: title='%s' by='%s'", title, user.getUsername())
        return jsonify({"success": True, "error": result})
    except Exception as e:
        log.error("DELETE /risks failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400
