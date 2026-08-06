import os
import queue
import threading
from time import time, sleep
from random import randint
from flask import Blueprint, request, jsonify, Response, stream_with_context
from flask_mail import Message

import sse
from core import app, mail, log, userDB
from GlobalData import globalData
from models.User import User, UserRoles
from utils import objToDict

authBp = Blueprint("auth", __name__)

resetCodes = {}
_RESET_CODE_TTL = 15 * 60
_RESET_CODE_PRUNE_INTERVAL = 5 * 60


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


@authBp.get("/events")
def sse_stream():
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("SSE connection rejected: unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    role = user.getRole()
    q = sse.registerClient(role)
    log.info("SSE client connected: user='%s' role=%s total_for_role=%d", user.getUsername(), role, sse.clientCount(role))

    def generate():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    yield q.get(timeout=30)
                except queue.Empty:
                    yield ": heartbeat\n\n"
        finally:
            sse.unregisterClient(role, q)
            log.info("SSE client disconnected: user='%s' role=%s", user.getUsername(), role)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@authBp.route("/login", methods=["POST"])
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


@authBp.route("/reset-password-request", methods=["POST"])
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


@authBp.route("/reset-password", methods=["POST"])
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
