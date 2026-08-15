# Known Issues & Security Backlog

Issues are grouped by severity. Fixed items are noted at the bottom for traceability.

The **Full-Project Audit (2026-08-15)** section below was added after a code review of the entire client and server. Its findings use `C#`/`H#`/`M#`/`L#` ids numbered to not collide with the historical ids further down (which keep their original numbers, including the still-open `H2`/`H3`/`M1`). Line numbers are as of that review and may drift.

---

## Full-Project Audit — 2026-08-15

**Cross-cutting root cause (read first).** Several of the worst findings share one root: **the server authorizes an action against the authenticated user but then persists authoritative fields straight from the client payload** instead of deriving them server-side. `PUT /users` trusted `role`/`is_active`/`department` (C1, fixed 2026-08-15 with a self-editable-field whitelist — the model for the rest); `PUT /ptws` trusts `approvals`/`run_cycles`; `POST /ptws` trusts `requestor`/`department`; the approval/run/hold/close endpoints trust `pa`/`ia`/`approval.username`. Contrast `POST /ics`, which correctly stamps `requestor`/`requestor_department` from `getVerifiedUser()`. Fixing this class (whitelist which fields each endpoint accepts, and stamp actor/identity/state fields from the authenticated session) closes C1, C2, H7, and part of M-series at once. None of these require the official client — only a valid login and a crafted HTTP request — so the server is the only trust boundary that matters.

### Critical

#### C2 — Approval/run forgery: the owner of a RETURNED permit can self-approve it via `PUT /ptws`
**File:** `server/routes/ptws.py` — `updatePTWRequest`; `server/models/PTW.py` — `PTW.__init__` (`self.approvals`/`self.run_cycles` built from the dict), `validate()`

`PUT /ptws` guards on `existing.department == user.getDepartment()` and `existing.approval_status == RETURNED`, then rebuilds the permit with `PTW(ptwDict)` and writes it back wholesale. `PTW.__init__` populates `approvals` and `run_cycles` directly from the payload (`server/models/PTW.py:676,689`), and `validate()` never inspects those arrays. So a user editing their own returned permit can submit a forged `approvals` array (a complete approval chain) — the permit becomes `APPROVED` with no approver ever acting — and even a forged `run_cycles` to make it `RUNNING`, bypassing the linked-IC isolation gate (that gate is only enforced on `/ptws/run-request` and `/ptws/run`, not on `PUT`). In a permit-to-work system this defeats the entire approval and isolation safety chain.

**Fix:** On `PUT /ptws`, preserve `approvals`/`run_cycles`/`requestor`/`is_archived` from the existing server-side record; only accept the editable form fields from the client. Never reconstruct the audit trail from the request body.

### High

#### H5 — Deleting or re-roling an approver silently regresses APPROVED/RUNNING permits
**File:** `server/models/PTW.py` / `client/models/PTW.py` — `_stageSatisfied` (`:1103`), `__updateRunningStatus` (`:1136-1138`); `server/routes/users.py` — `deleteUserRequest`

Approval replay resolves each approver through `globalData.allUsers.get(a.username)` and matches their **current** role/department (`matchesUser`). User deletion is a hard delete with no guard for outstanding approvals. When an approver of an already-`APPROVED`/`RUNNING` permit is deleted (or has their role/department changed), the next status recompute (runs on every mutation and on the periodic refresh) fails `_stageSatisfied`, regresses `approval_status` to `UNDER_REVIEW`, and — because `__updateRunningStatus` early-returns `NOT_RUNNING` for any non-approved permit — forces a **physically running permit back to NOT_RUNNING**, hiding it from Running tabs and re-enabling run-requests on it. Client and server regress identically, so nothing flags it. (Pre-isolation ICs regress `APPROVED → REQUESTED` the same way; already-ACTIVE ICs are protected because `IC.getStatus()` checks isolator fields first.)

**Fix:** Block deletion/role-change of a user with outstanding approvals, or snapshot the approver's role+department into each `Approval` at approval time and replay against the snapshot instead of the live user record.

#### H6 — SSE stream has no read timeout: a half-open connection silently kills all real-time updates
**File:** `client/network/SSEListener.py:60` (`timeout=(10, None)`)

The read timeout is `None`. The server heartbeats every 30 s, but if the TCP connection dies without FIN/RST (server crash, NAT/Wi-Fi idle drop, VLAN change) `resp.iter_lines()` blocks forever — no exception, so the reconnect path never runs. The client keeps relying on SSE for post-action refresh (`MainWindow` deliberately does not re-fetch after actions), so operators act on stale isolation/permit state indefinitely while the app looks alive.

**Fix:** Set a read timeout greater than the heartbeat interval, e.g. `timeout=(10, 65)`, so a dead link raises `ReadTimeout` and the existing reconnect loop recovers.

#### H7 — SSE reconnect loses every event during the outage, with no resync
**File:** `client/network/SSEListener.py:81-83`; `server/sse.py` (per-connection queue, no replay/Last-Event-ID); `client/windows/MainWindow.py` (no refetch-on-reconnect)

