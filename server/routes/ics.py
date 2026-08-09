"""Flask blueprint implementing the Isolation Certificate (IC) lifecycle.

Covers IC creation and its staged approval chain, the isolate cycle
(request -> IA confirm -> isolator execute), the de-isolate cycle (request
-> IA confirm -> isolator execute), PTW<->IC link/unlink, and IC (P&ID /
wiring) attachments.
"""

import os
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file

import sse
import paths
from core import log, icDB, ptwDB, syncPtwCache
from GlobalData import globalData
from models.User import UserRoles
from models.PTW import PTW
from models.Isolation import IC
from models.SSE import SSEObject, SSEAction
from routes.auth import getVerifiedUser
from utils import objToDict

icsBp = Blueprint("ics", __name__)


def setDeisolateRequested(icId, by: str):
    """Shared by the manual /ics/deisolate-request route and the automatic check below —
    moves an IC into DEISOLATE_CONFIRMING, resetting any stale IA decision from a previous,
    since-returned attempt."""
    icDB.updateICFromDict({
        'id': icId,
        'deisolate_requestor': by,
        'deisolate_requestor_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        'deisolate_issuing': None,
        'deisolate_issuing_timestamp': None,
        'deisolate_issuing_action': '',
    })
    updated = icDB.getICById(icId)
    if updated:
        with globalData.lock:
            globalData.ics[updated.id] = updated
    sse.broadcast(SSEObject.IC, icId, SSEAction.DEISOLATE_REQUESTED, by)


def checkAndAutoDeisolateICs(icIds: list, by: str = "system"):
    """Called after a PTW stops actively needing IC(s) it's linked to — on close-accept,
    hold-accept, and manual unlink. The link itself is never removed, so for each IC we check
    whether every PTW still linked to it no longer needs it either (closed, or held without
    listing it in that PTW's held_ics) and if so, auto-request its de-isolation."""
    for icIdStr in icIds:
        if not icIdStr:
            continue
        try:
            icId = int(icIdStr)
        except (TypeError, ValueError):
            continue
        with globalData.lock:
            ic = globalData.ics.get(icId)
        if ic is None or ic.getStatus() != IC.Status.ACTIVE or not ic.linked_ptws:
            continue
        allClear = True
        for linkedPtwIdStr in ic.linked_ptws:
            try:
                linkedPtw = globalData.allPTWs.get(int(linkedPtwIdStr))
            except (TypeError, ValueError):
                linkedPtw = None
            if linkedPtw is None:
                try:
                    linkedPtw = ptwDB.getPTWById(linkedPtwIdStr)
                except Exception:
                    linkedPtw = None
            if linkedPtw is None:
                allClear = False
                break
            if linkedPtw.running_status == PTW.RunningStatus.CLOSED:
                continue
            if linkedPtw.running_status == PTW.RunningStatus.HELD and str(icId) not in linkedPtw.getHeldICs():
                continue
            allClear = False
            break
        if allClear:
            setDeisolateRequested(icId, by)
            log.info("IC auto de-isolate requested: id=%s (all linked PTWs closed or held without requiring it)", icId)


