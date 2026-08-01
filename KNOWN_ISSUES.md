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

### ~~M14 — Unhandled exception in a Qt slot aborts the whole application~~ ✓
**File:** `client/main.py`

PyQt6's default behavior when a Python exception escapes a slot invoked from the C++ side (a button click, a timer, a queued callback) is to print the traceback and abort the process — there was no override, so any transient bug anywhere in the client (a stale-index lookup, a `None` where an object was expected) took the whole app down instead of just failing that one action. Fixed by installing a `sys.excepthook` that logs the traceback and shows a warning dialog instead of letting the process abort.

---

### ~~M13 — No timeout on any client HTTP request~~ ✓
**File:** `client/network/clientRequests.py`

Every `requests.get/post/put/patch/delete` call in the file was unbounded — a hung or unresponsive server left that specific request waiting indefinitely, with no way to recover short of restarting the client. Fixed by adding `ClientRequests.TIMEOUT` (15s, generic) and `ClientRequests.FILE_TIMEOUT` (60s, for the five upload/download endpoints: PTW attachments upload/download/copy, MIWI upload/download) and passing one or the other to every call.

---

### ~~M12 — Department-scoped required approvers can't see the PTW they're required to approve~~ ✓
**Files:** `server/app.py` (`getAllPTWs`, `getArchivedPTWs`)

`requiredApprovers()` can require a `USER`-role approver from a specific department to sign off (e.g. `EX`-type permits require one `USER` approver from each of Turbo, Mech, Instrumentation, Telecom, Project, Civil, and Cathodic Protection, in parallel). But PTW *visibility* for `USER`/`GUEST` roles was scoped to the logged-in user's own department with no exception for "PTW where I'm a named required approver," so a required approver from another department could never even fetch the PTW — it would stay stuck `UNDER_REVIEW` forever. Fixed by having `GET /ptws` filter the server's in-memory `globalData.allPTWs` cache (rather than re-querying the DB) through a new `_ptwVisibleToDepartment()` check: a PTW is visible to a department if it belongs to that department *or* that department currently has a pending required-approver slot on it (via `PTW.pendingApprovers()`). This also closed a related gap while touching the same code: the `department` filter on `GET /ptws` and `GET /ptws/archive` was previously whatever the client sent in the request body, with no server-side check against the caller's real department for `USER`/`GUEST` — both routes now force `department = user.getDepartment()` for those roles instead of trusting the client value. (`ISOLATOR` was deliberately left unrestricted, matching `MainWindow.refreshPtwUserGUI`'s existing behavior of always requesting all departments for that role.)

---

### ~~M11 — PTW-specific risk assessments were visible/selectable across all other PTWs~~ ✓
**Files:** `server/db/risksDb.py`, `server/app.py`, `client/dialogs/DialogPTW.py`, `client/MainWindow.py`, `client/reports/ReportGenerator.py`

Risk assessment rows only had a `title` column, and the convention was that a numeric `title` meant "specific to the PTW with that number." Nothing in the schema or the `GET /risks` handler enforced or filtered on that convention — every client received every PTW's specific risk rows on every fetch, and the PTW create/edit dialog then displayed *all* of them (not just its own) in the selectable risk list, letting a user accidentally attach another PTW's specific risk data to their own submission. Fixed by adding a real `ptw_id INTEGER` column (indexed as `idx_risks_ptw_id`): `GET /risks` now only ever returns generic rows (`ptw_id IS NULL`); a new `GET /risks/ptw` fetches one PTW's own row set on demand, department-scoped like MIWI access; and the `POST`/`PUT`/`DELETE /risks` authorization checks use `ptw_id is not None` instead of guessing from `title.isdigit()`. This was then superseded by the Preview-based materialized-table redesign — see [PROJECT.md § Risk Assessments](PROJECT.md#risk-assessments).

---

### ~~M9 — `POST /ptws` never validated incoming PTW data~~ ✓

**File:** `server/app.py` — `addPTWRequest`

The server persisted whatever `tools`/`hazards`/`controls`/`attachs` a client sent, with no check against the type-specific required/restricted rules or required attachments defined in `PTW`. A buggy or malicious client (or a stale build) could submit a PTW violating those rules and the server would store it as-is. Fixed by constructing a `PTW` from the payload and calling `validate()` before persisting; a failing submission is rejected with `400` and the reason, and nothing is written to the database. The server only validates — it does not call `updateRequirements()` or otherwise rewrite the submitted selections.

---

### ~~M10 — Required-attachment check compared bare titles against filenames with extensions~~ ✓
    
**Files:** `server/models/PTW.py`, `client/models/PTW.py` — `validate()`

