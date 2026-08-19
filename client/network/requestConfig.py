"""Shared HTTP client configuration constants and error-extraction helper used across
the network package."""

SERVER_URL = 'http://localhost:5000'
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