@icsBp.route("/ics/attachments", methods=["POST"])
def addIcAttachments():
    """Upload one or more P&ID/wiring attachment files to an IC.

    POST /ics/attachments (multipart form). Requires any authenticated
    user; no role restriction. Form fields: ``ic-id`` plus the uploaded
    files. Rejects path traversal, missing filenames, and filenames that
    already exist in the IC's attachment directory; saves the rest to
    disk. Responds with ``{"success": True}`` or a 400 listing any errors.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/attachments unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    attachments = request.files or {}
    payload = request.values.to_dict() or {}
    icId = payload.get('ic-id')
    if icId is None:
        log.warning("POST /ics/attachments: missing ic-id (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing IC id field"}), 400
    try:
        icId = int(icId)
    except (ValueError, TypeError):
        log.warning("POST /ics/attachments: invalid ic-id='%s' (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid IC id"}), 400

    attachDir = paths.attachmentsDir('ic', icId)
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
            log.warning("POST /ics/attachments: path traversal attempt: ic-id='%s' file='%s' user='%s'", icId, filename, user.getUsername())
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
                log.debug("Attachment saved: IC #%s file='%s'", icId, filename)
            except Exception as e:
                errors.append(f"Failed to upload {filename}: {str(e)}")
                log.error("Attachment upload failed: IC #%s file='%s': %s", icId, filename, e)

    if errors:
        log.warning("Attachment upload didn't complete due to errors: IC #%s errors=%s", icId, errors)
        return jsonify({"success": False, "error": "\n".join(errors)}), 400
    else:
        log.info("Attachments uploaded: IC #%s files=%s by='%s'", icId, [f[1] for f in validated], user.getUsername())
        return jsonify({"success": True, "message": "Files uploaded successfully"})


@icsBp.route("/ics/attachments", methods=["GET"])
def getIcAttachment():
    """List an IC's attachments, or download a single one.

    GET /ics/attachments. Requires any authenticated user; no role
    restriction. Body: ``{"ic-id": <int>, "filename": <optional str>}``.
    With ``filename``, streams that file (404 if missing, 400 on a
    path-traversal attempt); without it, responds with ``{"success": True,
    "attachments": [<filenames>]}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ics/attachments unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    filename = payload.get('filename')
    if icId is None:
        log.warning("GET /ics/attachments: missing ic-id (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        icId = int(icId)
    except (ValueError, TypeError):
        log.warning("GET /ics/attachments: invalid ic-id='%s' (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid IC id"}), 400
    try:
        attachDir = paths.attachmentsDir('ic', icId)
        if filename:
            filepath = os.path.join(attachDir, filename)
            if not os.path.isfile(filepath):
                log.warning("Attachment not found: IC #%s file='%s'", icId, filename)
                return jsonify({"success": False, "error": "File not found"}), 404
            if not os.path.abspath(filepath).startswith(os.path.abspath(attachDir)):
                log.warning("GET /ics/attachments: path traversal attempt: ic-id='%s' file='%s' user='%s'", icId, filename, user.getUsername())
                return jsonify({"success": False, "error": "Invalid filename"}), 400
            log.debug("Attachment served: IC #%s file='%s' to user='%s'", icId, filename, user.getUsername())
            return send_file(filepath, as_attachment=True)
        else:
            filenames = []
            if not os.path.exists(attachDir):
                return jsonify({"success": True, "message": "IC attachments dir not found", "attachments": []})
            for fname in os.listdir(attachDir):
                fpath = os.path.join(attachDir, fname)
                if os.path.isfile(fpath):
                    filenames.append(fname)
            log.debug("Attachment list: IC #%s count=%d user='%s'", icId, len(filenames), user.getUsername())
            return jsonify({"success": True, "attachments": filenames})
    except Exception as e:
        log.error("GET /ics/attachments failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/attachments", methods=["DELETE"])
