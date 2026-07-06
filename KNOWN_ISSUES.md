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


## Fixed

### ~~M9 — `POST /ptws` never validated incoming PTW data~~ ✓

**File:** `server/app.py` — `addPTWRequest`

The server persisted whatever `tools`/`hazards`/`controls`/`attachs` a client sent, with no check against the type-specific required/restricted rules or required attachments defined in `PTWData`. A buggy or malicious client (or a stale build) could submit a PTW violating those rules and the server would store it as-is. Fixed by constructing a `PTWData` from the payload and calling `validate()` before persisting; a failing submission is rejected with `400` and the reason, and nothing is written to the database. The server only validates — it does not call `updateRequirements()` or otherwise rewrite the submitted selections.

---

### ~~M10 — Required-attachment check compared bare titles against filenames with extensions~~ ✓
    
**Files:** `server/PTWData.py`, `client/PTWData.py` — `validate()`

`requiredAttachs()` returns bare descriptions (e.g. `"Power Tools Checklist"`), but `self.attachs` stores filenames with an extension appended (e.g. `"Power Tools Checklist.pdf"`, per `TableAttachments.uploadRequiredAttachment`). The old check (`required not in self.attachs`) could never match, so a required-attachment violation would never actually be caught. Fixed to a prefix match — `attach.startswith(required + '.')` — which matches regardless of the extension, including multi-dot extensions.

---

### ~~L4 — `IsolationDb.updateIsolation` has a TOCTOU race across two connections~~ ✓
**File:** `server/IsolationDb.py` — `updateIsolation`

Replaced the two-step `SELECT EXISTS` + conditional `INSERT`/`UPDATE` (each on separate pool connections) with a single atomic `INSERT ... ON CONFLICT (tag) DO UPDATE SET ...` upsert. The existence check and write are now one statement, eliminating the race entirely.

---

### ~~M8 — Blocking network calls on the GUI thread freeze the UI during submit and SSE refresh~~ ✓
**Files:** `client/clientRequests.py`, `client/RequestWorker.py`

All methods in `clientRequests.py` are now decorated with `@async_request` (from `RequestWorker.py`). When called with a `callback=` keyword argument, the decorator moves the request onto a fresh `QThread`, marshals the result back to the GUI thread via a queued signal, and calls the callback — leaving the GUI fully responsive throughout.

---

### ~~M6 — `updateRiskAssessmentFromDict` is non-atomic — delete succeeds but insert may fail~~ ✓
**File:** `server/risksDb.py` — `updateRiskAssessmentFromDict`

Rewrote to execute DELETE and all INSERTs on a single shared connection with one `conn.commit()` at the end. If any INSERT fails, `get_conn`'s exception handler rolls back the entire transaction, restoring the original assessment.

---

### ~~M7 — Multi-file attachment upload returns mid-loop on path-traversal, leaving orphaned files on disk~~ ✓
**File:** `server/app.py` — `addPtwAttachments`

Restructured into a two-pass approach: all filenames are validated first (empty name, path traversal, duplicate), and files are only written to disk if the entire validation pass is clean. The hard `return` on path traversal was replaced with an `errors.append` + `continue`, eliminating both the orphaned-file and silent-drop issues.

---

### ~~M5 — `Approval.__str__` and `__updateApprovalStatus` crash on deleted users~~ ✓
**Files:** `server/PTWData.py`, `client/PTWData.py`

All bare `globalData.allUsers[username]` lookups in `Approval.__str__`, `__updateApprovalStatus`, and `getApprovalStatus` replaced with `.get()` guards in both files. `__str__` falls back to `[deleted user: username]`; `__updateApprovalStatus` skips deleted users in the role set comprehension; `getApprovalStatus` skips deleted users in both approval-loop passes.

---

### ~~H4 — `getVerifiedUser` performs a full table scan on every authenticated request~~ ✓
**File:** `server/usersDb.py` — `getVerifiedUser`

Replaced `self.getAllUsers()` iteration with a direct `SELECT * FROM users WHERE username = %s` query. Since `username` is the primary key, the DB resolves the lookup via index in O(log n). Only one row is fetched and only its hash is passed to `_verify_password`, eliminating both the full table scan and the unnecessary in-memory exposure of all bcrypt hashes.

---

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

### ~~L2 — Global `_request_lock` is a DoS amplifier~~ ✓
**File:** `server/app.py`

Resolved as a direct consequence of the M3 fix. `_request_lock` and its `before_request`/`teardown_request` hooks were removed entirely. Requests now run concurrently; the `ThreadedConnectionPool` handles DB concurrency and `globalData.lock` (an `RLock`) serialises only the brief in-memory cache mutations.

---

### ~~M3 — psycopg2 connection shared across threads~~ ✓
**Files:** `server/commonDb.py`, `server/usersDb.py`, `server/ptwDb.py`, `server/risksDb.py`, `server/IsolationDb.py`, `server/GlobalData.py`, `server/app.py`

Replaced the single shared `self.conn` in every `*Db` class with a `ThreadedConnectionPool` in `CommonDB`. Each method now borrows a connection via `CommonDB.get_conn()` and returns it automatically. The global `_request_lock` was removed entirely; `GlobalData` now owns an `RLock` that protects only its in-memory cache mutations. The `_periodic_refresh` daemon and all route handlers that mutate `globalData` acquire this fine-grained lock for the minimum critical section only.

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
