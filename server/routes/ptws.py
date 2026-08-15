"""Flask blueprint for PTW (Permit To Work) endpoints: listing and CRUD,
the approval chain, the run/hold/close running-cycle state machine, manual
and automatic archiving, and PTW attachment management.
"""
import os
import shutil
import threading
from time import sleep
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, send_file

import sse
import paths
from core import log, ptwDB, risksDB, syncPtwCache
from GlobalData import globalData
from models.User import UserRoles
from models.PTW import PTW
from models.Isolation import IC
from models.SSE import SSEObject, SSEAction
from routes.auth import getVerifiedUser
from routes.ics import checkAndAutoDeisolateICs
from utils import objToDict

ptwsBp = Blueprint("ptws", __name__)

# PTW listing itself only restricts USER/GUEST (MainWindow.refreshPtwUserGUI passes
# department=None for ISOLATOR — isolators need cross-department PTW visibility).
# MIWI documents and PTW-specific risk assessments are reviewable by any authenticated
# user regardless of department — only PTW listing itself is department-scoped.
_RESTRICTED_PTW_ROLES = {UserRoles.USER, UserRoles.GUEST}

_AUTO_ARCHIVE_AFTER_DAYS = 7
_AUTO_ARCHIVE_CHECK_INTERVAL = 60 * 60


def _ptwVisibleToDepartment(ptw: PTW, department: str) -> bool:
    """department=None means unrestricted (approver-type roles). Otherwise a PTW is
    visible if it belongs to that department, or if that department currently has
    a pending required-approver slot on it (see KNOWN_ISSUES.md § M12)."""
    if department is None:
        return True
    dep = department.casefold()
    if (ptw.department or '').casefold() == dep:
        return True
    return any((a.department or '').casefold() == dep for a in ptw.pendingApprovers() if a.department)


@ptwsBp.route("/ptws", methods=["GET"])
def getAllPTWs():
    """Return all PTWs visible to the caller, optionally filtered by requestor.

    GET, any authenticated user. USER/GUEST are restricted to their own
    department; other roles may filter by an explicit ``department`` in
    the JSON body (or see all when omitted). Optionally filters by
    ``requestor``. Responds with ``{"success": True, "ptws": [...]}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ptws unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        dep = user.getDepartment() if user.getRole() in _RESTRICTED_PTW_ROLES else data.get('department')
        req = data.get('requestor')
        with globalData.lock:
            snapshot = list(globalData.allPTWs.values())
        ptws = [
            ptw for ptw in snapshot
            if _ptwVisibleToDepartment(ptw, dep) and (req is None or (ptw.requestor or '').casefold() == req.casefold())
        ]
        log.debug("GET /ptws: %d PTWs returned to user='%s'", len(ptws), user.getUsername())
        return jsonify({"success": True, "ptws": [objToDict(ptw) for ptw in ptws]})
    except Exception as e:
        log.error("GET /ptws failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/<int:ptwId>", methods=["GET"])
def getPTWByIdRoute(ptwId):
    """Single-record lookup for SSE-driven targeted refreshes — same visibility rule as GET /ptws.

    GET, any authenticated user; USER/GUEST are department-restricted.
    Responds with ``{"success": True, "ptw": ...}``, or 404 if the PTW
    doesn't exist or isn't visible to the caller's department.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ptws/%s unauthorized (ip=%s)", ptwId, request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    dep = user.getDepartment() if user.getRole() in _RESTRICTED_PTW_ROLES else None
    with globalData.lock:
        ptw = globalData.allPTWs.get(ptwId)
    if ptw is None or not _ptwVisibleToDepartment(ptw, dep):
        log.debug("GET /ptws/%s: not found or not visible to user='%s'", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "PTW not found"}), 404
    return jsonify({"success": True, "ptw": objToDict(ptw)})