Anything broadcast while the client is disconnected (≥5 s by design) is permanently lost — the server queue is created at register time with no replay, and the client does no full refetch on reconnect. There's also a smaller startup race: the initial full fetch and the SSE thread start are not ordered, so events landing between the fetch snapshot and stream registration are lost.

**Fix:** Emit a `connected`/`reconnected` signal from `SSEListener` and have `MainWindow` run a full `refreshGUI()` on it; start the SSE thread before (or atomically with) the initial fetch.

#### H8 — Login screen pre-fills a remembered user's password into a revealable field
**File:** `client/Login.py:336-360` (`_populateRememberedUsers`/`_fillPasswordFor`/`_onUsernameSelected`), `reset()` (`:386-390`)

The most-recent user's keyring password is auto-filled on load, any selected username's password is filled on selection, and the password field has an unmask (eye) toggle — so the plaintext is one click away. After logout, `reset()` re-fills the *previous* user's password for whoever is next at the machine. On a shared control-room PC under one OS login (common in plants, defeating keyring's per-OS-user isolation), anyone can read a colleague's password and forge approvals under their identity. *(Severity is deployment-dependent: with per-operator OS logins this is not cross-user exploitable. The keyring usage itself is sound — no plaintext fallback, no passwords in logs.)*

**Fix:** Never place a retrieved password into a revealable widget. Keep a sentinel and substitute the real credential only at submit time; at minimum disable the eye toggle for keyring-filled values.

#### H9 — DialogPTW never selects the PTW's saved MIWI: wrong safety document shown, silently overwritten on edit
**File:** `client/dialogs/DialogPTW.py:415-418` (combo populated, never set to `ptw.miwi`), `:883` (View MIWI reads `currentText()`), `:1022` (`collectData` writes `currentText()` back)

`boxMiwi` is filled with all MIWIs but never set to the permit's own `ptw.miwi`, so it always displays the first alphabetical entry. Viewing a permit shows/opens the **wrong** work-instruction document; editing a returned permit and resubmitting overwrites `ptw.miwi` with that wrong value (silent data corruption).

**Fix:** After populating the combo, `boxMiwi.setCurrentText(ptw.miwi)` (and handle the "MIWI not in list" case).

#### H10 — Edit-PTW silently drops attachment additions/deletions
**File:** `client/windows/MainWindow.py:904-924` (`editPTW`); `client/dialogs/DialogPTW.py:1064` (`collectData` fills `attachsToBeUploaded`)

The only consumer of `attachsToBeUploaded`/attachment deletions is `addPTWDialog`. `editPTW`'s accepted branch saves the risk assessment and calls `updatePTW`, but never uploads or deletes attachments. A permit returned for a missing document, re-opened in Edit with the file attached, resubmits with the file never uploaded and no error — approvers see nothing. Deletes in edit mode are equally ignored.

**Fix:** In `editPTW`'s accepted branch, call `addPtwAttachments` for pending uploads and the delete endpoint for removals, mirroring `addPTWDialog`.

#### H11 — Re-request copies reference attachments (and risk rows) only if a NEW attachment was also added
**File:** `client/windows/MainWindow.py:948-953, 970-971`

