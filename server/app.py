import os
import sys
import json
import queue
import logging
import threading
from time import time, sleep
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from flask import Flask, request, jsonify, Response, stream_with_context, send_file
from flask_mail import Mail, Message
from random import randint
import shutil

from commonDb import CommonDB
from usersDb import UsersDb
from ptwDb import PtwsDb
from risksDb import RisksDb
from ICDb import ICDb
from User import User, UserRoles, UserDepartments
from GlobalData import globalData
from PTWData import PTWData
from Isolation import IC
from utils import objToDict

# Resolve the directory that contains this file (works both as a plain script and
# as a Nuitka/PyInstaller onefile binary, regardless of the process's CWD).
_BASE_DIR = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) or getattr(sys, '__compiled__', False) else os.path.abspath(__file__))
_MIWI_DIR = os.path.join(_BASE_DIR, 'miwi')
_LOGS_DIR = os.path.join(_BASE_DIR, 'logs')
os.makedirs(_MIWI_DIR, exist_ok=True)
_MIWI_DEPARTMENTS = {d.value for d in UserDepartments}
# PTW listing itself only restricts USER/GUEST (MainWindow.refreshPtwUserGUI passes
# department=None for ISOLATOR — isolators need cross-department PTW visibility).
# MIWI documents and PTW-specific risk assessments are reviewable by any authenticated
# user regardless of department — only PTW listing itself is department-scoped.
_RESTRICTED_PTW_ROLES = {UserRoles.USER, UserRoles.GUEST}


def _resolveMiwiPath(filename: str, department: str = None) -> str:
    """Find `filename` under the MIWI store. `department` is preferred but the
    legacy flat layout and every other department folder are also searched —
    any authenticated user may review a MIWI belonging to any department.
    """
    candidateDirs = []
    if department in _MIWI_DEPARTMENTS:
        candidateDirs.append(os.path.join(_MIWI_DIR, department))
    candidateDirs.append(_MIWI_DIR)
    candidateDirs.extend(os.path.join(_MIWI_DIR, d) for d in _MIWI_DEPARTMENTS if d != department)
    for dirpath in candidateDirs:
        filepath = os.path.abspath(os.path.join(dirpath, filename))
        if not filepath.startswith(os.path.abspath(_MIWI_DIR)):
            continue
        if os.path.isfile(filepath):
            return filepath
    return None

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(location)-35s - %(message)s"
_LOG_DATE   = "%Y-%m-%d %H:%M:%S"

class _Formatter(logging.Formatter):
    def format(self, record):
        record.location = f"{record.name}:{record.funcName}:{record.lineno}"
        return super().format(record)

def _setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    fmt = _Formatter(_LOG_FORMAT, datefmt=_LOG_DATE)

    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    console.setFormatter(fmt)
    root.addHandler(console)

    os.makedirs(_LOGS_DIR, exist_ok=True)
    fh = RotatingFileHandler(os.path.join(_LOGS_DIR, 'ptw-server.log'), maxBytes=10 * 1024 * 1024, backupCount=5)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    logging.getLogger("werkzeug").setLevel(logging.WARNING)

_setup_logging()
log = logging.getLogger("app")

load_dotenv()
CommonDB.ensure_database_exists()
app = Flask(__name__)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD')
)
mail = Mail(app)

resetCodes = {}
_RESET_CODE_TTL = 15 * 60
_RESET_CODE_PRUNE_INTERVAL = 5 * 60

_DB_PERIODIC_REFRESH_INTERVAL = 5 * 60

_AUTO_ARCHIVE_AFTER_DAYS = 7
_AUTO_ARCHIVE_CHECK_INTERVAL = 60 * 60

_sse_clients: dict[UserRoles, list[queue.Queue]] = {}
_sse_lock = threading.Lock()


@app.before_request
def _log_request():
    log.debug("%s %s", request.method, request.path)


def _broadcast(event_type: str, data: dict, roles: list[UserRoles] = None):
    """Broadcast an SSE event. roles=None sends to all connected roles."""
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    dropped = 0
    with _sse_lock:
        targets = roles if roles is not None else list(_sse_clients.keys())
        for role in targets:
            for q in list(_sse_clients.get(role, [])):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    _sse_clients[role].remove(q)
                    dropped += 1
    if dropped:
        log.warning("SSE broadcast '%s': dropped %d full client queue(s)", event_type, dropped)
    else:
        log.debug("SSE broadcast '%s' data=%s", event_type, data)


try:
    log.info("Initializing databases...")
    CommonDB.init_pool()
    userDB = UsersDb()
    ptwDB = PtwsDb()
    risksDB = RisksDb()
    icDB = ICDb()
    globalData.refresh(userDB, ptwDB, icDB)
    log.info("All databases initialized successfully")
except Exception as e:
    log.critical("Database initialization failed: %s", e, exc_info=True)
    exit(1)


def _sync_ptw(ptw_id):
    updated = ptwDB.getPTWById(ptw_id)
    if updated:
        with globalData.lock:
            globalData.allPTWs[updated.id] = updated
        log.debug("PTW #%s synced from DB", ptw_id)
    else:
        log.warning("PTW #%s not found in DB during sync", ptw_id)


def _setDeisolateRequested(icId, by: str):
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
    _broadcast("ic_deisolate_request", {"ic_id": icId, "by": by})


