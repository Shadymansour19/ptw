# Known Issues & Security Backlog

Issues are grouped by severity. Fixed items are noted at the bottom for traceability.

---

## High

### H2 — No HTTPS — Basic Auth credentials sent unencrypted
**File:** `server/app.py:1141`

The server binds to plain HTTP on port 5000. Every request sends the username and password base64-encoded (not encrypted) in the `Authorization` header. Anyone on the local network path can capture credentials with a packet sniffer.

**Fix:** Terminate TLS at a reverse proxy (nginx/caddy) in front of Flask, or use `ssl_context` in `app.run()` with a certificate.

--- 

### H3 — No rate limiting on login or password-reset code
**File:** `server/app.py` — `/login` (line ~197), `/reset-password` (line ~307)

`/login` has no lockout or delay — unlimited brute-force attempts allowed. `/reset-password` accepts unlimited guesses against a 6-digit code (1,000,000 combinations). The global `_request_lock` slows sequential attempts but is not a security control and has no per-IP/per-user memory.

**Fix:** Add per-IP + per-username attempt counters with a short lockout (e.g., 5 attempts → 60 s delay). `flask-limiter` integrates directly with Flask routes.

---

## Medium

### M1 — Username enumeration via password-reset endpoint
**File:** `server/app.py:228`

`POST /reset-password-request` returns `"Can't find a mail associated to username {username}"` when the username does not exist (or has no email). An unauthenticated caller can probe for valid usernames by watching which error is returned.

**Fix:** Return a generic response regardless of whether the username exists: `"If this account exists, a verification code has been sent."` Log the real reason internally.

---


### M3 — psycopg2 connection shared across threads
**File:** `server/usersDb.py:11`, `server/ptwDb.py`, `server/risksDb.py`, `server/IsolationDb.py`

psycopg2 explicitly states that connections are **not thread-safe**. Each `*Db` class holds a single `self.conn` shared by the request-handling threads and the `_periodic_refresh` daemon thread. The `_request_lock` serialises most requests, but the SSE handler calls `userDB.getAllUsers()` without holding that lock, creating a race window.

**Fix:** Use `psycopg2.pool.ThreadedConnectionPool` (or `psycopg2.pool.SimpleConnectionPool` given the request lock), acquiring and releasing a connection per operation.

---

## Low

### L2 — Global `_request_lock` is a DoS amplifier
**File:** `server/app.py:77`

All non-SSE requests are serialized by a single threading lock. A slow DB query or large file upload from one client stalls every other client. An authenticated user can trivially cause service degradation.

**Fix:** Per-resource locking, or migrate to an async framework (e.g., Flask with gevent/eventlet, or FastAPI with asyncio). At minimum, document the single-threaded nature and ensure file upload timeouts are enforced.

---

## Fixed

### ~~H1 — Default `admin`/`admin` seed credentials~~ ✓
**File:** `server/usersDb.py` — `__init__`

Seed password is now generated with `secrets.token_urlsafe(12)` on first boot   and printed once to the log at `WARNING` level. The hardcoded `"admin"` password is gone.

---

### ~~M4 — SSEListener not restarted after password change~~ ✓
**File:** `client/MainWindow.py` — `dlgSettings`

`dlgSettings` now detects a password change, then stops and recreates `_sseListener` with the new credential before resuming.

---

### ~~L1 — Redundant path-traversal check in `getPtwAttachment`~~ ✓
**File:** `server/app.py` — `getPtwAttachment`

Removed the duplicate `filepath` reconstruction and second path-traversal check that immediately followed the first one.

---

### ~~M2 — Missing role checks on PTW state-change operations~~ ✓
**File:** `server/app.py`

- `/ptws/run`, `/ptws/hold`, `/ptws/close` — now require `ISSUING` role; returns 403 for any other role.
- `DELETE /ptws` — state guard added: active PTWs must have `approval_status == REJECTED`; PTWs not in the active cache (i.e. already archived) are also allowed through.
- `POST /ptws/archive` — state guard added: each PTW must be `REJECTED` or `CLOSED`; returns 403 otherwise.

---

### ~~L3 — `resetCodes` dict is never proactively pruned~~ ✓
**File:** `server/app.py`

Added `_RESET_CODE_TTL` and `_RESET_CODE_PRUNE_INTERVAL` constants. A daemon thread now prunes expired entries every `_RESET_CODE_PRUNE_INTERVAL` seconds. The inline `15 * 60` in `resetPassword` was replaced with `_RESET_CODE_TTL`.

---
