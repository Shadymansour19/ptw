import os
from flask import Blueprint, request, jsonify, send_file

import paths
import backupService
from core import log
from models.User import UserRoles
from routes.auth import getVerifiedUser

adminBp = Blueprint("admin", __name__)


@adminBp.route("/logs", methods=["GET"])
def getLogs():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        log.warning("GET /logs unauthorized: requester='%s' (ip=%s)", user.getUsername() if user else "unauthenticated", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    filename = payload.get('filename')
    try:
        if filename:
            filepath = os.path.join(paths.LOGS_DIR, filename)
            if not os.path.abspath(filepath).startswith(os.path.abspath(paths.LOGS_DIR)):
                log.warning("GET /logs: path traversal attempt for filename='%s' by='%s'", filename, user.getUsername())
                return jsonify({"success": False, "error": "Invalid filename"}), 400
            if not os.path.isfile(filepath):
                log.warning("GET /logs: file not found '%s' (admin='%s')", filename, user.getUsername())
                return jsonify({"success": False, "error": "Log file not found"}), 404
            log.info("Log file served: '%s' to admin='%s'", filename, user.getUsername())
            return send_file(os.path.abspath(filepath), as_attachment=True, mimetype='text/plain')
        else:
            if not os.path.exists(paths.LOGS_DIR):
                return jsonify({"success": True, "logs": []})
            filenames = sorted([f for f in os.listdir(paths.LOGS_DIR) if os.path.isfile(os.path.join(paths.LOGS_DIR, f))])
            log.debug("GET /logs: %d log files listed for admin='%s'", len(filenames), user.getUsername())
            return jsonify({"success": True, "logs": filenames})
    except Exception as e:
        log.error("GET /logs failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@adminBp.route("/backups", methods=["GET", "POST", "DELETE"])
def backups():
    user = getVerifiedUser(request.authorization)
    if user is None or user.getRole() != UserRoles.ADMIN:
        log.warning("/backups unauthorized: requester='%s' (ip=%s)", user.getUsername() if user else "unauthenticated", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    if request.method == "GET":
        payload = request.get_json(silent=True) or {}
        name = payload.get('name')
        which = payload.get('which')
        try:
            if name:
                filepath = backupService.backupFilePath(name, which)
                if not os.path.isfile(filepath):
                    log.warning("GET /backups: file not found name='%s' which='%s' (admin='%s')", name, which, user.getUsername())
                    return jsonify({"success": False, "error": "Backup file not found"}), 404
                log.info("Backup file served: name='%s' which='%s' to admin='%s'", name, which, user.getUsername())
                return send_file(os.path.abspath(filepath), as_attachment=True)
            summary = backupService.listBackups()
            log.debug("GET /backups: %d backups listed for admin='%s'", len(summary["backups"]), user.getUsername())
            return jsonify({"success": True, **summary})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            log.error("GET /backups failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 400

    if request.method == "POST":
        try:
            row = backupService.createBackup()
            log.info("Backup created: name='%s' by admin='%s'", row["name"], user.getUsername())
            return jsonify({"success": True, "backup": row})
        except Exception as e:
            log.error("POST /backups failed: %s", e, exc_info=True)
            return jsonify({"success": False, "error": str(e)}), 500

    payload = request.get_json(silent=True) or {}
    name = payload.get('name')
    try:
        backupService.deleteBackup(name)
        log.info("Backup deleted: name='%s' by admin='%s'", name, user.getUsername())
        return jsonify({"success": True})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        log.error("DELETE /backups failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400