def deleteIcAttachments():
    """Delete an IC's attachments except those explicitly kept.

    DELETE /ics/attachments. Requires any authenticated user; no role
    restriction. Body: ``{"ic-id": <int>, "keep-filenames": [<str>, ...]}``.
    Removes every file in the IC's attachment directory not listed in
    ``keep-filenames``. Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("DELETE /ics/attachments unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    keepFilenames = payload.get('keep-filenames')
    if icId is None or keepFilenames is None:
        log.warning("DELETE /ics/attachments: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        icId = int(icId)
    except (ValueError, TypeError):
        log.warning("DELETE /ics/attachments: invalid ic-id='%s' (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "Invalid IC id"}), 400
    keepFilenames = set(keepFilenames)
    try:
        dirpath = paths.attachmentsDir('ic', icId)
        deleted = []
        if os.path.exists(dirpath):
            for fname in os.listdir(dirpath):
                fpath = os.path.join(dirpath, fname)
                if os.path.isfile(fpath) and fname not in keepFilenames:
                    os.remove(fpath)
                    deleted.append(fname)
        log.info("Attachments deleted: IC #%s deleted=%s by='%s'", icId, deleted, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("DELETE /ics/attachments failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics", methods=["GET"])
def getAllICs():
    """List ICs, department-scoped for the USER role.

    GET /ics. Requires any authenticated user. A ``USER`` role only sees
    ICs whose ``requestor_department`` matches their own department; other
    roles may pass an optional ``"department"`` filter in the JSON body,
    or omit it to see every IC. Responds with ``{"success": True, "ics":
    [...]}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ics unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        dep = user.getDepartment() if user.getRole() == UserRoles.USER else data.get('department')
        with globalData.lock:
            snapshot = list(globalData.ics.values())
        ics = [c for c in snapshot if dep is None or (c.requestor_department or '').casefold() == dep.casefold()]
        log.debug("GET /ics: %d ICs returned to user='%s'", len(ics), user.getUsername())
        return jsonify({"success": True, "ics": objToDict(ics)})
    except Exception as e:
        log.error("GET /ics failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/<int:icId>", methods=["GET"])
def getICByIdRoute(icId):
    """Fetch a single IC by id, for SSE-driven targeted refreshes.

    GET /ics/<icId>. Requires any authenticated user; same
    department-visibility rule as GET /ics (a ``USER`` only sees ICs in
    their own ``requestor_department``). Responds with ``{"success": True,
    "ic": ...}``, or 404 if not found or not visible to the caller.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /ics/%s unauthorized (ip=%s)", icId, request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    dep = user.getDepartment() if user.getRole() == UserRoles.USER else None
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None or (dep is not None and (ic.requestor_department or '').casefold() != dep.casefold()):
        log.debug("GET /ics/%s: not found or not visible to user='%s'", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    return jsonify({"success": True, "ic": objToDict(ic)})


@icsBp.route("/ics", methods=["POST"])
def addICRequest():
    """Create a new IC.

    POST /ics. Requires an authenticated non-guest user. Stamps
    ``requestor``/``requestor_department``/``requestor_timestamp`` from the
    caller (never trusted from the payload). 400 if ``execution_department``
    is missing, or (for a Self-type IC) doesn't match
    ``requestor_department``, or (when ``is_psic``) ``psic_reasons`` is
    empty or any of ``psic_system_description``/``psic_isolation_method``/
    ``psic_control_measures`` is blank. Broadcasts an IC CREATED SSE event
    to the ISSUING role. Responds with ``{"success": True, "ic-id": <id>}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ics: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    icDict = request.get_json(silent=True) or {}
    ic = IC(icDict)
    ic.requestor_department = user.getDepartment()
    if not ic.execution_department:
        log.warning("POST /ics: missing execution_department (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Execution department is required"}), 400
    if ic.type == IC.Types.SELF and ic.execution_department != ic.requestor_department:
        log.warning(
            "POST /ics: forbidden — self-isolation execution_department '%s' must match requestor_department '%s' (user='%s')",
            ic.execution_department, ic.requestor_department, user.getUsername(),
        )
        return jsonify({"success": False, "error": "Self-isolation must be executed by the requestor's own department"}), 400
    if ic.is_psic:
        if not ic.psic_reasons:
            log.warning("POST /ics: PSIC with no reason selected (user='%s')", user.getUsername())
            return jsonify({"success": False, "error": "At least one PSIC reason is required"}), 400
        if not (ic.psic_system_description or '').strip() or not (ic.psic_isolation_method or '').strip() or not (ic.psic_control_measures or '').strip():
            log.warning("POST /ics: PSIC missing system description / isolation method / control measures (user='%s')", user.getUsername())
            return jsonify({"success": False, "error": "PSIC system description, isolation method, and control measures are all required"}), 400
    try:
        ic.requestor = user.getUsername()
        ic.requestor_timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        ic_id = icDB.addICFromDict(objToDict(ic))
        new_ic = icDB.getICById(ic_id)
        if new_ic:
            with globalData.lock:
                globalData.ics[new_ic.id] = new_ic
        sse.broadcast(SSEObject.IC, ic_id, SSEAction.CREATED, user.getUsername(), roles=[UserRoles.ISSUING])
        log.info("IC created: id=%s type='%s' by='%s'", ic_id, ic.type, user.getUsername())
        return jsonify({"success": True, "ic-id": ic_id})
    except Exception as e:
        log.error("POST /ics failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/approvals", methods=["POST"])
