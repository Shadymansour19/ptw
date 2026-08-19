"""Shared HTTP client configuration constants and error-extraction helper used across
the network package."""

import os
from dotenv import load_dotenv
from helper.utils import resource_path

# Unlike the server (which loads `server/.env` via python-dotenv from its own directory),
# the client has no other use for a config file yet - this is it. `resource_path` resolves
# to the source `client/` dir in dev or the frozen Nuitka --onedir folder when built, so
# dropping a `.env` next to the installed executable works the same way as editing it next
# to `main.py` in dev. Missing file is fine - load_dotenv() just no-ops, leaving the
# os.environ.get() defaults below in place.
load_dotenv(resource_path('.env'))

# Overridable per-machine (env var, or `client/.env` - see `.env.example`) so the same
# build can point at a dev server or a real deployment without a code change - see
# KNOWN_ISSUES.md H2. Left defaulting to plain HTTP against localhost for local dev
# (running `python app.py` directly, no reverse proxy in front); a real deployment sets
# PTW_SERVER_URL to the proxy's https:// URL.
SERVER_URL = os.environ.get('PTW_SERVER_URL', 'http://localhost:5000')

# `verify=` value for every `requests` call in this package - the public half of the
# self-signed cert generated for the nginx/caddy reverse proxy, pinned directly rather
# than relying on a CA (there is no CA in this setup; see the H2 rollout plan). Only
# consulted by `requests` when SERVER_URL is https:// - a plain http:// URL (the local
# dev default above) ignores it entirely, so this is safe to always pass.
# PTW_CA_CERT_PATH (env var or `client/.env`) must point at the real deployment's
# distributed .crt file once one exists; the fallback below is for local development
# against a self-hosted dev server only. Never change this to `False` to "skip
# verification" - that defeats the point of switching to HTTPS at all.
# A relative value (the expected case - keeps `.env` portable instead of baking in one
# machine's absolute path) is resolved via `resource_path`, i.e. against the client's
# own install directory, NOT the process's current working directory - so it still
# resolves correctly no matter where the app was launched from. An absolute value is
# used as-is.
_ca_cert_path = os.environ.get('PTW_CA_CERT_PATH', os.path.join('certs', 'dev-server-cert.pem'))
VERIFY = _ca_cert_path if os.path.isabs(_ca_cert_path) else resource_path(_ca_cert_path)

TIMEOUT = 15        # seconds; generic request timeout
FILE_TIMEOUT = 60   # seconds; upload/download endpoints transferring file content


def extractError(response, exc: Exception = None) -> str:
    """Return a human-readable error message for a failed request.

    Tries `response`'s JSON `{"error": ...}` / `{"message": ...}` body first, falling
    back to its raw text if the body isn't JSON at all (a proxy/HTML error page, an
    empty body, or - for a `raise_for_status()` failure on a non-JSON API - anything
    else) - `response.json()` raises `JSONDecodeError` (a `ValueError`) on those, and
    every call site in this package used to call it directly inside an `except` block,
    where that new exception would escape in place of the original error instead of
    being caught.

    If `response` is None (the request failed before any response arrived at all, e.g.
    a connection error or timeout), falls back to `str(exc)` instead. Never call this
    on the response of a successful *binary* download (e.g. a PDF) - there is no JSON
    to parse and `response.text` would just be undecodable binary noise; use the local
    exception's own message there instead.
    """
    if response is None:
        return str(exc) if exc is not None else "Unknown error"
    try:
        data = response.json()
    except ValueError:
        return response.text
    if isinstance(data, dict):
        return data.get("error") or data.get("message") or response.text
    return response.text
