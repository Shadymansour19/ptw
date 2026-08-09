"""Flask blueprint for MIWI (Maintenance and Work Instruction) document
endpoints: list, download, and upload per-department PDF documents.
"""
import os
from flask import Blueprint, request, jsonify, send_file

import paths
from core import log
from routes.auth import getVerifiedUser

documentsBp = Blueprint("documents", __name__)


@documentsBp.route("/miwi", methods=["GET"])
def getMIWI():
    """Download a MIWI PDF by filename.

    GET, any authenticated user. Body carries ``filename`` (required) and
    an optional ``department`` used only to narrow/prefer the search —
    reading is not restricted to the caller's own department. Returns the
    file as an attachment, or a 404/400 JSON error on failure.
    """
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
        filepath = paths.resolveMiwiPath(filename, department)
        if filepath is None:
            log.warning("GET /miwi: file not found '%s' department='%s' (user='%s')", filename, department, user.getUsername())
            return jsonify({"success": False, "error": "File not found"}), 404
        log.debug("MIWI served: file='%s' to user='%s'", filename, user.getUsername())
        return send_file(filepath, as_attachment=True)
    except Exception as e:
        log.error("GET /miwi failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@documentsBp.route("/miwis", methods=["GET"])
def getAllMIWIs():
    """List MIWI filenames, optionally scoped by department.

    GET, any authenticated user. Body carries an optional ``department``;
    if it's a recognized department only that folder is listed, otherwise
    every department folder plus any legacy flat top-level files are
    returned. Responds with ``{"success": True, "miwis": [...]}``.
    """
    user = getVerifiedUser(request.authorization)
    if user is None:
        log.warning("GET /miwis unauthorized (ip=%s)", request.remote_addr)
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    department = payload.get('department')
    try:
        if department in paths.MIWI_DEPARTMENTS:
            deptDir = os.path.join(paths.MIWI_DIR, department)
            filenames = [f for f in os.listdir(deptDir) if os.path.isfile(os.path.join(deptDir, f))] if os.path.isdir(deptDir) else []
        else:
            # No (valid) department scoping requested: return everything across all
            # department folders plus any legacy files left at the flat top level.
            filenames = [f for f in os.listdir(paths.MIWI_DIR) if os.path.isfile(os.path.join(paths.MIWI_DIR, f))]
            for d in paths.MIWI_DEPARTMENTS:
                deptDir = os.path.join(paths.MIWI_DIR, d)
                if os.path.isdir(deptDir):
                    filenames.extend(f for f in os.listdir(deptDir) if os.path.isfile(os.path.join(deptDir, f)))
        log.debug("GET /miwis: %d files returned to user='%s' department='%s'", len(filenames), user.getUsername(), department)
        return jsonify({"success": True, "miwis": filenames})
    except Exception as e:
        log.error("GET /miwis failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400


@documentsBp.route("/miwi", methods=["POST"])
def uploadMIWI():
    """Upload a new MIWI PDF into a department folder.

    POST, any authenticated user. Takes the file from
    ``request.files['miwi']`` and ``department`` from the form fields,
    validated against ``paths.MIWI_DEPARTMENTS``; rejects path-traversal
    attempts and filenames that already exist. Responds with
    ``{"success": True, "message": ...}``.
    """
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
    if department not in paths.MIWI_DEPARTMENTS:
        log.warning("POST /miwi: invalid department='%s' (user='%s')", department, user.getUsername())
        return jsonify({"success": False, "error": "Invalid or missing department"}), 400

    try:
        deptDir = os.path.join(paths.MIWI_DIR, department)
        filepath = os.path.join(deptDir, filename)
        if not os.path.abspath(filepath).startswith(os.path.abspath(paths.MIWI_DIR)):
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
