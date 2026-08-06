import os
import threading
from flask import Blueprint, request, jsonify
from flask_mail import Message

from core import app, mail, log, userDB
from GlobalData import globalData
from models.User import User, UserRoles
from routes.auth import getVerifiedUser
from utils import objToDict

usersBp = Blueprint("users", __name__)


@usersBp.route("/user", methods=["GET"])
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


@usersBp.route("/users", methods=["GET"])
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


@usersBp.route("/usernames", methods=["GET"])
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


@usersBp.route("/users", methods=["POST"])
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


@usersBp.route("/users", methods=["PUT"])
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


@usersBp.route("/users/theme", methods=["PATCH"])
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


@usersBp.route("/users/active", methods=["PATCH"])
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


@usersBp.route("/users", methods=["DELETE"])
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
