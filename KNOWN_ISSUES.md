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


### M6 — `updateRiskAssessmentFromDict` is non-atomic — delete succeeds but insert may fail
**File:** `server/risksDb.py` — `updateRiskAssessmentFromDict` (line 37)

The update is implemented as `deleteRiskAssessment` followed by `addRiskAssessmentFromDict`. Each call acquires its own DB connection from the pool, so they cannot share a transaction. If the insert fails for any reason (constraint violation, lost connection, malformed row) the old assessment has already been permanently deleted with no rollback path.

**Fix:** Run both operations inside a single `with CommonDB.get_conn() as conn` block — DELETE then INSERT — so the connection's rollback on exception restores the original data. The individual helper methods can remain as-is; `updateRiskAssessmentFromDict` should bypass them and execute both statements directly on the shared connection.

---

### M7 — Multi-file attachment upload returns mid-loop on path-traversal, leaving orphaned files on disk
**File:** `server/app.py` — `addPtwAttachments` (line 867)

When uploading multiple files in one request, a path-traversal check failure inside the loop does a hard `return` immediately. Any files already saved earlier in the same loop iteration are left on disk with no corresponding DB record, and all remaining valid files are silently dropped. The client receives a 400 with no indication of which files were saved.

**Fix:** Validate all filenames before writing any file to disk — collect errors in the first pass, then only proceed to save if no errors were found. This guarantees the operation is all-or-nothing from the client's perspective.

---

### L4 — `IsolationDb.updateIsolation` has a TOCTOU race across two connections
**File:** `server/IsolationDb.py` — `updateIsolation` (line 29)

The existence check (`SELECT EXISTS`) and the subsequent `UPDATE` or `INSERT` each borrow a separate connection from the pool. Between the two calls, a concurrent request could insert a row with the same `tag`, causing the second connection's `INSERT` to fail with a unique-key violation. This is a classic check-then-act race condition.

**Fix:** Replace the two-step logic with a single upsert: `INSERT INTO isolations (...) VALUES (...) ON CONFLICT (tag) DO UPDATE SET ...`. This is atomic and eliminates the race entirely.

---


## Fixed

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