def _checkAndAutoDeisolateICs(icIds: list, by: str = "system"):
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
            if linkedPtw.running_status == PTWData.RunningStatus.CLOSED:
                continue
            if linkedPtw.running_status == PTWData.RunningStatus.HELD and str(icId) not in linkedPtw.getHeldICs():
                continue
            allClear = False
            break
        if allClear:
            _setDeisolateRequested(icId, by)
            log.info("IC auto de-isolate requested: id=%s (all linked PTWs closed or held without requiring it)", icId)


def _periodic_refresh():
    while True:
        sleep(_DB_PERIODIC_REFRESH_INTERVAL)
        try:
            globalData.refresh(userDB, ptwDB, icDB)
            log.info("Periodic DB resync completed")
        except Exception as e:
            log.error("Periodic DB resync failed: %s", e, exc_info=True)

threading.Thread(target=_periodic_refresh, daemon=True, name="globaldata-refresh").start()
log.info("Periodic DB resync thread started (interval: 5 min)")


def _prune_reset_codes():
    while True:
        sleep(_RESET_CODE_PRUNE_INTERVAL)
        cutoff = time() - _RESET_CODE_TTL
        expired = [u for u, (_, ts) in list(resetCodes.items()) if ts < cutoff]
        for u in expired:
            del resetCodes[u]
        if expired:
            log.debug("Pruned %d expired reset code(s)", len(expired))

threading.Thread(target=_prune_reset_codes, daemon=True, name="reset-codes-pruner").start()


def _auto_archive_closed_ptws():
    while True:
        sleep(_AUTO_ARCHIVE_CHECK_INTERVAL)
        try:
            cutoff = datetime.now() - timedelta(days=_AUTO_ARCHIVE_AFTER_DAYS)
            with globalData.lock:
                closed = [ptw for ptw in globalData.allPTWs.values() if ptw.running_status == PTWData.RunningStatus.CLOSED]
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
                _broadcast("ptw_archived", {"ptw_ids": staleIds, "by": "system"})
                log.info("Auto-archived %d closed PTW(s) older than %d days: ids=%s", len(staleIds), _AUTO_ARCHIVE_AFTER_DAYS, staleIds)
        except Exception as e:
            log.error("Auto-archive sweep failed: %s", e, exc_info=True)

threading.Thread(target=_auto_archive_closed_ptws, daemon=True, name="ptw-auto-archive").start()
log.info("PTW auto-archive thread started (threshold: %d days, check interval: %ds)", _AUTO_ARCHIVE_AFTER_DAYS, _AUTO_ARCHIVE_CHECK_INTERVAL)


def getVerifiedUser(auth) -> User:
    try:
        username = auth.username
        password = auth.password
    except AttributeError:
        return None
    if not username:
        return None

    user = userDB.getVerifiedUser(username, password)
    if user is not None:
        # Deactivated accounts are rejected on every authenticated request, not just login.
        return user if user.getIsActive() else None

    # Guests aren't registered accounts: any username that isn't a real,
    # password-protected account is allowed through unauthenticated as a GUEST.
    # This never shadows a real account, since isUsernameExists() takes priority above.
    if not password and not userDB.isUsernameExists(username):
        return User(username=username, name=username, role=UserRoles.GUEST, department='')
    return None


