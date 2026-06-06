# Known Issues & Security Backlog

Issues are grouped by severity. Fixed items are noted at the bottom for traceability.

---

## High

### H1 — Default `admin`/`admin` seed credentials
**File:** `server/usersDb.py` — `__init__`

The database seed inserts an `admin` account with password `"admin"` when the `users` table is empty. This underlying credential is trivially weak. Any fresh deployment is open until the password is manually changed.

**Fix:** Force the admin to set a real password on first login, or generate a random seed password and print it once to the console/log on first boot.

---

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

### M2 — Missing role checks on PTW state-change operations
**File:** `server/app.py` — routes `/ptws/run`, `/ptws/hold`, `/ptws/close`, `/ptws/approvals`, `DELETE /ptws`, `POST /ptws/archive`

These endpoints only verify that the caller is authenticated — they do not verify role. Any authenticated user (including `UserRoles.USER`) can accept/reject a run, hold, or close request, delete any PTW, or archive permits. The enforcement of who is allowed to take each action exists only in the client UI, not in the server.

**Fix:** Add explicit `user.getRole()` guards that match the business rules (e.g., only `ISSUING` can accept a run request, only `ADMIN` or the requestor can delete a PTW).

---

### M3 — psycopg2 connection shared across threads
**File:** `server/usersDb.py:11`, `server/ptwDb.py`, `server/risksDb.py`, `server/IsolationDb.py`

psycopg2 explicitly states that connections are **not thread-safe**. Each `*Db` class holds a single `self.conn` shared by the request-handling threads and the `_periodic_refresh` daemon thread. The `_request_lock` serialises most requests, but the SSE handler calls `userDB.getAllUsers()` without holding that lock, creating a race window.

**Fix:** Use `psycopg2.pool.ThreadedConnectionPool` (or `psycopg2.pool.SimpleConnectionPool` given the request lock), acquiring and releasing a connection per operation.

---

### M4 — SSEListener not restarted after password change
**File:** `client/MainWindow.py:368`, `client/SSEListener.py`

`SSEListener` is initialised once at login with the user's password. If the user changes their password via Settings, the listener continues using the old credential. When the SSE connection drops and the listener attempts to reconnect, authentication will fail silently and real-time events will stop arriving.

**Fix:** After a successful password change in `dlgSettings()`, stop and restart `_sseListener` with the new password.

---

## Low

### L1 — Redundant path-traversal check in `getPtwAttachment`
**File:** `server/app.py` — `getPtwAttachment` (~line 864)

The path-traversal containment check is performed, then `filepath` is reconstructed identically, then the same check runs again. The duplicate is dead code.

**Fix:** Remove the second construction + check block.

---

### L2 — Global `_request_lock` is a DoS amplifier
**File:** `server/app.py:77`

All non-SSE requests are serialised by a single threading lock. A slow DB query or large file upload from one client stalls every other client. An authenticated user can trivially cause service degradation.

**Fix:** Per-resource locking, or migrate to an async framework (e.g., Flask with gevent/eventlet, or FastAPI with asyncio). At minimum, document the single-threaded nature and ensure file upload timeouts are enforced.

---

### L3 — `resetCodes` dict is never proactively pruned
**File:** `server/app.py:74`

The in-memory `resetCodes` dict grows with every password-reset request. Expired entries are only removed when a matching (possibly expired) code submission arrives. Under sustained reset requests the dict leaks memory indefinitely.

**Fix:** Prune expired entries on a background timer, or use a time-keyed `OrderedDict` and evict from the front on each insert.

---
