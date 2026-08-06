from flask import Blueprint, request, jsonify

from core import log, ptwDB, risksDB
from models.User import UserRoles
from routes.auth import getVerifiedUser
from utils import objToDict

risksBp = Blueprint("risks", __name__)


@risksBp.route("/risks", methods=["GET"])
def getAllRiskAssessments():
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
