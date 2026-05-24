import os
import json
import queue
import threading
from pathlib import Path
from time import time

# Load .env if present (keeps secrets out of source code)
_env_path = Path(__file__).parent / '.env'
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith('#') and '=' in _line:
            _k, _v = _line.split('=', 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from requests import *
from flask import *
from flask_mail import Mail, Message
from random import randint

from usersDb import UsersDb
from ptwDb import PtwsDb
from risksDb import RisksDb
from IsolationDb import IsolationDb
from User import User, UserRoles
from GlobalData import globalData
from PTWData import objToDict, PTWData, ActiveIsolation

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

_sse_clients: dict[UserRoles, list[queue.Queue]] = {}   # role -> connected queues
_sse_lock = threading.Lock()

def _broadcast(event_type: str, data: dict, roles: list[UserRoles] = None):
    """Broadcast an SSE event. roles=None sends to all connected roles."""
    msg = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
    with _sse_lock:
        targets = roles if roles is not None else list(_sse_clients.keys())
        for role in targets:
            for q in list(_sse_clients.get(role, [])):
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    _sse_clients[role].remove(q)

try:
    userDB = UsersDb()
    ptwDB = PtwsDb()
    risksDB = RisksDb()
    isoDB = IsolationDb()
    globalData.refresh()
except Exception as e:
    exit(1)


def getVerifiedUser(auth) -> User:
    try:
        username = auth.username
        password = auth.password
        for user in userDB.getAllUsers():
            if user.getUsername() == username and user.getPassword() == password:
                return user
        return None
    except AttributeError:
        return None


@app.get("/events")
def sse_stream():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    role = user.getRole()
    q = queue.Queue(maxsize=50)
    with _sse_lock:
        _sse_clients.setdefault(role, []).append(q)
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
    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/login", methods=["POST"])
def login():
    try:
        auth = request.authorization
        username = auth.username
        password = auth.password
        for user in userDB.getAllUsers():
            if user.getUsername() == username and user.getPassword() == password:
                return jsonify({"success": True, "user": objToDict(user)})
        return jsonify({"success": False, "error": "Invalid username or password"}), 401
    except Exception as e:
        return jsonify({"success": False, "error": "Invalid request format"}), 400

@app.route("/reset-password-request", methods=["POST"])
def requestResetPassword():
    payload = request.get_json(silent=True) or {}
    username = payload.get('username')
    if not username:
        return jsonify({"success": False, "error": "No username specified"}), 401
    try:
        userEmail = globalData.allUsers[username].getEmail()
        # userEmail = userDB.getSecuredUser(username).getEmail()
        if not userEmail:
            raise Exception("No email associated to this user")
    except Exception as e:
        return jsonify({"success": False, "error": f"Can't find a mail associated to username {username}"}), 400

    code = str(randint(0, 10**6 - 1)).zfill(6)
    msg = Message(
        subject='PTW Reset Password Verification Code',
        sender=os.environ.get('MAIL_USERNAME'),
        recipients=[userEmail], 
        cc=['shady.abdelhady@rashpetco.com'], 
        # body='An automated flask test mail', 
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
    
    resetCodes[username] = (code, time())
    return jsonify({"success": True, "message": "Verification code sent to registered email address"})


@app.route("/reset-password", methods=["POST"])
def resetPassword():
    payload = request.get_json(silent=True) or {}
    username = payload.get('username')
    newPassword = payload.get('new-password')
    verificationCode = payload.get('verification-code')
    if not username or not newPassword or not verificationCode:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    if username not in resetCodes:
        return jsonify({"success": False, "error": "No reset password request found for this username"}), 404
    code, timestamp = resetCodes[username]
    if time() - timestamp > 15 * 60:  # code expires after 15 minutes
        del resetCodes[username]
        return jsonify({"success": False, "error": "Verification code expired"}), 400
    if verificationCode != code:
        return jsonify({"success": False, "error": "Invalid verification code"}), 400
    
    try:
        userDB.updateUserPassword(username, newPassword)
        del resetCodes[username]
        return jsonify({"success": True, "message": "Password reset successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/user", methods=["GET"])
def getSecuredUser():
    user = getVerifiedUser(request.authorization)
    data = request.get_json(silent=True) or {}
    requestedUsername = data.get('username')
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        return jsonify({"success": True, "user": objToDict(userDB.getSecuredUser(requestedUsername))})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/users", methods=["GET"])
def getAllUsers():  
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        return jsonify({"success": True, "all-users": objToDict(userDB.getAllSecuredUsers())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/usernames", methods=["GET"])
def getAllUsernames():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        users = userDB.getAllUsernames()
        return jsonify({"success": True, "usernames": users})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/users", methods=["POST"])
def newUserRequest():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    userDataDict = request.get_json(silent=True) or {}
    try:
        err = userDB.addUserFromDict(userDataDict)
        return jsonify({"success": True, "error": err})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/users", methods=["PUT"])
def updateUserRequest():
    authUser = getVerifiedUser(request.authorization)
    if authUser is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    userDataDict = request.get_json(silent=True) or {}
    try:
        if authUser.getRole() == UserRoles.ADMIN or authUser.getUsername() == userDataDict["username"]:
            return jsonify({"success": True, "user": userDB.updateUserFromDict(userDataDict)})
        else:
            return jsonify({"success": False, "error": "Unauthorized"}), 401
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/users", methods=["DELETE"])
def deleteUserRequest():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"success": True, "user": userDB.deleteUser(User(username=data["username"]))})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/ptws", methods=["GET"])
def getAllPTWs():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        dep = data.get('department')
        req = data.get('requestor')
        ptws = ptwDB.getAllPTWs(department=dep, requestor=req)
        return jsonify({"success": True, "ptws": [objToDict(ptw) for ptw in ptws]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/ptws/archive", methods=["GET"])
def getArchivedPTWs():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True) or {}
        dep = data.get('department')
        ptws = ptwDB.getArchivedPTWs(department=dep)
        return jsonify({"success": True, "ptws": [objToDict(ptw) for ptw in ptws]})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/ptws", methods=["POST"])
def addPTWRequest():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    ptwDict = request.get_json(silent=True) or {}
    try:
        ptw_id = ptwDB.addPTWFromDict(ptwDict)
        _broadcast("new_ptw", {"ptw_id": ptw_id, "type": ptwDict.get("type", ""), "by": user.getUsername()}, roles=[UserRoles.USER, UserRoles.COORDINATOR])
        return jsonify({"success": True, "ptw-id": ptw_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws", methods=["DELETE"])
def deletePTWRequest():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        ptw_id = payload.get('ptw-id')
        result = ptwDB.deletePTW(ptw_id)
        _broadcast("ptw_deleted", {"ptw_id": ptw_id, "by": user.getUsername()})
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/ptws/approvals", methods=["POST"])
def updatePTWApprovals():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    approval = PTWData.Approval(**payload.get('approval'))
    if ptwId is None or approval is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        result = ptwDB.updatePTWApprovals(ptwId, approval)
        _broadcast("ptw_approval", {"ptw_id": ptwId, "action": str(approval.action), "by": user.getUsername()})
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    
@app.route("/ptws/archive", methods=["POST"])
def archivePTWs():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwIds = payload.get('ptw-ids')
    if ptwIds is None:
        return jsonify({"success": False, "error": "Missing required field: ptw-ids"}), 400
    try:
        result = ptwDB.archivePTWs(ptwIds)
        _broadcast("ptw_archived", {"ptw_ids": ptwIds, "by": user.getUsername()})
        return jsonify({"success": True, "ptw": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/ptws/run-request", methods=["POST"])
def requestToRunPTW():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    pa = payload.get('pa')
    ts = payload.get('timestamp')
    if ptwId is None or pa is None or ts is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        result = ptwDB.requestToRunPTW(ptwId, pa, ts)
        _broadcast("ptw_run_request", {"ptw_id": ptwId, "by": pa}, roles=[UserRoles.USER, UserRoles.ISSUING])
        return jsonify({"success": True, "message": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/run", methods=["POST"])
def runPTW():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    ia = payload.get('ia')
    ts = payload.get('timestamp')
    ok = payload.get('response')
    if ptwId is None or ia is None or ts is None or ok is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    ptw = None
    for p in globalData.allPTWs:
        if p.id == ptwId:
            ptw = p
    if ptw is None:
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400

    try:
        if ok:
            ptwDB.runAcceptPTW(ptwId, ia, ts)
            for iso in ptw.isolations:
                if iso.tag not in globalData.activeIsolations:
                    globalData.activeIsolations[iso.tag] = ActiveIsolation(type=iso.type, tag=iso.tag, description=iso.description)
                globalData.activeIsolations[iso.tag].linkPTW(ptwId)
                isoDB.updateIsolation(globalData.activeIsolations[iso.tag])
            _broadcast("ptw_run", {"ptw_id": ptwId, "accepted": True, "by": ia})
            return jsonify({"success": True})
        else:
            ptwDB.runRejectPTW(ptwId, ia, ts)
            _broadcast("ptw_run", {"ptw_id": ptwId, "accepted": False, "by": ia})
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    

@app.route("/ptws/hold-request", methods=["POST"])
def requestToHldPTW():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    pa = payload.get('pa')
    ts = payload.get('timestamp')
    keepTags = payload.get('keep-tags', [])
    if ptwId is None or pa is None or ts is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        ptwDB.requestToHldPTW(ptwId, pa, ts, keepTags)
        for p in globalData.allPTWs:
            if p.id == ptwId:
                p.keep_isolations = keepTags
                p.running_status = PTWData.RunningStatus.WAITING_HLD_CONFIRM
                break
        _broadcast("ptw_hold_request", {"ptw_id": ptwId, "by": pa}, roles=[UserRoles.USER, UserRoles.ISSUING])
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/hold", methods=["POST"])
def hldPTW():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    ia = payload.get('ia')
    ts = payload.get('timestamp')
    ok = payload.get('response')
    if ptwId is None or ia is None or ts is None or ok is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400

    ptw = next((p for p in globalData.allPTWs if p.id == ptwId), None)
    if ptw is None:
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400

    try:
        keepTags = ptw.keep_isolations
        if ok:
            ptwDB.hldAcceptPTW(ptwId, ia, ts)
            for iso in ptw.isolations:
                if iso.tag not in keepTags and iso.tag in globalData.activeIsolations:
                    globalData.activeIsolations[iso.tag].unlinkPTW(ptwId)
                    isoDB.updateIsolation(globalData.activeIsolations[iso.tag])
            _broadcast("ptw_hold", {"ptw_id": ptwId, "accepted": True, "by": ia})
            return jsonify({"success": True})
        else:
            ptwDB.hldRejectPTW(ptwId, ia, ts)
            _broadcast("ptw_hold", {"ptw_id": ptwId, "accepted": False, "by": ia})
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/close-request", methods=["POST"])
def requestToClsPTW():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    pa = payload.get('pa')
    ts = payload.get('timestamp')
    if ptwId is None or pa is None or ts is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        result = ptwDB.requestToClsPTW(ptwId, pa, ts)
        _broadcast("ptw_close_request", {"ptw_id": ptwId, "by": pa}, roles=[UserRoles.USER, UserRoles.ISSUING])
        return jsonify({"success": True, "message": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/ptws/close", methods=["POST"])
def clsPTW():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    ia = payload.get('ia')
    ts = payload.get('timestamp')
    ok = payload.get('response')
    if ptwId is None or ia is None or ts is None or ok is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    ptw = next((p for p in globalData.allPTWs if p.id == ptwId), None)
    if ptw is None:
        return jsonify({"success": False, "error": f"PTW# {ptwId} not found"}), 400
    
    try:
        if ok:
            ptwDB.clsAcceptPTW(ptwId, ia, ts)
            for iso in ptw.isolations:
                if iso.tag in globalData.activeIsolations:
                    globalData.activeIsolations[iso.tag].unlinkPTW(ptwId)
                    isoDB.updateIsolation(globalData.activeIsolations[iso.tag])
                else:
                    print(f"Isolation {iso.tag} not found in active isolations")
            _broadcast("ptw_close", {"ptw_id": ptwId, "accepted": True, "by": ia})
            return jsonify({"success": True})
        else:
            ptwDB.clsRejectPTW(ptwId, ia, ts)
            _broadcast("ptw_close", {"ptw_id": ptwId, "accepted": False, "by": ia})
            return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    

@app.route("/ptws/attachments", methods=["POST"])
def addPtwAttachments():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    attachments = request.files or {}
    payload = request.values.to_dict() or {}

    ptwId = payload.get('ptw-id')
    if ptwId is None:
        return jsonify({"success": False, "error": "Missing PTW id field"}), 400
    
    errors = []
    succeeded = []
    for file in attachments.values():
        filename = file.filename if file else None
        if not filename:
            errors.append(f"No file selected for uploading {filename}")
            continue
        
        try:
            os.makedirs(f'./ptw-{ptwId}-attachments', exist_ok=True)
            filepath = os.path.join(f'./ptw-{ptwId}-attachments', filename)
            if os.path.exists(filepath):
                errors.append(f"File with the same name already exists for {filename}")
                continue
            file.save(filepath)
            succeeded.append(filename)
        except Exception as e:
            errors.append(f"Failed to upload file for {filename}: {str(e)}")

    # err = ptwDB.addPtwAttachments(ptwId, succeeded)
    # if err:
    #     return jsonify({"success": False, "error": err}), 400
    if errors:
        return jsonify({"success": False, "error": "\n".join(errors)}), 400
    else:
        return jsonify({"success": True, "message": "Files uploaded successfully"})
    

@app.route("/ptws/attachments", methods=["GET"])
def getPtwAttachment():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    filename = payload.get('filename')
    if ptwId is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        if filename:
            filepath = os.path.join(f'./ptw-{ptwId}-attachments', filename)
            if not os.path.isfile(filepath):
                return jsonify({"success": False, "error": "File not found"}), 404
            return send_file(filepath, as_attachment=True)
        else:
            filenames = []
            dir = f'./ptw-{ptwId}-attachments'
            if not os.path.exists(dir):
                return jsonify({"success": True, "message": "PTW attachments dir not found", "attachments": []})
            for filename in os.listdir(dir):
                filepath = os.path.join(dir, filename)
                if os.path.isfile(filepath):
                    filenames.append(filename)
            return jsonify({"success": True, "attachments": filenames})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    
@app.route("/ptws/attachments", methods=["DELETE"])
def deletePtwAttachments():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    ptwId = payload.get('ptw-id')
    keepFilenames = payload.get('keep-filenames')
    if ptwId is None or keepFilenames is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    keepFilenames = set(keepFilenames)
    try:
        dir = f'./ptw-{ptwId}-attachments'
        if os.path.exists(dir):
            for filename in os.listdir(dir):
                filePath = os.path.join(dir, filename)
                if os.path.isfile(filePath) and filename not in keepFilenames:
                    os.remove(filePath)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/ptws/attachments/copy", methods=["POST"])
def copyPtwAttachments():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    sourcePtwId = payload.get('source-ptw-id')
    targetPtwId = payload.get('target-ptw-id')
    if sourcePtwId is None or targetPtwId is None:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    try:
        sourceDir = f'./ptw-{sourcePtwId}-attachments'
        targetDir = f'./ptw-{targetPtwId}-attachments'
        if not os.path.exists(sourceDir):
            return jsonify({"success": False, "error": "Source PTW attachments not found"}), 404
        os.makedirs(targetDir, exist_ok=True)
        successfullyCopied = []
        for filename in os.listdir(sourceDir):
            sourceFilePath = os.path.join(sourceDir, filename)
            targetFilePath = os.path.join(targetDir, filename)
            if os.path.isfile(sourceFilePath):
                with open(sourceFilePath, 'rb') as srcFile:
                    with open(targetFilePath, 'wb') as tgtFile:
                        tgtFile.write(srcFile.read())
                successfullyCopied.append(filename)
        # ptwDB.addPtwAttachments(targetPtwId, successfullyCopied)
        return jsonify({"success": True, "message": "Attachments copied successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    

@app.route("/isolations", methods=["GET"])
def getAllIsolations():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        return jsonify({"success": True, "isolations": objToDict([iso for iso in isoDB.getAllIsolations().values()])})
    except Exception as e:
        print(str(e))
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/risks", methods=["GET"])
def getAllRiskAssessments():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        return jsonify({"success": True, "risks": objToDict(risksDB.getAllRiskAssessments())})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/risks", methods=["POST"])
def addNewRiskAssessment():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.SAFETY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    riskAssessmentDict = request.get_json(silent=True) or {}
    try:
        return jsonify({"success": True, "error": risksDB.addRiskAssessmentFromDict(riskAssessmentDict)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/risks", methods=["PUT"])
def updateRiskAssessment():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.SAFETY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    riskAssessmentDict = request.get_json(silent=True) or {}
    try:
        return jsonify({"success": True, "error": risksDB.updateRiskAssessmentFromDict(riskAssessmentDict)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

@app.route("/risks", methods=["DELETE"])
def deleteRiskAssessment():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.SAFETY:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({"success": True, "error": risksDB.deleteRiskAssessment(data['title'])})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/miwi", methods=["GET"])
def getMIWI():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        filename = payload.get('filename')
        if not filename:
            return jsonify({"success": False, "error": "Filename not provided"}), 400
        filepath = './miwi/' + filename
        if not os.path.isfile(filepath):
            return jsonify({"success": False, "error": "File not found"}), 404
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400
    

@app.route("/miwis", methods=["GET"])
def getAllMIWIs():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        miwiPath = './miwi'
        filenames = [f for f in os.listdir(miwiPath) if os.path.isfile(os.path.join(miwiPath, f))]
        return jsonify({"success": True, "miwis": filenames})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/miwi", methods=["POST"])
def uploadMIWI():
    user = getVerifiedUser(request.authorization)
    if user is None:
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    if 'miwi' not in request.files:
        return jsonify({"success": False, "error": "No file part in the request"}), 400
    
    file = request.files['miwi']
    filename = file.filename if file else None
    if not filename:
        return jsonify({"success": False, "error": "No file selected for uploading"}), 400
    
    try:
        filepath = os.path.join('./miwi', filename)
        if os.path.exists(filepath):
            return jsonify({"success": False, "error": "File with the same name already exists"}), 400
        file.save(filepath)
        return jsonify({"success": True, "message": "File uploaded successfully"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)