def updateICApprovals():
    """Submit an approve/return decision on the IC's staged approval chain.

    POST /ics/approvals. Requires an authenticated non-guest user whose
    ``getApprovalStatus(role, department)`` is currently ``Requested`` for
    this IC (403 otherwise), i.e. it must be their turn. Body:
    ``{"ic-id": <int>, "approval": {...}}``. If this approval completes the
    chain and ``isolate_asap`` is set, also auto-stamps
    ``isolate_requestor``/``isolate_requestor_timestamp``. Broadcasts an IC
    APPROVED/RETURNED SSE event. Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/approvals unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ics/approvals: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    approvalData = payload.get('approval')
    if icId is None or not approvalData:
        log.warning("POST /ics/approvals: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/approvals: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getApprovalStatus(role=user.getRole(), department=user.getDepartment()) != IC.Status.REQUESTED:
        log.warning(
            "POST /ics/approvals: forbidden — user '%s' (role=%s, dept=%s) not an eligible approver for IC #%s at its current stage",
            user.getUsername(), user.getRole(), user.getDepartment(), icId,
        )
        return jsonify({"success": False, "error": "You are not an eligible approver for this IC at its current stage"}), 403
    approval = IC.Approval(**approvalData)
    try:
        icDB.updateICApprovals(icId, approval)
        updated = icDB.getICById(icId)
        if updated and updated.isolate_asap and not updated.isolate_requestor and updated.getApprovalStatus() == IC.Status.APPROVED:
            # Isolate ASAP skips the manual "Request Isolate" step the moment full approval
            # is reached — it still has to go through IA confirmation and isolator execution,
            # it just doesn't wait on a person to click Request Isolate first.
            icDB.updateICFromDict({
                'id': icId,
                'isolate_requestor': updated.requestor,
                'isolate_requestor_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            })
            updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        sseAction = SSEAction.APPROVED if approval.action == IC.ApprovalActions.APPROVED else SSEAction.RETURNED
        sse.broadcast(SSEObject.IC, icId, sseAction, user.getUsername())
        log.info("IC approval updated: id=%s action='%s' by='%s'", icId, approval.action, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/approvals failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/isolate-request", methods=["POST"])
def requestIsolateIC():
    """Request that an approved IC's isolation be carried out.

    POST /ics/isolate-request. Requires an authenticated non-guest user.
    Body: ``{"ic-id": <int>}``. 403 unless the IC's ``getStatus()`` is
    ``Approved``. Stamps ``isolate_requestor``/
    ``isolate_requestor_timestamp`` and clears any stale
    ``isolate_issuing*`` decision left over from a previously returned
    attempt. Broadcasts an IC ISOLATE_REQUESTED SSE event. Responds with
    ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/isolate-request unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ics/isolate-request: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    if icId is None:
        log.warning("POST /ics/isolate-request: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/isolate-request: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getStatus() != IC.Status.APPROVED:
        log.warning(
            "POST /ics/isolate-request: forbidden — IC #%s not awaiting an isolate request (user='%s')",
            icId, user.getUsername(),
        )
        return jsonify({"success": False, "error": "IC is not awaiting an isolate request"}), 403
    try:
        icDB.updateICFromDict({
            'id': icId,
            'isolate_requestor': user.getUsername(),
            'isolate_requestor_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            # Reset any stale decision from a previous, since-returned attempt so a fresh
            # IA review starts clean — otherwise a leftover 'Returned' would mask this new request.
            'isolate_issuing': None,
            'isolate_issuing_timestamp': None,
            'isolate_issuing_action': '',
        })
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        sse.broadcast(SSEObject.IC, icId, SSEAction.ISOLATE_REQUESTED, user.getUsername())
        log.info("IC isolate requested: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/isolate-request failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/isolate-confirm", methods=["POST"])
def confirmIsolateIC():
    """Issuing confirms or returns a pending isolate request.

    POST /ics/isolate-confirm. Requires the ``ISSUING`` role (403
    otherwise). Body: ``{"ic-id": <int>, "response": <bool>}``. 403 unless
    the IC's ``getStatus()`` is ``Isolate Confirming``. Stamps
    ``isolate_issuing``/``isolate_issuing_timestamp``/
    ``isolate_issuing_action`` (``Approved`` or ``Returned``). Broadcasts
    an IC ISOLATE_CONFIRMED/ISOLATE_REJECTED SSE event. Responds with
    ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/isolate-confirm unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISSUING:
        log.warning("POST /ics/isolate-confirm: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    response = payload.get('response')
    if icId is None or response is None:
        log.warning("POST /ics/isolate-confirm: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/isolate-confirm: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getStatus() != IC.Status.ISOLATE_CONFIRMING:
        log.warning(
            "POST /ics/isolate-confirm: forbidden — IC #%s not awaiting IA confirmation (user='%s')",
            icId, user.getUsername(),
        )
        return jsonify({"success": False, "error": "IC is not awaiting IA confirmation"}), 403
    try:
        action = IC.ApprovalActions.APPROVED if response else IC.ApprovalActions.RETURNED
        icDB.updateICFromDict({
            'id': icId,
            'isolate_issuing': user.getUsername(),
            'isolate_issuing_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            'isolate_issuing_action': action,
        })
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        sseAction = SSEAction.ISOLATE_CONFIRMED if action == IC.ApprovalActions.APPROVED else SSEAction.ISOLATE_REJECTED
        sse.broadcast(SSEObject.IC, icId, sseAction, user.getUsername())
        log.info("IC isolate confirmation: id=%s action='%s' by='%s'", icId, action, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/isolate-confirm failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/isolate-execute", methods=["POST"])
def executeIsolateIC():
    """Isolator carries out the isolation, completing the isolate cycle.

    POST /ics/isolate-execute. Requires the ``ISOLATOR`` role, and the
    caller's department must match the IC's ``execution_department`` (403
    otherwise). Body: ``{"ic-id": <int>, "items": <optional list of
    {"tag", "lock_num", "lock_box_num"}>}``. 403 unless the IC's
    ``getStatus()`` is ``Pending``. Merges ``lock_num``/``lock_box_num``
    into ``ic.items`` by tag — ``tag``/``description``/``state`` stay
    server-authoritative, and an unrecognized tag in the payload is
    dropped. Stamps ``isolate_isolator``/``isolate_isolator_timestamp``,
    moving the IC to ``Active``. Broadcasts an IC ISOLATED SSE event.
    Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/isolate-execute unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISOLATOR:
        log.warning("POST /ics/isolate-execute: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    if icId is None:
        log.warning("POST /ics/isolate-execute: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/isolate-execute: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getStatus() != IC.Status.PENDING:
        log.warning(
            "POST /ics/isolate-execute: forbidden — IC #%s not ready for isolator execution (user='%s')",
            icId, user.getUsername(),
        )
        return jsonify({"success": False, "error": "IC is not ready for isolator execution"}), 403
    if (user.getDepartment() or '').casefold() != (ic.execution_department or '').casefold():
        log.warning(
            "POST /ics/isolate-execute: forbidden — IC #%s execution department '%s' does not match user department '%s' (user='%s')",
            icId, ic.execution_department, user.getDepartment(), user.getUsername(),
        )
        return jsonify({"success": False, "error": "This IC is routed to a different execution department"}), 403
    try:
        # Merge by tag rather than trusting the submitted list wholesale — only lock_num/
        # lock_box_num are ever taken from the client, tag/description/state stay server-authoritative.
        lockUpdatesByTag = {i.get('tag'): i for i in (payload.get('items') or []) if i.get('tag')}
        updatedItems = []
        for item in ic.items:
            upd = lockUpdatesByTag.get(item.tag)
            if upd:
                item.lock_num = upd.get('lock_num', item.lock_num)
                item.lock_box_num = upd.get('lock_box_num', item.lock_box_num)
            updatedItems.append(objToDict(item))
        icDB.updateICFromDict({
            'id': icId,
            'isolate_isolator': user.getUsername(),
            'isolate_isolator_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            'items': updatedItems,
        })
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        sse.broadcast(SSEObject.IC, icId, SSEAction.ISOLATED, user.getUsername())
        log.info("IC isolate execution: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/isolate-execute failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/deisolate-request", methods=["POST"])
def requestDeisolateIC():
    """Request that an active IC be de-isolated.

    POST /ics/deisolate-request. Requires an authenticated non-guest user.
    Body: ``{"ic-id": <int>}``. 403 unless the IC's ``getStatus()`` is
    ``Active``. Delegates to ``setDeisolateRequested`` to stamp
    ``deisolate_requestor``/``deisolate_requestor_timestamp`` and clear any
    stale ``deisolate_issuing*`` decision. Responds with
    ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/deisolate-request unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() == UserRoles.GUEST:
        log.warning("POST /ics/deisolate-request: forbidden for guest '%s'", user.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    if icId is None:
        log.warning("POST /ics/deisolate-request: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/deisolate-request: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getStatus() != IC.Status.ACTIVE:
        log.warning(
            "POST /ics/deisolate-request: forbidden — IC #%s not awaiting a de-isolate request (user='%s')",
            icId, user.getUsername(),
        )
        return jsonify({"success": False, "error": "IC is not awaiting a de-isolate request"}), 403
    try:
        setDeisolateRequested(icId, user.getUsername())
        log.info("IC de-isolate requested: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/deisolate-request failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/deisolate-confirm", methods=["POST"])
def confirmDeisolateIC():
    """Issuing confirms or returns a pending de-isolate request.

    POST /ics/deisolate-confirm. Requires the ``ISSUING`` role (403
    otherwise). Body: ``{"ic-id": <int>, "response": <bool>}``. 403 unless
    the IC's ``getStatus()`` is ``Deisolate Confirming``. Stamps
    ``deisolate_issuing``/``deisolate_issuing_timestamp``/
    ``deisolate_issuing_action`` (``Approved`` or ``Returned``). Broadcasts
    an IC DEISOLATE_CONFIRMED/DEISOLATE_REJECTED SSE event. Responds with
    ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/deisolate-confirm unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISSUING:
        log.warning("POST /ics/deisolate-confirm: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    response = payload.get('response')
    if icId is None or response is None:
        log.warning("POST /ics/deisolate-confirm: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/deisolate-confirm: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getStatus() != IC.Status.DEISOLATE_CONFIRMING:
        log.warning(
            "POST /ics/deisolate-confirm: forbidden — IC #%s not awaiting IA confirmation (user='%s')",
            icId, user.getUsername(),
        )
        return jsonify({"success": False, "error": "IC is not awaiting IA confirmation"}), 403
    try:
        action = IC.ApprovalActions.APPROVED if response else IC.ApprovalActions.RETURNED
        icDB.updateICFromDict({
            'id': icId,
            'deisolate_issuing': user.getUsername(),
            'deisolate_issuing_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            'deisolate_issuing_action': action,
        })
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        sseAction = SSEAction.DEISOLATE_CONFIRMED if action == IC.ApprovalActions.APPROVED else SSEAction.DEISOLATE_REJECTED
        sse.broadcast(SSEObject.IC, icId, sseAction, user.getUsername())
        log.info("IC de-isolate confirmation: id=%s action='%s' by='%s'", icId, action, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/deisolate-confirm failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/deisolate-execute", methods=["POST"])
def executeDeisolateIC():
    """Isolator carries out the de-isolation, completing the de-isolate cycle.

    POST /ics/deisolate-execute. Requires the ``ISOLATOR`` role, and the
    caller's department must match the IC's ``execution_department`` (403
    otherwise). Body: ``{"ic-id": <int>}``. 403 unless the IC's
    ``getStatus()`` is ``Closing``. Stamps ``deisolate_isolator``/
    ``deisolate_isolator_timestamp``, moving the IC to ``Closed`` — the
    only path to that status. Broadcasts an IC DEISOLATED SSE event.
    Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/deisolate-execute unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() != UserRoles.ISOLATOR:
        log.warning("POST /ics/deisolate-execute: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    if icId is None:
        log.warning("POST /ics/deisolate-execute: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/deisolate-execute: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if ic.getStatus() != IC.Status.CLOSING:
        log.warning(
            "POST /ics/deisolate-execute: forbidden — IC #%s not ready for isolator de-isolation (user='%s')",
            icId, user.getUsername(),
        )
        return jsonify({"success": False, "error": "IC is not ready for isolator de-isolation"}), 403
    if (user.getDepartment() or '').casefold() != (ic.execution_department or '').casefold():
        log.warning(
            "POST /ics/deisolate-execute: forbidden — IC #%s execution department '%s' does not match user department '%s' (user='%s')",
            icId, ic.execution_department, user.getDepartment(), user.getUsername(),
        )
        return jsonify({"success": False, "error": "This IC is routed to a different execution department"}), 403
    try:
        icDB.updateICFromDict({
            'id': icId,
            'deisolate_isolator': user.getUsername(),
            'deisolate_isolator_timestamp': datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        })
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        sse.broadcast(SSEObject.IC, icId, SSEAction.DEISOLATED, user.getUsername())
        log.info("IC de-isolate execution: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/deisolate-execute failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/link-ptw", methods=["POST"])
def linkPTWToIC():
    """Link a PTW to an IC, symmetrically updating both sides.

    POST /ics/link-ptw. Requires the ``USER``, ``ISSUING``, or
    ``COORDINATOR`` role (403 otherwise). Body: ``{"ic-id": <int>,
    "ptw-id": <int>}``. 400 if the PTW is already linked, 404 if the IC or
    PTW doesn't exist, 403 if ``IC.canLinkPTW(ptw)`` rejects the pair.
    Updates ``IC.linked_ptws``/``held_by`` and ``PTW.linked_ics``, resyncs
    the PTW cache, and broadcasts LINKED SSE events for both the IC and
    the PTW. Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/link-ptw unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() not in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR):
        log.warning("POST /ics/link-ptw: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    ptwId = payload.get('ptw-id')
    if icId is None or not ptwId:
        log.warning("POST /ics/link-ptw: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/link-ptw: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if str(ptwId) in ic.linked_ptws:
        return jsonify({"success": False, "error": f"PTW #{ptwId} is already linked to this IC"}), 400
    try:
        ptw = ptwDB.getPTWById(ptwId)
        if ptw is None:
            log.warning("POST /ics/link-ptw: PTW #%s not found (user='%s')", ptwId, user.getUsername())
            return jsonify({"success": False, "error": f"PTW #{ptwId} not found"}), 404
        if not ic.canLinkPTW(ptw):
            log.warning(
                "POST /ics/link-ptw: forbidden — IC #%s / PTW #%s not in a linkable state (ic status='%s', PTW approval='%s', PTW running='%s') (user='%s')",
                icId, ptwId, ic.getStatus(), ptw.approval_status, ptw.running_status, user.getUsername(),
            )
            return jsonify({"success": False, "error": "IC or PTW is not in a linkable state"}), 403
        ic.linkPTW(ptwId)
        icDB.updateICFromDict({
            'id': icId,
            'linked_ptws': ic.linked_ptws,
            'held_by': ic.held_by,
        })
        if str(icId) not in ptw.linked_ics:
            ptw.linked_ics.append(str(icId))
            ptwDB.updatePTWFromDict({'id': ptwId, 'linked_ics': ptw.linked_ics})
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        syncPtwCache(ptwId)
        sse.broadcast(SSEObject.IC, icId, SSEAction.LINKED, user.getUsername())
        sse.broadcast(SSEObject.PTW, ptwId, SSEAction.LINKED, user.getUsername())
        log.info("IC linked to PTW: id=%s ptw=%s by='%s'", icId, ptwId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/link-ptw failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@icsBp.route("/ics/unlink-ptw", methods=["POST"])
def unlinkPTWFromIC():
    """Unlink a PTW from an IC, symmetrically updating both sides.

    POST /ics/unlink-ptw. Requires the ``USER``, ``ISSUING``, or
    ``COORDINATOR`` role (403 otherwise). Body: ``{"ic-id": <int>,
    "ptw-id": <int>}``. 400 if the PTW isn't currently in the IC's
    ``linked_ptws``/``held_by``. Updates ``IC.linked_ptws``/``held_by`` and
    ``PTW.linked_ics``, resyncs the PTW cache, broadcasts UNLINKED SSE
    events for both the IC and the PTW, and runs the automatic
    de-isolate check on the IC. Responds with ``{"success": True}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ics/unlink-ptw unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if user.getRole() not in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR):
        log.warning("POST /ics/unlink-ptw: forbidden for role='%s' user='%s'", user.getRole(), user.getUsername())
        return jsonify({"success": False, "error": "Forbidden"}), 403
    payload = request.get_json(silent=True) or {}
    icId = payload.get('ic-id')
    ptwId = payload.get('ptw-id')
    if icId is None or not ptwId:
        log.warning("POST /ics/unlink-ptw: missing required fields (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    with globalData.lock:
        ic = globalData.ics.get(icId)
    if ic is None:
        log.warning("POST /ics/unlink-ptw: IC #%s not found (user='%s')", icId, user.getUsername())
        return jsonify({"success": False, "error": "IC not found"}), 404
    if str(ptwId) not in ic.linked_ptws and str(ptwId) not in ic.held_by:
        return jsonify({"success": False, "error": f"PTW #{ptwId} is not linked to this IC"}), 400
    try:
        ptw = ptwDB.getPTWById(ptwId)
        ic.unlinkPTW(ptwId)
        icDB.updateICFromDict({
            'id': icId,
            'linked_ptws': ic.linked_ptws,
            'held_by': ic.held_by,
        })
        if ptw is not None and str(icId) in ptw.linked_ics:
            ptw.linked_ics.remove(str(icId))
            ptwDB.updatePTWFromDict({'id': ptwId, 'linked_ics': ptw.linked_ics})
        updated = icDB.getICById(icId)
        if updated:
            with globalData.lock:
                globalData.ics[updated.id] = updated
        syncPtwCache(ptwId)
        sse.broadcast(SSEObject.IC, icId, SSEAction.UNLINKED, user.getUsername())
        sse.broadcast(SSEObject.PTW, ptwId, SSEAction.UNLINKED, user.getUsername())
        log.info("IC unlinked from PTW: id=%s ptw=%s by='%s'", icId, ptwId, user.getUsername())
        checkAndAutoDeisolateICs([icId], user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/unlink-ptw failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400