@app.get("/events")
def sse_stream():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("SSE connection rejected: unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    role = user.getRole()
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_clients.setdefault(role, []).append(q)
    log.info("SSE client connected: user='%s' role=%s total_for_role=%d", user.getUsername(), role, len(_sse_clients.get(role, [])))

    def generate():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    yield q.get(timeout=30)
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            with _sse_lock:
                try:
                    _sse_clients[role].remove(q)
                except (ValueError, KeyError):
                    pass
            log.info("SSE client disconnected: user='%s' role=%s", user.getUsername(), role)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/login", methods=["POST"])
def login():
    try:
        auth = request.authorization
        username = auth.username if auth else None
        password = auth.password if auth else None
        user = userDB.getVerifiedUser(username, password)
        if user:
            if not user.getIsActive():
                log.warning("Login rejected: user='%s' account is not active (ip=%s)", username, request.remote_addr)
                return jsonify({"success": False, "error": "Your account is not active. Please contact an administrator."}), 403
            log.info("Login successful: user='%s' role=%s", username, user.getRole())
            return jsonify({"success": True, "user": objToDict(user)})
        log.warning("Login failed: invalid credentials for username='%s' (ip=%s)", username, request.remote_addr)
        return jsonify({"success": False, "error": "Invalid username or password"}), 401
    except Exception as e:
        log.error("Login request error: %s (ip=%s)", e, request.remote_addr, exc_info=True)
        return jsonify({"success": False, "error": "Invalid request format"}), 400


def _sendResetPasswordEmail(username, userEmail, code):
    msg = Message(
        subject='PTW Reset Password Verification Code',
        sender=os.environ.get('MAIL_USERNAME'),
        recipients=[userEmail],
        cc=['shady.abdelhady@rashpetco.com'],
        html=f'''<!DOCTYPE html>
            <html lang="en">
            <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
            <body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:40px 0;">
                <tr><td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

                    <!-- Header -->
                    <tr>
                    <td style="background-color:#1a3a5c;padding:28px 40px;text-align:center;">
                        <h1 style="margin:0;color:#ffffff;font-size:22px;letter-spacing:1px;">PTW</h1>
                        <p style="margin:4px 0 0;color:#a8c4e0;font-size:13px;">Permit to Work System</p>
                    </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                    <td style="padding:40px 40px 32px;">
                        <h2 style="margin:0 0 12px;color:#1a3a5c;font-size:18px;">Password Reset Request</h2>
                        <p style="margin:0 0 24px;color:#555555;font-size:14px;line-height:1.6;">
                        We received a request to reset the password for your account.<br>
                        Use the verification code below to complete the process. This code is valid for <strong>15 minutes</strong>.
                        </p>

                        <!-- Code box -->
                        <table width="100%" cellpadding="0" cellspacing="0">
                        <tr><td align="center" style="padding:8px 0 32px;">
                            <div style="display:inline-block;background-color:#f0f5fb;border:1px solid #c5d8ee;border-radius:8px;padding:20px 48px;">
                            <p style="margin:0 0 4px;color:#6b7280;font-size:11px;letter-spacing:2px;text-transform:uppercase;">Verification Code</p>
                            <p style="margin:0;color:#1a3a5c;font-size:36px;font-weight:bold;letter-spacing:10px;">{code}</p>
                            </div>
                        </td></tr>
                        </table>

                        <p style="margin:0;color:#888888;font-size:13px;line-height:1.6;">
                        If you did not request a password reset, please ignore this email or contact your system administrator immediately.<br>
                        <strong>Do not share this code with anyone.</strong>
                        </p>
                    </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                    <td style="background-color:#f8f9fa;border-top:1px solid #e9ecef;padding:20px 40px;text-align:center;">
                        <p style="margin:0;color:#aaaaaa;font-size:12px;">
                        This is an automated message from the PTW System. Please do not reply to this email.
                        </p>
                    </td>
                    </tr>

                </table>
                </td></tr>
            </table>
            </body>
            </html>''',
    )
    with app.app_context():
        mail.send(msg)


@app.route("/reset-password-request", methods=["POST"])
def requestResetPassword():
    payload = request.get_json(silent=True) or {}
    username = payload.get('username')
    if not username:
        log.warning("Password reset request missing username (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "No username specified"}), 401
    try:
        userEmail = globalData.allUsers[username].getEmail()
        if not userEmail:
            raise Exception("No email associated to this user")
    except Exception as e:
        log.warning("Password reset: no email found for username='%s': %s", username, e)
        return jsonify({"success": False, "error": f"Can't find a mail associated to username {username}"}), 400

    code = str(randint(0, 10**6 - 1)).zfill(6)
    try:
        _sendResetPasswordEmail(username, userEmail, code)
        log.info("Password reset code sent: username='%s' email='%s'", username, userEmail)
    except Exception as e:
        log.error("Failed to send password reset email for username='%s': %s", username, e, exc_info=True)
        return jsonify({"success": False, "error": "Failed to send verification email"}), 500

    resetCodes[username] = (code, time())
    return jsonify({"success": True, "message": "Verification code sent to registered email address"})


@app.route("/reset-password", methods=["POST"])
def resetPassword():
    payload = request.get_json(silent=True) or {}
    username = payload.get('username')
    newPassword = payload.get('new-password')
    verificationCode = payload.get('verification-code')
    if not username or not newPassword or not verificationCode:
        log.warning("Password reset: missing required fields (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    if username not in resetCodes:
        log.warning("Password reset: no pending reset for username='%s'", username)
        return jsonify({"success": False, "error": "No reset password request found for this username"}), 404
    code, timestamp = resetCodes[username]
    if time() - timestamp > _RESET_CODE_TTL:
        del resetCodes[username]
        log.warning("Password reset: expired code used for username='%s'", username)
        return jsonify({"success": False, "error": "Verification code expired"}), 400
    if verificationCode != code:
        log.warning("Password reset: invalid verification code for username='%s' (ip=%s)", username, request.remote_addr)
        return jsonify({"success": False, "error": "Invalid verification code"}), 400

    try:
        userDB.updateUserPassword(username, newPassword)
        del resetCodes[username]
        log.info("Password reset successful: username='%s'", username)
        return jsonify({"success": True, "message": "Password reset successfully"})
    except Exception as e:
        log.error("Password reset DB update failed for username='%s': %s", username, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/user", methods=["GET"])
def getSecuredUser():
    user = getVerifiedUser(request.authorization)
    data = request.get_json(silent=True) or {}
    requestedUsername = data.get('username')
    if user is None:
        log.warning("GET /user unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        result = userDB.getSecuredUser(requestedUsername)
        log.debug("GET /user: requester='%s' requested='%s'", user.getUsername(), requestedUsername)
        return jsonify({"success": True, "user": objToDict(result)})
    except Exception as e:
        log.error("GET /user failed for '%s': %s", requestedUsername, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/users", methods=["GET"])
def getAllUsers():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /users unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        result = userDB.getAllSecuredUsers()
        log.debug("GET /users: %d users returned to '%s'", len(result), user.getUsername())
        return jsonify({"success": True, "all-users": objToDict(result)})
    except Exception as e:
        log.error("GET /users failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/usernames", methods=["GET"])
def getAllUsernames():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /usernames unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        users = userDB.getAllUsernames()
        log.debug("GET /usernames: %d usernames returned to '%s'", len(users), user.getUsername())
        return jsonify({"success": True, "usernames": users})
    except Exception as e:
        log.error("GET /usernames failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


def _sendInvitationEmail(username, password, name, userEmail):
    msg = Message(
        subject='PTW Invitation',
        sender=os.environ.get('MAIL_USERNAME'),
        recipients=[userEmail],
        cc=['shady.abdelhady@rashpetco.com'],
        html=f'''<!DOCTYPE html>
            <html lang="en">
            <head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
            <body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,sans-serif;">
            <table width="100%" cellpadding="0" cellspacing="0" style="background-color:#f4f4f4;padding:40px 0;">
                <tr><td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

                    <!-- Header -->
                    <tr>
                    <td style="background-color:#1a3a5c;padding:28px 40px;text-align:center;">
                        <h1 style="margin:0;color:#ffffff;font-size:22px;letter-spacing:1px;">PTW</h1>
                        <p style="margin:4px 0 0;color:#a8c4e0;font-size:13px;">Permit to Work System</p>
                    </td>
                    </tr>

                    <!-- Body -->
                    <tr>
                    <td style="padding:40px 40px 32px;">
                        <h2 style="margin:0 0 12px;color:#1a3a5c;font-size:18px;">Welcome to PTW System</h2>
                        <p style="margin:0 0 24px;color:#555555;font-size:14px;line-height:1.6;">
                        We're excited to have you on board, <strong>{name}</strong>!<br>
                        Get started by exploring the features and functionality of our system.
                        </p>

                        <!-- Username box -->
                        <table width="100%" cellpadding="0" cellspacing="0">
                        <tr><td align="center" style="padding:8px 0 32px;">
                            <div style="display:inline-block;background-color:#f0f5fb;border:1px solid #c5d8ee;border-radius:8px;padding:20px 48px;">
                            <p style="margin:0 0 4px;color:#6b7280;font-size:11px;letter-spacing:2px;text-transform:uppercase;">Username</p>
                            <p style="margin:0;color:#1a3a5c;font-size:36px;font-weight:bold;letter-spacing:10px;">{username}</p>
                            </div>
                        </td></tr>
                        </table>

                        <!-- Password box -->
                        <table width="100%" cellpadding="0" cellspacing="0">
                        <tr><td align="center" style="padding:8px 0 32px;">
                            <div style="display:inline-block;background-color:#f0f5fb;border:1px solid #c5d8ee;border-radius:8px;padding:20px 48px;">
                            <p style="margin:0 0 4px;color:#6b7280;font-size:11px;letter-spacing:2px;text-transform:uppercase;">Initial Password</p>
                            <p style="margin:0;color:#1a3a5c;font-size:36px;font-weight:bold;letter-spacing:10px;">{password}</p>
                            </div>
                        </td></tr>
                        </table>

                        <p style="margin:0;color:#888888;font-size:13px;line-height:1.6;">
                        Consider changing this immediately after first login.<br>
                        <strong>Do not share this password with anyone.</strong>
                        </p>
                    </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                    <td style="background-color:#f8f9fa;border-top:1px solid #e9ecef;padding:20px 40px;text-align:center;">
                        <p style="margin:0;color:#aaaaaa;font-size:12px;">
                        This is an automated message from the PTW System. Please do not reply to this email.
                        </p>
                    </td>
                    </tr>

                </table>
                </td></tr>
            </table>
            </body>
            </html>''',
    )
    try:
        with app.app_context():
            mail.send(msg)
        log.info("Invitation email sent: username='%s' email='%s'", username, userEmail)
    except Exception as e:
        log.error("Failed to send invitation email for username='%s': %s", username, e, exc_info=True)


@app.route("/users", methods=["POST"])
def newUserRequest():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        log.warning("POST /users unauthorized: requester='%s' (ip=%s)", user.getUsername() if user else "unauthenticated", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    userDataDict = request.get_json(silent=True) or {}
    try:
        err = userDB.addUserFromDict(userDataDict)
        username = userDataDict.get('username')
        if err is None:
            if username:
                try:
                    with globalData.lock:
                        globalData.allUsers[username] = userDB.getSecuredUser(username)
                except Exception:
                    pass
            log.info("User created: username='%s' by admin='%s'", username, user.getUsername())
            username = userDataDict.get('username')
            password = userDataDict.get('password')
            name = userDataDict.get('name')
            userEmail = userDataDict.get('email')
            if userEmail:
                threading.Thread(
                    target=_sendInvitationEmail,
                    args=(username, password, name, userEmail),
                    daemon=True,
                    name=f"invite-email-{username}",
                ).start()
        else:
            log.warning("User creation failed for '%s': %s (by admin='%s')", username, err, user.getUsername())
        return jsonify({"success": True, "error": err})
    except Exception as e:
        log.error("POST /users exception: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/users", methods=["PUT"])
def updateUserRequest():
    authUser = getVerifiedUser(request.authorization)
    if authUser is None:
        log.warning("PUT /users unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    userDataDict = request.get_json(silent=True) or {}
    target = userDataDict.get("username")
    if authUser.getRole() == UserRoles.GUEST:
        log.warning("PUT /users: guest '%s' attempted to update '%s'", authUser.getUsername(), target)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        if authUser.getRole() == UserRoles.ADMIN or authUser.getUsername() == target:
            result = userDB.updateUserFromDict(userDataDict)
            if result is None:
                if target:
                    try:
                        with globalData.lock:
                            globalData.allUsers[target] = userDB.getSecuredUser(target)
                    except Exception:
                        pass
            log.info("User updated: username='%s' by='%s'", target, authUser.getUsername())
            return jsonify({"success": True, "user": result})
        else:
            log.warning("PUT /users: '%s' attempted to update '%s' without permission", authUser.getUsername(), target)
            return jsonify({"success": False, "error": "Unauthorized"}), 401
    except Exception as e:
        log.error("PUT /users exception for '%s': %s", target, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/users/theme", methods=["PATCH"])
def updateUserTheme():
    authUser = getVerifiedUser(request.authorization)
    if authUser is None:
        log.warning("PATCH /users/theme unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if authUser.getRole() == UserRoles.GUEST:
        log.warning("PATCH /users/theme: guest '%s' attempted to change theme", authUser.getUsername())
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    theme = data.get('theme')
    if authUser.getUsername() != username:
        log.warning("PATCH /users/theme: '%s' attempted to change theme for '%s'", authUser.getUsername(), username)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        userDB.updateTheme(username, theme)
        log.debug("Theme updated: user='%s' theme='%s'", username, theme)
        return jsonify({"success": True})
    except Exception as e:
        log.error("PATCH /users/theme failed for '%s': %s", username, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/users/active", methods=["PATCH"])
def setUserActiveRequest():
    authUser = getVerifiedUser(request.authorization)
    if authUser is None or authUser.getRole() != UserRoles.ADMIN:
        log.warning("PATCH /users/active unauthorized: requester='%s' (ip=%s)", authUser.getUsername() if authUser else "unauthenticated", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    is_active = data.get('is_active')
    if not username or is_active is None:
        return jsonify({"success": False, "error": "Missing username or is_active"}), 400
    if username == authUser.getUsername() and not is_active:
        log.warning("PATCH /users/active: admin '%s' attempted to deactivate their own account", authUser.getUsername())
        return jsonify({"success": False, "error": "You cannot deactivate your own account"}), 400
    try:
        userDB.setUserActive(username, is_active)
        with globalData.lock:
            globalData.allUsers[username] = userDB.getSecuredUser(username)
        log.info("User %s: username='%s' by admin='%s'", "activated" if is_active else "deactivated", username, authUser.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("PATCH /users/active failed for '%s': %s", username, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/users", methods=["DELETE"])
def deleteUserRequest():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        log.warning("DELETE /users unauthorized: requester='%s' (ip=%s)", user.getUsername() if user else "unauthenticated", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        username = data["username"]
        userDB.deleteUser(User(username=username))
        with globalData.lock:
            globalData.allUsers.pop(username, None)
        log.info("User deleted: username='%s' by admin='%s'", username, user.getUsername())
        return jsonify({"success": True, "user": None})
    except Exception as e:
        log.error("DELETE /users failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


def _ptwVisibleToDepartment(ptw: PTWData, department: str) -> bool:
    """department=None means unrestricted (approver-type roles). Otherwise a PTW is
    visible if it belongs to that department, or if that department currently has
    a pending required-approver slot on it (see KNOWN_ISSUES.md § M12)."""
    if department is None:
        return True
    dep = department.casefold()
    if (ptw.department or '').casefold() == dep:
        return True
    return any((a.department or '').casefold() == dep for a in ptw.pendingApprovers() if a.department)


@app.route("/ptws", methods=["GET"])
def getAllPTWs():
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


@app.route("/ptws/archive", methods=["GET"])
def getArchivedPTWs():
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


@app.route("/ptws", methods=["POST"])
def addPTWRequest():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /ptws unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    ptwDict = request.get_json(silent=True) or {}
    try:
        ptw = PTWData(ptwDict)
        err = ptw.validate()
        if err:
            log.warning("POST /ptws rejected: %s (by='%s')", err, user.getUsername())
            return jsonify({"success": False, "error": err}), 400
        ptw_id = ptwDB.addPTWFromDict(objToDict(ptw))
        new_ptw = ptwDB.getPTWById(ptw_id)
        if new_ptw:
            with globalData.lock:
                globalData.allPTWs[new_ptw.id] = new_ptw
        _broadcast("new_ptw", {"ptw_id": ptw_id, "type": ptwDict.get("type", ""), "by": user.getUsername()}, roles=[UserRoles.USER, UserRoles.COORDINATOR])
        log.info("PTW created: id=%s type='%s' by='%s'", ptw_id, ptwDict.get("type"), user.getUsername())
        return jsonify({"success": True, "ptw-id": ptw_id})
    except Exception as e:
        log.error("POST /ptws failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws", methods=["PUT"])
def updatePTWRequest():
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
    if existing.department != user.getDepartment() or existing.approval_status != PTWData.ApprovalStatus.RETURNED:
        log.warning("PUT /ptws: forbidden — PTW #%s status='%s' department='%s' user='%s' (dept='%s')", ptwId, existing.approval_status, existing.department, user.getUsername(), user.getDepartment())
        return jsonify({"success": False, "error": "Can only edit RETURNED PTWs from your own department"}), 403
    try:
        ptw = PTWData(ptwDict)
        err = ptw.validate()
        if err:
            log.warning("PUT /ptws rejected: %s (by='%s')", err, user.getUsername())
            return jsonify({"success": False, "error": err}), 400
        dbErr = ptwDB.updatePTWFromDict(objToDict(ptw))
        if dbErr:
            raise dbErr
        _sync_ptw(ptwId)
        _broadcast("ptw_updated", {"ptw_id": ptwId, "by": user.getUsername()}, roles=[UserRoles.USER, UserRoles.COORDINATOR])
        log.info("PTW updated: id=%s by='%s'", ptwId, user.getUsername())
        return jsonify({"success": True, "ptw-id": ptwId})
    except Exception as e:
        log.error("PUT /ptws failed for id=%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws", methods=["DELETE"])
def deletePTWRequest():
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
        if ptw is not None and ptw.approval_status != PTWData.ApprovalStatus.RETURNED:
            log.warning("DELETE /ptws: forbidden — PTW #%s status='%s' user='%s'", ptw_id, ptw.approval_status, user.getUsername())
            return jsonify({"success": False, "error": "Can only delete REJECTED or ARCHIVED PTWs"}), 403
        result = ptwDB.deletePTW(ptw_id)
        with globalData.lock:
            globalData.allPTWs.pop(ptw_id, None)
        _broadcast("ptw_deleted", {"ptw_id": ptw_id, "by": user.getUsername()})
        log.info("PTW deleted: id=%s by='%s'", ptw_id, user.getUsername())
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        log.error("DELETE /ptws failed for id=%s: %s", payload.get('ptw-id'), e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/approvals", methods=["POST"])
def updatePTWApprovals():
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
    if ptw.getApprovalStatus(role=user.getRole(), department=user.getDepartment()) != PTWData.ApprovalStatus.UNDER_REVIEW:
        log.warning("POST /ptws/approvals: forbidden — user '%s' (role=%s, dept=%s) not an eligible approver for PTW #%s at its current stage", user.getUsername(), user.getRole(), user.getDepartment(), ptwId)
        return jsonify({"success": False, "error": "You are not an eligible approver for this PTW at its current stage"}), 403
    approval = PTWData.Approval(**approvalData)
    try:
        result = ptwDB.updatePTWApprovals(ptwId, approval)
        _sync_ptw(ptwId)
        _broadcast("ptw_approval", {"ptw_id": ptwId, "action": str(approval.action), "by": user.getUsername()})
        log.info("PTW approval updated: id=%s action='%s' by='%s'", ptwId, approval.action, user.getUsername())
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        log.error("POST /ptws/approvals failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/archive", methods=["POST"])
def archivePTWs():
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
        if ptw.running_status not in [PTWData.RunningStatus.CLOSED]:
            log.warning("POST /ptws/archive: forbidden — PTW #%s approval='%s' running='%s' user='%s'", pid, ptw.approval_status, ptw.running_status, user.getUsername())
            return jsonify({"success": False, "error": f"PTW# {pid} cannot be archived (must be CLOSED)"}), 403
    try:
        result = ptwDB.archivePTWs(ptwIds)
        with globalData.lock:
            for pid in ptwIds:
                globalData.allPTWs.pop(pid, None)
        _broadcast("ptw_archived", {"ptw_ids": ptwIds, "by": user.getUsername()})
        log.info("PTWs archived: ids=%s by='%s'", ptwIds, user.getUsername())
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        log.error("POST /ptws/archive failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/run-request", methods=["POST"])
def requestToRunPTW():
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
        _sync_ptw(ptwId)
        _broadcast("ptw_run_request", {"ptw_id": ptwId, "by": pa}, roles=[UserRoles.USER, UserRoles.ISSUING])
        log.info("PTW run requested: id=%s by PA='%s'", ptwId, pa)
        return jsonify({"success": True, "message": result})
    except Exception as e:
        log.error("POST /ptws/run-request failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/run", methods=["POST"])
def runPTW():
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
            with globalData.lock:
                unisolatedICs = [
                    icId for icId in ptw.linked_ics
                    if not (ic := globalData.ics.get(int(icId))) or ic.getStatus() != IC.Status.ACTIVE
                ]
            if unisolatedICs:
                log.warning("POST /ptws/run: forbidden — PTW #%s has non-isolated linked IC(s) %s", ptwId, unisolatedICs)
                return jsonify({"success": False, "error": f"Cannot run: IC(s) #{', '.join(unisolatedICs)} are not isolated"}), 403
            ptwDB.runAcceptPTW(ptwId, ia, ts, comment)
            _sync_ptw(ptwId)
            _broadcast("ptw_run", {"ptw_id": ptwId, "accepted": True, "by": ia})
            log.info("PTW run accepted: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
        else:
            ptwDB.runRejectPTW(ptwId, ia, ts, comment)
            _sync_ptw(ptwId)
            _broadcast("ptw_run", {"ptw_id": ptwId, "accepted": False, "by": ia})
            log.info("PTW run rejected: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/run failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/hold-request", methods=["POST"])
def requestToHldPTW():
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
        _sync_ptw(ptwId)
        _broadcast("ptw_hold_request", {"ptw_id": ptwId, "by": pa}, roles=[UserRoles.USER, UserRoles.ISSUING])
        log.info("PTW hold requested: id=%s by PA='%s' held_ics=%s", ptwId, pa, heldICs)
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/hold-request failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/hold", methods=["POST"])
def hldPTW():
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
            _sync_ptw(ptwId)
            _checkAndAutoDeisolateICs(ptw.linked_ics)
            _broadcast("ptw_hold", {"ptw_id": ptwId, "accepted": True, "by": ia})
            log.info("PTW hold accepted: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
        else:
            ptwDB.hldRejectPTW(ptwId, ia, ts, comment)
            _sync_ptw(ptwId)
            _broadcast("ptw_hold", {"ptw_id": ptwId, "accepted": False, "by": ia})
            log.info("PTW hold rejected: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/hold failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/close-request", methods=["POST"])
def requestToClsPTW():
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
    try:
        result = ptwDB.requestToClsPTW(ptwId, pa, ts, comment)
        _sync_ptw(ptwId)
        _broadcast("ptw_close_request", {"ptw_id": ptwId, "by": pa}, roles=[UserRoles.USER, UserRoles.ISSUING])
        log.info("PTW close requested: id=%s by PA='%s'", ptwId, pa)
        return jsonify({"success": True, "message": result})
    except Exception as e:
        log.error("POST /ptws/close-request failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/close", methods=["POST"])
def clsPTW():
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
            _sync_ptw(ptwId)
            _checkAndAutoDeisolateICs(ptw.linked_ics)
            _broadcast("ptw_close", {"ptw_id": ptwId, "accepted": True, "by": ia})
            log.info("PTW closed (accepted): id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
        else:
            ptwDB.clsRejectPTW(ptwId, ia, ts, comment)
            _sync_ptw(ptwId)
            _broadcast("ptw_close", {"ptw_id": ptwId, "accepted": False, "by": ia})
            log.info("PTW close rejected: id=%s by IA='%s'", ptwId, ia)
            return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ptws/close failed for PTW #%s: %s", ptwId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/attachments", methods=["POST"])
def addPtwAttachments():
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

    attachDir = os.path.join(_BASE_DIR, f'ptw-{ptwId}-attachments')
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


@app.route("/ptws/attachments", methods=["GET"])
def getPtwAttachment():
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
        attachDir = os.path.join(_BASE_DIR, f'ptw-{ptwId}-attachments')
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


@app.route("/ptws/attachments", methods=["DELETE"])
def deletePtwAttachments():
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
        dirpath = os.path.join(_BASE_DIR, f'ptw-{ptwId}-attachments')
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


@app.route("/ptws/attachments/copy", methods=["POST"])
def copyPtwAttachments():
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
        sourceDir = os.path.join(_BASE_DIR, f'ptw-{sourcePtwId}-attachments')
        targetDir = os.path.join(_BASE_DIR, f'ptw-{targetPtwId}-attachments')
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


@app.route("/ics", methods=["GET"])
def getAllICs():
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


@app.route("/ics", methods=["POST"])
def addICRequest():
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
    try:
        ic.requestor = user.getUsername()
        ic.requestor_timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        ic_id = icDB.addICFromDict(objToDict(ic))
        new_ic = icDB.getICById(ic_id)
        if new_ic:
            with globalData.lock:
                globalData.ics[new_ic.id] = new_ic
        _broadcast(
            "new_ic",
            {"ic_id": ic_id, "type": ic.type, "by": user.getUsername()},
            roles=[UserRoles.ISSUING],
        )
        log.info("IC created: id=%s type='%s' by='%s'", ic_id, ic.type, user.getUsername())
        return jsonify({"success": True, "ic-id": ic_id})
    except Exception as e:
        log.error("POST /ics failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/approvals", methods=["POST"])
def updateICApprovals():
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
        _broadcast("ic_approval", {"ic_id": icId, "action": str(approval.action), "by": user.getUsername()})
        log.info("IC approval updated: id=%s action='%s' by='%s'", icId, approval.action, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/approvals failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/isolate-request", methods=["POST"])
def requestIsolateIC():
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
        _broadcast("ic_isolate_request", {"ic_id": icId, "by": user.getUsername()})
        log.info("IC isolate requested: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/isolate-request failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/isolate-confirm", methods=["POST"])
def confirmIsolateIC():
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
        _broadcast("ic_isolate_confirm", {"ic_id": icId, "action": str(action), "by": user.getUsername()})
        log.info("IC isolate confirmation: id=%s action='%s' by='%s'", icId, action, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/isolate-confirm failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/isolate-execute", methods=["POST"])
def executeIsolateIC():
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
        _broadcast("ic_isolate_execute", {"ic_id": icId, "by": user.getUsername()})
        log.info("IC isolate execution: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/isolate-execute failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/deisolate-request", methods=["POST"])
def requestDeisolateIC():
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
        _setDeisolateRequested(icId, user.getUsername())
        log.info("IC de-isolate requested: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/deisolate-request failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/deisolate-confirm", methods=["POST"])
def confirmDeisolateIC():
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
        _broadcast("ic_deisolate_confirm", {"ic_id": icId, "action": str(action), "by": user.getUsername()})
        log.info("IC de-isolate confirmation: id=%s action='%s' by='%s'", icId, action, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/deisolate-confirm failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/deisolate-execute", methods=["POST"])
def executeDeisolateIC():
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
        _broadcast("ic_deisolate_execute", {"ic_id": icId, "by": user.getUsername()})
        log.info("IC de-isolate execution: id=%s by='%s'", icId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/deisolate-execute failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/link-ptw", methods=["POST"])
def linkPTWToIC():
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
        _sync_ptw(ptwId)
        _broadcast("ic_link_ptw", {"ic_id": icId, "ptw_id": ptwId, "by": user.getUsername()})
        log.info("IC linked to PTW: id=%s ptw=%s by='%s'", icId, ptwId, user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/link-ptw failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ics/unlink-ptw", methods=["POST"])
def unlinkPTWFromIC():
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
        _sync_ptw(ptwId)
        _broadcast("ic_unlink_ptw", {"ic_id": icId, "ptw_id": ptwId, "by": user.getUsername()})
        log.info("IC unlinked from PTW: id=%s ptw=%s by='%s'", icId, ptwId, user.getUsername())
        _checkAndAutoDeisolateICs([icId], user.getUsername())
        return jsonify({"success": True})
    except Exception as e:
        log.error("POST /ics/unlink-ptw failed for IC #%s: %s", icId, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/risks", methods=["GET"])
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


@app.route("/risks/ptw", methods=["GET"])
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


@app.route("/risks", methods=["POST"])
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


@app.route("/risks", methods=["PUT"])
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


@app.route("/risks", methods=["DELETE"])
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


@app.route("/miwi", methods=["GET"])
def getMIWI():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /miwi unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        filename = payload.get('filename')
        department = payload.get('department')
        if not filename:
            log.warning("GET /miwi: filename not provided (user='%s')", user.getUsername())
            return jsonify({"success": False, "error": "Filename not provided"}), 400
        filepath = _resolveMiwiPath(filename, department)
        if filepath is None:
            log.warning("GET /miwi: file not found '%s' department='%s' (user='%s')", filename, department, user.getUsername())
            return jsonify({"success": False, "error": "File not found"}), 404
        log.debug("MIWI served: file='%s' to user='%s'", filename, user.getUsername())
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        log.error("GET /miwi failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/miwis", methods=["GET"])
def getAllMIWIs():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /miwis unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    department = payload.get('department')
    try:
        if department in _MIWI_DEPARTMENTS:
            deptDir = os.path.join(_MIWI_DIR, department)
            filenames = [f for f in os.listdir(deptDir) if os.path.isfile(os.path.join(deptDir, f))] if os.path.isdir(deptDir) else []
        else:
            # No (valid) department scoping requested: return everything across all
            # department folders plus any legacy files left at the flat top level.
            filenames = [f for f in os.listdir(_MIWI_DIR) if os.path.isfile(os.path.join(_MIWI_DIR, f))]
            for d in _MIWI_DEPARTMENTS:
                deptDir = os.path.join(_MIWI_DIR, d)
                if os.path.isdir(deptDir):
                    filenames.extend(f for f in os.listdir(deptDir) if os.path.isfile(os.path.join(deptDir, f)))
        log.debug("GET /miwis: %d files returned to user='%s' department='%s'", len(filenames), user.getUsername(), department)
        return jsonify({"success": True, "miwis": filenames})
    except Exception as e:
        log.error("GET /miwis failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/miwi", methods=["POST"])
def uploadMIWI():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("POST /miwi unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if 'miwi' not in request.files:
        log.warning("POST /miwi: no file part in request (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "No file part in the request"}), 400

    file = request.files['miwi']
    filename = file.filename if file else None
    if not filename:
        log.warning("POST /miwi: no filename provided (user='%s')", user.getUsername())
        return jsonify({"success": False, "error": "No file selected for uploading"}), 400

    department = request.values.get('department')
    if department not in _MIWI_DEPARTMENTS:
        log.warning("POST /miwi: invalid department='%s' (user='%s')", department, user.getUsername())
        return jsonify({"success": False, "error": "Invalid or missing department"}), 400

    try:
        deptDir = os.path.join(_MIWI_DIR, department)
        filepath = os.path.join(deptDir, filename)
        if not os.path.abspath(filepath).startswith(os.path.abspath(_MIWI_DIR)):
            log.warning("POST /miwi: path traversal attempt '%s' (user='%s')", filename, user.getUsername())
            return jsonify({"success": False, "error": "Invalid filename"}), 400
        if os.path.exists(filepath):
            log.warning("POST /miwi: file already exists '%s' department='%s' (user='%s')", filename, department, user.getUsername())
            return jsonify({"success": False, "error": "File with the same name already exists"}), 400
        os.makedirs(deptDir, exist_ok=True)
        file.save(filepath)
        log.info("MIWI uploaded: file='%s' department='%s' by='%s'", filename, department, user.getUsername())
        return jsonify({"success": True, "message": "File uploaded successfully"})
    except Exception as e:
        log.error("POST /miwi failed for file='%s': %s", filename, e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/logs", methods=["GET"])
def getLogs():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        log.warning("GET /logs unauthorized: requester='%s' (ip=%s)", user.getUsername() if user else "unauthenticated", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    filename = payload.get('filename')
    try:
        if filename:
            filepath = os.path.join(_LOGS_DIR, filename)
            if not os.path.abspath(filepath).startswith(os.path.abspath(_LOGS_DIR)):
                log.warning("GET /logs: path traversal attempt for filename='%s' by='%s'", filename, user.getUsername())
                return jsonify({"success": False, "error": "Invalid filename"}), 400
            if not os.path.isfile(filepath):
                log.warning("GET /logs: file not found '%s' (admin='%s')", filename, user.getUsername())
                return jsonify({"success": False, "error": "Log file not found"}), 404
            log.info("Log file served: '%s' to admin='%s'", filename, user.getUsername())
            return send_file(os.path.abspath(filepath), as_attachment=True, mimetype='text/plain')
        else:
            if not os.path.exists(_LOGS_DIR):
                return jsonify({"success": True, "logs": []})
            filenames = sorted([f for f in os.listdir(_LOGS_DIR) if os.path.isfile(os.path.join(_LOGS_DIR, f))])
            log.debug("GET /logs: %d log files listed for admin='%s'", len(filenames), user.getUsername())
            return jsonify({"success": True, "logs": filenames})
    except Exception as e:
        log.error("GET /logs failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


if __name__ == "__main__":
    log.info("Starting PTW server on 0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