`requiredAttachs()` returns bare descriptions (e.g. `"Power Tools Checklist"`), but `self.attachs` stores filenames with an extension appended (e.g. `"Power Tools Checklist.pdf"`, per `TableAttachments.uploadRequiredAttachment`). The old check (`required not in self.attachs`) could never match, so a required-attachment violation would never actually be caught. Fixed to a prefix match — `attach.startswith(required + '.')` — which matches regardless of the extension, including multi-dot extensions.

---

### ~~L4 — `IsolationDb.updateIsolation` has a TOCTOU race across two connections~~ ✓
**File:** `server/IsolationDb.py` — `updateIsolation`

Replaced the two-step `SELECT EXISTS` + conditional `INSERT`/`UPDATE` (each on separate pool connections) with a single atomic `INSERT ... ON CONFLICT (tag) DO UPDATE SET ...` upsert. The existence check and write are now one statement, eliminating the race entirely.

---

### ~~M8 — Blocking network calls on the GUI thread freeze the UI during submit and SSE refresh~~ ✓
**Files:** `client/network/clientRequests.py`, `client/network/RequestWorker.py`

All methods in `network/clientRequests.py` are now decorated with `@async_request` (from `network/RequestWorker.py`). When called with a `callback=` keyword argument, the decorator moves the request onto a fresh `QThread`, marshals the result back to the GUI thread via a queued signal, and calls the callback — leaving the GUI fully responsive throughout.

**2026-07-26 follow-up:** the decorator alone wasn't sufficient — several call sites invoked an `@async_request`-decorated method *without* `callback=`, which falls back to the synchronous branch in `RequestWorker.async_request`'s wrapper and blocks the GUI thread exactly as before. Found and fixed in `MainWindow.refreshArchivedPTWs`, `Login.login`/`forgotPassword`, `TabServerLogs.refresh` and its per-entry log fetch (`onToggle`), and `DialogPTW.newMIWI`'s upload — all now pass `callback=`. A new `RefreshOverlay` (`client/widgets/RefreshOverlay.py`) also now dims the window and blocks input with a loading animation around every refresh/mutation reachable across the client (`MainWindow`, `Login`, `DialogIC`, `DialogPTW`, and the table widgets embedded in them), so a slow-but-async operation is visibly in progress rather than looking unresponsive, and a stray click can't land on a table mid-rebuild.

---

### ~~M6 — `updateRiskAssessmentFromDict` is non-atomic — delete succeeds but insert may fail~~ ✓
**File:** `server/db/risksDb.py` — `updateRiskAssessmentFromDict`

Rewrote to execute DELETE and all INSERTs on a single shared connection with one `conn.commit()` at the end. If any INSERT fails, `get_conn`'s exception handler rolls back the entire transaction, restoring the original assessment.

---

### ~~M7 — Multi-file attachment upload returns mid-loop on path-traversal, leaving orphaned files on disk~~ ✓
**File:** `server/app.py` — `addPtwAttachments`

Restructured into a two-pass approach: all filenames are validated first (empty name, path traversal, duplicate), and files are only written to disk if the entire validation pass is clean. The hard `return` on path traversal was replaced with an `errors.append` + `continue`, eliminating both the orphaned-file and silent-drop issues.

---

### ~~M5 — `Approval.__str__` and `__updateApprovalStatus` crash on deleted users~~ ✓
**Files:** `server/models/PTW.py`, `client/models/PTW.py`

All bare `globalData.allUsers[username]` lookups in `Approval.__str__`, `__updateApprovalStatus`, and `getApprovalStatus` replaced with `.get()` guards in both files. `__str__` falls back to `[deleted user: username]`; `__updateApprovalStatus` skips deleted users in the role set comprehension; `getApprovalStatus` skips deleted users in both approval-loop passes.

---

### ~~H4 — `getVerifiedUser` performs a full table scan on every authenticated request~~ ✓
**File:** `server/db/usersDb.py` — `getVerifiedUser`

Replaced `self.getAllUsers()` iteration with a direct `SELECT * FROM users WHERE username = %s` query. Since `username` is the primary key, the DB resolves the lookup via index in O(log n). Only one row is fetched and only its hash is passed to `_verify_password`, eliminating both the full table scan and the unnecessary in-memory exposure of all bcrypt hashes.

---

### ~~H1 — Default `admin`/`admin` seed credentials~~ ✓
**File:** `server/db/usersDb.py` — `__init__`

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
**Files:** `server/db/commonDb.py`, `server/db/usersDb.py`, `server/db/ptwDb.py`, `server/db/risksDb.py`, `server/IsolationDb.py`, `server/GlobalData.py`, `server/app.py`

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