@ptwsBp.route("/ptws/archive", methods=["GET"])
def getArchivedPTWs():
    """Return archived PTWs, optionally filtered by department.

    GET, any authenticated user. USER/GUEST are restricted to their own
    department; other roles may pass an explicit ``department`` in the
    JSON body. Responds with ``{"success": True, "ptws": [...]}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ptws/archive unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        dep = user.getDepartment() if user.getRole() in _RESTRICTED_PTW_ROLES else data.get('department')
        ptws = ptwDB.getArchivedPTWs(department=dep)
        log.debug("GET /ptws/archive: %d PTWs returned to user='%s'", len(ptws), user.getUsername())
        return jsonify({"success": True, "ptws": [objToDict(ptw) for ptw in ptws]})
    except Exception as e:
        log.error("GET /ptws/archive failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws", methods=["POST"])
def addPTWRequest():
    """Create a new PTW.

    POST, any authenticated user. Body is the full PTW dict; rejected with
    400 if ``PTW.validate()`` fails. On success persists the PTW, updates
    the in-memory cache, broadcasts a ``PTW created`` SSE event to USER and
    COORDINATOR roles, and responds with ``{"success": True, "ptw-id": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    ptwDict = request.get_json(silent=True) or {}
    try:
        ptw = PTW(ptwDict)
        err = ptw.validate()
        if err:
            log.warning("POST /ptws rejected: %s (by='%s')", err, user.getUsername())
            return jsonify({"success": False, "error": err}), 400
        ptw_id = ptwDB.addPTWFromDict(objToDict(ptw))
        new_ptw = ptwDB.getPTWById(ptw_id)
        if new_ptw:
            with globalData.lock:
                globalData.allPTWs[new_ptw.id] = new_ptw
        sse.broadcast(SSEObject.PTW, ptw_id, SSEAction.CREATED, user.getUsername(), roles=[UserRoles.USER, UserRoles.COORDINATOR])
        log.info("PTW created: id=%s type='%s' by='%s'", ptw_id, ptwDict.get("type"), user.getUsername())
        return jsonify({"success": True, "ptw-id": ptw_id})
    except Exception as e:
        log.error("POST /ptws failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws", methods=["PUT"])
def updatePTWRequest():
    """Edit and resubmit a RETURNED PTW.

    PUT, any authenticated user. Only allowed on a PTW belonging to the
    caller's own department whose ``approval_status`` is ``RETURNED`` (403
    otherwise); body is the updated PTW dict, validated via
    ``PTW.validate()``. Broadcasts a ``PTW updated`` SSE event to USER and
    COORDINATOR roles and responds with ``{"success": True, "ptw-id": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("PUT /ptws unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    ptwDict = request.get_json(silent=True) or {}
    ptwId = ptwDict.get('id')
    try:
        ptwId = int(ptwId)
    except (TypeError, ValueError):
        log.warning("PUT /ptws: invalid PTW id=%r (user='%s')", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid PTW id"}), 400
    existing = globalData.allPTWs.get(ptwId)
    if existing is None:
        log.warning("PUT /ptws: PTW #%s not found (user='%s')", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "PTW not found"}), 404
    if existing.department != user.getDepartment() or existing.approval_status != PTW.ApprovalStatus.RETURNED:
        log.warning("PUT /ptws: forbidden — PTW #%s status='%s' department='%s' user='%s' (dept='%s')", ptwId, existing.approval_status, existing.department, user.getUsername(), user.getDepartment())
        return jsonify({"success": False, "error": "Can only edit RETURNED PTWs from your own department"}), 403
    try:
        ptw = PTW(ptwDict)
        err = ptw.validate()
        if err:
            log.warning("PUT /ptws rejected: %s (by='%s')", err, user.getUsername())
            return jsonify({"success": False, "error": err}), 400
        dbErr = ptwDB.updatePTWFromDict(objToDict(ptw))
        if dbErr:
            raise dbErr
        syncPtwCache(ptwId)
        sse.broadcast(SSEObject.PTW, ptwId, SSEAction.UPDATED, user.getUsername(), roles=[UserRoles.USER, UserRoles.COORDINATOR])
        log.info("PTW updated: id=%s by='%s'", ptwId, user.getUsername())
        return jsonify({"success": True, "ptw-id": ptwId})
    except Exception as e:
        log.error("PUT /ptws failed for id=%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws", methods=["DELETE"])
def deletePTWRequest():
    """Delete a PTW.

    DELETE, any non-guest authenticated user (guest forbidden). Body
    carries ``ptw-id``; if that PTW is currently cached its
    ``approval_status`` must be ``RETURNED`` (403 otherwise), then it's
    removed from the database and the in-memory cache and a ``PTW deleted``
    SSE event is broadcast. Responds with ``{"success": True, "ptw": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("DELETE /ptws unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("DELETE /ptws: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        ptw_id = payload.get('ptw-id')
        ptw = globalData.allPTWs.get(ptw_id)
        if ptw is not None and ptw.approval_status != PTW.ApprovalStatus.RETURNED:
            log.warning("DELETE /ptws: forbidden — PTW #%s status='%s' user='%s'", ptw_id, ptw.approval_status, user.getUsername())
            return jsonify({"success": False, "error": "Can only delete REJECTED or ARCHIVED PTWs"}), 403
        result = ptwDB.deletePTW(ptw_id)
        with globalData.lock:
            globalData.allPTWs.pop(ptw_id, None)
        sse.broadcast(SSEObject.PTW, ptw_id, SSEAction.DELETED, user.getUsername())
        log.info("PTW deleted: id=%s by='%s'", ptw_id, user.getUsername())
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        log.error("DELETE /ptws failed for id=%s: %s", payload.get('ptw-id'), e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/approvals", methods=["POST"])
def updatePTWApprovals():
    """Submit an approval or return action on a PTW's approval chain.

    POST, any non-guest authenticated user. Body carries ``ptw-id`` and an
    ``approval`` dict (built into ``PTW.Approval``); the caller must
    currently be an eligible approver at the PTW's stage
    (``getApprovalStatus`` == ``UNDER_REVIEW`` for their role/department),
    else 403. Broadcasts a ``PTW approved``/``PTW returned`` SSE event and
    responds with ``{"success": True, "ptw": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/approvals unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ptws/approvals: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    approvalData = payload.get('approval')
    if ptwId is None or not approvalData:
        log.warning("POST /ptws/approvals: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    ptw = globalData.allPTWs.get(ptwId)
    if ptw is None:
        log.warning("POST /ptws/approvals: PTW #%s not found (user='%s')", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "PTW not found"}), 404
    if ptw.getApprovalStatus(role=user.getRole(), department=user.getDepartment()) != PTW.ApprovalStatus.UNDER_REVIEW:
        log.warning("POST /ptws/approvals: forbidden — user '%s' (role=%s, dept=%s) not an eligible approver for PTW #%s at its current stage", user.getUsername(), user.getRole(), user.getDepartment(), ptwId)
        return jsonify({"success": False, "error": "You are not an eligible approver for this PTW at its current stage"}), 403
    approval = PTW.Approval(**approvalData)
    # Snapshot the verified actor's role/department into the record (never the
    # payload's), so replaying the approval chain stays valid even if this
    # user is later deleted or re-roled.
    approval.role = user.getRole()
    approval.department = user.getDepartment()
    try:
        result = ptwDB.updatePTWApprovals(ptwId, approval)
        syncPtwCache(ptwId)
        sseAction = SSEAction.APPROVED if approval.action == PTW.ApprovalActions.APPROVED else SSEAction.RETURNED
        sse.broadcast(SSEObject.PTW, ptwId, sseAction, user.getUsername())
        log.info("PTW approval updated: id=%s action='%s' by='%s'", ptwId, approval.action, user.getUsername())
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        log.error("POST /ptws/approvals failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/archive", methods=["POST"])
def archivePTWs():
    """Archive one or more CLOSED PTWs.

    POST, any non-guest authenticated user. Body carries ``ptw-ids``; each
    must resolve to a currently-cached PTW whose ``running_status`` is
    ``CLOSED`` (404/403 otherwise). Archived PTWs are dropped from the
    in-memory cache and a ``PTW archived`` SSE event is broadcast per id.
    Responds with ``{"success": True, "ptw": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/archive unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ptws/archive: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwIds = payload.get('ptw-ids')
    if ptwIds is None:
        log.warning("POST /ptws/archive: missing ptw-ids (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required field: ptw-ids"}), 400
    for pid in ptwIds:
        ptw = globalData.allPTWs.get(pid)
        if ptw is None:
            log.warning("POST /ptws/archive: PTW #%s not found (user='%s')", pid, user.getUsername())
            return jsonify({"success": False, "error": f"PTW# {pid} not found"}), 404
        if ptw.running_status not in [PTW.RunningStatus.CLOSED]:
            log.warning("POST /ptws/archive: forbidden — PTW #%s approval='%s' running='%s' user='%s'", pid, ptw.approval_status, ptw.running_status, user.getUsername())
            return jsonify({"success": False, "error": f"PTW# {pid} cannot be archived (must be CLOSED)"}), 403
    try:
        result = ptwDB.archivePTWs(ptwIds)
        with globalData.lock:
            for pid in ptwIds:
                globalData.allPTWs.pop(pid, None)
        for pid in ptwIds:
            sse.broadcast(SSEObject.PTW, pid, SSEAction.ARCHIVED, user.getUsername())
        log.info("PTWs archived: ids=%s by='%s'", ptwIds, user.getUsername())
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        log.error("POST /ptws/archive failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/run-request", methods=["POST"])
def requestToRunPTW():
    """Record the Performing Authority's request to start work on a PTW.

    POST, any non-guest authenticated user. Body carries ``ptw-id``, ``pa``,
    and ``timestamp``. 403s if the PTW's 14-shift validity has expired or
    any linked IC isn't ``Active``. Broadcasts a ``PTW run requested`` SSE
    event to USER and ISSUING roles and responds with
    ``{"success": True, "message": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/run-request unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ptws/run-request: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    pa = payload.get('pa')
    ts = payload.get('timestamp')
    if ptwId is None or pa is None or ts is None:
        log.warning("POST /ptws/run-request: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    ptw = globalData.allPTWs.get(ptwId)
    if ptw is None:
        log.warning("POST /ptws/run-request: PTW #%s not found in active PTWs", ptwId)
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400

    if ptw.isValidityExpired():
        log.warning("POST /ptws/run-request: forbidden — PTW #%s exceeded its 14-shift validity period", ptwId)
        return jsonify({"success": False, "error": f"Cannot request run: PTW #{ptwId} exceeded its 14-shift validity period"}), 403

    with globalData.lock:
        unisolatedICs = [
            icId for icId in ptw.linked_ics
            if not (ic := globalData.ics.get(int(icId))) or ic.getStatus() != IC.Status.ACTIVE
        ]
    if unisolatedICs:
        log.warning("POST /ptws/run-request: forbidden — PTW #%s has non-isolated linked IC(s) %s", ptwId, unisolatedICs)
        return jsonify({"success": False, "error": f"Cannot request run: IC(s) #{', '.join(unisolatedICs)} are not isolated"}), 403

    try:
        result = ptwDB.requestToRunPTW(ptwId, pa, ts)
        syncPtwCache(ptwId)
        sse.broadcast(SSEObject.PTW, ptwId, SSEAction.RUN_REQUESTED, pa, roles=[UserRoles.USER, UserRoles.ISSUING])
        log.info("PTW run requested: id=%s by PA='%s'", ptwId, pa)
        return jsonify({"success": True, "message": result})
    except Exception as e:
        log.error("POST /ptws/run-request failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/run", methods=["POST"])
def runPTW():
    """Record the Issuing Authority's accept/reject response to a run request.

    POST, ``ISSUING`` role only. Body carries ``ptw-id``, ``ia``,
    ``timestamp``, ``response`` (accept/reject) and an optional
    ``comment``. Accepting 403s if the PTW's 14-shift validity has expired
    or any linked IC isn't ``Active``; otherwise records the accept/reject
    via ``ptwDB.runAcceptPTW``/``runRejectPTW``, broadcasts the matching
    ``PTW run accepted``/``PTW run rejected`` SSE event, and responds with
    ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/run unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISSUING:
        log.warning("POST /ptws/run: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    ia = payload.get('ia')
    ts = payload.get('timestamp')
    ok = payload.get('response')
    comment = payload.get('comment')
    if ptwId is None or ia is None or ts is None or ok is None:
        log.warning("POST /ptws/run: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    ptw = globalData.allPTWs.get(ptwId)
    if ptw is None:
        log.warning("POST /ptws/run: PTW #%s not found in active PTWs", ptwId)
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400

    try:
        if ok:
            if ptw.isValidityExpired():
                log.warning("POST /ptws/run: forbidden — PTW #%s exceeded its 14-shift validity period", ptwId)
                return jsonify({"success": False, "error": f"Cannot run: PTW #{ptwId} exceeded its 14-shift validity period"}), 403
            with globalData.lock:
                unisolatedICs = [
                    icId for icId in ptw.linked_ics
                    if not (ic := globalData.ics.get(int(icId))) or ic.getStatus() != IC.Status.ACTIVE
                ]
            if unisolatedICs:
                log.warning("POST /ptws/run: forbidden — PTW #%s has non-isolated linked IC(s) %s", ptwId, unisolatedICs)
                return jsonify({"success": False, "error": f"Cannot run: IC(s) #{', '.join(unisolatedICs)} are not isolated"}), 403
            ptwDB.runAcceptPTW(ptwId, ia, ts, comment)
            syncPtwCache(ptwId)
            sse.broadcast(SSEObject.PTW, ptwId, SSEAction.RUN_ACCEPTED, ia)
            log.info("PTW run accepted: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
        else:
            ptwDB.runRejectPTW(ptwId, ia, ts, comment)
            syncPtwCache(ptwId)
            sse.broadcast(SSEObject.PTW, ptwId, SSEAction.RUN_REJECTED, ia)
            log.info("PTW run rejected: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/run failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/hold-request", methods=["POST"])
def requestToHldPTW():
    """Record the Performing Authority's request to hold work on a PTW.

    POST, any non-guest authenticated user. Body carries ``ptw-id``, ``pa``,
    ``timestamp``, an optional ``comment``, and ``held-ics`` (isolation
    tags to keep linked through the hold). Broadcasts a ``PTW hold
    requested`` SSE event to USER and ISSUING roles and responds with
    ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/hold-request unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ptws/hold-request: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    pa = payload.get('pa')
    ts = payload.get('timestamp')
    comment = payload.get('comment')
    heldICs = payload.get('held-ics', [])
    if ptwId is None or pa is None or ts is None:
        log.warning("POST /ptws/hold-request: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        ptwDB.requestToHldPTW(ptwId, pa, ts, comment, heldICs)
        syncPtwCache(ptwId)
        sse.broadcast(SSEObject.PTW, ptwId, SSEAction.HOLD_REQUESTED, pa, roles=[UserRoles.USER, UserRoles.ISSUING])
        log.info("PTW hold requested: id=%s by PA='%s' held_ics=%s", ptwId, pa, heldICs)
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/hold-request failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/hold", methods=["POST"])
def hldPTW():
    """Record the Issuing Authority's accept/reject response to a hold request.

    POST, ``ISSUING`` role only. Body carries ``ptw-id``, ``ia``,
    ``timestamp``, ``response`` and an optional ``comment``. Accepting also
    runs ``checkAndAutoDeisolateICs`` over the PTW's linked ICs. Broadcasts
    the matching ``PTW held``/``PTW hold rejected`` SSE event and responds
    with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/hold unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISSUING:
        log.warning("POST /ptws/hold: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    ia = payload.get('ia')
    ts = payload.get('timestamp')
    ok = payload.get('response')
    comment = payload.get('comment')
    if ptwId is None or ia is None or ts is None or ok is None:
        log.warning("POST /ptws/hold: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    ptw = globalData.allPTWs.get(ptwId)
    if ptw is None:
        log.warning("POST /ptws/hold: PTW #%s not found in active PTWs", ptwId)
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400

    try:
        if ok:
            ptwDB.hldAcceptPTW(ptwId, ia, ts, comment)
            syncPtwCache(ptwId)
            checkAndAutoDeisolateICs(ptw.linked_ics)
            sse.broadcast(SSEObject.PTW, ptwId, SSEAction.HELD, ia)
            log.info("PTW hold accepted: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
        else:
            ptwDB.hldRejectPTW(ptwId, ia, ts, comment)
            syncPtwCache(ptwId)
            sse.broadcast(SSEObject.PTW, ptwId, SSEAction.HOLD_REJECTED, ia)
            log.info("PTW hold rejected: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/hold failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/close-request", methods=["POST"])
def requestToClsPTW():
    """Record the Performing Authority's request to close a PTW.

    POST, any non-guest authenticated user. Body carries ``ptw-id``, ``pa``,
    ``timestamp`` and an optional ``comment``; 403s unless the PTW's
    ``approval_status`` is ``APPROVED`` (covers both a normally-running
    PTW and one that was approved but never run). Broadcasts a ``PTW close
    requested`` SSE event to USER and ISSUING roles and responds with
    ``{"success": True, "message": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/close-request unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ptws/close-request: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    pa = payload.get('pa')
    ts = payload.get('timestamp')
    comment = payload.get('comment')
    if ptwId is None or pa is None or ts is None:
        log.warning("POST /ptws/close-request: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    ptw = globalData.allPTWs.get(ptwId)
    if ptw is None:
        log.warning("POST /ptws/close-request: PTW #%s not found in active PTWs", ptwId)
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400
    if ptw.approval_status != PTW.ApprovalStatus.APPROVED:
        # Defensive: PtwsDb.requestToClsPTW now appends a stop-only cycle when there's no open
        # cycle to patch (see there) — that path must stay reachable only for an approved PTW
        # that simply never ran, never for one still under review/returned (those have their
        # own delete/edit-resubmit flows, not "close").
        log.warning("POST /ptws/close-request: forbidden — PTW #%s approval_status='%s'", ptwId, ptw.approval_status)
        return jsonify({"success": False, "error": f"Cannot close: PTW #{ptwId} is not approved"}), 403

    try:
        result = ptwDB.requestToClsPTW(ptwId, pa, ts, comment)
        syncPtwCache(ptwId)
        sse.broadcast(SSEObject.PTW, ptwId, SSEAction.CLOSE_REQUESTED, pa, roles=[UserRoles.USER, UserRoles.ISSUING])
        log.info("PTW close requested: id=%s by PA='%s'", ptwId, pa)
        return jsonify({"success": True, "message": result})
    except Exception as e:
        log.error("POST /ptws/close-request failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/close", methods=["POST"])
def clsPTW():
    """Record the Issuing Authority's accept/reject response to a close request.

    POST, ``ISSUING`` role only. Body carries ``ptw-id``, ``ia``,
    ``timestamp``, ``response`` and an optional ``comment``. Accepting also
    runs ``checkAndAutoDeisolateICs`` over the PTW's linked ICs. Broadcasts
    the matching ``PTW closed``/``PTW close rejected`` SSE event and
    responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/close unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISSUING:
        log.warning("POST /ptws/close: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    ia = payload.get('ia')
    ts = payload.get('timestamp')
    ok = payload.get('response')
    comment = payload.get('comment')
    if ptwId is None or ia is None or ts is None or ok is None:
        log.warning("POST /ptws/close: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    ptw = globalData.allPTWs.get(ptwId)
    if ptw is None:
        log.warning("POST /ptws/close: PTW #%s not found in active PTWs", ptwId)
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400

    try:
        if ok:
            ptwDB.clsAcceptPTW(ptwId, ia, ts, comment)
            syncPtwCache(ptwId)
            checkAndAutoDeisolateICs(ptw.linked_ics)
            sse.broadcast(SSEObject.PTW, ptwId, SSEAction.CLOSED, ia)
            log.info("PTW closed (accepted): id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
        else:
            ptwDB.clsRejectPTW(ptwId, ia, ts, comment)
            syncPtwCache(ptwId)
            sse.broadcast(SSEObject.PTW, ptwId, SSEAction.CLOSE_REJECTED, ia)
            log.info("PTW close rejected: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/close failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/attachments", methods=["POST"])
def addPtwAttachments():
    """Upload one or more attachment files to a PTW.

    POST, any authenticated user. Takes files from ``request.files`` and
    ``ptw-id`` from the form fields; rejects a missing/invalid id, path-
    traversal attempts, and filenames that already exist on disk (per-file
    errors are collected and, if any occurred, none of the batch is
    saved). Responds with ``{"success": True, "message": ...}`` or the
    collected errors joined into ``error``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/attachments unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    attachments = request.files or {}
    payload = request.values.to_dict() or {}
    ptwId = payload.get('ptw-id')
    if ptwId is None:
        log.warning("POST /ptws/attachments: missing ptw-id (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing PTW id field"}), 400
    try:
        ptwId = int(ptwId)
    except (ValueError, TypeError):
        log.warning("POST /ptws/attachments: invalid ptw-id='%s' (user='%s')", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid PTW id"}), 400

    attachDir = paths.attachmentsDir('ptw', ptwId)
    os.makedirs(attachDir, exist_ok=True)

    errors = []
    validated = []
    for file in attachments.values():
        filename = file.filename if file else None
        if not filename:
            errors.append("No file selected for uploading")
            continue
        filepath = os.path.join(attachDir, filename)
        if not os.path.abspath(filepath).startswith(os.path.abspath(attachDir)):
            log.warning("POST /ptws/attachments: path traversal attempt: ptw-id='%s' file='%s' user='%s'", ptwId, filename, user.getUsername())
            errors.append(f"Invalid filename: {filename}")
            continue
        if os.path.exists(filepath):
            errors.append(f"File already exists: {filename}")
            continue
        validated.append((file, filename, filepath))

    if not errors:
        for file, filename, filepath in validated:
            try:
                file.save(filepath)
                log.debug("Attachment saved: PTW #%s file='%s'", ptwId, filename)
            except Exception as e:
                errors.append(f"Failed to upload {filename}: {str(e)}")
                log.error("Attachment upload failed: PTW #%s file='%s': %s", ptwId, filename, e)

    if errors:
        log.warning("Attachment upload didn't complete due to errors: PTW #%s errors=%s", ptwId, errors)
        return jsonify({"success": False, "error": "\n".join(errors)}), 400
    else:
        log.info("Attachments uploaded: PTW #%s files=%s by='%s'", ptwId, [f[1] for f in validated], user.getUsername())
        return jsonify({"success": True, "message": "Files uploaded successfully"})


@ptwsBp.route("/ptws/attachments", methods=["GET"])
def getPtwAttachment():
    """List a PTW's attachments, or download one by name.

    GET, any authenticated user. Body carries ``ptw-id`` and an optional
    ``filename``. With ``filename`` set, streams that file (404 if
    missing, 400 on a path-traversal attempt); otherwise responds with
    ``{"success": True, "attachments": [...]}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ptws/attachments unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    filename = payload.get('filename')
    if ptwId is None:
        log.warning("GET /ptws/attachments: missing ptw-id (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        ptwId = int(ptwId)
    except (ValueError, TypeError):
        log.warning("GET /ptws/attachments: invalid ptw-id='%s' (user='%s')", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid PTW id"}), 400
    try:
        attachDir = paths.attachmentsDir('ptw', ptwId)
        if filename:
            filepath = os.path.join(attachDir, filename)
            if not os.path.isfile(filepath):
                log.warning("Attachment not found: PTW #%s file='%s'", ptwId, filename)
                return jsonify({"success": False, "error": "File not found"}), 404
            if not os.path.abspath(filepath).startswith(os.path.abspath(attachDir)):
                log.warning("GET /ptws/attachments: path traversal attempt: ptw-id='%s' file='%s' user='%s'", ptwId, filename, user.getUsername())
                return jsonify({"success": False, "error": "Invalid filename"}), 400
            log.debug("Attachment served: PTW #%s file='%s' to user='%s'", ptwId, filename, user.getUsername())
            return send_file(filepath, as_attachment=True)
        else:
            filenames = []
            if not os.path.exists(attachDir):
                return jsonify({"success": True, "message": "PTW attachments dir not found", "attachments": []})
            for fname in os.listdir(attachDir):
                fpath = os.path.join(attachDir, fname)
                if os.path.isfile(fpath):
                    filenames.append(fname)
            log.debug("Attachment list: PTW #%s count=%d user='%s'", ptwId, len(filenames), user.getUsername())
            return jsonify({"success": True, "attachments": filenames})
    except Exception as e:
        log.error("GET /ptws/attachments failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/attachments", methods=["DELETE"])
def deletePtwAttachments():
    """Delete a PTW's attachments except those listed to keep.

    DELETE, any authenticated user. Body carries ``ptw-id`` and
    ``keep-filenames``; every file in that PTW's attachment directory not
    in the keep list is removed. Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("DELETE /ptws/attachments unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    keepFilenames = payload.get('keep-filenames')
    if ptwId is None or keepFilenames is None:
        log.warning("DELETE /ptws/attachments: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        ptwId = int(ptwId)
    except (ValueError, TypeError):
        log.warning("DELETE /ptws/attachments: invalid ptw-id='%s' (user='%s')", ptwId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid PTW id"}), 400
    keepFilenames = set(keepFilenames)
    try:
        dirpath = paths.attachmentsDir('ptw', ptwId)
        deleted = []
        if os.path.exists(dirpath):
            for fname in os.listdir(dirpath):
                fpath = os.path.join(dirpath, fname)
                if os.path.isfile(fpath) and fname not in keepFilenames:
                    os.remove(fpath)
                    deleted.append(fname)
        log.info("Attachments deleted: PTW #%s deleted=%s by='%s'", ptwId, deleted, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("DELETE /ptws/attachments failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@ptwsBp.route("/ptws/attachments/copy", methods=["POST"])
def copyPtwAttachments():
    """Copy one PTW's attachments (and risk assessment) onto another.

    POST, any non-guest authenticated user. Body carries
    ``source-ptw-id`` and ``target-ptw-id``; copies every file from the
    source's attachment directory into the target's (creating it if
    needed) and additively copies the source's PTW-specific risk
    assessment onto the target via
    ``risksDB.copyRiskAssessmentForPTW``. Responds with
    ``{"success": True, "message": ..., "risk-copy-error": ...}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws/attachments/copy unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ptws/attachments/copy: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    sourcePtwId = payload.get('source-ptw-id')
    targetPtwId = payload.get('target-ptw-id')
    if sourcePtwId is None or targetPtwId is None:
        log.warning("POST /ptws/attachments/copy: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        sourcePtwId = int(sourcePtwId)
        targetPtwId = int(targetPtwId)
    except (ValueError, TypeError):
        log.warning("POST /ptws/attachments/copy: invalid ptw-id(s) source='%s' target='%s' (user='%s')", sourcePtwId, targetPtwId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid PTW id"}), 400
    try:
        sourceDir = paths.attachmentsDir('ptw', sourcePtwId)
        targetDir = paths.attachmentsDir('ptw', targetPtwId)
        successfullyCopied = []
        if os.path.exists(sourceDir):
            os.makedirs(targetDir, exist_ok=True)
            for filename in os.listdir(sourceDir):
                sourceFilePath = os.path.join(sourceDir, filename)
                if os.path.isfile(sourceFilePath):
                    shutil.copy2(sourceFilePath, os.path.join(targetDir, filename))
                    successfullyCopied.append(filename)
            log.info("Attachments copied: PTW #%s -> PTW #%s files=%s by='%s'", sourcePtwId, targetPtwId, successfullyCopied, user.getUsername())
        else:
            log.info("Attachments copy skipped: source PTW #%s has no attachments dir", sourcePtwId)

        riskErr = risksDB.copyRiskAssessmentForPTW(sourcePtwId, targetPtwId)
        if riskErr:
            log.error("Risk assessment copy failed: PTW #%s -> PTW #%s: %s", sourcePtwId, targetPtwId, riskErr)
        else:
            log.info("Risk assessment copied: PTW #%s -> PTW #%s by='%s'", sourcePtwId, targetPtwId, user.getUsername())

        return jsonify({"success": True, "message": "Attachments copied successfully", "risk-copy-error": riskErr})
    except Exception as e:
        log.error("POST /ptws/attachments/copy failed %s->%s: %s", sourcePtwId, targetPtwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


def _auto_archive_closed_ptws():
    """Background sweep that auto-archives long-CLOSED PTWs.

    Runs forever on a daemon thread, sleeping
    ``_AUTO_ARCHIVE_CHECK_INTERVAL`` seconds between passes. Each pass
    archives every ``CLOSED`` PTW whose last run cycle's
    ``stop_ia_timestamp`` is at least ``_AUTO_ARCHIVE_AFTER_DAYS`` days
    old, evicts it from the in-memory cache, and broadcasts a ``PTW
    archived`` SSE event with ``by="system"``.
    """
    while True:
        sleep(_AUTO_ARCHIVE_CHECK_INTERVAL)
        try:
            cutoff = datetime.now() - timedelta(days=_AUTO_ARCHIVE_AFTER_DAYS)
            with globalData.lock:
                closed = [ptw for ptw in globalData.allPTWs.values() if ptw.running_status == PTW.RunningStatus.CLOSED]
            staleIds = []
            for ptw in closed:
                lastCycle = ptw.lastRunCycle()
                closeTimestamp = lastCycle.stop_ia_timestamp if lastCycle else None
                if not closeTimestamp:
                    continue
                try:
                    closedAt = datetime.strptime(closeTimestamp, "%d/%m/%Y %H:%M:%S")
                except ValueError:
                    log.warning("Auto-archive: PTW #%s has unparseable close timestamp='%s'", ptw.id, closeTimestamp)
                    continue
                if closedAt <= cutoff:
                    staleIds.append(ptw.id)
            if staleIds:
                ptwDB.archivePTWs(staleIds)
                with globalData.lock:
                    for pid in staleIds:
                        globalData.allPTWs.pop(pid, None)
                for pid in staleIds:
                    sse.broadcast(SSEObject.PTW, pid, SSEAction.ARCHIVED, "system")
                log.info("Auto-archived %d closed PTW(s) older than %d days: ids=%s", len(staleIds), _AUTO_ARCHIVE_AFTER_DAYS, staleIds)
        except Exception as e:
            log.error("Auto-archive sweep failed: %s", e, exc_info=True)


threading.Thread(target=_auto_archive_closed_ptws, daemon=True, name="ptw-auto-archive").start()
log.info("PTW auto-archive thread started (threshold: %d days, check interval: %ds)", _AUTO_ARCHIVE_AFTER_DAYS, _AUTO_ARCHIVE_CHECK_INTERVAL)