`copyPtwAttachments` runs only inside `on_attachments_uploaded`, which only fires under `if dlg.attachsToBeUploaded:`. Re-requesting a permit without adding a new file leaves that list empty (the reference permit's attachments arrive marked `uploaded=True`), so the copy never happens — the new permit is created with **zero attachments**, and the server-side risk-row copy that rides on the same endpoint is skipped too, even though the dialog displayed all the originals.

**Fix:** Call `copyPtwAttachments` unconditionally on re-request (independent of whether new files were staged).

#### H12 — Closing the window (even Cancel or minimize-to-tray) permanently disables the safety-alarm polling
**File:** `client/windows/MainWindow.py:808-809`

`self._ptwAlarmTimer.stop()` and `self._fabProximityTimer.stop()` run unconditionally at the top of `closeEvent`, before the tray/exit/Cancel branching, and are only ever started in `__init__` (`_restoreFromTray` doesn't restart them). A USER-role PA who presses X and picks "keep running in tray" (whose whole purpose is background notifications), or who presses X then Cancel, never gets shift-ended / 14-shift-validity alarms again for the rest of the session — a silently disabled safety alarm.

**Fix:** Only stop the timers in the real-exit branch (or restart them in `_restoreFromTray`).

#### H13 — Stale row indexes after async round-trips race SSE updates: wrong row deleted/overwritten, desync, crashes
**File:** `client/tables/TablePTWs.py:348-377` (`updatePTW`/`deletePTW`); `client/windows/MainWindow.py:913-924` (`editPTW`), `:1871-1890` (`_applyPTWEvent`)

`deletePTW`/`updatePTW` capture a row index, then act on it in an `on_done` callback that fires after a modal confirm **and** an async HTTP round-trip. The server emits the same mutation over SSE (before the HTTP response returns), and `_applyPTWEvent` removes/moves the row by id first — so the later callback pops or repaints a *different* PTW's row, or raises `IndexError`/`KeyError` on the next `_syncPtwsData`. With two clients open, deleting PTW #12 can make #13 vanish from the table and every subsequent right-click on that tab target the wrong permit until a manual refresh. (`archivePTWs` already uses the correct id-based, SSE-only pattern.)

**Fix:** Make all table mutations id-based (look up the row by PTW id at apply time), and let SSE be the single source of truth for row add/remove/move rather than the action callback.

### Medium

#### M17 — `DELETE /ptws` state-guard bypassable by id type-confusion; no ownership check
**File:** `server/routes/ptws.py` — `deletePTWRequest`

`ptw = globalData.allPTWs.get(ptw_id)` reads a cache keyed by **int** id. If `ptw-id` arrives as a JSON string (`"5"`), the lookup misses, the `approval_status == RETURNED` guard is skipped, and `ptwDB.deletePTW("5")` runs `DELETE ... WHERE id = %s` (Postgres casts the string) — deleting an active/approved/running permit regardless of state. Separately, even with an int id there is no department/ownership check: any non-guest can delete any RETURNED permit from any department.

**Fix:** `int()`-coerce `ptw-id` (400 on failure); fetch the authoritative row from the DB for the guard rather than only the cache; add an ownership/department check.

#### M18 — `DELETE /risks` authorization checks `ptw_id` but the delete is scoped only by `title`
**File:** `server/routes/risks.py` — `deleteRiskAssessment`; `server/db/risksDb.py` — `deleteRiskAssessment`

The route lets a non-Safety user through only when `ptw_id is not None`, but `risksDB.deleteRiskAssessment(title)` runs `DELETE FROM risks WHERE title = %s` with no `ptw_id` scoping. So any authenticated user can delete a **generic Safety-library assessment** (or any other PTW's rows) by sending `{"title": "<generic name>", "ptw_id": 1}` — any non-null `ptw_id` satisfies the check while `title` selects the victim rows. (The `UPDATE` path is correctly scoped by `title AND ptw_id`; only DELETE is not.)

**Fix:** `deleteRiskAssessment(title, ptw_id)` scoping the DELETE by both; for a non-Safety caller, verify the `ptw_id` row exists and belongs to a permit they may edit.

#### M19 — Full user directory (names, roles, departments, emails) readable by guests
**File:** `server/routes/users.py` — `getAllUsers`, `getAllUsernames`, `getSecuredUser`

These endpoints admit any `getVerifiedUser()` result, including the unauthenticated GUEST session. `SecuredUser` includes `email`/`ext`/`name`/`role`/`department`, so an anonymous guest can dump the entire organizational directory with email addresses (and this broadens the historical M1 username-enumeration issue to a full directory leak).

**Fix:** Require a real (non-guest) account for the user-listing endpoints, or restrict the fields returned to guests.

#### M20 — Password-reset codes and new-user initial passwords are CC'd to a hardcoded personal mailbox
**File:** `server/routes/auth.py` — `_sendResetPasswordEmail` (`cc=['shady.abdelhady@rashpetco.com']`); `server/routes/users.py` — `_sendInvitationEmail` (same CC)

Every password-reset verification code and every new user's initial password is copied to a fixed third-party inbox. That mailbox can reset any account (it receives the codes) and holds every new account's starting credential — a standing credential-exposure and privacy problem.

**Fix:** Remove the hardcoded CC. If an ops audit copy is genuinely required, send a non-secret notification (no code/password) to a configured address.

#### M21 — Guest file upload + no request-size limit (storage abuse / disk-fill DoS)
**File:** `server/routes/documents.py` — `uploadMIWI`; `server/routes/ptws.py`/`ics.py` — attachment uploads; `server/app.py` (no `MAX_CONTENT_LENGTH`)

The upload endpoints don't block the GUEST session, and no `MAX_CONTENT_LENGTH` is configured anywhere, and there's no content-type restriction. An effectively-unauthenticated user can write arbitrary files (any type) into shared MIWI/attachment storage, and upload arbitrarily large files to exhaust disk.

**Fix:** Block guests on all upload endpoints; set `app.config['MAX_CONTENT_LENGTH']`; validate content type/extension.

#### M22 — `validate()` empty-field check can never fire on `None`; server accepts skeleton permits
**File:** `server/models/PTW.py:869` / `client/models/PTW.py:1930` (`if field == '':`)

Every validated field defaults to `None` (`data.get(...)`), and the client's own empty-id path yields `None`, not `''`, so `if field == '':` never matches — the "… cannot be empty" rule is dead. A `POST /ptws {"description":"x","mos":"y"}` passes validation and inserts a permit with NULL type/department/location/requestor, which then enters the normal approval flow.

**Fix:** `if not field:` (both copies).

#### M23 — Model divergence: server's `ALL_HAZARDS['Scaffolding']` cascades `Working at Height`; client's doesn't
**File:** `server/models/PTW.py:316-321` vs `client/models/PTW.py:330-332`

The server copy of the `Scaffolding` hazard carries a `Working at Height` requirement; the client copy is a bare `CheckBox`. So the client's `updateRequirements()`/`validate()` never adds or demands it, and a submit that checks Scaffolding alone is accepted client-side but **rejected 400 by the server** with an error the UI never predicted (and the cascaded medical-check attachment is never requested). This is exactly the hand-kept-in-sync drift the module docstrings warn about.

**Fix:** Re-sync the two model copies (add the requirement to the client), and ideally add a CI check that diffs the shared tables/methods.

#### M24 — `response.json()` inside exception handlers crashes on any non-JSON error body (~60 sites)
**File:** `client/network/authRequests.py:32,40` and the same pattern across `ptwRequests.py`, `icRequests.py`, `riskRequests.py`, `adminRequests.py`, `documentRequests.py`

The error path does `response.json().get("error", response.text)` inside the `except`; if the body isn't JSON (Flask HTML 500, gateway page, empty body) `response.json()` raises `JSONDecodeError` from within the handler and escapes — the async path surfaces "Expecting value: line 1 column 1", the sync path (reports) hits the excepthook crash dialog. The variants that call `response.json()` in the temp-file-write `except` of a **successful binary PDF** download (`ptwRequests.py:239-241`, `icRequests.py:193-195`, `documentRequests.py:43-45`) are always-wrong. (`authRequests.py:40` also references an undefined `e` in its `else` branch.)

**Fix:** One shared helper that tries `response.json()` and falls back to `response.text`; never call `.json()` in a binary-download error path.

#### M25 — Password change leaves tables and the SSE listener on the old credentials
**File:** `client/windows/MainWindow.py` — `dlgSettings` (`self.loggedUser = user`); tables capture the login-time `User`; `client/network/SSEListener.py` (built with credential strings)

`dlgSettings` replaces `MainWindow.loggedUser` with a new object rather than mutating the shared one, but every table captured the original `User` at construction, and `SSEListener` holds the old password strings. After an in-session password change, table-initiated actions authenticate with the old password (401), and the SSE listener 401s forever inside its silent reconnect loop — real-time updates die with no error shown until re-login.

**Fix:** Mutate the shared `loggedUser` in place (or propagate the new object to tables), and restart the SSE listener with the new credentials (the historical M4 fix did this for the password-reset path — extend it here).

#### M26 — Sortable isolation tables delete by row index without resync: wrong item removed after a sort
**File:** `client/tables/TableIsolations.py:40,92-106`; `client/tables/TableIsolationItems.py:44,135-150`

Both call `setSortingEnabled(True)` but keep their backing lists in insertion order and delete via `list.pop(row)` on the view row. After the user sorts by a column, right-clicking a row and deleting removes a **different** isolation item from the data than the one shown; the corrupted list is what gets submitted on the IC. (`TableIsolationItems` already stashes the item in `UserRole` for double-click resolution, but the delete path wasn't given the same fix.)

**Fix:** Resolve the target from `UserRole`/id at delete time, not the view row index (mirror the double-click fix).

#### M27 — Report generation (and PTW/risk dialog opens) run synchronous HTTP on the GUI thread
**File:** `client/reports/ReportGenerator.py:272,279,497,504,509` (per-attachment 60 s downloads in a loop); `client/windows/MainWindow.py:2096-2111` (`printPTW`/`printPTWs`); `client/dialogs/DialogPTW.py:136,143,363,369` (`getPtwAttachmentNames`/`getPTWSpecificRiskAssessment` in `__init__`)

These call `ClientRequests.*` **without** `callback=`, taking the synchronous branch and blocking the GUI thread — the exact regression class the async decorator was meant to eliminate. Opening any PTW view/edit/re-request dialog can freeze for up to 2×15 s on a slow server; "print current tab" over N permits can freeze for minutes (the RefreshOverlay animation stalls). Also `MainWindow.py:605,1378` block up to 15 s in the theme/language "Restart Now" branches.

**Fix:** Route these through the async path with `callback=`, or run report generation on a worker thread.

#### M28 — RefreshOverlay refcount leak on dialog-construction exceptions → permanently frozen app
**File:** `client/windows/MainWindow.py:891-894,910-912,936-938`; `client/dialogs/DialogIC.py:322-324`; `client/dialogs/DialogPtwAlarms.py:163-165`

These do `showBusy()` … construct a dialog … `hideBusy()` with no `try/finally` (unlike `printPTW`/`printIC`). If the dialog constructor raises — and M24's sync error path is a concrete trigger, since it does the blocking fetches in `__init__` — the input-blocking overlay is never hidden; `sys.excepthook` keeps the process alive but the app is frozen until killed.

**Fix:** Wrap each show/construct/hide in `try/finally: hideBusy()`.

#### M29 — `refreshPtwUserGUI` ignores the refresh error and reports success on stale data
**File:** `client/windows/MainWindow.py:1975-1997`

`on_done(err, _)` never checks `err`; it rebuilds every tab from the (possibly stale) cache, beeps, and shows "GUI refreshed successfully." even when the server is unreachable. (`refreshArchivedPTWs` and the Isolator/Admin refreshers all check `err`.)

**Fix:** Check `err` and surface it instead of the success toast.

#### M30 — Client-supplied actor identity on create/approve/run endpoints (audit-trail integrity)
**File:** `server/routes/ptws.py` — `addPTWRequest` (`requestor`/`department` from payload), `updatePTWApprovals` (`approval` built from payload), `requestToRunPTW`/`runPTW`/hold/close (`pa`/`ia` from payload); `server/routes/ics.py` — `updateICApprovals`

The server authorizes against the authenticated user but records the actor from client-supplied fields. An eligible approver can record an approval under a different `username`; a run/hold/close records whatever `pa`/`ia` name the client sends; `POST /ptws` trusts `requestor`/`department`. For a safety-permit audit trail ("who requested/approved/ran/issued") this is spoofable by a crafted request. (Part of the cross-cutting root cause above; `POST /ics` already stamps its requestor correctly and is the model to follow.)

**Fix:** Stamp `requestor`/`pa`/`ia`/`approval.username`/`department` from `getVerifiedUser()`; ignore those fields in the payload.

#### M31 — Unguarded `datetime.strptime` on client-supplied approval timestamp → server 500 + USER-client crash-loop
**File:** `server/models/PTW.py:1229` / `client/models/PTW.py` — `fullApprovalTimestamp`; timestamp comes from `PTW.Approval(**approvalData)` (`server/routes/ptws.py:267`)

`fullApprovalTimestamp` does `datetime.strptime(self.approvals[-1].timestamp, TIMESTAMP_FORMAT)` with no try/except and no `None` guard. Since the approval `timestamp` is taken verbatim from the request body, one malformed/None timestamp on the chain-completing approval makes `POST /ptws/run-request` raise before its try block (persistent 500 for that permit) and makes the client's 60 s `_checkPtwAlarms` timer slot raise every minute — aborting the app for every USER client in that department. The normal UI always writes the right format, so the trigger is a raw API caller or edited/legacy data, but the blast radius is large.

**Fix:** Guard the parse (try/except + None check) and reject malformed timestamps at the route; combined with M30 (stamp the timestamp server-side), the input can't be malformed.

#### M32 — `slr()` crashes the risk report on an empty analysis field
**File:** `client/reports/ReportGenerator.py:1138`

```python
t = text or ''
return t[0], t[-1], t
```
Any risk item with an empty severity/likelihood/evaluation string → `IndexError`, which kills `riskAssessmentReport` and therefore the whole PTW PDF (called from `ptwReport`).

**Fix:** `return (t[:1] or ' '), (t[-1:] or ' '), t`.

### Low

- **L5 — `optionDoForAllSelected` iterates an unordered `set` then reverses it.** `client/tables/TablePTWs.py:426-431` (and `TableICs.py:363-368`): `list(set(rows))[::-1]` is not guaranteed descending, so a multi-row delete can remove wrong rows (compounded by the H13 index race). Fix: `sorted(rows, reverse=True)` + id-based removal.
- **L6 — PTW#/IC# columns sort lexicographically.** `client/tables/TablePTWs.py:261,402-407`, `TableICs.py:230-243`: id stored as display text, so ordering goes 1, 10, 11, 2 … once ids exceed 9. Fix: numeric sort key in `UserRole` (same pattern as the Fast-Track/Long-Term columns).
- **L7 — Path containment uses `startswith` without a trailing separator.** `server/routes/ptws.py`/`ics.py` attachment handlers, `server/paths.py:74` (`resolveMiwiPath`), `server/routes/admin.py:33` (`getLogs`): `abspath(fp).startswith(abspath(dir))` would accept a sibling dir sharing the prefix (e.g. `miwi` vs `miwi_x`). Not attacker-creatable here, so hardening-level; `backupService` is already safe via a strict regex. Fix: `os.path.commonpath([...])` or append `os.sep`.
- **L8 — `resetCodes` mutated without a lock.** `server/routes/auth.py:265-275`: the pruner does `del resetCodes[u]` while `resetPassword` may delete the same key concurrently → `KeyError` kills the pruner thread. Fix: guard with a lock or use `resetCodes.pop(u, None)`.
- **L9 — Cache refresh fails silently / partially.** `server/GlobalData.py:refresh` returns an error string instead of raising and commits `allUsers` before fetching PTWs/ICs; `server/core.py:_periodic_refresh` ignores the return and logs "completed" even on failure. Fix: check the return; make the refresh atomic.
- **L10 — Temp files are never cleaned up.** Reports/QR/attachment/export/burn-in all use `delete=False`/`mkstemp` with no removal (`ReportGenerator.py:98,491,854,973,1074,1266`, `ptwRequests.py:236`, `icRequests.py:190`, `documentRequests.py:40`, `PidWiringHighlighter.py:315,356,410`). Unbounded temp growth on operator machines; `ptwRequests.py:236` also forces a `.pdf` suffix on every attachment and embeds the server filename in the temp name unsanitized. Fix: clean up after use / open with `delete=True` where possible.
- **L11 — Context-menu `QMenu`/`QAction` objects leak per right-click.** `TablePTWs.py:443`, `TableICs.py:379`, `TableUsers.py:299`, `TableBackups.py:209`, `TableIsolations.py:115`, `TableIsolationItems.py:160`: parented to the table, never deleted. Slow session-long growth.
- **L12 — `TablePTWs.showContextMenu` ignores `MenuOption.visibleFor`.** `TablePTWs.py:445-448` (contrast `TableICs.py:380-382`). Currently masked because the only predicate-guarded PTW option is wired to tabs where it's always true, but any future wiring to a mixed tab silently shows forbidden actions. Also `TableICs.showContextMenu` gates on the right-clicked row but then runs the action over all selected rows.
- **L13 — `isInMeeting()` includes RETURNED permits in the "PTW in Meeting" overlay.** `client/models/PTW.py:2260-2263`: the per-role `getApprovalStatus` check ignores the overall RETURNED state, so a permit returned at the parallel Issuing/Safety stage still shows in the Meeting tab. Fix: add an `approval_status != RETURNED` conjunct.
- **L14 — `PTW.Approval.__str__` diverged between copies.** `client/models/PTW.py:1565-1566` shows the USER approver's department; `server/models/PTW.py:545-552` doesn't (yet `IC.Approval.__str__` has it on both sides). Latent until a server-side report/log stringifies an approval.
- **L15 — Login `SSEListener.stop()` can't interrupt a blocked read.** `client/network/SSEListener.py` (read timeout `None`) + `MainWindow.py` `stop(); wait(1000)`: after logout the old thread can linger up to 30 s (next heartbeat) still authenticated as the previous user, and can be torn down while running on quit. Fix: keep a reference to the `requests` response and `.close()` it in `stop()` (plus the H6 read timeout).
- **L16 — Async callbacks can fire into deleted/closed dialogs.** `client/network/RequestWorker.py:45-47` calls `cb(err, result)` with no guard; a callback bound to a dialog deleted before delivery raises `RuntimeError: wrapped C/C++ object has been deleted`. Fix: guard with `sip.isdeleted(cb.__self__)` / try-except.
- **L17 — `@async_request` spawns an unbounded QThread per call.** `client/network/RequestWorker.py`: the bulk user-import loop (`TableUsers.py:466-467`) fires one thread + HTTP request per row (a 1,000-row file → 1,000 concurrent). Resource exhaustion, not a crash. Fix: a bounded pool / batch endpoint.
- **L18 — Bulk user import surfaces and exports plaintext passwords; weak validation.** `client/reports/ImportUsersExcel.py:105-109,210-218`, `client/tables/TableUsers.py:437-491`: generated passwords are shown and written to an xlsx 'Password' column; no email-format or username-charset validation (a username containing `:` corrupts HTTP Basic auth). Fix: don't persist plaintext credentials to disk; validate email/username.
- **L19 — Unescaped user-influenced strings in a few `Paragraph()` calls.** `client/reports/ReportGenerator.py:339,370,716,747,1184-1190`: timestamps/approver labels/analysis chars not routed through the escaping `arabicParagraph`; a stored `<`/`&` makes ReportLab's parser raise → per-record report DoS. (Everything routed through `arabicParagraph`→`pdfMarkup` is correctly escaped.) Fix: escape or route all user text through `arabicParagraph`.
- **L20 — QR payload can overflow.** `client/reports/ReportGenerator.py:80-83`: location+equipment+description at `ERROR_CORRECT_Q` beyond ~1.6 KB raises `DataOverflowError`, failing the whole report. Fix: cap/trim the QR payload or lower the EC level.
- **L21 — Dev-scripts persist plaintext credentials; one stale docstring.** `dev-scripts/generate_bookmarklet.py` bakes plaintext passwords into a bookmark (bookmark-sync exposure — it carries its own SECURITY NOTE), `dev-scripts/reset_all_passwords.py` writes plaintext passwords to `test_data/import_result.xlsx` and its docstring wrongly claims it sets a blank-string hash (it actually sets random passwords). Dev-only tooling, but worth flagging so nobody runs them against production data.

---

## High

### H2 — No HTTPS — Basic Auth credentials sent unencrypted
**File:** `server/app.py` — `app.run()`

The server binds to plain HTTP on port 5000. Every request sends the username and password base64-encoded (not encrypted) in the `Authorization` header. Anyone on the local network path can capture credentials with a packet sniffer.

**Fix:** Terminate TLS at a reverse proxy (nginx/caddy) in front of Flask, or use `ssl_context` in `app.run()` with a certificate.

--- 

### H3 — No rate limiting on login or password-reset code
**File:** `server/routes/auth.py` — `/login`, `/reset-password`

`/login` has no lockout or delay — unlimited brute-force attempts allowed. `/reset-password` accepts unlimited guesses against a 6-digit code (1,000,000 combinations). The global `_request_lock` slows sequential attempts but is not a security control and has no per-IP/per-user memory.

**Fix:** Add per-IP + per-username attempt counters with a short lockout (e.g., 5 attempts → 60 s delay). `flask-limiter` integrates directly with Flask routes.

---

## Medium

### M1 — Username enumeration via password-reset endpoint
**File:** `server/routes/auth.py` — `requestResetPassword`

`POST /reset-password-request` returns `"Can't find a mail associated to username {username}"` when the username does not exist (or has no email). An unauthenticated caller can probe for valid usernames by watching which error is returned.

**Fix:** Return a generic response regardless of whether the username exists: `"If this account exists, a verification code has been sent."` Log the real reason internally.

---


## Fixed

### ~~C1 — Privilege escalation: any user can make themselves Admin via `PUT /users`~~ ✓
**File:** `server/routes/users.py` — `updateUserRequest`

A non-admin self-update (`authUser.getUsername() == target`) handed the full client dict to `updateUserFromDict` → `updateRecordFromDict`, which set **every key that is a real column** — including `role`, `is_active`, and `department`. A logged-in low-privilege user could send `PUT /users {"username": "<self>", "role": "Admin"}` and become an administrator, or widen PTW/IC visibility by changing their own `department`. Fixed (2026-08-15) by introducing `SELF_EDITABLE_FIELDS = {name, email, ext, password}` in `server/routes/users.py`: a non-admin self-update is stripped to that whitelist (plus `username`, kept only as the row-match key) before reaching the generic column-setter, and any dropped privileged fields are logged at `WARNING` as an attack indicator. Admin updates are unchanged. The client's Settings self-update still sends the full `user.__dict__`, but its `role`/`department`/`is_active` values match the existing row, so dropping them is behavior-neutral. (The sibling findings from the same root cause — C2, M30 — remain open.)

---

### ~~M16 — Arabic UI translation was silently a no-op (only the layout direction flipped)~~ ✓
**File:** `client/helper/i18n.py`

`i18n.init(lang)` resolved its translation file's directory relative to its own module location (`os.path.dirname(__file__) + '/translations/'`), which was correct only while the module lived at `client/i18n.py`. The 2026-08-01 "Improve project files structure" reorganization moved it to `client/helper/i18n.py` (a pure rename, no logic change) without updating that relative path, and `client/translations/` was never moved alongside it — so it resolved to the non-existent `client/helper/translations/ar.json`. `init()`'s existing "file not found" fallback (`_translations = {}`, so `t()` returns every key untranslated) swallowed this completely silently: `is_rtl()` is a plain lang-code check with no file dependency, so switching to Arabic still correctly flipped the app to right-to-left layout, making the language switch *look* like it partially worked while translating nothing. This was live for ~12 days and reported by the user directly ("I see only text direction changed but no arabic text there") rather than caught by any test. Fixed by resolving the path as an explicit sibling of `helper/` (`.../helper/../translations/`) instead of a subdirectory of it, and by logging a warning whenever a non-English `init()` falls back to the empty dict, so this class of bug can't go silent again.

---

### ~~M15 — Leaving the password field blank in Settings could corrupt the session's stored credentials~~ ✓
**File:** `client/windows/MainWindow.py` — `dlgSettings`

`DialogSettings.collectData()` sets a blank password field to Python `None` (`self.loggedUser.setPassword(new_pass or None)` — intentional, so a no-op password field isn't resubmitted), but `dlgSettings`'s `on_update_done` callback then promoted that edited copy straight into the live session object (`self.loggedUser = user`) unconditionally. Every authenticated request builds `auth=(loggedUser.getUsername(), loggedUser.getPassword())`, and a `None` password isn't rejected client-side — `requests` silently base64-encodes the literal string `"None"` as the password. That fails `bcrypt.checkpw` server-side, so every subsequent authenticated call (not just the triggering one) returned `401 Unauthorized` until the user logged out and back in — the only place a real password is re-supplied. Fixed by restoring the current password onto the edited copy before promoting it whenever the field was left blank: `if not user.getPassword(): user.setPassword(self.loggedUser.getPassword())`.

---

### ~~M14 — Unhandled exception in a Qt slot aborts the whole application~~ ✓
**File:** `client/main.py`

PyQt6's default behavior when a Python exception escapes a slot invoked from the C++ side (a button click, a timer, a queued callback) is to print the traceback and abort the process — there was no override, so any transient bug anywhere in the client (a stale-index lookup, a `None` where an object was expected) took the whole app down instead of just failing that one action. Fixed by installing a `sys.excepthook` that logs the traceback and shows a warning dialog instead of letting the process abort.

---

### ~~M13 — No timeout on any client HTTP request~~ ✓
**File:** `client/network/clientRequests.py`

Every `requests.get/post/put/patch/delete` call in the file was unbounded — a hung or unresponsive server left that specific request waiting indefinitely, with no way to recover short of restarting the client. Fixed by adding `TIMEOUT` (15s, generic) and `FILE_TIMEOUT` (60s, for the five upload/download endpoints: PTW attachments upload/download/copy, MIWI upload/download) — now in `client/network/requestConfig.py` — and passing one or the other to every call.

---

### ~~M12 — Department-scoped required approvers can't see the PTW they're required to approve~~ ✓
**Files:** `server/routes/ptws.py` (`getAllPTWs`, `getArchivedPTWs`)

`requiredApprovers()` can require a `USER`-role approver from a specific department to sign off (e.g. `EX`-type permits require one `USER` approver from each of Turbo, Mech, Instrumentation, Telecom, Project, Civil, and Cathodic Protection, in parallel). But PTW *visibility* for `USER`/`GUEST` roles was scoped to the logged-in user's own department with no exception for "PTW where I'm a named required approver," so a required approver from another department could never even fetch the PTW — it would stay stuck `UNDER_REVIEW` forever. Fixed by having `GET /ptws` filter the server's in-memory `globalData.allPTWs` cache (rather than re-querying the DB) through a new `_ptwVisibleToDepartment()` check: a PTW is visible to a department if it belongs to that department *or* that department currently has a pending required-approver slot on it (via `PTW.pendingApprovers()`). This also closed a related gap while touching the same code: the `department` filter on `GET /ptws` and `GET /ptws/archive` was previously whatever the client sent in the request body, with no server-side check against the caller's real department for `USER`/`GUEST` — both routes now force `department = user.getDepartment()` for those roles instead of trusting the client value. (`ISOLATOR` was deliberately left unrestricted, matching `MainWindow.refreshPtwUserGUI`'s existing behavior of always requesting all departments for that role.)

---

### ~~M11 — PTW-specific risk assessments were visible/selectable across all other PTWs~~ ✓
**Files:** `server/db/risksDb.py`, `server/routes/risks.py`, `client/dialogs/DialogPTW.py`, `client/windows/MainWindow.py`, `client/reports/ReportGenerator.py`

Risk assessment rows only had a `title` column, and the convention was that a numeric `title` meant "specific to the PTW with that number." Nothing in the schema or the `GET /risks` handler enforced or filtered on that convention — every client received every PTW's specific risk rows on every fetch, and the PTW create/edit dialog then displayed *all* of them (not just its own) in the selectable risk list, letting a user accidentally attach another PTW's specific risk data to their own submission. Fixed by adding a real `ptw_id INTEGER` column (indexed as `idx_risks_ptw_id`): `GET /risks` now only ever returns generic rows (`ptw_id IS NULL`); a new `GET /risks/ptw` fetches one PTW's own row set on demand, department-scoped like MIWI access; and the `POST`/`PUT`/`DELETE /risks` authorization checks use `ptw_id is not None` instead of guessing from `title.isdigit()`. This was then superseded by the Preview-based materialized-table redesign — see [PROJECT.md § Risk Assessments](PROJECT.md#risk-assessments).

---

### ~~M9 — `POST /ptws` never validated incoming PTW data~~ ✓

**File:** `server/routes/ptws.py` — `addPTWRequest`

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
**File:** `server/routes/ptws.py` — `addPtwAttachments`

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
**File:** `client/windows/MainWindow.py` — `dlgSettings`

`dlgSettings` now detects a password change, then stops and recreates `_sseListener` with the new credential before resuming.

---

### ~~L1 — Redundant path-traversal check in `getPtwAttachment`~~ ✓
**File:** `server/routes/ptws.py` — `getPtwAttachment`

Removed the duplicate `filepath` reconstruction and second path-traversal check that immediately followed the first one.

---

### ~~L2 — Global `_request_lock` is a DoS amplifier~~ ✓
**File:** `server/core.py`

Resolved as a direct consequence of the M3 fix. `_request_lock` and its `before_request`/`teardown_request` hooks were removed entirely. Requests now run concurrently; the `ThreadedConnectionPool` handles DB concurrency and `globalData.lock` (an `RLock`) serialises only the brief in-memory cache mutations.

---

### ~~M3 — psycopg2 connection shared across threads~~ ✓
**Files:** `server/db/commonDb.py`, `server/db/usersDb.py`, `server/db/ptwDb.py`, `server/db/risksDb.py`, `server/IsolationDb.py`, `server/GlobalData.py`, `server/core.py`, `server/routes/*.py`

Replaced the single shared `self.conn` in every `*Db` class with a `ThreadedConnectionPool` in `CommonDB`. Each method now borrows a connection via `CommonDB.get_conn()` and returns it automatically. The global `_request_lock` was removed entirely; `GlobalData` now owns an `RLock` that protects only its in-memory cache mutations. The `_periodic_refresh` daemon and all route handlers that mutate `globalData` acquire this fine-grained lock for the minimum critical section only.

---

### ~~M2 — Missing role checks on PTW state-change operations~~ ✓
**File:** `server/routes/ptws.py`

- `/ptws/run`, `/ptws/hold`, `/ptws/close` — now require `ISSUING` role; returns 403 for any other role.
- `DELETE /ptws` — state guard added: active PTWs must have `approval_status == REJECTED`; PTWs not in the active cache (i.e. already archived) are also allowed through.
- `POST /ptws/archive` — state guard added: each PTW must be `REJECTED` or `CLOSED`; returns 403 otherwise.

---

### ~~L3 — `resetCodes` dict is never proactively pruned~~ ✓
**File:** `server/routes/auth.py`

Added `_RESET_CODE_TTL` and `_RESET_CODE_PRUNE_INTERVAL` constants. A daemon thread now prunes expired entries every `_RESET_CODE_PRUNE_INTERVAL` seconds. The inline `15 * 60` in `resetPassword` was replaced with `_RESET_CODE_TTL`.

---
