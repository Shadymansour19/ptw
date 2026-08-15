# PTW System — Permit To Work

## Overview

This is a desktop-based **Permit To Work (PTW)** management system built for industrial operations (Rashpetco). It enforces a structured, multi-stage safety workflow that governs when and how maintenance or hazardous work is authorized, executed, and closed. The system tracks approvals, manages equipment isolations, and provides a full audit trail for every permit.

The application runs as a **PyQt6 desktop client** communicating with a **Flask REST API server** backed by **PostgreSQL**.

This file is the full domain/architecture/API/DB reference. See [README.md](README.md) for the
public-facing overview, [file-structure.txt](file-structure.txt) for the current file-by-file
layout, and [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for the bug/security backlog.

---

## Technology Stack

| Layer        | Technology                          |
|--------------|-------------------------------------|
| Client UI    | Python 3.12+, PyQt6, qtawesome      |
| HTTP Client  | requests (Basic Auth + SSE stream)  |
| Server       | Python 3.12+, Flask                 |
| Database     | PostgreSQL (psycopg2)               |
| Email        | Flask-Mail (Gmail SMTP)             |
| Credentials  | keyring                             |
| Reports      | ReportLab (PDF), Pillow, qrcode, arabic-reshaper, python-bidi |
| Excel Export | openpyxl                            |
| Distribution | Nuitka `--onedir` → zipped for release (Windows + Linux) |

---

## PTW Types

Each PTW is classified by the nature of the work. The type drives visual theming in the UI:

| Code | Name          | Background | Text  | Use Case                           |
|------|---------------|------------|-------|------------------------------------|
| CW   | Cold Work     | Blue       | White | Non-spark generating work          |
| SP   | Spark         | Yellow     | Black | Work that may produce sparks       |
| HT   | Hot Work      | Red        | White | Open flame / welding               |
| HC   | HydroCarbon   | Black      | White | Work near HC systems               |
| EX   | Excavation    | Gray       | White | Ground excavation work             |
| CS   | Confined Space| Green      | White | Work inside confined spaces        |

---

## Locations & Departments

**Locations:** Phase VII, Phase V, Scarab, Simian

**Departments:** Turbo, Mech (Mechanical), Elec (Electrical), IT, Prod (Production), Safety, Instrumentation, HVAC, Civil, Telecom, Project, Cathodic Protection, Petrojet, Petromaint, Egypt Gas, Contractor

---

## User Roles

The system defines 11 roles with distinct permissions:

| Role        | Description                                                    |
|-------------|----------------------------------------------------------------|
| User        | Creates PTWs; requests run, hold, close                        |
| Coordinator | Reviews and approves PTWs in the coordination stage            |
| Issuing     | Authorizes PTW execution; accepts/rejects run, hold, close     |
| Safety      | Reviews PTWs from a safety perspective; manages risk assessments|
| PDH         | Plant/Department Head — approval authority                     |
| PGM         | Production General Manager — approval authority                  |
| SOD         | System/Operation Director — approval authority                 |
| DFGM        | Direct Field General Manager — highest approval authority |
| Isolator    | Manages physical equipment isolations                          |
| Guest       | Unauthenticated visitor; creates PTWs and views only |
| Admin       | Full system access; manages users                              |

---

## PTW Lifecycle

A PTW passes through two major cycles: the **Approval Cycle** and the **Running Cycle**.

### 1. Approval Cycle

After a PTW is created, it enters an approval cycle defined by `PTW.requiredApprovers()`, which returns a **list of sequential stages**, each stage being a **list of parallel `Approver` requirements** (`PTW.Approver(role, department=None)`):

- Stages must be satisfied **in order** — stage *N+1* can't start until every `Approver` in stage *N* has approved.
- Within a stage, every `Approver` must approve before that stage counts as satisfied — they can approve in **any order/in parallel**.
- An `Approver` with `department=None` matches that role regardless of department (e.g. `SOD`, `DFGM`); one with a department set only matches a user with both that role *and* that department.

Typical stages, in order:

```
[Coordinator (Prod)]
    → [User (Turbo) ∥ User (Mech) ∥ User (Instrumentation) ∥ User (Telecom)
       ∥ User (Project) ∥ User (Civil) ∥ User (Cathodic Protection)]   — EX-type only
    → [Issuing (Prod) ∥ Safety (Safety)]
    → [PGM (Prod)] → [DFGM]                                            — HT/CS types only
```

A PTW no longer adds PDH/PGM/SOD/DFGM stages for a protective isolation — that manager approval now happens once, on the linked IC's own approval chain when that IC is a PSIC (`IC.requiredApprovers()`, see [Isolation Management](#isolation-management)), not duplicated on the PTW itself. This changed 2026-07-25; previously a PTW with a protective isolation + MOS also required `[PDH]→[PGM]→[SOD]→[DFGM]` on its own chain. (At the time, "protective" meant the IC's `type` was `Protective System`; as of 2026-07-31 it means the IC's `is_psic` flag is set — see [Isolation Management](#isolation-management).)

`PTW.pendingApprovers()` returns the flattened list of `Approver`s still outstanding (from the first unsatisfied stage onward) — used by `MainWindow.viewApprovals` to show a "Pending Approvers" list alongside the approval history, and by `getApprovalStatus(role, department)` to decide whether it's a given user's turn to act.

Each approval action is recorded with the approver's username, timestamp, action taken, and an optional comment. Any `RETURNED` action anywhere in the log immediately marks the whole PTW `RETURNED`, regardless of position — this matters once parallel approvers exist, since a later `APPROVED` from a sibling approver must not paper over an earlier return.

A required `Approver` with a department different from the PTW's own `department` still sees it: `GET /ptws` filters the server's in-memory PTW cache so a department sees a PTW if it either owns it or currently has a pending required-approver slot on it (`server/routes/ptws.py` — `_ptwVisibleToDepartment`, `PTW.pendingApprovers()`). See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (Fixed § M12) for the history.

**Approval Statuses:**

| Status       | Meaning                                                     |
|--------------|-------------------------------------------------------------|
| UNDER_REVIEW | PTW is awaiting approval from one or more approvers         |
| APPROVED     | All required approvals received; PTW is ready to run        |
| RETURNED     | Sent back to requestor for corrections; can be resubmitted  |
| REJECTED     | Permanently declined; cannot proceed                        |

### 2. Running Cycle

Once `approval_status = APPROVED`, the permit enters the running cycle. This is a state machine with the following states and transitions:

```
NOT_RUNNING
    │
    │ [Performing Authority (PA) sends run request]
    │
    ▼
WAITING_RUN_CONFIRM
    │                      
    ├───────────────────────────────────────────┐
    │                                           │
    │ [Issuing Authority (IA) accepts]          │ [IA rejects]
    │                                           │
    ▼                                           ▼
 RUNNING                                  NOT_RUNNING (back to approved)
    │
    │
    ├──── [PA sends close request]
    │         │
    │         │
    │         ▼
    │     WAITING_CLS_CONFIRM
    │         │
    │         ├─────────────────────────────────┐
    │         │                                 │
    │         │ [IA accepts]                    │ [IA rejects]
    │         │                                 │
    │         ▼                                 ▼
    │       CLOSED                           RUNNING (returns)
    │         │
    │         │ [Archive — manual, or automatic after 7 days]
    │         │ (sets is_archived; running_status stays CLOSED)
    │         ▼
    │      (is_archived = true)
    │
    │
    └──── [PA sends hold request + selects which ICs to keep held]
              │
              │
              ▼
          WAITING_HLD_CONFIRM
              │
              ├─────────────────────────────────┐
              │                                 │
              │                                 │
              │ [IA accepts]                    │  [IA rejects]
              │                                 │
              ▼                                 ▼
            HELD                             RUNNING (returns)
              │
              └──── [Can resume back to be RUNNING]
```

**Running Statuses:**

| Status               | Meaning                                                               |
|----------------------|-----------------------------------------------------------------------|
| NOT_RUNNING          | PTW approved but work not yet started                                 |
| WAITING_RUN_CONFIRM  | Run request sent to Issuing Authority; awaiting confirmation          |
| RUNNING              | Work is actively in progress                                          |
| WAITING_CLS_CONFIRM  | Close request sent to Issuing Authority; awaiting confirmation        |
| CLOSED               | Work complete; permit closed                                          |
| WAITING_HLD_CONFIRM  | Hold request sent to Issuing Authority; awaiting confirmation         |
| HELD                 | Work paused; selected isolations maintained                           |

**`running_status` is computed, not stored** — `PTW.__updateRunningStatus()` (both `client`/`server` `models/PTW.py`) replays `run_cycles` forward on every read (same pattern as `approval_status`/`approvals`, see [Database Schema](#database-schema)): a stop request (`stop_pa_request`/`stop_ia_action`) is checked ahead of `run_ia_action` so a cycle still resolves correctly even where `run_ia_action` didn't survive the old flat-columns migration (see `RunCycle` below); a rejected run/stop request simply leaves the replay's running status wherever it already was, which is what makes a separate `prev_running_status` snapshot unnecessary — it no longer exists.

**Archiving is a separate `is_archived` boolean, not a `running_status` value** — a `CLOSED` PTW can be archived manually (`POST /ptws/archive`, any authenticated non-guest user) or automatically. A daemon thread (`server/routes/ptws.py` — `_auto_archive_closed_ptws`) sweeps `globalData.allPTWs` every `_AUTO_ARCHIVE_CHECK_INTERVAL` (1 hour) and archives any `CLOSED` PTW whose last `RunCycle.stop_ia_timestamp` is `_AUTO_ARCHIVE_AFTER_DAYS` (7 days) or older. Both paths call the same `PtwsDb.archivePTWs()` (`UPDATE ptws SET is_archived = TRUE`) and broadcast the same `ptw_archived` SSE event with `"by"` set to the acting user (manual) or `"system"` (automatic). `running_status` keeps showing the real last state (`CLOSED`) forever, even once archived — `is_archived` is checked independently wherever code needs to know that (e.g. `PtwsDb.getAllPTWs()`/`getArchivedPTWs()` filter on it, not on `running_status`).

**`RunCycle` — full audit trail for the running cycle** (`PTW.RunCycle`, `client`/`server` `models/PTW.py`, kept in sync): `PTW.run_cycles` is an ordered list of `RunCycle` records, one per pass through the state machine above — a fresh `RunCycle` is appended every time a PA sends a run request (including resuming from `HELD`), and its `stop_*` fields are filled in later, in place, as that same cycle progresses. Each `RunCycle` has:

- `run_pa` / `run_pa_timestamp` — who requested the run, and when.
- `run_ia` / `run_ia_action` (`Approved`/`Rejected`) / `run_ia_comment` / `run_ia_timestamp` — the IA's response to the run request.
- `stop_pa` / `stop_pa_request` (`Hold`/`Close`) / `stop_pa_comment` / `stop_pa_timestamp` — the PA's hold-or-close request, once running.
- `stop_ia` / `stop_ia_action` (`Approved`/`Rejected`) / `stop_ia_comment` / `stop_ia_timestamp` — the IA's response to that stop request.
- `held_ics` — the linked IC ids selected to remain held for this specific hold (submitted alongside the hold request; empty for a close, or if this cycle hasn't reached a stop request yet). Renamed from `keep_isolations` when PTW↔isolation linkage moved from plain tags to ICs (see [Isolation Management](#isolation-management)) — it now holds IC ids, not raw isolation tags.

A cycle is "open" (`RunCycle.isOpen()`) as long as its run wasn't rejected and its stop hasn't been approved; `PTW.currentRunCycle()` returns the last cycle if it's still open (used for `getPerforming()`/`getIssuing()` — the live PA/IA of an in-progress run — mirroring the old behavior where those fields went blank once a hold/close was accepted). `PTW.lastRunCycle()` always returns the most recent cycle regardless of whether it's still open. `PTW.operativeRunCycle()` walks backward from the end and skips any trailing cycle(s) whose run was rejected — a rejected resume-from-`HELD` attempt appends its own (otherwise-empty) cycle for the audit trail, but never actually changes running/isolation state, so reads that care about "what's actually in effect" (`getHeldICs()`, and `ReportGenerator`'s de-isolation report reading back who performed the hold/close) use `operativeRunCycle()` rather than `lastRunCycle()`, so they aren't fooled by that trailing no-op cycle into looking blank. This replaces the old flat, overwritten `performing`/`issuing`/`hold_*`/`close_*`/`keep_isolations` fields, which silently lost history on every rejection (a reject handler blanked its own fields instead of recording who rejected and when) and on every hold/close acceptance (which wiped `performing`/`issuing` rather than keeping them alongside the new stop record).

### Shifts, Run-Cycle & PTW Validity Limits

**Added 2026-08-07.** A "shift" is a fixed 12-hour window starting at `07:00` or `19:00` (`PTW.SHIFT_START_HOURS`/`SHIFT_DURATION_HOURS`, `PTW.shiftStart(dt)`/`shiftEnd(dt)`, `client`/`server` `models/PTW.py`, kept in sync like the rest of `PTW`). Two independent limits sit on top of the running-cycle state machine above — **neither one ever transitions or closes a PTW automatically**; both only drive the client-side reminder described below:

- **Per-run-cycle shift limit** — a `RunCycle` is only valid for the single shift it started running in, not a full 12 hours from whenever that was. `RunCycle.runShiftEnd()` takes `run_ia_timestamp` (when the IA actually approved the run) and returns the *end of that shift* — a run accepted at 8 AM is valid only until 7 PM, not until 8 PM. `PTW.isRunCycleShiftExpired()` is true once that time has passed while `running_status` is still `RUNNING` — the work isn't stopped; this is purely a signal that the department should be nagged to hold or close it.
- **Whole-PTW 14-shift validity** — once a PTW is fully approved, it may only be *run* for `PTW.VALIDITY_SHIFTS` (14) shifts, counted from the start of the *next* shift after the approval action that completed its chain (`PTW.fullApprovalTimestamp()`, the timestamp of `approvals[-1]`) — not from the approval moment itself (`PTW.validityExpiry()`). `PTW.isValidityExpired()` is enforced server-side as a hard gate on both `POST /ptws/run-request` and the accept branch of `POST /ptws/run` (`403`, mirroring the existing linked-IC isolation gate) — once expired, the PTW can't be run again, including resuming from `HELD` (same two endpoints). If it's already running/held when this expires, it is **not** auto-closed — `PTW.needsCloseAlarm()` (still open, i.e. not `CLOSED`, and past `isValidityExpired()`) just flags that a human must close it manually.

**Alarm — client-side only, per session, no new server state or SSE event.** `PTW.isRunCycleShiftExpired()`/`needsCloseAlarm()` are computed live from data the client already has synced — there is no server sweep for this. `MainWindow._checkPtwAlarms()` polls every `_PTW_ALARM_CHECK_INTERVAL_MS` (1 minute), but only acts for a `USER`-role viewer (the Performing Authority side — the only role that can hold/close a permit), scoped to PTWs in that viewer's own department (`ptw.department` matched case-insensitively against `loggedUser.getDepartment()`).

Both conditions are independent and can hold for the same PTW at once — `_showPtwAlarms()` opens a single `DialogPtwAlarms` (`client/dialogs/DialogPtwAlarms.py`) with **two separate, individually collapsible sections**, never a single flat popup:

- **Exceeded 14-shift validity** (`needsCloseAlarm()`) — each row (`PTW #{id} — {description}`) has **View** and **Close** buttons, plus a **Close All** bulk button that requests closing every not-yet-actioned row in the section after one confirmation (rather than one confirmation per PTW).
- **Run cycle shift ended** (`isRunCycleShiftExpired()`) — each row has **View**, **Hold**, and **Close** buttons.

Each section's header (`_collapsibleSection`) is a single row: a checkable `QToolButton` (chevron-down/chevron-right icon) that shows/hides that section's rows, plus — for the validity section only — **Close All** pinned to the right of it via an optional `headerExtra` widget. Putting `headerExtra` in the header row itself (not inside the collapsible `content`) keeps it reachable even while that section's rows are collapsed. Both sections start expanded, since surfacing everything is the whole point of the dialog; collapsing one is purely a decluttering aid while working through a long list, it never affects which PTWs are actually alarmed.

**Close/Hold** call straight into the same `MainWindow.requestToHldPTW`/`requestToClsPTW` the table context menus already use (both now take an optional `callback` — defaulting to the usual `_on_request_done_generic` — so the dialog can hook its own row-update instead of a generic one); nothing here duplicates that request logic or takes action on a PTW without an explicit click; "Close All" is the one exception, sending the requests directly (bypassing the per-row confirm) after its own single bulk confirmation. **View**, however, does *not* delegate to `MainWindow.viewPTW` — it builds its own `DialogPTW` directly, showing the busy overlay on `DialogPtwAlarms`'s own `RefreshOverlay` (parented to the alarm dialog itself) rather than `MainWindow`'s, since `MainWindow.viewPTW`'s overlay is parented to the main window and would flash on the (possibly obscured) window behind this modal dialog instead of on the dialog actually in front of the user — the same reasoning `DialogIC._viewLinkedPTW` already follows for its own linked-PTW View button. Once a row's Hold or Close request succeeds, that row's own **Hold**/**Close** buttons disable themselves in place (both together — a stop request is now pending, so a second one before the IA responds doesn't make sense) and relabel to say so, without closing the dialog, so the rest of the list stays workable; "Close All" disables itself too once every row it covers has been actioned. The dialog itself doesn't auto-refresh/re-fetch while open — it's a snapshot from when `_checkPtwAlarms()` last fired.

**Closing a PTW that was never actually run (or whose only run was rejected) reuses the exact same PA-requests-close → IA-confirms flow as a normal close — not a separate mechanism.** `needsCloseAlarm()` fires for `NOT_RUNNING` PTWs too (any status but `CLOSED`), which includes both a PTW that never had a run requested at all (`run_cycles` empty) and one whose only run attempt was rejected (`run_cycles` non-empty but its last entry isn't `isOpen()`) — in both cases there's no open cycle for the usual patch-in-place to attach to. `PtwsDb.requestToClsPTW` (`server/db/ptwDb.py`) now checks this first (`_hasOpenRunCycle`): if there *is* an open cycle, it patches it exactly as before; otherwise it **appends** a brand-new `RunCycle` carrying only the `stop_pa`/`stop_pa_request`/`stop_pa_timestamp` fields (no `run_pa`/`run_ia` at all — it never ran) — mirroring how resuming from `HELD` already appends a fresh cycle rather than patching a dead one. `__updateRunningStatus()` resolves that straight to `WAITING_CLS_CONFIRM`, so the PTW lands in `IssuingMainWindow`'s existing **Waiting Close Confirmation** tab and goes through ordinary `clsAcceptPTW`/`clsRejectPTW` — no new tab, dialog, or IA-facing code needed. One replay-logic bug this surfaced and fixed: a **rejected** close used to unconditionally revert `running_status` to `RUNNING` (correct for a cycle that really had been running) — for this never-run cycle that fabricated a `RUNNING` state with no PA/timestamp behind it. `__updateRunningStatus()` now checks `run_ia_action == APPROVED` (`wasRunning`) before choosing `RUNNING` vs. `NOT_RUNNING` on a rejected close, in both `client`/`server` `models/PTW.py` — verified directly against the model (forcing each of: pending / rejected / accepted on a never-run cycle, and rejected / accepted on a genuinely-running cycle as a regression check) rather than by inspection alone. `POST /ptws/close-request` (`server/routes/ptws.py`) additionally 403s up front unless `approval_status == APPROVED` — this path must stay reachable only for an approved-but-unused PTW, never one still under review/returned (those have their own delete/edit-resubmit flows).

`PtwsDb._patchLastRunCycle` still independently guards every *other* caller (`requestToHldPTW`/`runAcceptPTW`/`runRejectPTW`/`clsAcceptPTW`/`clsRejectPTW`/`hldAcceptPTW`/`hldRejectPTW`) against patching a missing-or-closed cycle, raising a clean `ValueError` instead of corrupting `run_cycles` — this was a real, previously-latent bug (not just theoretical): letting that `UPDATE` through on an empty array reads `run_cycles[cardinality(run_cycles)]` out-of-bounds as SQL `NULL`, and `NULL || jsonb` is itself `NULL` (verified empirically against a scratch database), so the assignment left `run_cycles` holding a single JSON `null` element — crashing every later read of that PTW, including the server's periodic full resync and every fresh login's initial load, silently going stale for *all* PTWs (not just the corrupted one) until the bad row was manually cleaned up. `DialogPtwAlarms`'s **Close** button (both per-row and **Close All**) no longer needs to special-case this — it's unconditionally wired now that the server handles both the open-cycle and no-open-cycle cases correctly.

Dismissing the dialog (its only bottom button is `OK`) snoozes the *next* popup for `_PTW_ALARM_REPEAT_MINUTES` (5); it doesn't clear the underlying condition, so anything still unresolved simply reappears, recomputed fresh, at the next repeat. The tray notification (`_trayIcon.showMessage()`, same pattern already used for SSE notifications) fires alongside every popup, just as a plain count.

**Report generation.** `PTW.runningStatusDisplay()` is what every report now prints instead of the raw `running_status` (`ReportGenerator.ptwReport()`'s basic-info table, the multi-PTW Excel export, and the PDF's embedded QR payload) — for every status except `RUNNING` it's unchanged (the plain status/approval string), but a `RUNNING` PTW prints as `Running <from> - <until>`, where `<from>` is the time-of-day (not date) of the current run cycle's `run_ia_timestamp` and `<until>` is that same shift's end.

---

## Isolation Management

**Architecture as of 2026-07-25: plain isolation tags are purely declarative; all runtime isolation state lives on IC.** Before this date, a separate `isolations` DB table + `Isolation.linkPTW`/`holdPTW`/`unlinkPTW` tracked which PTWs currently held which physical tag, mirrored by a global "Isolations" browse tab in the client. That entire subsystem has been removed. It is not documented below except where noted as history — don't resurrect it from an older version of this file.

### Isolation (declarative only)

`Isolation` (`client`/`server` `models/Isolation.py`) is now a minimal, stateless record: `type` (Mechanical/Electrical/Self/Protective System/Other), `tag`, `description` — nothing else. It exists solely to declare, on a PTW request, which isolations that PTW is expected to need (`PTW.isolations: list[Isolation]`, edited via the `TablePTWIsolations` widget embedded in `DialogPTW`'s Isolation tab). It carries no linkage/runtime state and is never looked up in a global registry — there is no `GET /isolations`, no `globalData.isolations`, no `isolations` DB table.

The system pre-loads a library of known isolation points (tags like `XV-7227A`, `LV-1409E`, etc.) covering mechanical, electrical, protective, and self-isolations across all plant areas, offered when adding an isolation to a PTW's declarative list.

**Before a PTW can run, it must be linked to an actual `IC`** (see below) — that's where physical isolation execution, approval, and linkage now live. See [Running Cycle](#2-running-cycle) / the run-accept gate below for the enforcement point.

### IC (Isolation Certificate)

A formal, independently-approved isolation-request document — class `IC` (`client`/`server` `models/Isolation.py`, renamed from `IsolationCertificate` 2026-07-25; DB table `ics`, renamed from `isolation_certificates` — see [Database Schema](#database-schema)). An IC's `items` list references individual isolation tags/points; the IC itself is the approval document wrapping them (type, department, location, equipment, reason, long-term flag), and — since 2026-07-25 — the sole place PTW↔isolation linkage state lives.

**Fields:** `type` (Mechanical/Electrical/Self/Other — `Protective System` was removed as a `type` value 2026-07-31, replaced by the `is_psic` flag below; `type` no longer matches declarative `Isolation.Types`, which still has `Protective System` as a tag-classification value, a separate and unrelated concept), `requestor_department`/`execution_department` (split from a single `department` field 2026-07-26 — see below), `requestor`/`requestor_timestamp` (who submitted the IC form, mirrors PTW's own `requestor`), `approvals` (list of `Approval`, see below), `location`, `equipment`, `reason`, `items` (list of `IC.IsolationItem`: tag, description, state `OPEN`/`CLOSE`, `lock_num`, `lock_box_num`), `isolate_asap` (checkbox — see below), `long_term`/`long_term_reason`, `is_psic`/`psic_reasons`/`psic_moc_number`/`psic_system_description`/`psic_isolation_method`/`psic_control_measures` (PSIC fields, see below), `linked_ptws`/`held_by` (the IC's own runtime linkage lists — see [PTW↔IC Linkage](#ptwic-linkage) below), and four groups of requestor/issuing/isolator username+timestamp fields — `isolate_*` (fully implemented), `sanction_*` (sanction for test), `reisolate_*`, `deisolate_*` (these three groups still deferred, see below). `isolate_issuing_action` (`'Approved'`/`'Returned'`/`''`) records the IA's decision on an isolate request.

**PSIC (Protective System IC), added 2026-07-31, ownership moved 2026-08-14** — any IC, regardless of its `type`, can be flagged `is_psic: bool`, meaning it isolates something belonging to a protective system rather than being classified by `type` as `Protective System` (that type value is gone — see above). Nobody sets any of this at creation any more: `addICRequest` unconditionally force-blanks `is_psic`/every `psic_*` field regardless of what the payload sends (`DialogIC`'s PSIC tab is fully hidden behind an info note in new-mode for the same reason). Instead:

- **Issuing flags it.** `MainWindow.acceptIC()` offers Issuing (and only Issuing, and only while `is_psic` isn't already set) a "Mark as PSIC" checkbox alongside the normal approve confirm; ticking it sends `mark_psic: true` to `POST /ics/approvals`, which flips `is_psic` to `True` as a follow-up write right after recording Issuing's own approval.
- **Coordinator's approval of their own stage is what defines its terms.** Once `is_psic` is set, `IC.requiredApprovers()` inserts a `Coordinator` stage right after Issuing's (before PDH/PGM/SOD/DFGM — see the approval chain below); accepting that stage (`MainWindow.acceptIC`'s Coordinator branch) opens `DialogDefinePsicTerms` instead of a plain confirm, and its own OK button *is* the confirmation. There's no "define terms" action separate from approving — the terms are submitted together with the approval itself (`psic_terms` in the same `POST /ics/approvals` call), validated server-side *before* anything is recorded, so an incomplete submission never gets approved.
  - `psic_reasons: list[str]` — why the isolation is protective-system-relevant; at least one is required. The option list (`PSIC_REASONS` in `client/models/Isolation.py`: ESD, Fire Protection, Fire Detection, Gas Detection, Protection System, Other) is defined **client-side only** — the server just checks non-empty, no fixed enum of its own.
  - `psic_moc_number: str` — optional; may be left blank.
  - `psic_system_description`/`psic_isolation_method`/`psic_control_measures: str` — description of the system being isolated, the method of isolation, and the control measure/mitigation, respectively. All three are required whenever `is_psic` is set; stored as `VARCHAR(300) NOT NULL` columns the same way `long_term_reason` is — always written as an empty string rather than left unset when not applicable.
  - **Autofill from tag** — `DialogDefinePsicTerms` has a tag combo (populated from the IC's own `items`) plus an "Autofill from Tag" button that fills `psic_reasons` (checking/unchecking the reason grid to match) and the three text fields above from `PSIC_TAG_SAMPLES` (also relocated to `client/models/Isolation.py`, client-only), a small client-side dict keyed by tag. Placeholder/sample data standing in for a real per-tag data source, which doesn't exist yet.
- No new status and no separate `psic_terms_*` audit columns exist for any of this — Coordinator's own `Approval` entry (username + timestamp, already on the `approvals` array) *is* the record of who defined the terms and when, exactly like every other stage. Until Coordinator acts, the IC just sits at whatever the ordinary approval-chain machinery already shows for a pending stage — a gray "Pending Coordinator" entry in `DialogIC`'s Approval Timeline, and the IC sitting in Coordinator's own **Under Review** tab (see "Roles wired" below) — no bespoke UI needed.
- `requiredApprovers()` still branches on `is_psic` rather than `type` — see the approval chain below.
- UI: a dedicated **PSIC** tab in `DialogIC`, positioned after **P&ID / Wiring** — view-only content in readonly mode (any role); in new-mode (User creating an IC) it shows only an info note, since none of this is settable there any more.

**`requestor_department` vs `execution_department`** — `requestor_department` is stamped server-side from the creator (`user.getDepartment()`, never trusted from the payload), same as before the split. `execution_department` — the department actually responsible for carrying out the physical isolate/de-isolate work — must always be explicitly supplied by the client; `POST /ics` 400s if it's missing. For a `Self`-type IC, `execution_department` is required to equal `requestor_department` — enforced twice: client-side, `DialogIC._certTypeChanged()` locks (disables) the execution-department combo and syncs its value the moment `Self` is selected; server-side, `addICRequest` independently 400s if a `Self`-type submission's `execution_department` doesn't match `requestor_department`, so the rule holds even against a client that skips the dialog's lock. **Routing**: once an IC reaches `Pending` or `Closing` (see `getStatus()` below), `MainWindow.refreshICsGUI()` only shows it to an `Isolator` whose own department matches `execution_department` — an isolator elsewhere doesn't see it queued at all, in either tab. The two execute endpoints (`/ics/isolate-execute`, `/ics/deisolate-execute`) independently re-check the same department match server-side (403 otherwise) — routing alone is a UI convenience, not a security boundary, so both sides enforce it.

**`isolate_requestor`/`isolate_requestor_timestamp` are *not* the IC creator** — that's the top-level `requestor`/`requestor_timestamp` above. `isolate_requestor` instead records whoever requests that the (already-approved) isolation actually be carried out — a distinct, later action that may be performed by someone other than the original requestor. That's also why `isolate_requestor_timestamp` (and its `sanction_*`/`reisolate_*`/`deisolate_*` siblings) has no `datetime.now()` fallback default the way `requestor_timestamp` does — it must stay unset until that action genuinely happens, not read as "now" the moment a fresh object is instantiated. `isolate_asap` is a requestor-set checkbox meaning "trigger that isolate-request automatically the moment the IC is fully approved" — implemented: `POST /ics/approvals` checks it right after persisting the approval that completes the chain, and if set, auto-stamps `isolate_requestor`/`isolate_requestor_timestamp` itself (skipping the manual "Request Isolate" click below) — it does **not** skip IA confirmation or isolator execution, it just skips the person having to click the button.

**Approval chain — implemented, mirrors `PTW`'s `Approval`/`Approver`/`requiredApprovers()`/`pendingApprovers()` pattern exactly** (`IC.Approval`/`Approver`/`ApprovalActions`, `requiredApprovers()`/`_stageSatisfied()`/`_pendingStageIndex()`/`pendingApprovers()`/`getApprovalStatus()`, all in `client`/`server` `models/Isolation.py`, kept in sync). `requiredApprovers()` returns `[[Issuing]]` for a normal IC, or `[[Issuing], [Coordinator], [PDH], [PGM], [SOD], [DFGM]]` for a PSIC (`is_psic == True`, see [Isolation Management](#isolation-management) above — this branch was on `type == Protective System` before 2026-07-31, and gained the `Coordinator` stage 2026-08-14, when PSIC ownership moved from the requestor to Issuing-flags/Coordinator-defines). **Note this manager-approval requirement lives only here, on the IC's own chain** — as of 2026-07-25, a PTW's own `requiredApprovers()` no longer adds PDH/PGM/SOD/DFGM for a protective isolation (see [Approval Cycle](#1-approval-cycle)); linking a PSIC to a PTW is now the only place that approval is collected, rather than being required twice. `getApprovalStatus(role=None)` gives the overall chain status (`Requested`/`Returned`/`Approved`); `getApprovalStatus(role, department)` gives one viewer's status: the action they already took, `Requested` if it's their turn right now, or `None` if they're not an approver at all. `POST /ics/approvals` (mirrors `/ptws/approvals`) appends an `Approval` and re-authorizes on every call — the caller's `getApprovalStatus(role, department)` must currently be `Requested`, otherwise 403. Like PTW, there is no permanent "Rejected" outcome — `ApprovalActions`/`Status` are `Approved`/`Returned` only (no `Rejected`), exactly matching `PTW.ApprovalActions`/`ApprovalStatus`. Approved or returned-for-edits via `MainWindow.acceptIC`/`requestEditsIC` (menu options "Accept"/"Request Edits", mirroring PTW's own `optionAcceptPTW`/`optionRequestEditsPTW`) → `ClientRequests.updateApprovalIC` → server; broadcasts an unrestricted (no role filter) `ic_approval` SSE event, same as PTW's `ptw_approval`, so whichever role is up next gets notified regardless of which one that is.

**The isolate cycle (request → IA confirm → isolator execute) is fully implemented**, three roles in sequence:
1. **Request** — a `User`, from the **Approved** tab, clicks **Request Isolate** (`optionRequestIsolateIC`) → `MainWindow.requestIsolateIC` → `POST /ics/isolate-request` (guarded to `getStatus() == Approved`). Stamps `isolate_requestor`/`isolate_requestor_timestamp`, and — defensively — resets `isolate_issuing`/`isolate_issuing_timestamp`/`isolate_issuing_action` to blank, so a re-request after a prior Return can't leave a stale decision lying around to mask the fresh request.
2. **IA confirm** — `Issuing`, from the **Isolate Confirming** tab, clicks **Confirm Isolate** or **Return Isolate Request** (`optionConfirmIsolateIC`/`optionReturnIsolateIC`) → `MainWindow.confirmIsolateIC`/`returnIsolateIC` → `ClientRequests.confirmIsolateIC(..., response: bool)` → `POST /ics/isolate-confirm` (guarded to `getStatus() == Isolate Confirming`, role must be `ISSUING`). Stamps `isolate_issuing`/`isolate_issuing_timestamp`/`isolate_issuing_action` (`Approved` or `Returned`). No comment field — accept/return is a plain decision, unlike the main approval chain's `Approval.comment`.
3. **Isolator execute** — `Isolator`, from the **Pending** tab, clicks **Complete Isolation** (`optionExecuteIsolateIC`) → `MainWindow.executeIsolateIC`. If the IC has items, this opens `DialogCompleteIsolation` first — a table of all items (Tag/Description/State read-only, **Lock #**/**Lock Box #** editable, both optional/blank-is-fine) — otherwise it's a plain Yes/No confirm. → `POST /ics/isolate-execute` (guarded to `getStatus() == Pending`, role must be `ISOLATOR`), with an optional `items` payload. The server merges `lock_num`/`lock_box_num` into `ic.items` **by tag** (`tag`/`description`/`state` stay server-authoritative — an unrecognized tag in the payload is silently dropped, never inserted as a new item). Stamps `isolate_isolator`/`isolate_isolator_timestamp` → IC becomes `Active`.

A **Return** at step 2 does **not** clear `isolate_requestor` — it's kept as a permanent record of who originally asked, alongside `isolate_issuing`/`action='Returned'` recording who declined it and when. `getStatus()` treats a `Returned` isolate confirmation as reverting the IC to `Approved` (ready for a fresh Request Isolate), which is why step 1 above resets the stale `isolate_issuing*` fields on every new request — otherwise the leftover `Returned` decision would keep masking the new request's status.

**The de-isolate cycle (request → IA confirm → isolator execute) is implemented too, an exact mirror of the isolate cycle above**, three roles in sequence, but starting from `Active` instead of `Approved`:
1. **Request** — a `User`, from the **Active** tab, clicks **Request De-isolate** (`optionRequestDeisolateIC`) → `POST /ics/deisolate-request` (guarded to `getStatus() == Active`). Stamps `deisolate_requestor`/`deisolate_requestor_timestamp`, and resets `deisolate_issuing`/`deisolate_issuing_timestamp`/`deisolate_issuing_action` — same defensive reset as isolate-request, for the same reason (a re-request after a prior Return must not leave a stale decision behind).
2. **IA confirm** — `Issuing`, from the **Deisolate Confirming** tab, clicks **Confirm De-isolate** or **Return De-isolate Request** (`optionConfirmDeisolateIC`/`optionReturnDeisolateIC`) → `POST /ics/deisolate-confirm` (guarded to `getStatus() == Deisolate Confirming`, role must be `ISSUING`). Stamps `deisolate_issuing`/`deisolate_issuing_timestamp`/`deisolate_issuing_action`.
3. **Isolator execute** — `Isolator`, from the **Closing** tab, clicks **Complete De-isolation** (`optionExecuteDeisolateIC`) → `POST /ics/deisolate-execute` (guarded to `getStatus() == Closing`, role must be `ISOLATOR`). Stamps `deisolate_isolator`/`deisolate_isolator_timestamp` → IC becomes `Closed` — this is the *only* path to `Closed`. Unlike `isolate-execute`, this endpoint doesn't take an `items` payload — no lock-clearing UI yet, just the plain confirm.

**`getStatus()`** layers both cycles on top of the approval chain: `deisolate_isolator` set → `Closed`; `sanction_isolator` set and not yet reversed by `reisolate_isolator` → `Sanctioned` (both `sanction_*`/`reisolate_*` cycles still deferred, so unreachable today); else if `isolate_isolator` or `reisolate_isolator` is set (physically isolated) — nested inside that: if `deisolate_requestor` is set, `deisolate_issuing_action == Approved` → `Closing` (awaiting isolator), `deisolate_issuing_action == Returned` → falls through to plain `Active`, otherwise → `Deisolate Confirming` (awaiting IA); with no `deisolate_requestor`, plain `Active`; else if `isolate_requestor` is set: `isolate_issuing_action == Approved` → `Pending` (awaiting isolator), `isolate_issuing_action == Returned` → falls through to `getApprovalStatus()` (i.e. `Approved`, ready to re-request), otherwise → `Isolate Confirming` (awaiting IA); with no `isolate_requestor` at all, falls through to `getApprovalStatus()` (`Requested`/`Returned`/`Approved`). Row/type coloring (`backgroundColor()`/`foregroundColor()`/`backgroundColorForType()`) mirrors `PTW`'s pattern: Mechanical=gray, Electrical=yellow, Self=green, Other=neutral gray — **unless `is_psic` is set, in which case it overrides `type` and renders red** (`__PSIC_BACKGROUND_COLOR`/`__PSIC_FOREGROUND_COLOR` in `client/models/Isolation.py`, the same red the old `Protective System` type used) — applies everywhere `backgroundColor()`/`foregroundColor()`/`backgroundColorForType()`/`foregroundColorForType()` are read: `TableICs` rows and `DialogIC`'s tab bar (`_certTypeChanged()`, which also reacts live to the PSIC checkbox toggling, not just the type combo).

**Tab routing is per-viewer, like PTW's Requested/Under Review split** (`MainWindow.refreshICsGUI()`), one tab per `Status` value: **Requested** → **Under Review** (per-viewer, whoever's approval stage is current) → **Approved** → **Isolate Confirming** → **Pending** → **Active** → **Deisolate Confirming** → **Closing** → **Sanctioned** → **Closed**. A viewer whose approval stage already passed (e.g. Issuing, once a PSIC has moved on to PDH) falls back to **Requested** as a tracking view — `IssuingMainWindow` doesn't have a Requested button today, so that specific tracking case is a known, accepted gap (rare: only affects multi-stage PSICs after Issuing's own stage is done).

Per-row menu visibility uses a `TablePTWs.MenuOption(..., visibleFor=lambda ic: ...)` predicate (default `None` = always visible), checked in `TableICs.showContextMenu` only — `TablePTWs`'s own context menu is untouched, so this doesn't affect PTW menus. Used defensively on both cycles' actions (e.g. `optionConfirmDeisolateIC.visibleFor` checks `getStatus() == Deisolate Confirming`) even though tab routing alone already guarantees the right rows end up in the right tab — belt-and-suspenders against a stale row lingering between an action and the next refresh.

**Roles wired:**
- `UserMainWindow` — Requested / Approved (+ Request Isolate) / Isolate Confirming (view-only) / Pending / Active (+ Request De-isolate) / Deisolate Confirming (view-only) / Closing (view-only) / Sanctioned / Closed tabs; FAB on the Requested tab creates a new IC (`TableICs.addNewICDialog()`), submitting via `POST /ics`.
- `IssuingMainWindow` — Under Review (with Accept/Request Edits) / Approved (view-only) / Isolate Confirming (+ Confirm Isolate/Return Isolate Request) / Pending (view-only) / Active (view-only) / Deisolate Confirming (+ Confirm De-isolate/Return De-isolate Request) / Closing (view-only) / Sanctioned / Closed tabs.
- `ManagerMainWindow` (PDH/PGM/SOD/DFGM) — Under Review tab only (with Accept/Request Edits) — Managers are only ever pulled into a PSIC's chain, after Issuing.
- `IsolatorMainWindow` — Pending (+ Complete Isolation) / Active (view-only) / Closing (+ Complete De-isolation) / Sanctioned tabs only, no PTW tabs, FAB permanently hidden. No Approved, Isolate Confirming, or Deisolate Confirming tab — nothing for the isolator to do at any of those stages.
- `CoordinatorMainWindow` *(added 2026-07-26)* — the same 9 IC tabs as `IssuingMainWindow` (Under Review/Approved/Isolate Confirming/Pending/Active/Deisolate Confirming/Closing/Sanctioned/Closed, no Requested tab, same reasoning), view-only plus **Link to PTW** — none of Issuing's Confirm/Return/Execute actions — **except Under Review**, which since 2026-08-14 also gets **Accept**/**Request Edits**: Coordinator is now a real required approver on a PSIC's chain (see above), so `myTurn` is `True` for them the moment Issuing's own stage is satisfied and `is_psic` is set, routing it there exactly like it would for any other role's pending stage — no bespoke tab or routing change was needed, only wiring the two options onto a tab that was already present. A non-PSIC IC never adds a Coordinator stage, so this tab still shows nothing for those, same as before Coordinator had any action at all here.
- Safety/Admin/Guest are untouched.

**`DialogIC` is tabbed, mirroring `DialogPTW`'s pattern** — both now subclass `dialogs/TabbedDialog.py` (added 2026-08-06), which owns the shared mechanics: the tab bar (`addTab()` registers a page + its `TabButton`), the `QStackedWidget`, the Back/Next/Finish/Cancel button row (`bottomButtonsLayout()` — Back/Next page the stack, Finish/Cancel accept/reject the dialog), and `setTabBarColor(bgColor)`, which recolors the bar and automatically picks a readable black/white text/icon color for both the selected and unselected `TabButton`s via `bestForegroundColor()` (perceived luminance, `widgets/UiUtils.py`) rather than each dialog supplying its own foreground color. `DialogIC._certTypeChanged()` (also reacting live to the PSIC checkbox toggling, not just the type combo) and `DialogPTW.ptwTypeChanged()` each just compute their own background color from their model (`IC`/`PTW` `backgroundColorForType()`) and call `self.setTabBarColor(color)` — same palette as the row coloring above, but no longer consulting `foregroundColorForType()` for the tab bar (that model-level method is still used for row/report coloring elsewhere, see `getStatus()` above).
- **Basic Info** — IC #, Type, Requestor Department, Execution Department, Requestor, Request Time, Location, Equipment, Reason, Isolate ASAP, Long Term (+ reason).
- **Isolation Items** — the embedded `TableIsolationItems` list. Lock #/Lock Box # are always read-only here regardless of mode, never editable by the requestor — they're filled in by the isolator instead, via a separate dialog (`DialogCompleteIsolation`) shown when completing isolation (see below), not inline in this tab. Double-clicking a row opens `DialogIsolationItem` in edit mode (if the IC dialog itself is editable) or view-only (if not).
- **P&ID / Wiring** — the embedded `WidgetPidWiring` — see [P&ID / Wiring Highlighting](#pid--wiring-highlighting) below.
- **History** — only added in readonly mode (a brand-new IC has no approvals yet), a two-pane `QHBoxLayout` exactly mirroring `DialogPTW`'s History tab: left pane is the **Approval Timeline** (`_buildApprovalTimelinePane`, reusing `Timeline`/`TimelineEntry` — green/orange dots for each `Approval`, gray "Pending" dots for `pendingApprovers()`), right pane is the **Isolation Timeline** (`_buildIsolationTimelinePane`/`_isolationStageEntry`). `Isolate` and `De-isolate` are fixed lifecycle stages — their Requested/Confirmed/Carried-Out rows always render, gray "— Pending" until each field is set, green once it is. `Sanction` (for test) and `Re-isolate` are optional excursions — each of their three rows only appears once its own field is set, no gray placeholder. The isolate group's middle ("Confirmed") row also reflects `isolate_issuing_action`: green "Isolate Approved", orange "Isolate Returned", or green "Isolate Confirmed" as a fallback if set with no recorded action — the other three groups have no action field, so their Confirmed rows are always green once set.
- **PTW Linkage** — also readonly-only, a plain `QVBoxLayout` (not a `QFormLayout`) titled **"Linked PTWs"**: one row per linked PTW (`ic.linked_ptws` only — `held_by` isn't currently surfaced here, since nothing populates it yet) via `_addPTWLinkRows`/`_ptwLinkRow`, each row a read-only `QLineEdit` reading `"PTW #{id} — {running_status}"` (looks the PTW up in `globalData.allPTWs`/`archivedPTWs`; falls back to just `"PTW #{id}"` if not found) plus a **View** button (`_viewLinkedPTW`, opens a readonly `DialogPTW`) and, for any non-Guest viewer, an **Unlink** button; an empty list shows a plain "No linked PTWs." label instead, no rows. Below the list, a **Link to PTW** button (`_linkNewPTW`, `QInputDialog.getText` for the PTW #) — visible whenever `not ic.isWindingDown()` (the same predicate `optionLinkPTWToIC.visibleFor` already uses) — calls the same `ClientRequests.linkPTWToIC` as the PTW-side button below, so either dialog can initiate the same link (see [PTW↔IC Linkage](#ptwic-linkage)).

### PTW↔IC Linkage

**Fully implemented as of 2026-07-25: link and unlink, both directions, symmetric on both sides.** Either a PTW or an IC can initiate the link/unlink; the server keeps `IC.linked_ptws`/`held_by` and `PTW.linked_ics` in sync in the same request.

**Role-restricted to `USER`/`ISSUING`/`COORDINATOR` only (tightened 2026-07-26 — previously any non-Guest role could reach these)**, enforced on both sides:
- Client: the Unlink button (both dialogs) and the Link New IC / Link to PTW buttons check `self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR)` before showing at all (an Isolator, PDH, Safety, etc. viewing either dialog sees no linking controls whatsoever). `CoordinatorMainWindow`'s `tabApprovedPTWs` gained `optionLinkICToPTW` in its menu to match — it previously had no menu-based linking at all.
- Server: `POST /ics/link-ptw` and `POST /ics/unlink-ptw` independently re-check the same three-role allowlist (403 otherwise) — the old check only rejected `GUEST`, so a non-Guest role outside the three could still hit the endpoint directly even with no UI path to it.

- **Link from the IC side** — two access points to the same action: the **Link to PTW** menu option (`optionLinkPTWToIC`, `UserMainWindow` and `IssuingMainWindow` only, on every non-winding-down IC tab) *and* a **Link to PTW** button directly inside `DialogIC`'s "PTW Linkage" tab (`_linkNewPTW`, visible whenever `not ic.isWindingDown()` **and** the role check above). Either pops a plain `QInputDialog.getText` asking for a PTW #, then → `MainWindow.linkPTWToIC` / `DialogIC._linkNewPTW` → `ClientRequests.linkPTWToIC` → `POST /ics/link-ptw`.
- **Link from the PTW side** — likewise two access points: the **Link to IC** menu option (`optionLinkICToPTW`, `UserMainWindow`/`IssuingMainWindow`/`CoordinatorMainWindow`, on the Approved PTWs tab) *and* a **Link New IC** button directly inside `DialogPTW`'s "IC Linkage" tab (`_linkNewIC`, visible whenever `ptw.canLinkIC()` **and** the role check above). Both prompt for an IC # → `MainWindow.linkICToPTW` / `DialogPTW._linkNewIC` → the same `POST /ics/link-ptw` endpoint (it just takes an `ic-id`/`ptw-id` pair regardless of which side supplies which, so either side can initiate the link).
- **Unlink from either side** — an **Unlink** button on the IC's "PTW Linkage" tab (`DialogIC._unlinkPTW`) and on the PTW's "IC Linkage" tab (`DialogPTW._unlinkIC`), both → `POST /ics/unlink-ptw`. Confirms via Yes/No, then closes the (now-stale) read-only dialog on success — the caller reopens it to see the refreshed linkage rather than the UI trying to patch rows in place.

Both tabs were redesigned 2026-07-26 from a `QFormLayout` (grouped by IC type / split into "Linked PTW"+"Held By" fields) to a plain `QVBoxLayout`: a bold title (**"Linked ICs"** / **"Linked PTWs"**), a flat list of link rows — each row's field text is `"IC #{id} — {status}"` / `"PTW #{id} — {running_status}"` (falls back to just the bare `#{id}` if the linked object can't be found in `globalData`) — or a plain "No linked ICs/PTWs." label if empty, then the Link button described above.

Each row on the PTW side ("Linked ICs") also has a **Request Isolate** button (`_requestIsolateIC`, `UserRoles.USER` only — narrower than even the link/unlink allowlist above, matching `optionRequestIsolateIC`'s own `UserMainWindow`-only scope in `MainWindow.py`; same confirm-dialog wording and `ClientRequests.requestIsolateIC` call as `MainWindow.requestIsolateIC`) — lets the PA request isolation on a linked IC without leaving the PTW dialog. Unlike the Link/View/Unlink buttons, this one stays **visible but disabled** rather than hidden: `setEnabled(bool(ic) and ic.getStatus() == IC.Status.APPROVED)`, so a row for an IC that isn't found or isn't yet `Approved` shows the button grayed out instead of missing.

Two gates on linking, both expressed on the model so they're checked identically whether called from a menu predicate, a dialog button, or the endpoint:
- `IC.isWindingDown()` — `True` once `Sanctioned`/`Deisolate Confirming`/`Closing`/`Closed`, i.e. the IC is past the point where a new PTW should be attached. Drives both `optionLinkPTWToIC.visibleFor` and `DialogIC`'s **Link to PTW** button directly (neither has a specific PTW in hand yet, so this is the IC-only half of the check).
- `PTW.canLinkIC()` — the PTW-only half, symmetric to the above: `approval_status == Approved` and `running_status == Not Running` (the window between a PTW being approved and it actually starting work). Drives both `optionLinkICToPTW.visibleFor` and `DialogPTW`'s **Link New IC** button.
- `IC.canLinkPTW(ptw)` — the full check once an actual PTW is known: `isWindingDown()` **and** the target PTW's own `canLinkIC()`. Not linkable while the PTW is still under review/returned, nor once run/hold/close has been requested or done. Used server-side only, after `ptwDB.getPTWById(ptwId)` — by design, neither client-side button/menu predicate can check this half up front, since they only ever have one side of the pair (the IC or the PTW, never both) until the id is typed in.

`canLinkPTW` needs `PTW`'s `ApprovalStatus`/`RunningStatus` enums, imported lazily inside the method body rather than at module scope — `models/PTW.py` already imports the plain `Isolation` class at module scope, so a top-level `models/Isolation.py → models/PTW.py` import would be a real circular import.

`IC.linkPTW(ptwId)`: un-holds the PTW if it was held, appends to `linked_ptws`. `IC.unlinkPTW(ptwId)`: removes from both `linked_ptws` and `held_by`, no other side effects. There is no `holdPTW` on `IC` (unlike the old, now-removed `Isolation.holdPTW`) — a PTW going `RUNNING`→`HELD`→`CLOSED` no longer automatically moves its linked ICs between `linked_ptws`/`held_by`, or unlinks them; that coupling was removed along with the old tag-tracking subsystem. Unlinking an IC from a PTW is now a purely manual, deliberate user action (the Unlink button above), never an automatic side effect of the PTW's own state transitions.

**Run safety gate (new 2026-07-25, extended to run-request 2026-07-26):** both `POST /ptws/run-request` (PA requesting to run) and `POST /ptws/run`'s accept branch (IA accepting that request) independently require every id in `ptw.linked_ics` to resolve to an `IC` whose `getStatus() == IC.Status.ACTIVE` — otherwise rejected `403` with the offending IC ids listed in the error (`"Cannot request run: ..."` / `"Cannot run: ..."`). `SANCTIONED`/`DEISOLATE_CONFIRMING`/`CLOSING` and all pre-isolation statuses do **not** count as isolated for this check; only `ACTIVE` does. Checking it at request-time too (not just accept-time) catches the problem earlier — a PA can no longer even ask to run a PTW with an unfinished isolation, rather than finding out only when IA tries to accept. This replaces the old automatic tag-linking side effect that used to run here (see the removed-subsystem note at the top of this section) — it's now a pure validation, not a state mutation. Hold-accept and close-accept no longer touch isolation state at all.

**`TableICs` columns**: IC# (id), Status, Type, L.T. (Long Term), Requestor, Request Time, Requestor Dept., Execution Dept., Location, Equipment, Reason. The L.T. column follows `TablePTWs`' Fast Track pattern exactly — real value lives in `Qt.ItemDataRole.UserRole` (cell text is intentionally empty), a `mdi6.timer-sand` icon badge renders in a fixed-width column, and the whole row goes bold when set. (An `fa6s.infinity`/`ph.infinity`/`mdi.infinity` badge was tried first — every icon set's infinity glyph turned out to have ~0px horizontal padding, always spanning the full pixmap width, so it visually clipped inside the circular badge regardless of size.)

**Not implemented yet — explicitly deferred:** the entire `sanction_*` (sanction-for-test) and `reisolate_*` cycles (no trigger, no confirm, no execute — the isolate/de-isolate cycles above are the template these will eventually mirror, per-cycle: `sanctionConfirming`/`reisolateConfirming` tabs alongside `isolateConfirming`/`deisolateConfirming`). Also still deferred: clearing/editing `lock_num`/`lock_box_num` at de-isolate-execution time (the isolator physically removes the locks, but `deisolate-execute` doesn't touch `items` the way `isolate-execute` does), a dedicated "Returned" tab + edit-and-resubmit flow for a returned IC (PTW has `tabReturnedPTWs` + re-request; IC doesn't — a returned IC just falls back into the Requested tab today), and PTW reports printing linked ICs (the old "Isolations"/"De-Isolation" sections and the whole "Print De-Isolation" report feature were removed from `reports/ReportGenerator.py` 2026-07-25 since they depended on the removed tag-tracking subsystem; nothing prints isolation/IC info on a PTW report yet).

Server-side: `GET /ics` (list, department-scoped for `UserRoles.USER` only, matched against `requestor_department`), `POST /ics` (create, 400s if `execution_department` missing or, for `Self`-type, mismatched with `requestor_department`), `POST /ics/approvals` (staged approve/return), `POST /ics/isolate-request` (Approved → Isolate Confirming), `POST /ics/isolate-confirm` (Issuing approve/return, role-gated), `POST /ics/isolate-execute` (Isolator complete, role-gated + `execution_department`-gated, optional per-item lock numbers), `POST /ics/deisolate-request` (Active → Deisolate Confirming), `POST /ics/deisolate-confirm` (Issuing approve/return, role-gated), `POST /ics/deisolate-execute` (Isolator complete, role-gated + `execution_department`-gated) → `Closed`, `POST /ics/link-ptw` (link a PTW, gated by `canLinkPTW`, symmetric write to both sides), `POST /ics/unlink-ptw` (unlink, symmetric write to both sides).

### P&ID / Wiring Highlighting

**Implemented as of 2026-07-28.** A tab inside `DialogIC` (after Isolation Items) where the requestor attaches one or more diagrams (PDF or image) to an IC and sees every isolation item's tag automatically located and highlighted on them — red for `OPEN` items, green for `CLOSE` (`IC.colorForItemState`) — using the IC's own `items` list as the source of truth for what to look for.

**Data model** (`client`/`server` `models/Isolation.py`): `IC.pid_documents: list[IC.PidWiringDocument]`, each holding `filename` (the highlighted/burned-in file — served to the app and to external viewers), `original_filename` (the pristine upload, kept only so highlights can be recomputed later), `page_count`, `ocr_used`, and `highlights: list[IC.Highlight]` (`tag`, `page`, `rect` — `[x, y, w, h]` fractional 0..1 of page size, `state`, `manual` — set once a highlight has been hand-drawn or adjusted, so a later Sync never overwrites it). `PidWiringDocument._asHighlight()` tolerates a `Highlight` arriving as an already-built object, a plain dict, or a `SimpleNamespace` — three different callers (in-memory construction, raw JSON, and the DB-row `dictToObj` path) hand it three different shapes.

**Highlight detection** (`client/widgets/PidWiringHighlighter.py`, client-only — nothing server-side inspects a highlight's contents): `computeHighlights(filePath, items)` opens the file via `QPdfDocument`/`QImage` and, per page, either searches the page's real text layer natively (`QPdfSearchModel`, whenever `QPdfDocument.getAllText(page)` returns anything at all — a page dense with short tag labels and no prose can legitimately have very little text, so "any text vs none" is the signal, not a length threshold) or falls back to OCR (`pytesseract`, English-only, catches `TesseractNotFoundError` and any other exception and just skips that page's highlights rather than crashing) for a scanned page or a plain image upload. Two Qt/pypdf quirks needed working around: `QPdfSearchModel` can hand back a rectangle with a negative width/height (observed on rotated pages) — every rect goes through `.normalized()` before use; and `QPdfDocument.render()` returns a page image with a **transparent** background (alpha 0, not opaque white), which reads as black once alpha is dropped (by Tesseract, or by anything that doesn't composite transparency) — `renderPage()` now composites onto white before the image is used for OCR or on-screen display. Each detected box is padded (`HIGHLIGHT_PAD_RATIO`/`HIGHLIGHT_PAD_MIN`) so the highlight reads as a callout around the text rather than a shrink-wrapped outline.

**Highlights are burned into the file itself, not drawn as an in-app-only overlay** — `burnInHighlights(filePath, highlights)` produces a new file with the highlight rectangles physically drawn in (`pypdf`+`reportlab` merge for PDFs, `Pillow` `ImageDraw` for images) and returns its path; the original upload is left untouched. This is what actually gets uploaded/stored as `pid_documents[i].filename`, so opening it from the server's attachments folder, or in any external viewer via **Open Externally** (`ReportGenerator.openPDF`, the same helper `TableAttachments` uses for PTW attachments), shows the same highlights the app computed — not just something drawn on top inside this app's own viewer. **Rotated PDF pages** (`/Rotate` 90/270) needed a specific fix: `pypdf`'s `page.mediabox` reports the page's raw, un-rotated box, which comes out swapped relative to `QPdfDocument.pagePointSize()`/`render()` (the rotation-aware, visual size the highlight rects are actually computed against) — `_burnInPdf` calls `page.transfer_rotation_to_content()` first, baking the rotation into the actual content and zeroing `/Rotate`, so pypdf's dimensions agree with Qt's before the overlay is drawn.

**`client/widgets/WidgetPidWiring.py`** — the tab itself. A combo box picks between a document's multiple attached files; **Upload**, **Open Externally**, and (non-readonly) **Delete** sit beside it. Below the zoom/pan preview (`_PidGraphicsView`, wheel-zoom + drag-pan) and page nav: **Sync Highlights** (recomputes automatic highlights for *every* document from the current items list, preserving any manual ones), **Clear Highlights** (wipes every highlight — manual included — from the *currently selected* document only), **Add Highlight**, and **Delete Highlight**. There's no separate "edit mode" toggle — whenever the IC itself is editable (not readonly), the preview always shows the pristine original with the current highlights overlaid as live, draggable/corner-resizable rectangles (`_EditableHighlightItem`); any drag-release, add, or delete re-burns the file immediately. Only the highlight that actually moved gets marked `manual` — an untouched sibling on the same page keeps whatever it already was, so a later Sync can still refresh it if it was never a manual override. Adding a highlight (`_AssignHighlightDialog`) only asks which item/tag it's for — its state is always taken from that item's current state in the items list, never chosen independently. Read-only viewing (an already-submitted IC) shows the burned-in file flatly, with none of the above editing controls.

**Isolation items ↔ P&ID resync**: `TableIsolationItems.itemsChanged` (a new signal, emitted on add, edit, or bulk-delete — double-clicking a row now opens `DialogIsolationItem` in edit or view mode depending on whether the IC dialog itself is editable) is wired to `WidgetPidWiring.onItemsChanged()`, which — if the IC already has any P&ID documents — asks whether to resync now (same "keep manual" Sync logic above).

**Upload lifecycle mirrors PTW attachments exactly, creation-time only**: `DialogIC` is never opened in an editable-existing-IC mode (there's no `PUT /ics`, no edit flow at all — see [IC](#ic-isolation-certificate) above), so P&ID documents can only be attached while creating a brand-new IC. Both the burned-in file and the pristine original are staged locally (`WidgetPidWiring.docsToBeUploaded: list[Attachment]`) and only actually uploaded — via new `POST /ics/attachments` — after `addIC` succeeds and the IC has an id (`TableICs.addNewICDialog`, mirrors `MainWindow.addPTWDialog`'s post-`addPTW` attachment upload). Server storage mirrors the PTW attachment routes almost verbatim: `server/ic-{id}-attachments/`, `POST`/`GET`/`DELETE /ics/attachments` — no copy route, since there's no "re-request IC" flow to mirror `copyPtwAttachments` for.

**Not implemented / known limitations:** a tag whose text is split across two lines by the diagram layout won't match via either the native-text or OCR path. Tesseract itself must be present on the machine running OCR — bundling it into the Nuitka client build (Windows via Chocolatey, Linux via `apt`, both staged into `client/tesseract-bin/` and picked up at runtime by `client/helper/OcrConfig.py`) is wired into `.github/workflows/build.yml`, English-only, but not yet verified against an actual CI run. Since ICs have no edit flow at all, there's also no way to attach a P&ID/wiring document to an IC after it's been submitted.

---

## Risk Assessments

Safety department creates and maintains a **generic risk assessment library** — reusable documents that can be selected while requesting a PTW.

Each `RiskAssessment` contains:
- `title`: assessment name (unique for generic entries; `str(ptw_id)` for a PTW-specific row set)
- `date`: creation/last-update date
- `ptw_id`: `NULL` for a generic library entry; set to a PTW's id for that PTW's own materialized risk table
- `risks`: list of `RiskItem` entries

Each `RiskItem` documents:
- `hazard`: the identified hazard
- `effect`: potential consequence
- `free_analysis`: analysis prior to applying controls
- `ctrl`: control measure applied
- `ctrl_analysis`: analysis after applying controls
- `eval`: final risk evaluation/rating

Only users with the **Safety** role can create/update/delete *generic* assessments (`ptw_id IS NULL`). Any user can create/update/delete the *PTW-specific* row set for a PTW (`ptw_id` set) — enforced server-side in `POST`/`PUT`/`DELETE /risks` by checking `ptw_id is not None`, not by trusting a client-declared role. Deleting a generic assessment is applicable but NOT allowed to keep already-done PTWs valid — a PTW's materialized rows (below) are independent copies, unaffected by later edits or deletion of the generic assessment they were derived from.

### PTW-specific risk assessment (`widgets/RiskPreview.py`)

The PTW request/edit/view dialog's Risks tab (`DialogPTW`) shows a single flat table — `RiskPreview.RiskItemsTable` — in **all three modes** (new, edit, view). There's no separate checkbox-based generic-selection step embedded in the PTW dialog anymore; the table itself, and the buttons above it, are the entire UI:

- **Add Items** → a chooser with three ways to populate rows:
  - *Add Manually* — `DialogRiskItem`, a single-item form (Hazard/Effect/Free Analysis/Control/Controlled Analysis/Evaluation), reused for both creating a new row and (via double-click on an existing row) editing one in place.
  - *Use Generic Risks* — `DialogSelectGenericRisks`, a modal that embeds `TableRisks` (the same checkbox-list widget the old embedded selector used, just in a dialog instead of inline) over the generic library (`globalData.allRiskAssessments`); every `RiskItem` from the checked assessments is deep-copied in.
  - *Import from Excel* — `RiskItemsTable._parseRiskItemsFile()`, built on the shared `utils.parseTabularFile()` reader (see below); invalid rows are skipped and reported, not fatal.
- **Delete Selected Items** — removes checked rows after confirmation.
- **Print Preview** — calls `ReportGenerator.riskAssessmentReport(riskAssessment=...)` directly on the in-progress table.

Every addition path (manual, generic-picker, Excel import) and every in-place edit runs through the same dedup check — `riskItemKey()` (exact match, case/whitespace-insensitive, across all 6 fields): a new item identical to one already present is silently rejected (with a message), and an edit that would make a row identical to a *different* existing row is discarded and reverted rather than applied.

**Persistence**: there is no intermediate "preview" state distinct from what's saved — the table *is* the data. On submit, `MainWindow._savePTWRiskAssessment` reads `dlg.riskAssessmentPreviewTable.getRiskItems()` straight from the table and upserts it as a single `RiskAssessment` with `title = str(ptw_id)` and `ptw_id = <the PTW's id>` (`PUT /risks`). Viewing an already-submitted PTW fetches and shows that same row set read-only. PTWs from before this table existed (no `ptw_id` row) just show an empty table — no backfill migration.

On **re-request**, the server additively copies the original PTW's `ptw_id` row set onto the new PTW's `ptw_id` (`risksDb.copyRiskAssessmentForPTW`, run from `POST /ptws/attachments/copy` right after the attachment file copy), so custom rows from the original carry over even if the user doesn't reselect or retype them in the new request.

**Status of `ptw.risks`**: `PTW` still has a `risks: list[str]` field (generic-title list) and `addRisk()`/`updateRequirements()` still populate it from tool/hazard/control `RISK`-type requirements, but the `validate()` check that used to enforce "selecting X requires risk assessment Y" is commented out — the field is inert and slated for removal along with the `RISK` requirement type, now that risk content is authored directly rather than derived from required generic titles.

### Shared tabular file parsing

`utils.parseTabularFile(filepath, headers)` reads a `.xlsx` or `.csv` file and returns its data rows re-ordered to match a given list of column headers — matching is order-independent and case/whitespace/newline-insensitive, so the caller's headers and the file's actual column order never need to line up. It raises `ValueError` listing any header it couldn't find. It does not skip blank rows itself, so callers that number rows against the source file can still do so accurately.

Two importers share it: `RiskItemsTable._parseRiskItemsFile()` (risk items, with per-row required-field and analysis-format validation) and `ImportUsersExcel.parseFile()` (bulk user import, with username/role/department validation).

---

## PTW Data Model

### Core Fields

```
id              — Auto-incremented integer (primary key)
type            — Permit type (CW, SP, HT, HC)
date            — Creation date (DD/MM/YYYY)
location        — Site location
equipment       — Equipment being worked on
area_class      — Hazard (HAZ) or Non-Hazard (NHZ)
department      — Responsible department
description     — Work description (max 300 chars)
requestor       — Username of person requesting the permit
fast_track      — Whether this permit is flagged for fast-track processing (bool, defaults to false)
```

### Running Cycle History

```
run_cycles  — Ordered list of RunCycle records, one per pass through the running state
              machine (run request/response, then hold-or-close request/response); see
              RunCycle above. Replaces the old flat performing/issuing/hold_*/close_*/
              keep_isolations fields.
```

`getPerforming()` / `getIssuing()` / `getPerformingTimestamp()` / `getIssuingTimestamp()` return the live PA/IA of the currently open run cycle (or `None` once it's been rejected, held, or closed — matching the old fields' behavior of going blank at that point). `getHeldICs()` returns the most recent operative cycle's kept IC ids regardless of whether that cycle is still open (used both while `WAITING_HLD_CONFIRM`/`HELD`, and read back afterward for reporting).

### Safety & Work Instructions

```
miwi        — Maintenance and Work Instructions,document (PDF)
mos         — Method of Statement, manually typed as a text of steps.
attachs     — List of uploaded attachment filenames
tools       — Selected tools: Hand Tools, Power Tools, Non-Ex Tools, Test Tools, Pneumatic Tools
hazards     — Identified hazards: Confined Space, Working at Height, etc...
controls    — Safety controls: Initial Gas Test, Continuous Gas Test, etc...
risks       — List of referenced risk assessment titles
isolations  — List of declarative Isolation objects (type, tag, description only — what
              this PTW is expected to need; no runtime linkage state, see Isolation
              Management)
linked_ics  — List of linked IC ids — fully implemented (link+unlink, both directions,
              symmetric with IC.linked_ptws); a PTW can't run unless every linked IC is
              Active, see Isolation Management
```

### Tools, Hazards & Controls Rules

`tools`, `hazards`, and `controls` are each backed by a lookup table in `PTW` — `ALL_TOOLS`, `ALL_HAZARDS`, `ALL_CONTROLS` — mapping title → `CheckBox`:

- `title` — display name (e.g. `'Power Tools'`, `'Confined Space'`)
- `isRequired(ptwType)` / `isRestricted(ptwType)` — per-permit-type rules, e.g. `'Non-Ex Tools'` is restricted for Cold Work; the `'Electrical / Mechanical Spark'` hazard is required for Spark permits and restricted for Cold Work
- `requirements` — a list of `Requirement` objects (`TOOL` / `HAZARD` / `CONTROL` / `RISK` / `ATTACH` / `DOC`) that must also be satisfied once this item is selected, e.g. selecting the `'Scaffolding'` hazard also requires the `'Working at Height'` hazard; selecting `'Power Tools'` requires the `'Power Tools Checklist'` attachment

**`updateRequirements()`** (client-only, called from `DialogPTW.checkRequirement()`) walks these tables to auto-check required items, auto-uncheck restricted ones, and cascade-add linked requirements — keeping the checkbox UI in sync as the user picks a permit type. This method only exists to drive the live UI; it is never called server-side.

**`validate()`** (called client-side before submit, and server-side on `POST /ptws`) independently re-checks the same three rules — required, restricted, and cascading requirements — plus required attachments (matched by filename prefix, since uploaded attachments carry a file extension: `"Power Tools Checklist.pdf"` satisfies the requirement `"Power Tools Checklist"`). It returns a descriptive error string on the first violation found. The server only validates and rejects; it never silently "fixes" or rewrites incoming tool/hazard/control selections.

### Status Fields

```
approval_status        — Current approval state (UNDER_REVIEW, APPROVED, RETURNED) — computed, not stored
running_status         — Current execution state (NOT_RUNNING through HELD) — computed, not stored
is_archived            — Archived after closure — the only one of these that IS a real column
approvals              — Ordered list of Approval records (full audit trail)
```

---

## Attachments

Each PTW has its own attachment directory on the server: `ptw-{id}-attachments/`. Files can be uploaded, downloaded, deleted, or copied between PTWs. Common attachments include medical certificates, tool checklists, and technical documents.

## MIWI Documents

Maintenance and Work Instructions (MIWI) are PDF documents describing the steps for a specific job, stored per-department on the server under `paths.DATA_DIR/miwi/<department>/` (e.g. `miwi/Turbo/`; see `server/paths.py`). MIWIs are not copied for every PTW, instead a PTW is linked to the MIWI to minimize used space.

**Uploads** always land in the uploading user's own department folder — `POST /miwi` takes the department from the client-supplied field (the uploader's own department), whitelisted against the `UserDepartments` enum, and creates the folder on demand.

**Reading is unrestricted by role** — any authenticated user can list (`GET /miwis`) or download (`GET /miwi`) a MIWI from any department, including the legacy flat files, since a PTW may need review by people outside its own department. `department` only narrows/prefers results when supplied (`server/paths.py` — `resolveMiwiPath`); it's never enforced against the caller's own department for these read endpoints. Only **uploading** (`POST /miwi`) is confined to the uploader's own department, per above.

A handful of legacy files still sit directly under `DATA_DIR/miwi/` (uploaded before the per-department layout existed) and are only reachable by approver-type roles until sorted into department folders manually.

---

## Authentication & Security

- All API endpoints require HTTP Basic Auth (username + password).
- Passwords are hashed with **bcrypt** before storage. The server never returns a password hash in any API response.
- **First boot:** if the `users` table is empty, a random admin password is generated with `secrets.token_urlsafe(12)` and printed once to the server log at `WARNING` level. Change it immediately after first login.
- **New user creation:** the initial password is auto-generated (`secrets.token_urlsafe(12)`), shown read-only in the admin's "Add User" dialog, and emailed to the new user's registered email address (see **Guest Access** below for the email itself — it uses the same template family as password reset).
- **Password Reset** flow: user requests a reset → server sends a 6-digit verification code to the user's registered email via Gmail SMTP → code expires after 15 minutes → user submits new password with code.
- Role-based access control is enforced at the API layer for sensitive operations (user management, risk assessment management, PTW lifecycle: only `ISSUING` can accept/reject run, hold, and close requests).
- `DELETE /ptws` and `POST /ptws/archive` are open to all authenticated users but are state-gated: deletion requires `approval_status == RETURNED` — an archived PTW qualifies too, but only incidentally, since `globalData.allPTWs` excludes archived rows entirely (see [Database Schema](#database-schema)) and the lookup returning nothing skips the check rather than passing it explicitly; archiving requires `running_status == CLOSED`.

### Guest Access

Anyone can click "Login as a Guest" without an account. The client prompts for a **name** (becomes their username/requestor identity) and **department** (free text — not restricted to the fixed department list, since guests may be outside contractors). Server-side, `getVerifiedUser()` checks the real `users` table first; only if that fails, the password is empty, and the username doesn't already belong to a real account does it construct an ephemeral `GUEST`-role session — so a guest can never shadow or spoof a real account (if their typed name collides with a real username, they get a plain "Unauthorized" instead).

Guests can create PTWs and request run/hold/close on their own submissions, scoped to their self-reported department (same fetch-filtering as the `User` role). They are explicitly denied on every other mutating endpoint: `PUT /users`, `PATCH /users/theme`, `DELETE /ptws`, `POST /ptws/approvals`, `POST /ptws/archive`, and `POST /ptws/attachments/copy`. Note the department scoping is self-reported, not an authoritative security boundary — there's no real account behind it to validate against.

### Invitation & Notification Email

New-user invitation email (`POST /users`) and the password-reset verification email both use HTML templates sent via Flask-Mail. The two email sends use **different concurrency models** on purpose:

- **Invitation email** — fire-and-forget on a background `threading.Thread(daemon=True)`; `POST /users` returns success as soon as the user row is created, without waiting on the SMTP round-trip. A failed send is only logged server-side, never surfaced to the admin.
- **Password-reset email** — sent synchronously inside the request handler, so a send failure can be returned to the client as a real error and the reset code is only stored after a confirmed send. `app.run(...)` passes `threaded=True` so this synchronous send only blocks the requesting client, not other users.

---

## API Reference

### Authentication
| Method | Endpoint                  | Description                        |
|--------|---------------------------|------------------------------------|
| POST   | `/login`                  | Authenticate user                  |
| POST   | `/reset-password-request` | Send verification code to email    |
| POST   | `/reset-password`         | Reset password with code           |

### Users
| Method | Endpoint        | Description                                               | Auth Required |
|--------|-----------------|-----------------------------------------------------------|---------------|
| GET    | `/users`        | Get all users (secured view)                              | Any           |
| GET    | `/user`         | Get a specific user                                       | Any           |
| GET    | `/usernames`    | Get all usernames                                         | Any           |
| POST   | `/users`        | Create a new user                                         | Admin only    |
| PUT    | `/users`        | Update a user                                             | Admin or self |
| PATCH  | `/users/active` | Activate/inactivate a user (`{"username", "is_active"}`)  | Admin only    |
| DELETE | `/users`        | Delete a user                                             | Admin only    |

### PTWs
| Method | Endpoint                    | Description                                |
|--------|-----------------------------|--------------------------------------------|
| GET    | `/ptws`                     | Get all PTWs (filterable by dept/requestor)|
| GET    | `/ptws/<id>`                | Get a single PTW by id (same visibility rule as `GET /ptws`, `404` if not found/not visible) — used for SSE-driven targeted refreshes instead of re-fetching everything |
| POST   | `/ptws`                     | Create new PTW                             |
| DELETE | `/ptws`                     | Delete a PTW                               |
| POST   | `/ptws/approvals`           | Submit an approval action                  |
| POST   | `/ptws/run-request`         | PA requests to start work (403s if any linked IC isn't `Active` — see [Run safety gate](#ptwic-linkage)) |
| POST   | `/ptws/run`                 | IA accepts or rejects run request (accept 403s under the same linked-IC gate) |
| POST   | `/ptws/hold-request`        | PA requests to hold work                   |
| POST   | `/ptws/hold`                | IA accepts or rejects hold request         |
| POST   | `/ptws/close-request`       | PA requests to close permit                |
| POST   | `/ptws/close`               | IA accepts or rejects close request        |
| GET    | `/ptws/archive`             | Get all archived PTWs                      |
| POST   | `/ptws/archive`             | Archive a closed PTW                       |

`POST /ptws` runs `PTW.validate()` (required/restricted/requirements rules for tools, hazards, controls, plus required attachments — see [Tools, Hazards & Controls Rules](#tools-hazards--controls-rules)) before persisting; a failing submission is rejected with `400` and never written to the database.

`/ptws/run`, `/ptws/hold`, `/ptws/close` (the IA's response) and `/ptws/hold-request`, `/ptws/close-request` (the PA's stop request) all accept an optional `comment` field in the JSON body, stored on the relevant `RunCycle` (`run_ia_comment`/`stop_pa_comment`/`stop_ia_comment` — see [Running Cycle](#2-running-cycle)); `/ptws/run-request` has no comment field, matching `RunCycle.run_pa`/`run_pa_timestamp` having none either.

### Real-Time Events (SSE)
| Method | Endpoint   | Description                                              |
|--------|------------|----------------------------------------------------------|
| GET    | `/events`  | SSE stream; pushes PTW change events to the client       |

The server broadcasts role-filtered events over this stream. The client connects via `SSEListener` (a QThread), which forwards any event generically — dispatch happens entirely on the `data` payload, not the SSE `event:` name.

**Envelope.** Every broadcast is a fixed `{object, object_id, action, by}` shape (`server/models/SSE.py` — `SSEObject`, `SSEAction`; mirrored in `client/models/SSE.py`), built by `_broadcast(obj, object_id, action, by, roles=None)`. `object` is `PTW` or `IC`; `action` values are themselves the human-readable phrase (e.g. `"run rejected"`, `"isolate requested"`), so `MainWindow._onSSEEvent` renders the notification as a plain `f"{object} #{object_id} {action} by {by}"` with no per-event branching. Archiving multiple PTWs at once (manual or the auto-archive daemon) broadcasts one `PTW … archived` event per id rather than a single batch event, so every broadcast stays one-object-per-message. Linking/unlinking a PTW and IC broadcasts twice — once as `IC … linked/unlinked`, once as `PTW … linked/unlinked` — since both records actually change.

On receipt, the client does **not** do a full `globalData.refresh()` — `MainWindow._applyPTWEvent`/`_applyICEvent` fetch just the one touched record (`GET /ptws/<id>` / `GET /ics/<id>`, added specifically for this — see [PTWs](#ptws)/[ICs](#ics) above) and patch it into `GlobalData` (`upsertPTW`/`removePTW`/`upsertIC`/`removeIC`) and into whichever single tab it belongs in (`MainWindow._ptwTargetTab`/`_icTargetTab` — the same categorization the full-refresh loops use, extracted once so both paths agree; `TablePTWs.removePTWById`/`TableICs.removeICById` drop the row from wherever it currently sits first). A `404` from the lookup (not visible / no longer exists) removes the record locally instead of erroring. The manual Refresh button and the initial post-login load are unchanged — they still do a full `refreshGUI()`.

| Object / action | Triggered by |
|------------------|--------------|
| `PTW created`                        | New PTW created (`new_ptw`) |
| `PTW deleted`                        | PTW deleted |
| `PTW updated`                        | Returned PTW edited and resubmitted |
| `PTW approved` / `PTW returned`      | Approval action submitted |
| `PTW archived`                       | PTW archived (one event per id, manual or automatic) |
| `PTW run requested`                  | PA sends run request |
| `PTW run accepted` / `PTW run rejected` | IA accepts/rejects run request |
| `PTW hold requested`                 | PA sends hold request |
| `PTW held` / `PTW hold rejected`     | IA accepts/rejects hold request |
| `PTW close requested`                | PA sends close request |
| `PTW closed` / `PTW close rejected`  | IA accepts/rejects close request |
| `PTW linked` / `PTW unlinked`        | The PTW side of an IC link/unlink (see below) |
| `IC created`                         | New IC created (broadcast to `ISSUING` only — the creator's own view updates via a local optimistic add instead, see [Isolation Management](#isolation-management)) |
| `IC approved` / `IC returned`        | Approve/reject action recorded on an IC's approval chain (unrestricted broadcast, like `PTW approved`/`returned`) |
| `IC isolate requested` / `IC isolate confirmed` / `IC isolate rejected` / `IC isolated` | Isolate cycle: request / IA confirm / IA return / isolator execute |
| `IC deisolate requested` / `IC deisolate confirmed` / `IC deisolate rejected` / `IC deisolated` | De-isolate cycle: request / IA confirm / IA return / isolator execute |
| `IC linked` / `IC unlinked`          | A PTW was linked to / unlinked from an IC (either side can have initiated it; also broadcasts the `PTW linked`/`unlinked` counterpart above) |

### Attachments
| Method | Endpoint                    | Description                          |
|--------|-----------------------------|--------------------------------------|
| POST   | `/ptws/attachments`         | Upload files to a PTW                |
| GET    | `/ptws/attachments`         | List or download PTW attachments     |
| DELETE | `/ptws/attachments`         | Delete attachments except for `keep-list`       |
| POST   | `/ptws/attachments/copy`    | Copy attachments from one PTW to another (also additively copies the source PTW's risk assessment onto the target) |

### ICs
| Method | Endpoint                | Description                                                              | Auth Required   |
|--------|-------------------------|---------------------------------------------------------------------------|-----------------|
| GET    | `/ics`                  | Get all ICs (department-scoped for `USER` role against `requestor_department`, unrestricted for others) | Any authenticated user |
| GET    | `/ics/<id>`             | Get a single IC by id (same visibility rule as `GET /ics`, `404` if not found/not visible) — used for SSE-driven targeted refreshes instead of re-fetching everything | Any authenticated user |
| POST   | `/ics`                  | Create a new IC (`requestor_department`/`requestor`/`requestor_timestamp` are stamped server-side from the caller, not trusted from the payload; `execution_department` is required from the client — 400 if missing, or if `Self`-type and it doesn't match `requestor_department`; `is_psic` and every `psic_*` field are force-blanked regardless of the payload — see [Isolation Management § PSIC](#ic-isolation-certificate)) | Any non-guest   |
| POST   | `/ics/approvals`        | Submit an approve/reject action on the IC's approval chain (mirrors `/ptws/approvals`); an `ISSUING` approval may set `mark_psic: true` to flag `is_psic`, and a `COORDINATOR` approval of a PSIC must carry `psic_terms` (`psic_reasons`/`psic_moc_number`/`psic_system_description`/`psic_isolation_method`/`psic_control_measures`) — 400 if `psic_reasons` is empty or any of the three description fields is blank, before recording anything | Caller's `getApprovalStatus(role, department)` must currently be `Requested` (i.e. it's their turn) |
| POST   | `/ics/isolate-request`  | User requests the approved IC's isolation be carried out (`Approved`→`Isolate Confirming`) | Any non-guest |
| POST   | `/ics/isolate-confirm`  | Issuing confirms or returns the isolate request | `ISSUING` |
| POST   | `/ics/isolate-execute`  | Isolator carries out the isolation, optional per-item lock #/lock box # (`Pending`→`Active`) | `ISOLATOR` whose department matches the IC's `execution_department` |
| POST   | `/ics/deisolate-request`| User requests de-isolation (`Active`→`Deisolate Confirming`) | Any non-guest |
| POST   | `/ics/deisolate-confirm`| Issuing confirms or returns the de-isolate request | `ISSUING` |
| POST   | `/ics/deisolate-execute`| Isolator carries out the de-isolation → `Closed` | `ISOLATOR` whose department matches the IC's `execution_department` |
| POST   | `/ics/link-ptw`         | Link a PTW to an IC (either side can supply the id it already has), gated by `canLinkPTW`, symmetric write to both `IC.linked_ptws` and `PTW.linked_ics` | Any non-guest |
| POST   | `/ics/unlink-ptw`       | Unlink a PTW from an IC, symmetric write to both sides | Any non-guest |
| POST   | `/ics/attachments`      | Upload P&ID/wiring files to an IC (mirrors `/ptws/attachments`) | Any authenticated user |
| GET    | `/ics/attachments`      | List or download an IC's P&ID/wiring attachments (mirrors `/ptws/attachments`) | Any authenticated user |
| DELETE | `/ics/attachments`      | Delete attachments except for `keep-filenames` (mirrors `/ptws/attachments`) | Any authenticated user |

Hold/sanction-for-test and re-isolate routes don't exist yet (see [Isolation Management](#isolation-management)). No `/ics/attachments/copy` — there's no "re-request IC" flow to mirror `/ptws/attachments/copy` for.

### Risk Assessments
| Method | Endpoint     | Description                                                      | Auth Required |
|--------|--------------|-------------------------------------------------------------------|---------------|
| GET    | `/risks`     | Get all **generic** risk assessments (`ptw_id IS NULL`)          | Any           |
| GET    | `/risks/ptw` | Get one PTW's specific risk assessment (body: `{"ptw_id": ...}`) | Any authenticated user, any department |
| POST   | `/risks`     | Create a risk assessment                                          | Safety (generic) or any user for their own PTW's row (`ptw_id` set) |
| PUT    | `/risks`     | Update a risk assessment                                          | same as POST  |
| DELETE | `/risks`     | Delete a risk assessment                                          | same as POST  |

### MIWI Documents

| Method | Endpoint | Description                                                    |
|--------|----------|----------------------------------------------------------------|
| GET    | `/miwi`  | Download a MIWI PDF by name, optionally scoped by `department` |
| GET    | `/miwis` | List MIWI filenames, optionally scoped by `department`         |
| POST   | `/miwi`  | Upload a new MIWI PDF into the uploader's own department       |

`department` is advisory only for both read endpoints — it narrows/prefers results but is never enforced against the caller's department; any authenticated user can read any department's MIWIs. Only `POST /miwi` (upload) is confined to the uploader's own department — see [MIWI Documents](#miwi-documents).

### Logs
Admin-only. The request body is JSON (`{"filename": "<name>"}`) to fetch a specific file; omit the body to list all files.

| Method | Endpoint | Description                                          | Auth Required |
|--------|----------|------------------------------------------------------|---------------|
| GET    | `/logs`  | List log filenames **or** download a specific log file | Admin only  |

Path traversal is prevented server-side via `os.path.abspath` containment check.

### Backups

Admin-only, backs `client/tables/TableBackups.py`. `GET`/`POST` bodies are JSON; `POST` takes none.

| Method | Endpoint   | Description | Auth Required |
|--------|------------|--------------|---------------|
| GET    | `/backups` | List existing backups (omit body), or download one backup's dump/files archive (body: `{"name": "<timestamp>", "which": "dump"\|"files"}`) | Admin only |
| POST   | `/backups` | Create a new on-demand backup now (`backupService.createBackup()`) | Admin only |
| DELETE | `/backups` | Delete a backup (body: `{"name": "<timestamp>"}`) | Admin only |

`GET /backups` (list form) returns `{"backups": [...], "retentionDays": 14, "freeBytes": <int|null>, "lastBackupAt": <iso|null>}`; each backup row has `name` (its `YYYYMMDD_HHMMSS` timestamp), `created`, `dumpSizeBytes`, `filesSizeBytes`, `totalSizeBytes`, `complete` (both the DB dump and file archive are present and non-empty). A backup is a `pg_dump -Fc` dump plus a `files.tar.gz` of `.env` + the MIWI/PTW-attachments/IC-attachments directories, written under `paths.BACKUP_DIR` (`DATA_DIR/backups/`) — the *same* on-disk format `server/dev-scripts/backup.sh`/`.ps1` produce, so backups made via either path are interchangeable with `restore.sh`/`.ps1`. Because `DATA_DIR/backups/` lives on the same disk as the live data it's backing up, this in-app path is a convenient manual snapshot/download mechanism, not a disaster-recovery solution by itself — `server/dev-scripts/backup.sh`/`.ps1` (run on a schedule to a separate, off-disk location; its default backup root is `paths.BACKUP_DIR` too, but an explicit path outside `DATA_DIR` is what actually gets the data off this machine) is the one meant for that.

---

## Database Schema

Database name: `ptw_database` (PostgreSQL, localhost). `server/dev-scripts/init_db.py` is the one-time script that creates the database and every table below in this final shape — run it once before starting the server for the first time. The `*Db.py` classes (`db/usersDb.py`/`db/ptwDb.py`/`db/risksDb.py`/`db/ICDb.py`) assume their table already exists; they no longer `CREATE TABLE`/`ALTER TABLE` on every server startup the way they used to while the schema was still evolving (table/column renames, drops, splits — that churn is done, so a fresh database now gets the end result directly instead of walking through it). `UsersDb` is the one exception: its constructor still seeds the initial `admin` account if `users` is empty, since that's data seeding rather than schema.

### `users`
```sql
username    VARCHAR(50)  PRIMARY KEY
password    VARCHAR(100) NOT NULL
name        VARCHAR(100) NOT NULL
role        VARCHAR(50)  NOT NULL
department  VARCHAR(100)
email       VARCHAR(100)
ext         VARCHAR(50)
theme       VARCHAR(20)
is_active   BOOLEAN      NOT NULL DEFAULT TRUE
```

### `ptws`
```sql
id                          SERIAL PRIMARY KEY
type                        VARCHAR(100)
request_date                VARCHAR(100)
location                    VARCHAR(100)
equipment                   VARCHAR(100)
area_class                  VARCHAR(100)
department                  VARCHAR(100)
description                 VARCHAR(300) NOT NULL
fast_track                  BOOLEAN NOT NULL DEFAULT FALSE
requestor                   VARCHAR(100)
run_cycles                  JSONB[]
miwi                        VARCHAR(100)
mos                         VARCHAR(100)
tools                       TEXT[]
hazards                     TEXT[]
controls                    TEXT[]
risks                       TEXT[]
linked_ics                  TEXT[]
approvals                   JSONB[]
isolations                  JSONB[]
is_archived                 BOOLEAN NOT NULL DEFAULT FALSE
```

`linked_ics` — fully implemented PTW↔IC linkage (list of linked IC ids; see [Isolation Management](#isolation-management)). `run_cycles` replaced the old flat `performing`/`issuing`/`performing_timestamp`/`issuing_timestamp`/`close_performing`/`close_issuing`/`close_performing_timestamp`/`close_issuing_timestamp`/`hold_performing`/`hold_issuing`/`hold_performing_timestamp`/`hold_issuing_timestamp`/`keep_isolations` columns (see [Running Cycle](#2-running-cycle)); `dev-scripts/migrate_ptw_run_cycles.py` is the one-time migration that adds it, backfills it from those old columns, and drops them.

**Three `PTW` fields are deliberately not columns here.** `approval_status` and `running_status` are both recomputed by `__updateStatus()` from `approvals`/`run_cycles` on every read (see [Running Cycle](#2-running-cycle)), so a stored copy would just be a stale duplicate — this also removed the old `prev_running_status` column entirely, since the replay-forward derivation never needs a "revert to" snapshot the way the old direct-SQL-write transitions did. `attachs` only ever holds the client's local, not-yet-uploaded staging list (used by `validate()`'s required-attachment check) — the actual attachment filenames live only in the `ptw-{id}-attachments/` folder on disk (see [Attachments](#attachments)); `ReportGenerator.ptwReport()` fetches that live listing via `GET /ptws/attachments` rather than trusting `ptw.attachs`. `is_archived` is the one exception that IS a real column — archiving isn't something a run cycle's fields can encode.

**There is no more `isolations` table.** It (and the plain `Isolation.linked_ptws`/`held_by`/`primary_ptw`/`latest_ptw`/`is_physically_isolated`/`linkPTW`/`holdPTW`/`unlinkPTW` state it backed) was removed entirely 2026-07-25 along with `server/IsolationDb.py` and the client's global "Isolations" browse tab — see [Isolation Management](#isolation-management). `PTW.isolations` still exists but is a plain `JSONB[]` column on `ptws` holding declarative `type`/`tag`/`description` records only, same as always.

### `ics`

Created by `server/dev-scripts/init_db.py` in the shape below (renamed from `isolation_certificates` 2026-07-25; `department` split into `requestor_department`/`execution_department` 2026-07-26; `pid_documents` added 2026-07-28, see [P&ID / Wiring Highlighting](#pid--wiring-highlighting); `is_psic`/`psic_reasons`/`psic_moc_number`/`psic_system_description`/`psic_isolation_method`/`psic_control_measures` added 2026-07-31 and `Protective System` dropped as a `type` value, see [Isolation Management](#isolation-management) — all migrations that a live install needed to get here have already run, so a fresh database just gets this final shape directly, see [Database Schema](#database-schema) above).

```sql
id                              SERIAL PRIMARY KEY
type                            VARCHAR(100)
requestor_department            VARCHAR(100)
execution_department            VARCHAR(100)
requestor                       VARCHAR(100)
requestor_timestamp             VARCHAR(100)
approvals                       JSONB[]
location                        VARCHAR(100)
equipment                       VARCHAR(100)
reason                          VARCHAR(300) NOT NULL
items                           JSONB[]
pid_documents                   JSONB[]
isolate_asap                    BOOLEAN NOT NULL DEFAULT FALSE
isolate_requestor               VARCHAR(100)
isolate_requestor_timestamp     VARCHAR(100)
isolate_issuing                 VARCHAR(100)
isolate_issuing_timestamp       VARCHAR(100)
isolate_issuing_action          VARCHAR(100)
isolate_isolator                VARCHAR(100)
isolate_isolator_timestamp      VARCHAR(100)
sanction_requestor              VARCHAR(100)
sanction_requestor_timestamp    VARCHAR(100)
sanction_issuing                VARCHAR(100)
sanction_issuing_timestamp      VARCHAR(100)
sanction_isolator               VARCHAR(100)
sanction_isolator_timestamp     VARCHAR(100)
reisolate_requestor             VARCHAR(100)
reisolate_requestor_timestamp   VARCHAR(100)
reisolate_issuing               VARCHAR(100)
reisolate_issuing_timestamp     VARCHAR(100)
reisolate_isolator              VARCHAR(100)
reisolate_isolator_timestamp    VARCHAR(100)
deisolate_requestor             VARCHAR(100)
deisolate_requestor_timestamp   VARCHAR(100)
deisolate_issuing               VARCHAR(100)
deisolate_issuing_timestamp     VARCHAR(100)
deisolate_issuing_action        VARCHAR(100)
deisolate_isolator              VARCHAR(100)
deisolate_isolator_timestamp    VARCHAR(100)
long_term                       BOOLEAN NOT NULL DEFAULT FALSE
long_term_reason                VARCHAR(300) NOT NULL
is_psic                         BOOLEAN NOT NULL DEFAULT FALSE
psic_reasons                    TEXT[]
psic_moc_number                 VARCHAR(100)
psic_system_description         VARCHAR(300) NOT NULL
psic_isolation_method           VARCHAR(300) NOT NULL
psic_control_measures           VARCHAR(300) NOT NULL
linked_ptws                     TEXT[]
held_by                         TEXT[]
```

`is_psic`/`psic_reasons`/`psic_moc_number`/`psic_system_description`/`psic_isolation_method`/`psic_control_measures` — see [Isolation Management § PSIC](#ic-isolation-certificate) for the full field-by-field breakdown. The three `psic_*` description columns are `NOT NULL` the same way `long_term_reason` is — always written as an empty string by the client rather than left unset when `is_psic` is false.

`linked_ptws`/`held_by` are the IC's own runtime linkage state — fully implemented (link+unlink, symmetric with `PTW.linked_ics`), see [Isolation Management](#isolation-management). `primary_ptw`/`latest_ptw`/`is_physically_isolated` columns existed at one point but were removed 2026-07-25 (`latest_ptw` was always derivable as `linked_ptws[-1]`, `is_physically_isolated` as `bool(linked_ptws or held_by)`, and `primary_ptw` had no clean replacement and wasn't worth keeping) — they're absent from the schema above and from any already-migrated install; a fresh database created by `init_db.py` never has them at all.

### `risks`
```sql
hazard         VARCHAR(300)  NOT NULL
effect         VARCHAR(300)  NOT NULL
free_analysis  VARCHAR(300)  NOT NULL
ctrl           VARCHAR(1000) NOT NULL
ctrl_analysis  VARCHAR(300)  NOT NULL
eval           VARCHAR(300)  NOT NULL
title          VARCHAR(300)  NOT NULL
date           VARCHAR(300)  NOT NULL
ptw_id         INTEGER                -- NULL = generic library entry; set = that PTW's own materialized row
```

`ctrl` is wider than the other text fields (1000 vs 300) — control-measure descriptions routinely ran past 300 characters in practice. Indexed on `ptw_id` (`idx_risks_ptw_id`) for fast per-PTW lookups.

---

## Client Architecture

The desktop client is structured around role-based main windows. After login, `main.py` routes the user to the appropriate role-specific window class (`client/windows/`, e.g., `IssuingMainWindow`, `SafetyMainWindow`, `AdminMainWindow`, etc...), each subclassing the base `MainWindow` (`windows/MainWindow.py`).

### Global Data Cache

`GlobalData` maintains an in-memory cache of:
- `allUsers` — dict of username → SecuredUser
- `allPTWs` — list of PTW objects (non-archived)
- `archivedPTWs` — list of PTW objects (archived permits)
- `ics` — dict of id → IC (renamed from `isolationCertificates` 2026-07-25; there is no more `isolations` dict — the plain-tag registry it backed was removed the same day)
- `allRiskAssessments` — dict of title → RiskAssessment (generic library only; a PTW's own specific row set is fetched on demand via `GET /risks/ptw`, never cached globally)
- `allMIWIs` — list of MIWI filenames

`allPTWs` is refreshed on login and after any mutation. `archivedPTWs` is fetched **on-demand only** (not automatically refreshed) to reduce server overhead — archived permits are stable and rarely queried.

### Key Client Modules

| Module                      | Purpose                                                          |
|-----------------------------|------------------------------------------------------------------|
| `main.py`                   | Entry point; launches QApplication                               |
| `Login.py`                  | Login screen; handles password reset flow                        |
| `windows/MainWindow.py`     | Base main-window class — chrome, PTW/IC action handlers, SSE sync; role-specific subclasses live alongside it in `windows/` |
| `network/clientRequests.py`         | HTTP wrapper; all server calls return `(err, data)`              |
| `network/RequestWorker.py`          | `@async_request` decorator — moves any request off the GUI thread via `QThread`; marshals result back via queued signal |
| `widgets/RefreshOverlay.py`         | `RefreshOverlay` — dims a window/dialog and blocks input while a refresh is in flight; refcounted `showBusy()`/`hideBusy()`, auto-tracks its parent's size via an event filter, plays an animated bouncing-logo sprite (baked offline by `dev-scripts/generate_refresh_overlay_frames.py` into `assets/sh-logo-bounce-frames.png`) |
| `GlobalData.py`             | Client-side data cache                                           |
| `network/SSEListener.py`            | QThread that connects to `/events` and emits real-time PTW events|
| `models/PTW.py`                | Mirrored data model classes (client-side copy)                   |
| `models/Isolation.py`              | Client-side model: `Isolation` (declarative type/tag/description only, no runtime state — used inside a PTW's own required-isolations list) + `IC` (renamed from `IsolationCertificate` 2026-07-25; the formal request document — approval chain, `getStatus()`, type coloring, and all runtime PTW-linkage state: `linked_ptws`/`held_by`) |
| `helper/utils.py`                  | Shared helpers: `resource_path`, `objToDict`, `dictToObj`, `parseTabularFile` |
| `models/User.py`                   | User model                                                       |
| `dialogs/TabbedDialog.py`           | *(added 2026-08-06)* Base class for `DialogPTW`/`DialogIC` — owns `tabsContainer`/`stack`/`tabsBtnsMap`, `addTab()`, `setTabBarColor()` (recolors the bar and auto-picks readable selected/unselected `TabButton` text+icon colors via `bestForegroundColor()`), the shared `btnBack`/`btnNext`/`btnFinish`/`btnCancel` row (`bottomButtonsLayout()`), and `stackTabChanged()` (keeps tab-button selection state and Back/Next enabled-state in sync with the stack) |
| `dialogs/DialogPTW.py`              | Full PTW form (create/view/edit); `DialogPTW` is tabbed (Basic Info / Tools / Hazards / Controls / Risks / Isolation / MIWI-MOS / Attachments / **History** / **IC Linkage** — the last two only in readonly mode, mirroring `DialogIC`'s History/PTW Linkage split). History renders the approval log and the running cycle as two side-by-side `Timeline` panes — a vertical rail of colored dots (green=approved, orange=returned/rejected, gray=pending) connected by a continuous line, each dot's row scrollable via `QScrollArea`. The Approval Timeline reads `ptw.approvals`; the Running Timeline (`_buildRunningTimelinePane`/`_runCycleRequestEntry`/`_runCycleResponseEntry`) reads `ptw.run_cycles`, rendering each `RunCycle` as a "Run Cycle #N" header followed by its Run Requested/Run Approved-or-Rejected rows, and — once a hold or close has actually been requested on that cycle — its Hold/Close Requested and Hold/Close Approved-or-Rejected rows (gray "Pending" only for whichever step the *current*, still-open cycle hasn't reached yet; earlier, already-finished cycles never show a pending row). IC Linkage groups `ptw.linked_ics` by looking up each id's type in `globalData.ics`, one row per `IC.Types` value, each row with **View** and (non-Guest) **Unlink** buttons. |
| `widgets/UiUtils.py`                 | Reusable UI helpers shared across dialogs: `TabButton` (colored tab-bar button — text/icon color is picked per-state by whoever calls `setHighlightColor()`, see `TabbedDialog.setTabBarColor()`), `lightenColor` (accent-color helper), `bestForegroundColor` (picks black/white by perceived luminance for readable text/icons against an arbitrary background), `Timeline`/`TimelineEntry` (vertical rail of colored dots + content, used for approval/isolation history panes) — extracted here since both `dialogs/DialogPTW.py` and `dialogs/DialogIC.py` (via `dialogs/TabbedDialog.py`) import them |
| `tables/TablePTWs.py`              | Table listing all PTWs with filters; supports Excel export; `filterColumn(label, values)` sets a specific column filter programmatically (used by the home dashboard's location segments) |
| `tables/TableUsers.py`             | Admin user management table; supports bulk user import from Excel; also has `filterColumn(label, values)` (used by the Admin dashboard's department segments) |
| `widgets/DonutChart.py`             | Reusable donut-chart widget (`DonutChart`/`DonutSegment`) for the home-page dashboard — clickable/hoverable ring + legend, fixed categorical palette |
| `reports/ImportUsersExcel.py`       | Parses bulk-user Excel/CSV imports + DialogUsersPreview dialog   |
| `tables/TableRisks.py`             | Generic risk assessment CRUD list (Safety admin tab); also embedded read-only+checkboxes inside `DialogSelectGenericRisks` |
| `widgets/RiskPreview.py`            | `DialogRiskItem` (single-item editor), `RiskItemsTable` (the flat table used for a PTW's risk assessment in all modes — add/delete/import/generic-pick, with dedup), `DialogSelectGenericRisks`, `RiskAssessmentPreview()` popup/embedded factory |
| `tables/TableIsolations.py`        | Embedded editable required-isolations list for a PTW form (`TablePTWIsolations`) — type/tag/description only. The old global all-isolation-points browser (`TableIsolationsBrowser`) was removed 2026-07-25 along with the registry it displayed. |
| `tables/TableICs.py`               | (renamed from `TableIsolationCertificates.py` 2026-07-25) IC list, one instance per tab (Requested/Under Review/Pending/Active/Sanctioned/Closed), mirrors `TablePTWs`; IC#/Status/Type/L.T./Requestor/Request Time/Requestor Dept./Execution Dept./Location/Equipment/Reason columns, L.T. rendered as an icon badge like Fast Track |
| `dialogs/DialogIC.py`               | (renamed from `DialogIsolationCertificate.py` 2026-07-25) IC create/view dialog, tabbed like `DialogPTW` (Basic Info / Isolation Items / P&ID / Wiring / PSIC / History / PTW Linkage — the last two only in readonly mode); `new`/`readOnly` flags mirror `DialogPTW`. The PSIC tab holds `is_psic`, `psic_reasons` (multi-select), `psic_moc_number`, and the three PSIC description fields, plus the "Autofill from Tag" button — all view-only content in readonly mode; in new-mode (creating an IC) it's just an info note instead, since none of it is settable there any more (see [Isolation Management](#isolation-management) and `dialogs/DialogDefinePsicTerms.py` below). PTW Linkage rows have **View** and (non-Guest) **Unlink** buttons. |
| `dialogs/DialogDefinePsicTerms.py`  | *(added 2026-08-14)* Plain (non-tabbed) dialog for Coordinator's approval of a PSIC's own stage — same PSIC fields `DialogIC`'s PSIC tab used to let the requestor fill in, now filled in here instead, opened from `MainWindow.acceptIC`'s Coordinator branch rather than a standalone "define terms" action. `getTerms()` returns the collected fields for `ClientRequests.updateApprovalIC`'s `psic_terms` argument. |
| `tables/TableIsolationItems.py`    | Embedded editable isolation-item list inside the IC dialog, mirrors `TablePTWIsolations`; Description column stretches to fill remaining width; `itemsChanged` signal (add/edit/bulk-delete) drives the P&ID resync prompt; double-click opens `DialogIsolationItem` in edit or view mode |
| `dialogs/DialogIsolationItem.py`    | Isolation-item add/edit/view dialog (tag/description/state/lock #/lock box #); lock fields are always read-only — set by the isolator on confirmation, not the requestor; `item=`/`readonly=` params drive edit-existing vs. view-only |
| `widgets/WidgetPidWiring.py`        | P&ID/Wiring tab embedded inside the IC dialog — document picker, zoom/pan preview, live manual highlight editing. See [P&ID / Wiring Highlighting](#pid--wiring-highlighting) |
| `widgets/PidWiringHighlighter.py`   | Pure logic (no UI): `computeHighlights()` (native text search + OCR fallback), `burnInHighlights()` (physically draws highlights into a new copy of the file), shared PDF render/load helpers |
| `helper/OcrConfig.py`              | Points `pytesseract` at the Tesseract binary bundled into the Nuitka build (`client/tesseract-bin/`, staged in `.github/workflows/build.yml`) when running frozen; no-op in dev |
| `tables/TableAttachments.py`       | PTW attachment management                                        |
| `widgets/TabServerLogs.py`          | Admin-only log viewer: collapsible file panels, lazy load, level filter, color-coded lines |
| `widgets/CheckableComboBox.py`      | Reusable multi-select checkbox combo box with `filterChanged` signal |
| `widgets/SearchableComboBox.py`     | Reusable editable combo box with fuzzy-match autocomplete; accepts free text not in its list |
| `dialogs/DialogUser.py`             | Create/edit user dialog                                          |
| `dialogs/DialogIsolation.py`        | Create/edit isolation dialog                                     |
| `dialogs/DialogSelectHeldICs.py` | Dual-mode linked-IC dialog for the PTW hold flow — PA selects which linked ICs stay held (`getHeldICIds()`), or a plain review of which ICs were kept |
| `dialogs/DialogPtwAlarms.py`        | Two-section, individually collapsible grouped popup for `MainWindow._checkPtwAlarms()` — 14-shift-validity-expired PTWs (View/Close/Close All) and run-cycle-shift-ended PTWs (View/Hold/Close), each row disabling its own acted-on button(s) in place on success; View opens its own `DialogPTW` with the busy overlay on this dialog rather than delegating to `MainWindow.viewPTW` |
| `dialogs/DialogSettings.py`         | App/session settings — profile fields, theme, and the close-behavior preference (below) |
| `reports/ReportGenerator.py`        | Generates printable PDF permit reports and Excel exports         |

### System Tray & Background Notifications

`MainWindow.closeEvent()` intercepts the window's close button. It first checks a remembered choice — `QSettings("PTW", "PTW")`, key `app/closeBehavior` (`""`/`"tray"`/`"exit"`) — and if one is set, acts on it immediately with no prompt. Otherwise it asks (Yes/No/Cancel) whether to keep receiving notifications in the background, now with a **"Remember my choice"** checkbox on the `QMessageBox` (added 2026-08-06): checking it before answering Yes or No persists that choice via the same `QSettings` key so the prompt won't reappear on later closes; Cancel never persists, checkbox state notwithstanding. **Yes** (or a remembered `"tray"`) ignores the event and hides the window instead of closing it (`_minimizeToTray()`) — the `SSEListener` thread and `_trayIcon` (already created in `MainWindow.__init__`, independent of window visibility) keep running untouched, so notifications keep showing via `_trayIcon.showMessage()` exactly as before. **No** (or a remembered `"exit"`) calls `_quitApp()` (stops `_sseListener`, hides the tray icon, `QApplication.quit()`). **Cancel** just re-ignores the event. The tray icon's context menu (**Open PTW** / **Quit**) and single/double-click (`_onTrayActivated`) restore the same still-logged-in window (`show()`/`raise_()`/`activateWindow()`) — since the process never exited, no re-login or state restore is needed, it's the same live instance.

The remembered choice isn't a one-way trap: `DialogSettings` has an **"On close:"** combo box (Always ask / Minimize to tray / Exit completely, same `QSettings` key) so it can be revisited or reset back to "Always ask" at any time. This preference is local-only (`QSettings`, per-machine) — it's never sent to the server, never part of the `User` model, and independent of the `ClientRequests.updateUser` network call the rest of the Settings dialog makes.

`logout()` sets a `_forceClose` flag before calling `self.close()` so it bypasses the close-behavior check entirely and does a real close (also stopping the SSE listener and hiding the tray icon, mirroring `_quitApp`). `main.py` sets `app.setQuitOnLastWindowClosed(False)` so hiding a window never implicitly quits the app; `Login.py`'s `LoginWindow` gets its own explicit `closeEvent` (`QApplication.instance().quit()`) since it has no tray/notification concept pre-login and would otherwise leave a windowless zombie process if closed.

### Internationalization (i18n) / Arabic Support

**Started 2026-06-19, continued/completed 2026-08-12-13.** English is the only language with UI strings written inline; Arabic is added as a translation layer on top, not a parallel set of source files.

- `client/helper/i18n.py` — module-level `init(lang)` loads `client/translations/<lang>.json` into memory (empty dict, i.e. English passthrough, if the file doesn't exist, logged as a warning for any non-English `lang` since that fallback is otherwise silent); `t(key)` looks up `key` and falls back to `key` itself; `is_rtl()` is true for `ar`/`he`/`fa`/`ur`; `current_lang()` returns the active code; `apply_layout(app)` applies the current language's layout direction *and* (RTL only) the bundled Arabic UI font to `app` - see below. Only one language is ever loaded at a time (global state, not per-window).
  - **Fixed 2026-08-13: `translations/` path resolution was wrong for ~12 days, silently breaking every Arabic string.** `client/i18n.py` moved to `client/helper/i18n.py` in a 2026-08-01 reorg; the `os.path.dirname(__file__)`-relative path to `translations/` was never updated, so it looked for `client/helper/translations/<lang>.json` (doesn't exist) instead of the real `client/translations/<lang>.json` (a sibling of `helper/`, not a child). `init()` silently fell back to its empty-dict branch - `is_rtl()` still flipped the layout direction correctly (pure lang-code check, no file needed), so the language toggle *looked* like it worked (RTL layout, mirrored icons) while `t()` returned every key untranslated. This is exactly the kind of bug that's invisible from reading `t()`'s call sites - only from actually switching to Arabic and looking. Fixed by resolving `_TRANSLATIONS_DIR` correctly and logging a warning if a non-English language's file still isn't found, so a future path mistake fails loudly instead of silently.
- **Language preference is a per-user server-side setting, mirroring `theme` field-for-field**: `User.language` (client+server `models/User.py`, `getLanguage()`/`setLanguage()`), `users.language` DB column (`server/dev-scripts/init_db.py`; existing installs need `dev-scripts/migrate_add_user_language.py`), `PATCH /users/language` (mirrors `PATCH /users/theme`, same guest-blocked/self-only auth shape), `ClientRequests.updateLanguage`. Settable two ways: the sidebar quick-toggle button (`MainWindow.btnLanguage`/`chgLanguage()`, English⇄Arabic flip) or the **Language** combo in `DialogSettings` (adds a "Default (System)" option, `None`, alongside English/Arabic).
- **Why a language change requires a restart (`MainWindow._applyLanguageChange`, mirrors `_applyThemeChange` exactly - same "Restart Now / Later / Cancel Change" modal):** every `t()` call resolves to a plain string baked into a widget at construction time, not re-evaluated later - there's no Qt `retranslateUi`-style live-refresh path. Choosing "Restart Now" saves the preference then calls `logout()`; the *next* login is what actually applies it, not the restart itself.
- **A saved preference applies with no restart the first time, on every fresh login** - `Login.py`'s `on_done` (right after a successful login, before the role `MainWindow` is constructed) calls `i18n.init(user.getLanguage())` then `i18n.apply_layout(QApplication.instance())`. `main.py` still calls `i18n.init(QLocale.system().name()[:2])` + `apply_layout()` once at process start purely so the pre-login `LoginWindow` itself has *some* language active; a `None` preference (never set, or explicitly reset to "Default (System)") just leaves that OS-locale default in place rather than forcing English.
- **RTL layout direction is app-wide** (`QApplication.setLayoutDirection`, inside `apply_layout()`), not per-widget - Qt cascades it to every window built afterward. The only per-widget overrides in the codebase (`MainWindow.py`'s two `btn.setLayoutDirection(LeftToRight)` calls) are on collapsed, icon-only sidebar buttons with no text, unrelated to this.
- **The app-wide UI font also switches for Arabic, via that same `apply_layout()`** - none of Qt's own fallback fonts are guaranteed to render Arabic well on every end-user machine, so for an RTL language it registers the bundled Noto Naskh Arabic font (`QFontDatabase.addApplicationFont`, once - cached in `_ARABIC_FONT_FAMILY`) and calls `app.setFont()` with it; switching back to a non-RTL language restores the app's real original default font exactly (captured once into `_ORIGINAL_FONT` before ever being touched, not hardcoded).
- **Sidebar's default dock side follows reading direction** (`MainWindow.__init__`, the initial `self.addToolBar(...)` call): left for English, right for Arabic. Still just a starting point - the sidebar's own right-click context menu (`_sideBarMoveMenu`/`_moveSidebar`) can move it to either side or the bottom regardless of language, same as before.
- **Directional icons (qtawesome chevrons) don't auto-mirror for RTL and need picking by hand** - Qt only auto-mirrors its own `QStyle`-drawn standard icons based on `layoutDirection`; a `qtawesome`-rendered icon is a plain static pixmap, so a "Back" button showing a left-chevron would still point left even once RTL layout puts it on the right-hand side of the button row, now pointing the wrong semantic direction. Fixed at both call sites that pair directional icons this way: `TabbedDialog.__init__` (`btnBack`/`btnNext`, used by `DialogPTW`/`DialogIC`'s wizard tabs) and `WidgetPidWiring` (`btnPrevPage`/`btnNextPage`, the P&ID/wiring document page nav) - both pick `chevron-left`/`chevron-right` (or the reverse) based on `i18n.is_rtl()` at construction time. Other directional-looking icons in the codebase (`DialogPtwAlarms`/`TabServerLogs`'s collapse/expand chevrons, `Login.py`'s login-arrow, `MainWindow`'s logout-arrow) are disclosure/symbolic icons rather than a paired prev/next control and were deliberately left alone.
- **Mixed Arabic/English text entry needs no special handling** - verified empirically (no code change): no `QLineEdit`/`QTextEdit` in the codebase has a character-restricting `QValidator`/input mask, and Qt's own text engine already applies the Unicode Bidi Algorithm per-paragraph (`QTextBlockFormat.layoutDirection()` defaults to `LayoutDirectionAuto`) independent of the app's cascaded `layoutDirection` - so a field displays/aligns Arabic or English content correctly based on what's actually typed into it, regardless of the app's own language setting.
- **PDF reports need real support code, unlike the Qt UI** - ReportLab has no bidi/text-shaping engine and its built-in fonts (Helvetica et al.) have zero Arabic glyphs. `reports/ArabicText.py` (`containsArabic`/`bidiVisual`/`isRtlBase`/`pdfMarkup`) wraps `arabic_reshaper` (joins Arabic letters into their correct contextual forms) + `python-bidi`'s `get_display()` (reorders into left-to-right visual order, since ReportLab always draws strictly left-to-right) and splits the result into script runs so each can be font-tagged independently - Noto Naskh Arabic (`client/fonts/NotoNaskhArabic/`, OFL-1.1) for Arabic runs, the paragraph's own font for everything else. `ReportGenerator.arabicParagraph(text, style, forceAlignment=True)` is the drop-in replacement for `Paragraph(html.escape(text), style)` wherever a field is free text a user typed (so may be Arabic, English, or mixed): it right-aligns the whole paragraph when `text`'s own base direction is Arabic, unless `forceAlignment=False` (e.g. a centered signature-block cell, which should stay centered regardless of script). `ReportGenerator._registerArabicFonts()` registers the two font files with ReportLab once (checked via `pdfmetrics.getFont()`, not re-registered every report). Wired into all four PDF report methods (`ptwReport`/`icReport`/`MOSReport`/`riskAssessmentReport`) and the Excel export (right-aligns Arabic cells; no font/bidi issue there since openpyxl+Excel already render Arabic natively).
  - **Font choice (2026-08-13): Noto Naskh Arabic, not the originally-shipped Noto Sans Arabic** - compared candidates by actually rendering the same sample text through this exact reshape→bidi→draw pipeline (not just eyeballing font specimens), since the pipeline does no real OpenType ligature substitution and not every attractive Arabic font survives that. Noto Sans Arabic read as generic UI chrome rather than a document; Amiri (traditional calligraphic Naskh) looked the best but showed occasional join artifacts without full ligature shaping; Noto Kufi Arabic and Scheherazade both broke into disconnected/placeholder glyphs entirely and were ruled out. Noto Naskh Arabic was the best balance - real book/print Naskh proportions, renders cleanly through this pipeline, same OFL-1.1 license and Google Noto family as what it replaced.
- **`t()`/`ar.json` coverage extended 2026-08-12 from the PTW/IC creation flow to the entire client**: `MainWindow.py`, `Login.py`, all 8 role-specific window files, every remaining `dialogs/Dialog*.py` file, all 8 `tables/Table*.py` files, and (closing gaps left over from the original 2026-06-19 pass) the rest of `DialogPTW.py`/`DialogIC.py`/`DialogCompleteIsolation.py`/`WidgetPidWiring.py`/`RiskPreview.py`. `ar.json` grew from 108 to 581 entries, then had a further wording pass for quality/consistency. Verified by an AST-based sweep (parses every `client/**/*.py`, finds every literal-string argument to a call named `t`, checks each is a key in `ar.json`) - zero gaps as of this pass, but a future string added without its `ar.json` entry won't be caught automatically; re-run that sweep after adding new `t()` call sites.
- **Topbar menu group names translated (2026-08-13)**, closing the gap noted above in an earlier pass. `topbarGroups` dict keys (passed by each role window to `setAvailableTabs`) were renamed from `'&PTWs'`/`'&ICs'`/`'&Users'`/`'&Risks'`/`'&View'`/`'&Help'` to plain, stable, never-displayed identifiers (`'PTWs'`/`'ICs'`/`'Users'`/`'Risks'`/`'View'`/`'Help'`) across all 8 role-window files and `MainWindow.setTopbarButtons()`'s two `group_widgets.pop("View", [])`/`pop("Help", [])` special cases. `make_menu_btn(key, actions)` now looks up the display label via `t(key)` and a keyboard mnemonic letter via a `MENU_MNEMONICS = {'en': {...}, 'ar': {...}}` table (English mnemonics are each key's original first letter, unchanged; Arabic ones are hand-picked non-colliding letters chosen from within each translated label - e.g. "PTWs"/"Risks" both translate to phrases starting with ت, so one of them uses a different in-word letter instead), then inserts `&` at that letter's position in the *translated* label and extracts the actual shortcut via Qt's own `QKeySequence.mnemonic(text)` (confirmed empirically to handle Arabic/Unicode mnemonic characters correctly, not just ASCII).
- **Table cell values and combo-box options also translate now (2026-08-13), not just static chrome.** Previously only labels/buttons/messages were translated - a Department/Type/Status/Location *value* itself (in a table cell or a dropdown) still showed raw English even in Arabic mode, and naively translating it would have broken filtering/comparison/server payloads, since those values are also used as data (dict keys, filter-match values, `.currentText()` reads feeding straight into `setRole()`/`setDepartment()`/etc.). Fixed with a consistent display/value-separation pattern applied everywhere such a value appears:
  - **`widgets/CheckableComboBox.py`** (the per-column table filter dropdown): `setItems(values, ..., display=None)` gained an optional `display` function (e.g. `t`) - each row shows `display(value)` as text but stores the real `value` in `Qt.ItemDataRole.UserRole`; `checkedItems()`/`setCheckedOnly()` operate on that real value, never the displayed text. `display=None` (every pre-existing caller) keeps value and text identical - fully backward compatible.
  - **Plain `QComboBox` enum pickers** (Role/Department/Type/State/Fast-Track-Yes-No dropdowns across `DialogUser.py`, `DialogSettings.py`, `DialogIsolation.py`, `DialogIsolationItem.py`, `DialogIC.py`'s `typeCombo`, `DialogPTW.py`'s `boxFastTrack`): converted to the pattern `DialogPTW.py`'s `boxPTWType`/`boxLocation`/`boxAreaClass` and `DialogIC.py`'s `boxExecutionDepartment`/`boxLocation` already used - populate via `addItem(t(value), value)`, preset via `.findData(rawValue)` + `.setCurrentIndex(...)` (never `.setCurrentText(...)`), read via `.currentData()` (never `.currentText()`).
  - **Table cells** (`TablePTWs.py`/`TableUsers.py`/`TableICs.py`): each has a `_TRANSLATABLE_FIELDS` set naming which columns hold fixed vocabulary (vs. free text/names/dates/ids) and a `_makeCell(col, value)` that shows `t(value)` while stashing the real `value` in the cell's `UserRole` (mirrors the pre-existing `_FastTrackItem`/`_LongTermItem` pattern, which did exactly this for one column already); `_cellFilterText(item)` prefers `UserRole` over `.text()` everywhere filtering/sorting reads a cell. `filterColumn(field, values)` (used by home-dashboard donut-segment drill-down) was changed to index by the stable field name in `summeryFields` (e.g. `'location'`), not the translated display label in `summeryLabels` - both call sites (`AdminMainWindow._openUsersFilteredByDept`, `MainWindow._openRunningFilteredByLocation`) updated to match; the donut segments' own labels are separately translated via `t()` where they're built.
  - **Simpler tables with no filter dropdown** (`TableIsolations.py`/`TableIsolationItems.py`) just translate the one enum-valued column's display text directly (no `UserRole` needed - confirmed nothing reads the raw value back off those cells); `TableIsolationItems.py`'s `state` values are lowercase (`'open'`/`'close'`, from `enum.auto()`) - `ar.json` has matching lowercase keys, distinct from the capitalized `Open`/`Close` used as button labels elsewhere. `TabServerLogs.py`'s single (non-per-column) log-level filter combo just gained `display=t` - the underlying level strings it matches against real `[LEVEL]` log-file text stay raw English, only the dropdown's own labels are translated.
  - `client/translations/ar.json` grew accordingly (all 16 `UserDepartments`, `Isolation.Types`/`IC.Types`, `IC.Status` values, log levels, etc.) - proper-noun company names (`Petrojet`/`Petromaint`/`Egypt Gas`) and universal acronyms (`IT`/`HVAC`) were deliberately kept as English identity entries, matching the existing `Phase VII`/`Scarab`/`Simian`/`MSDS`/`SIMOPS` precedent.
- **Caught in passing while verifying this pass, fixed by a separate concurrent session (not this one) editing the same file**: the original 2026-06-19 `ar.json` had `"Hazard"`/`"Non-Hazard"` as keys, but `PTW.AreaClasses`'s real enum values are `"Hazardous"`/`"Non-Hazardous"` (with the suffix) - that translation had been silently dead ever since (the Area Class dropdown in `DialogPTW.py` always showed untranslated English, exactly the "coverage looks complete but a key is subtly wrong" failure mode the AST-based coverage sweep can't catch, since it only verifies a key *exists*, not that it's the *right* key). Renamed to the correct `Hazardous`/`Non-Hazardous`, freeing up `Hazard`/`Non-Hazard`... actually just `Hazard`, reused for `RiskPreview.py`'s "Hazard" column header, a genuinely different, valid use.

### Role-Specific Windows (`client/windows/`)

All role-specific views are implemented as classes in `client/windows/` — one file per class, each subclassing the base `MainWindow` (`windows/MainWindow.py`). After login, `main.py` routes to the appropriate class based on the user's role:

- `AdminMainWindow` — full access
- `GuestMainWindow` — unauthenticated visitor; creates/views PTWs
- `UserMainWindow` — create PTWs, manage own permits. Has both a **Requested PTWs** tab (tracking-only — any PTW still `UNDER_REVIEW` that isn't currently this user's turn to act on) and an **Under Review** tab (actionable — this user's role+department is in the currently pending approval stage, e.g. a department rep on an `EX`-type permit). Also has Requested/Pending/Active/Sanctioned/Closed IC tabs (no Under Review — never populated for this role); the FAB on the Requested ICs tab creates a new IC
- `CoordinatorMainWindow` — PTW approval coordination
- `IssuingMainWindow` — run/hold/close confirmation. Also has Under Review/Pending/Active/Sanctioned/Closed IC tabs (no Requested — never populated for this role)
- `SafetyMainWindow` — risk assessments, safety approvals
- `ManagerMainWindow(loggedUser, role)` — one shared class for `PDH`/`PGM`/`SOD`/`DFGM`; `main.py` passes the role label in, it's not four separate classes
- `IsolatorMainWindow` — Pending (+ Complete Isolation) / Active (view-only) / Closing (+ Complete De-isolation) / Sanctioned IC tabs only, no PTW tabs; FAB is permanently hidden

### Sidebar, Topbar & Home Page

Each role-specific window's `__init__` calls `MainWindow.setAvailableTabs(sidebarGroups, topbarGroups)` once, which drives three things:

- **Sidebar** (`setSidebarButtons`) — a curated, positional list of button groups (`list[list[QPushButton]]`, separators between groups). Kept to a handful of the most-used buttons per role (≤8 nav buttons is the target); everything is still reachable via the topbar regardless of sidebar curation. Only `UserMainWindow` and `IssuingMainWindow` actually trim (12→8 and 11→8 nav buttons); the other five roles have ≤8 already, so their sidebar and topbar cover the same buttons.
- **Topbar** (`setTopbarButtons`) — always the *complete* button set for the role, declared explicitly as a `dict[str, list[QPushButton | None]]` mapping a menu label (e.g. `'&PTWs'`) to the buttons shown in that dropdown, in order; a `None` entry inserts a separator within the menu. `'&View'` and `'&Help'` always exist regardless of what a subclass supplies — `'&View'` gets the sidebar-visibility toggle and Left/Right/Bottom dock actions prepended, `'&Help'` gets "About PTW"/"About Qt" appended.
- **Home page** (`buildHomePage()` / `updateHomeDashboard()`) — a template-method pair (same override pattern as `refreshGUI()`), invoked once `setAvailableTabs` knows the role's full button set. The base `MainWindow.buildHomePage()` builds a live [`DonutChart`](client/widgets/DonutChart.py) dashboard: a donut of PTWs in the approval cycle (Requested/Under Review/Returned/Approved) and one of Running PTWs split by location — each only appears if at least one of its underlying tabs is reachable by the role at all (sidebar *or* topbar). Clicking a segment (or its legend row) calls the corresponding sidebar button's `.click()`; location segments additionally call `TablePTWs.filterColumn('Location', {location})` to pre-filter the target tab. `updateHomeDashboard()` is re-run after every data refresh (`refreshPtwUserGUI`) to keep segment counts current. `AdminMainWindow` (no PTW tabs) overrides both hooks with a Users-by-Department donut instead, using `TableUsers.filterColumn('Department', {dept})` the same way.

---

## Known Issues / Notes

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for the full backlog of open bugs and security items with fix guidance.

- **File storage is local filesystem** — attachments and MIWI documents are stored on the server's local disk, under `paths.DATA_DIR` (an OS-appropriate per-machine directory outside the repo by default, overridable via `PTW_DATA_DIR` — see `server/paths.py`), not beside the code. Regular backups of `DATA_DIR/miwi/` (per-department subfolders) and `DATA_DIR/ptw-*-attachments/` are recommended — `server/dev-scripts/backup.sh`/`.ps1` already do this.
