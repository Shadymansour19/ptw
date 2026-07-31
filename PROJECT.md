# PTW System — Permit To Work

## Overview

This is a desktop-based **Permit To Work (PTW)** management system built for industrial operations (Rashpetco). It enforces a structured, multi-stage safety workflow that governs when and how maintenance or hazardous work is authorized, executed, and closed. The system tracks approvals, manages equipment isolations, and provides a full audit trail for every permit.

The application runs as a **PyQt6 desktop client** communicating with a **Flask REST API server** backed by **PostgreSQL**.

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
| Reports      | ReportLab (PDF), Pillow, qrcode     |
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

After a PTW is created, it enters an approval cycle defined by `PTWData.requiredApprovers()`, which returns a **list of sequential stages**, each stage being a **list of parallel `Approver` requirements** (`PTWData.Approver(role, department=None)`):

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

A PTW no longer adds PDH/PGM/SOD/DFGM stages for a protective isolation — that manager approval now happens once, on the linked Protective-type IC's own approval chain (`IC.requiredApprovers()`, see [Isolation Management](#isolation-management)), not duplicated on the PTW itself. This changed 2026-07-25; previously a PTW with a protective isolation + MOS also required `[PDH]→[PGM]→[SOD]→[DFGM]` on its own chain.

`PTWData.pendingApprovers()` returns the flattened list of `Approver`s still outstanding (from the first unsatisfied stage onward) — used by `MainWindow.viewApprovals` to show a "Pending Approvers" list alongside the approval history, and by `getApprovalStatus(role, department)` to decide whether it's a given user's turn to act.

Each approval action is recorded with the approver's username, timestamp, action taken, and an optional comment. Any `RETURNED` action anywhere in the log immediately marks the whole PTW `RETURNED`, regardless of position — this matters once parallel approvers exist, since a later `APPROVED` from a sibling approver must not paper over an earlier return.

A required `Approver` with a department different from the PTW's own `department` still sees it: `GET /ptws` filters the server's in-memory PTW cache so a department sees a PTW if it either owns it or currently has a pending required-approver slot on it (`server/app.py` — `_ptwVisibleToDepartment`, `PTWData.pendingApprovers()`). See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) (Fixed § M12) for the history.

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
    └──── [PA sends hold request + selects keep_isolations]
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

**`running_status` is computed, not stored** — `PTWData.__updateRunningStatus()` (both `client`/`server` `PTWData.py`) replays `run_cycles` forward on every read (same pattern as `approval_status`/`approvals`, see [Database Schema](#database-schema)): a stop request (`stop_pa_request`/`stop_ia_action`) is checked ahead of `run_ia_action` so a cycle still resolves correctly even where `run_ia_action` didn't survive the old flat-columns migration (see `RunCycle` below); a rejected run/stop request simply leaves the replay's running status wherever it already was, which is what makes a separate `prev_running_status` snapshot unnecessary — it no longer exists.

**Archiving is a separate `is_archived` boolean, not a `running_status` value** — a `CLOSED` PTW can be archived manually (`POST /ptws/archive`, any authenticated non-guest user) or automatically. A daemon thread (`server/app.py` — `_auto_archive_closed_ptws`) sweeps `globalData.allPTWs` every `_AUTO_ARCHIVE_CHECK_INTERVAL` (1 hour) and archives any `CLOSED` PTW whose last `RunCycle.stop_ia_timestamp` is `_AUTO_ARCHIVE_AFTER_DAYS` (7 days) or older. Both paths call the same `PtwsDb.archivePTWs()` (`UPDATE ptws SET is_archived = TRUE`) and broadcast the same `ptw_archived` SSE event with `"by"` set to the acting user (manual) or `"system"` (automatic). `running_status` keeps showing the real last state (`CLOSED`) forever, even once archived — `is_archived` is checked independently wherever code needs to know that (e.g. `PtwsDb.getAllPTWs()`/`getArchivedPTWs()` filter on it, not on `running_status`).

**`RunCycle` — full audit trail for the running cycle** (`PTWData.RunCycle`, `client`/`server` `PTWData.py`, kept in sync): `PTWData.run_cycles` is an ordered list of `RunCycle` records, one per pass through the state machine above — a fresh `RunCycle` is appended every time a PA sends a run request (including resuming from `HELD`), and its `stop_*` fields are filled in later, in place, as that same cycle progresses. Each `RunCycle` has:

- `run_pa` / `run_pa_timestamp` — who requested the run, and when.
- `run_ia` / `run_ia_action` (`Approved`/`Rejected`) / `run_ia_comment` / `run_ia_timestamp` — the IA's response to the run request.
- `stop_pa` / `stop_pa_request` (`Hold`/`Close`) / `stop_pa_comment` / `stop_pa_timestamp` — the PA's hold-or-close request, once running.
- `stop_ia` / `stop_ia_action` (`Approved`/`Rejected`) / `stop_ia_comment` / `stop_ia_timestamp` — the IA's response to that stop request.
- `keep_isolations` — the isolation tags selected to remain linked for this specific hold (submitted alongside the hold request; empty for a close, or if this cycle hasn't reached a stop request yet).

A cycle is "open" (`RunCycle.isOpen()`) as long as its run wasn't rejected and its stop hasn't been approved; `PTWData.currentRunCycle()` returns the last cycle if it's still open (used for `getPerforming()`/`getIssuing()` — the live PA/IA of an in-progress run — mirroring the old behavior where those fields went blank once a hold/close was accepted). `PTWData.lastRunCycle()` always returns the most recent cycle regardless of whether it's still open. `PTWData.operativeRunCycle()` walks backward from the end and skips any trailing cycle(s) whose run was rejected — a rejected resume-from-`HELD` attempt appends its own (otherwise-empty) cycle for the audit trail, but never actually changes running/isolation state, so reads that care about "what's actually in effect" (`getKeepIsolations()`, and `ReportGenerator`'s de-isolation report reading back who performed the hold/close) use `operativeRunCycle()` rather than `lastRunCycle()`, so they aren't fooled by that trailing no-op cycle into looking blank. This replaces the old flat, overwritten `performing`/`issuing`/`hold_*`/`close_*`/`keep_isolations` fields, which silently lost history on every rejection (a reject handler blanked its own fields instead of recording who rejected and when) and on every hold/close acceptance (which wiped `performing`/`issuing` rather than keeping them alongside the new stop record).

---

## Isolation Management

**Architecture as of 2026-07-25: plain isolation tags are purely declarative; all runtime isolation state lives on IC.** Before this date, a separate `isolations` DB table + `Isolation.linkPTW`/`holdPTW`/`unlinkPTW` tracked which PTWs currently held which physical tag, mirrored by a global "Isolations" browse tab in the client. That entire subsystem has been removed. It is not documented below except where noted as history — don't resurrect it from an older version of this file.

### Isolation (declarative only)

`Isolation` (`client`/`server` `Isolation.py`) is now a minimal, stateless record: `type` (Mechanical/Electrical/Self/Protective System/Other), `tag`, `description` — nothing else. It exists solely to declare, on a PTW request, which isolations that PTW is expected to need (`PTWData.isolations: list[Isolation]`, edited via the `TablePTWIsolations` widget embedded in `WidgetPTW.DialogPTW`'s Isolation tab). It carries no linkage/runtime state and is never looked up in a global registry — there is no `GET /isolations`, no `globalData.isolations`, no `isolations` DB table.

The system pre-loads a library of known isolation points (tags like `XV-7227A`, `LV-1409E`, etc.) covering mechanical, electrical, protective, and self-isolations across all plant areas, offered when adding an isolation to a PTW's declarative list.

**Before a PTW can run, it must be linked to an actual `IC`** (see below) — that's where physical isolation execution, approval, and linkage now live. See [Running Cycle](#2-running-cycle) / the run-accept gate below for the enforcement point.

### IC (Isolation Certificate)

A formal, independently-approved isolation-request document — class `IC` (`client`/`server` `Isolation.py`, renamed from `IsolationCertificate` 2026-07-25; DB table `ics`, renamed from `isolation_certificates` — see [Database Schema](#database-schema)). An IC's `items` list references individual isolation tags/points; the IC itself is the approval document wrapping them (type, department, location, equipment, reason, long-term flag), and — since 2026-07-25 — the sole place PTW↔isolation linkage state lives.

**Fields:** `type` (Mechanical/Electrical/Self/Protective System/Other — same enum as declarative `Isolation`), `requestor_department`/`execution_department` (split from a single `department` field 2026-07-26 — see below), `requestor`/`requestor_timestamp` (who submitted the IC form, mirrors PTW's own `requestor`), `approvals` (list of `Approval`, see below), `location`, `equipment`, `reason`, `items` (list of `IC.IsolationItem`: tag, description, state `OPEN`/`CLOSE`, `lock_num`, `lock_box_num`), `isolate_asap` (checkbox — see below), `long_term`/`long_term_reason`, `linked_ptws`/`held_by` (the IC's own runtime linkage lists — see [PTW↔IC Linkage](#ptwic-linkage) below), and four groups of requestor/issuing/isolator username+timestamp fields — `isolate_*` (fully implemented), `sanction_*` (sanction for test), `reisolate_*`, `deisolate_*` (these three groups still deferred, see below). `isolate_issuing_action` (`'Approved'`/`'Returned'`/`''`) records the IA's decision on an isolate request.

**`requestor_department` vs `execution_department`** — `requestor_department` is stamped server-side from the creator (`user.getDepartment()`, never trusted from the payload), same as before the split. `execution_department` — the department actually responsible for carrying out the physical isolate/de-isolate work — must always be explicitly supplied by the client; `POST /ics` 400s if it's missing. For a `Self`-type IC, `execution_department` is required to equal `requestor_department` — enforced twice: client-side, `DialogIC._certTypeChanged()` locks (disables) the execution-department combo and syncs its value the moment `Self` is selected; server-side, `addICRequest` independently 400s if a `Self`-type submission's `execution_department` doesn't match `requestor_department`, so the rule holds even against a client that skips the dialog's lock. **Routing**: once an IC reaches `Pending` or `Closing` (see `getStatus()` below), `MainWindow.refreshICsGUI()` only shows it to an `Isolator` whose own department matches `execution_department` — an isolator elsewhere doesn't see it queued at all, in either tab. The two execute endpoints (`/ics/isolate-execute`, `/ics/deisolate-execute`) independently re-check the same department match server-side (403 otherwise) — routing alone is a UI convenience, not a security boundary, so both sides enforce it.

**`isolate_requestor`/`isolate_requestor_timestamp` are *not* the IC creator** — that's the top-level `requestor`/`requestor_timestamp` above. `isolate_requestor` instead records whoever requests that the (already-approved) isolation actually be carried out — a distinct, later action that may be performed by someone other than the original requestor. That's also why `isolate_requestor_timestamp` (and its `sanction_*`/`reisolate_*`/`deisolate_*` siblings) has no `datetime.now()` fallback default the way `requestor_timestamp` does — it must stay unset until that action genuinely happens, not read as "now" the moment a fresh object is instantiated. `isolate_asap` is a requestor-set checkbox meaning "trigger that isolate-request automatically the moment the IC is fully approved" — implemented: `POST /ics/approvals` checks it right after persisting the approval that completes the chain, and if set, auto-stamps `isolate_requestor`/`isolate_requestor_timestamp` itself (skipping the manual "Request Isolate" click below) — it does **not** skip IA confirmation or isolator execution, it just skips the person having to click the button.

**Approval chain — implemented, mirrors `PTWData`'s `Approval`/`Approver`/`requiredApprovers()`/`pendingApprovers()` pattern exactly** (`IC.Approval`/`Approver`/`ApprovalActions`, `requiredApprovers()`/`_stageSatisfied()`/`_pendingStageIndex()`/`pendingApprovers()`/`getApprovalStatus()`, all in `client`/`server` `Isolation.py`, kept in sync). `requiredApprovers()` returns `[[Issuing]]` for a normal IC, or `[[Issuing], [PDH], [PGM], [SOD], [DFGM]]` for a `Protective System`-type IC. **Note this manager-approval requirement lives only here, on the IC's own chain** — as of 2026-07-25, a PTW's own `requiredApprovers()` no longer adds PDH/PGM/SOD/DFGM for a protective isolation (see [Approval Cycle](#1-approval-cycle)); linking a Protective-type IC to a PTW is now the only place that approval is collected, rather than being required twice. `getApprovalStatus(role=None)` gives the overall chain status (`Requested`/`Returned`/`Approved`); `getApprovalStatus(role, department)` gives one viewer's status: the action they already took, `Requested` if it's their turn right now, or `None` if they're not an approver at all. `POST /ics/approvals` (mirrors `/ptws/approvals`) appends an `Approval` and re-authorizes on every call — the caller's `getApprovalStatus(role, department)` must currently be `Requested`, otherwise 403. Like PTW, there is no permanent "Rejected" outcome — `ApprovalActions`/`Status` are `Approved`/`Returned` only (no `Rejected`), exactly matching `PTWData.ApprovalActions`/`ApprovalStatus`. Approved or returned-for-edits via `MainWindow.acceptIC`/`requestEditsIC` (menu options "Accept"/"Request Edits", mirroring PTW's own `optionAcceptPTW`/`optionRequestEditsPTW`) → `ClientRequests.updateApprovalIC` → server; broadcasts an unrestricted (no role filter) `ic_approval` SSE event, same as PTW's `ptw_approval`, so whichever role is up next gets notified regardless of which one that is.

**The isolate cycle (request → IA confirm → isolator execute) is fully implemented**, three roles in sequence:
1. **Request** — a `User`, from the **Approved** tab, clicks **Request Isolate** (`optionRequestIsolateIC`) → `MainWindow.requestIsolateIC` → `POST /ics/isolate-request` (guarded to `getStatus() == Approved`). Stamps `isolate_requestor`/`isolate_requestor_timestamp`, and — defensively — resets `isolate_issuing`/`isolate_issuing_timestamp`/`isolate_issuing_action` to blank, so a re-request after a prior Return can't leave a stale decision lying around to mask the fresh request.
2. **IA confirm** — `Issuing`, from the **Isolate Confirming** tab, clicks **Confirm Isolate** or **Return Isolate Request** (`optionConfirmIsolateIC`/`optionReturnIsolateIC`) → `MainWindow.confirmIsolateIC`/`returnIsolateIC` → `ClientRequests.confirmIsolateIC(..., response: bool)` → `POST /ics/isolate-confirm` (guarded to `getStatus() == Isolate Confirming`, role must be `ISSUING`). Stamps `isolate_issuing`/`isolate_issuing_timestamp`/`isolate_issuing_action` (`Approved` or `Returned`). No comment field — accept/return is a plain decision, unlike the main approval chain's `Approval.comment`.
3. **Isolator execute** — `Isolator`, from the **Pending** tab, clicks **Complete Isolation** (`optionExecuteIsolateIC`) → `MainWindow.executeIsolateIC`. If the IC has items, this opens `DialogCompleteIsolation` first — a table of all items (Tag/Description/State read-only, **Lock #**/**Lock Box #** editable, both optional/blank-is-fine) — otherwise it's a plain Yes/No confirm. → `POST /ics/isolate-execute` (guarded to `getStatus() == Pending`, role must be `ISOLATOR`), with an optional `items` payload. The server merges `lock_num`/`lock_box_num` into `ic.items` **by tag** (`tag`/`description`/`state` stay server-authoritative — an unrecognized tag in the payload is silently dropped, never inserted as a new item). Stamps `isolate_isolator`/`isolate_isolator_timestamp` → IC becomes `Active`.

A **Return** at step 2 does **not** clear `isolate_requestor` — it's kept as a permanent record of who originally asked, alongside `isolate_issuing`/`action='Returned'` recording who declined it and when. `getStatus()` treats a `Returned` isolate confirmation as reverting the IC to `Approved` (ready for a fresh Request Isolate), which is why step 1 above resets the stale `isolate_issuing*` fields on every new request — otherwise the leftover `Returned` decision would keep masking the new request's status.

**The de-isolate cycle (request → IA confirm → isolator execute) is implemented too, an exact mirror of the isolate cycle above**, three roles in sequence, but starting from `Active` instead of `Approved`:
1. **Request** — a `User`, from the **Active** tab, clicks **Request De-isolate** (`optionRequestDeisolateIC`) → `POST /ics/deisolate-request` (guarded to `getStatus() == Active`). Stamps `deisolate_requestor`/`deisolate_requestor_timestamp`, and resets `deisolate_issuing`/`deisolate_issuing_timestamp`/`deisolate_issuing_action` — same defensive reset as isolate-request, for the same reason (a re-request after a prior Return must not leave a stale decision behind).
2. **IA confirm** — `Issuing`, from the **Deisolate Confirming** tab, clicks **Confirm De-isolate** or **Return De-isolate Request** (`optionConfirmDeisolateIC`/`optionReturnDeisolateIC`) → `POST /ics/deisolate-confirm` (guarded to `getStatus() == Deisolate Confirming`, role must be `ISSUING`). Stamps `deisolate_issuing`/`deisolate_issuing_timestamp`/`deisolate_issuing_action`.
3. **Isolator execute** — `Isolator`, from the **Closing** tab, clicks **Complete De-isolation** (`optionExecuteDeisolateIC`) → `POST /ics/deisolate-execute` (guarded to `getStatus() == Closing`, role must be `ISOLATOR`). Stamps `deisolate_isolator`/`deisolate_isolator_timestamp` → IC becomes `Closed` — this is the *only* path to `Closed`. Unlike `isolate-execute`, this endpoint doesn't take an `items` payload — no lock-clearing UI yet, just the plain confirm.

**`getStatus()`** layers both cycles on top of the approval chain: `deisolate_isolator` set → `Closed`; `sanction_isolator` set and not yet reversed by `reisolate_isolator` → `Sanctioned` (both `sanction_*`/`reisolate_*` cycles still deferred, so unreachable today); else if `isolate_isolator` or `reisolate_isolator` is set (physically isolated) — nested inside that: if `deisolate_requestor` is set, `deisolate_issuing_action == Approved` → `Closing` (awaiting isolator), `deisolate_issuing_action == Returned` → falls through to plain `Active`, otherwise → `Deisolate Confirming` (awaiting IA); with no `deisolate_requestor`, plain `Active`; else if `isolate_requestor` is set: `isolate_issuing_action == Approved` → `Pending` (awaiting isolator), `isolate_issuing_action == Returned` → falls through to `getApprovalStatus()` (i.e. `Approved`, ready to re-request), otherwise → `Isolate Confirming` (awaiting IA); with no `isolate_requestor` at all, falls through to `getApprovalStatus()` (`Requested`/`Returned`/`Approved`). Row/type coloring (`backgroundColor()`/`foregroundColor()`/`backgroundColorForType()`) mirrors `PTWData`'s pattern: Mechanical=gray, Electrical=yellow, Self=green, Protective System=red, Other=neutral gray.

**Tab routing is per-viewer, like PTW's Requested/Under Review split** (`MainWindow.refreshICsGUI()`), one tab per `Status` value: **Requested** → **Under Review** (per-viewer, whoever's approval stage is current) → **Approved** → **Isolate Confirming** → **Pending** → **Active** → **Deisolate Confirming** → **Closing** → **Sanctioned** → **Closed**. A viewer whose approval stage already passed (e.g. Issuing, once a `Protective`-type IC has moved on to PDH) falls back to **Requested** as a tracking view — `IssuingMainWindow` doesn't have a Requested button today, so that specific tracking case is a known, accepted gap (rare: only affects multi-stage `Protective` ICs after Issuing's own stage is done).

Per-row menu visibility uses a `TablePTWs.MenuOption(..., visibleFor=lambda ic: ...)` predicate (default `None` = always visible), checked in `TableICs.showContextMenu` only — `TablePTWs`'s own context menu is untouched, so this doesn't affect PTW menus. Used defensively on both cycles' actions (e.g. `optionConfirmDeisolateIC.visibleFor` checks `getStatus() == Deisolate Confirming`) even though tab routing alone already guarantees the right rows end up in the right tab — belt-and-suspenders against a stale row lingering between an action and the next refresh.

**Roles wired:**
- `UserMainWindow` — Requested / Approved (+ Request Isolate) / Isolate Confirming (view-only) / Pending / Active (+ Request De-isolate) / Deisolate Confirming (view-only) / Closing (view-only) / Sanctioned / Closed tabs; FAB on the Requested tab creates a new IC (`TableICs.addNewICDialog()`), submitting via `POST /ics`.
- `IssuingMainWindow` — Under Review (with Accept/Request Edits) / Approved (view-only) / Isolate Confirming (+ Confirm Isolate/Return Isolate Request) / Pending (view-only) / Active (view-only) / Deisolate Confirming (+ Confirm De-isolate/Return De-isolate Request) / Closing (view-only) / Sanctioned / Closed tabs.
- `ManagerMainWindow` (PDH/PGM/SOD/DFGM) — Under Review tab only (with Accept/Request Edits) — Managers are only ever pulled into a `Protective`-type IC's chain, after Issuing.
- `IsolatorMainWindow` — Pending (+ Complete Isolation) / Active (view-only) / Closing (+ Complete De-isolation) / Sanctioned tabs only, no PTW tabs, FAB permanently hidden. No Approved, Isolate Confirming, or Deisolate Confirming tab — nothing for the isolator to do at any of those stages.
- `CoordinatorMainWindow` *(added 2026-07-26)* — the same 9 IC tabs as `IssuingMainWindow` (Under Review/Approved/Isolate Confirming/Pending/Active/Deisolate Confirming/Closing/Sanctioned/Closed, no Requested tab, same reasoning), but view-only plus **Link to PTW** — none of Issuing's Accept/Request Edits/Confirm/Return/Execute actions. Same accepted gap as Issuing's Under Review tab, just wider: Coordinator is never a required approver on an IC's chain, so `myTurn` is unconditionally `False` for them — every not-yet-approved IC falls to the (unwired) Requested branch rather than Under Review, so it's simply not visible to Coordinator until some role approves it. "View all like Issuing, with less privilege" was the ask; this gap comes bundled with mirroring Issuing's tab set exactly, matching the same rare tradeoff already accepted there.
- Safety/Admin/Guest are untouched.

**`DialogIC` is tabbed, mirroring `WidgetPTW.DialogPTW`'s pattern** (both import the shared `TabButton`/`lightenColor`/`Timeline` helpers from `UiUtils.py` rather than duplicating them): a colored tab bar above a `QStackedWidget`, background/accent/highlight color driven by the IC's type (same palette as the row coloring above).
- **Basic Info** — IC #, Type, Requestor Department, Execution Department, Requestor, Request Time, Location, Equipment, Reason, Isolate ASAP, Long Term (+ reason).
- **Isolation Items** — the embedded `TableIsolationItems` list. Lock #/Lock Box # are always read-only here regardless of mode, never editable by the requestor — they're filled in by the isolator instead, via a separate dialog (`DialogCompleteIsolation`) shown when completing isolation (see below), not inline in this tab. Double-clicking a row opens `DialogIsolationItem` in edit mode (if the IC dialog itself is editable) or view-only (if not).
- **P&ID / Wiring** — the embedded `WidgetPidWiring` — see [P&ID / Wiring Highlighting](#pid--wiring-highlighting) below.
- **History** — only added in readonly mode (a brand-new IC has no approvals yet), a two-pane `QHBoxLayout` exactly mirroring `WidgetPTW`'s History tab: left pane is the **Approval Timeline** (`_buildApprovalTimelinePane`, reusing `Timeline`/`TimelineEntry` — green/orange dots for each `Approval`, gray "Pending" dots for `pendingApprovers()`), right pane is the **Isolation Timeline** (`_buildIsolationTimelinePane`/`_isolationStageEntry`). `Isolate` and `De-isolate` are fixed lifecycle stages — their Requested/Confirmed/Carried-Out rows always render, gray "— Pending" until each field is set, green once it is. `Sanction` (for test) and `Re-isolate` are optional excursions — each of their three rows only appears once its own field is set, no gray placeholder. The isolate group's middle ("Confirmed") row also reflects `isolate_issuing_action`: green "Isolate Approved", orange "Isolate Returned", or green "Isolate Confirmed" as a fallback if set with no recorded action — the other three groups have no action field, so their Confirmed rows are always green once set.
- **PTW Linkage** — also readonly-only, a plain `QVBoxLayout` (not a `QFormLayout`) titled **"Linked PTWs"**: one row per linked PTW (`ic.linked_ptws` only — `held_by` isn't currently surfaced here, since nothing populates it yet) via `_addPTWLinkRows`/`_ptwLinkRow`, each row a read-only `QLineEdit` reading `"PTW #{id} — {running_status}"` (looks the PTW up in `globalData.allPTWs`/`archivedPTWs`; falls back to just `"PTW #{id}"` if not found) plus a **View** button (`_viewLinkedPTW`, opens a readonly `WidgetPTW.DialogPTW`) and, for any non-Guest viewer, an **Unlink** button; an empty list shows a plain "No linked PTWs." label instead, no rows. Below the list, a **Link to PTW** button (`_linkNewPTW`, `QInputDialog.getText` for the PTW #) — visible whenever `not ic.isWindingDown()` (the same predicate `optionLinkPTWToIC.visibleFor` already uses) — calls the same `ClientRequests.linkPTWToIC` as the PTW-side button below, so either dialog can initiate the same link (see [PTW↔IC Linkage](#ptwic-linkage)).

### PTW↔IC Linkage

**Fully implemented as of 2026-07-25: link and unlink, both directions, symmetric on both sides.** Either a PTW or an IC can initiate the link/unlink; the server keeps `IC.linked_ptws`/`held_by` and `PTWData.linked_ics` in sync in the same request.

**Role-restricted to `USER`/`ISSUING`/`COORDINATOR` only (tightened 2026-07-26 — previously any non-Guest role could reach these)**, enforced on both sides:
- Client: the Unlink button (both dialogs) and the Link New IC / Link to PTW buttons check `self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR)` before showing at all (an Isolator, PDH, Safety, etc. viewing either dialog sees no linking controls whatsoever). `CoordinatorMainWindow`'s `tabApprovedPTWs` gained `optionLinkICToPTW` in its menu to match — it previously had no menu-based linking at all.
- Server: `POST /ics/link-ptw` and `POST /ics/unlink-ptw` independently re-check the same three-role allowlist (403 otherwise) — the old check only rejected `GUEST`, so a non-Guest role outside the three could still hit the endpoint directly even with no UI path to it.

- **Link from the IC side** — two access points to the same action: the **Link to PTW** menu option (`optionLinkPTWToIC`, `UserMainWindow` and `IssuingMainWindow` only, on every non-winding-down IC tab) *and* a **Link to PTW** button directly inside `DialogIC`'s "PTW Linkage" tab (`_linkNewPTW`, visible whenever `not ic.isWindingDown()` **and** the role check above). Either pops a plain `QInputDialog.getText` asking for a PTW #, then → `MainWindow.linkPTWToIC` / `DialogIC._linkNewPTW` → `ClientRequests.linkPTWToIC` → `POST /ics/link-ptw`.
- **Link from the PTW side** — likewise two access points: the **Link to IC** menu option (`optionLinkICToPTW`, `UserMainWindow`/`IssuingMainWindow`/`CoordinatorMainWindow`, on the Approved PTWs tab) *and* a **Link New IC** button directly inside `WidgetPTW.DialogPTW`'s "IC Linkage" tab (`_linkNewIC`, visible whenever `ptw.canLinkIC()` **and** the role check above). Both prompt for an IC # → `MainWindow.linkICToPTW` / `DialogPTW._linkNewIC` → the same `POST /ics/link-ptw` endpoint (it just takes an `ic-id`/`ptw-id` pair regardless of which side supplies which, so either side can initiate the link).
- **Unlink from either side** — an **Unlink** button on the IC's "PTW Linkage" tab (`DialogIC._unlinkPTW`) and on the PTW's "IC Linkage" tab (`WidgetPTW.DialogPTW._unlinkIC`), both → `POST /ics/unlink-ptw`. Confirms via Yes/No, then closes the (now-stale) read-only dialog on success — the caller reopens it to see the refreshed linkage rather than the UI trying to patch rows in place.

Both tabs were redesigned 2026-07-26 from a `QFormLayout` (grouped by IC type / split into "Linked PTW"+"Held By" fields) to a plain `QVBoxLayout`: a bold title (**"Linked ICs"** / **"Linked PTWs"**), a flat list of link rows — each row's field text is `"IC #{id} — {status}"` / `"PTW #{id} — {running_status}"` (falls back to just the bare `#{id}` if the linked object can't be found in `globalData`) — or a plain "No linked ICs/PTWs." label if empty, then the Link button described above.

Each row on the PTW side ("Linked ICs") also has a **Request Isolate** button (`_requestIsolateIC`, `UserRoles.USER` only — narrower than even the link/unlink allowlist above, matching `optionRequestIsolateIC`'s own `UserMainWindow`-only scope in `MainWindow.py`; same confirm-dialog wording and `ClientRequests.requestIsolateIC` call as `MainWindow.requestIsolateIC`) — lets the PA request isolation on a linked IC without leaving the PTW dialog. Unlike the Link/View/Unlink buttons, this one stays **visible but disabled** rather than hidden: `setEnabled(bool(ic) and ic.getStatus() == IC.Status.APPROVED)`, so a row for an IC that isn't found or isn't yet `Approved` shows the button grayed out instead of missing.

Two gates on linking, both expressed on the model so they're checked identically whether called from a menu predicate, a dialog button, or the endpoint:
- `IC.isWindingDown()` — `True` once `Sanctioned`/`Deisolate Confirming`/`Closing`/`Closed`, i.e. the IC is past the point where a new PTW should be attached. Drives both `optionLinkPTWToIC.visibleFor` and `DialogIC`'s **Link to PTW** button directly (neither has a specific PTW in hand yet, so this is the IC-only half of the check).
- `PTWData.canLinkIC()` — the PTW-only half, symmetric to the above: `approval_status == Approved` and `running_status == Not Running` (the window between a PTW being approved and it actually starting work). Drives both `optionLinkICToPTW.visibleFor` and `WidgetPTW.DialogPTW`'s **Link New IC** button.
- `IC.canLinkPTW(ptw)` — the full check once an actual PTW is known: `isWindingDown()` **and** the target PTW's own `canLinkIC()`. Not linkable while the PTW is still under review/returned, nor once run/hold/close has been requested or done. Used server-side only, after `ptwDB.getPTWById(ptwId)` — by design, neither client-side button/menu predicate can check this half up front, since they only ever have one side of the pair (the IC or the PTW, never both) until the id is typed in.

`canLinkPTW` needs `PTWData`'s `ApprovalStatus`/`RunningStatus` enums, imported lazily inside the method body rather than at module scope — `PTWData.py` already imports the plain `Isolation` class at module scope, so a top-level `Isolation.py → PTWData.py` import would be a real circular import.

`IC.linkPTW(ptwId)`: un-holds the PTW if it was held, appends to `linked_ptws`. `IC.unlinkPTW(ptwId)`: removes from both `linked_ptws` and `held_by`, no other side effects. There is no `holdPTW` on `IC` (unlike the old, now-removed `Isolation.holdPTW`) — a PTW going `RUNNING`→`HELD`→`CLOSED` no longer automatically moves its linked ICs between `linked_ptws`/`held_by`, or unlinks them; that coupling was removed along with the old tag-tracking subsystem. Unlinking an IC from a PTW is now a purely manual, deliberate user action (the Unlink button above), never an automatic side effect of the PTW's own state transitions.

**Run safety gate (new 2026-07-25, extended to run-request 2026-07-26):** both `POST /ptws/run-request` (PA requesting to run) and `POST /ptws/run`'s accept branch (IA accepting that request) independently require every id in `ptw.linked_ics` to resolve to an `IC` whose `getStatus() == IC.Status.ACTIVE` — otherwise rejected `403` with the offending IC ids listed in the error (`"Cannot request run: ..."` / `"Cannot run: ..."`). `SANCTIONED`/`DEISOLATE_CONFIRMING`/`CLOSING` and all pre-isolation statuses do **not** count as isolated for this check; only `ACTIVE` does. Checking it at request-time too (not just accept-time) catches the problem earlier — a PA can no longer even ask to run a PTW with an unfinished isolation, rather than finding out only when IA tries to accept. This replaces the old automatic tag-linking side effect that used to run here (see the removed-subsystem note at the top of this section) — it's now a pure validation, not a state mutation. Hold-accept and close-accept no longer touch isolation state at all.

**`TableICs` columns**: IC# (id), Status, Type, L.T. (Long Term), Requestor, Request Time, Requestor Dept., Execution Dept., Location, Equipment, Reason. The L.T. column follows `TablePTWs`' Fast Track pattern exactly — real value lives in `Qt.ItemDataRole.UserRole` (cell text is intentionally empty), a `mdi6.timer-sand` icon badge renders in a fixed-width column, and the whole row goes bold when set. (An `fa6s.infinity`/`ph.infinity`/`mdi.infinity` badge was tried first — every icon set's infinity glyph turned out to have ~0px horizontal padding, always spanning the full pixmap width, so it visually clipped inside the circular badge regardless of size.)

**Not implemented yet — explicitly deferred:** the entire `sanction_*` (sanction-for-test) and `reisolate_*` cycles (no trigger, no confirm, no execute — the isolate/de-isolate cycles above are the template these will eventually mirror, per-cycle: `sanctionConfirming`/`reisolateConfirming` tabs alongside `isolateConfirming`/`deisolateConfirming`). Also still deferred: clearing/editing `lock_num`/`lock_box_num` at de-isolate-execution time (the isolator physically removes the locks, but `deisolate-execute` doesn't touch `items` the way `isolate-execute` does), a dedicated "Returned" tab + edit-and-resubmit flow for a returned IC (PTW has `tabReturnedPTWs` + re-request; IC doesn't — a returned IC just falls back into the Requested tab today), and PTW reports printing linked ICs (the old "Isolations"/"De-Isolation" sections and the whole "Print De-Isolation" report feature were removed from `ReportGenerator.py` 2026-07-25 since they depended on the removed tag-tracking subsystem; nothing prints isolation/IC info on a PTW report yet).

Server-side: `GET /ics` (list, department-scoped for `UserRoles.USER` only, matched against `requestor_department`), `POST /ics` (create, 400s if `execution_department` missing or, for `Self`-type, mismatched with `requestor_department`), `POST /ics/approvals` (staged approve/return), `POST /ics/isolate-request` (Approved → Isolate Confirming), `POST /ics/isolate-confirm` (Issuing approve/return, role-gated), `POST /ics/isolate-execute` (Isolator complete, role-gated + `execution_department`-gated, optional per-item lock numbers), `POST /ics/deisolate-request` (Active → Deisolate Confirming), `POST /ics/deisolate-confirm` (Issuing approve/return, role-gated), `POST /ics/deisolate-execute` (Isolator complete, role-gated + `execution_department`-gated) → `Closed`, `POST /ics/link-ptw` (link a PTW, gated by `canLinkPTW`, symmetric write to both sides), `POST /ics/unlink-ptw` (unlink, symmetric write to both sides).

### P&ID / Wiring Highlighting

**Implemented as of 2026-07-28.** A tab inside `DialogIC` (after Isolation Items) where the requestor attaches one or more diagrams (PDF or image) to an IC and sees every isolation item's tag automatically located and highlighted on them — red for `OPEN` items, green for `CLOSE` (`IC.colorForItemState`) — using the IC's own `items` list as the source of truth for what to look for.

**Data model** (`client`/`server` `Isolation.py`): `IC.pid_documents: list[IC.PidWiringDocument]`, each holding `filename` (the highlighted/burned-in file — served to the app and to external viewers), `original_filename` (the pristine upload, kept only so highlights can be recomputed later), `page_count`, `ocr_used`, and `highlights: list[IC.Highlight]` (`tag`, `page`, `rect` — `[x, y, w, h]` fractional 0..1 of page size, `state`, `manual` — set once a highlight has been hand-drawn or adjusted, so a later Sync never overwrites it). `PidWiringDocument._asHighlight()` tolerates a `Highlight` arriving as an already-built object, a plain dict, or a `SimpleNamespace` — three different callers (in-memory construction, raw JSON, and the DB-row `dictToObj` path) hand it three different shapes.

**Highlight detection** (`client/PidWiringHighlighter.py`, client-only — nothing server-side inspects a highlight's contents): `computeHighlights(filePath, items)` opens the file via `QPdfDocument`/`QImage` and, per page, either searches the page's real text layer natively (`QPdfSearchModel`, whenever `QPdfDocument.getAllText(page)` returns anything at all — a page dense with short tag labels and no prose can legitimately have very little text, so "any text vs none" is the signal, not a length threshold) or falls back to OCR (`pytesseract`, English-only, catches `TesseractNotFoundError` and any other exception and just skips that page's highlights rather than crashing) for a scanned page or a plain image upload. Two Qt/pypdf quirks needed working around: `QPdfSearchModel` can hand back a rectangle with a negative width/height (observed on rotated pages) — every rect goes through `.normalized()` before use; and `QPdfDocument.render()` returns a page image with a **transparent** background (alpha 0, not opaque white), which reads as black once alpha is dropped (by Tesseract, or by anything that doesn't composite transparency) — `renderPage()` now composites onto white before the image is used for OCR or on-screen display. Each detected box is padded (`HIGHLIGHT_PAD_RATIO`/`HIGHLIGHT_PAD_MIN`) so the highlight reads as a callout around the text rather than a shrink-wrapped outline.

**Highlights are burned into the file itself, not drawn as an in-app-only overlay** — `burnInHighlights(filePath, highlights)` produces a new file with the highlight rectangles physically drawn in (`pypdf`+`reportlab` merge for PDFs, `Pillow` `ImageDraw` for images) and returns its path; the original upload is left untouched. This is what actually gets uploaded/stored as `pid_documents[i].filename`, so opening it from the server's attachments folder, or in any external viewer via **Open Externally** (`ReportGenerator.openPDF`, the same helper `TableAttachments` uses for PTW attachments), shows the same highlights the app computed — not just something drawn on top inside this app's own viewer. **Rotated PDF pages** (`/Rotate` 90/270) needed a specific fix: `pypdf`'s `page.mediabox` reports the page's raw, un-rotated box, which comes out swapped relative to `QPdfDocument.pagePointSize()`/`render()` (the rotation-aware, visual size the highlight rects are actually computed against) — `_burnInPdf` calls `page.transfer_rotation_to_content()` first, baking the rotation into the actual content and zeroing `/Rotate`, so pypdf's dimensions agree with Qt's before the overlay is drawn.

**`client/WidgetPidWiring.py`** — the tab itself. A combo box picks between a document's multiple attached files; **Upload**, **Open Externally**, and (non-readonly) **Delete** sit beside it. Below the zoom/pan preview (`_PidGraphicsView`, wheel-zoom + drag-pan) and page nav: **Sync Highlights** (recomputes automatic highlights for *every* document from the current items list, preserving any manual ones), **Clear Highlights** (wipes every highlight — manual included — from the *currently selected* document only), **Add Highlight**, and **Delete Highlight**. There's no separate "edit mode" toggle — whenever the IC itself is editable (not readonly), the preview always shows the pristine original with the current highlights overlaid as live, draggable/corner-resizable rectangles (`_EditableHighlightItem`); any drag-release, add, or delete re-burns the file immediately. Only the highlight that actually moved gets marked `manual` — an untouched sibling on the same page keeps whatever it already was, so a later Sync can still refresh it if it was never a manual override. Adding a highlight (`_AssignHighlightDialog`) only asks which item/tag it's for — its state is always taken from that item's current state in the items list, never chosen independently. Read-only viewing (an already-submitted IC) shows the burned-in file flatly, with none of the above editing controls.

**Isolation items ↔ P&ID resync**: `TableIsolationItems.itemsChanged` (a new signal, emitted on add, edit, or bulk-delete — double-clicking a row now opens `DialogIsolationItem` in edit or view mode depending on whether the IC dialog itself is editable) is wired to `WidgetPidWiring.onItemsChanged()`, which — if the IC already has any P&ID documents — asks whether to resync now (same "keep manual" Sync logic above).

**Upload lifecycle mirrors PTW attachments exactly, creation-time only**: `DialogIC` is never opened in an editable-existing-IC mode (there's no `PUT /ics`, no edit flow at all — see [IC](#ic-isolation-certificate) above), so P&ID documents can only be attached while creating a brand-new IC. Both the burned-in file and the pristine original are staged locally (`WidgetPidWiring.docsToBeUploaded: list[Attachment]`) and only actually uploaded — via new `POST /ics/attachments` — after `addIC` succeeds and the IC has an id (`TableICs.addNewICDialog`, mirrors `MainWindow.addPTWDialog`'s post-`addPTW` attachment upload). Server storage mirrors the PTW attachment routes almost verbatim: `server/ic-{id}-attachments/`, `POST`/`GET`/`DELETE /ics/attachments` — no copy route, since there's no "re-request IC" flow to mirror `copyPtwAttachments` for.

**Not implemented / known limitations:** a tag whose text is split across two lines by the diagram layout won't match via either the native-text or OCR path. Tesseract itself must be present on the machine running OCR — bundling it into the Nuitka client build (Windows via Chocolatey, Linux via `apt`, both staged into `client/tesseract-bin/` and picked up at runtime by `client/OcrConfig.py`) is wired into `.github/workflows/build.yml`, English-only, but not yet verified against an actual CI run. Since ICs have no edit flow at all, there's also no way to attach a P&ID/wiring document to an IC after it's been submitted.

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

### PTW-specific risk assessment (`RiskPreview.py`)

The PTW request/edit/view dialog's Risks tab (`WidgetPTW.DialogPTW`) shows a single flat table — `RiskPreview.RiskItemsTable` — in **all three modes** (new, edit, view). There's no separate checkbox-based generic-selection step embedded in the PTW dialog anymore; the table itself, and the buttons above it, are the entire UI:

- **Add Items** → a chooser with three ways to populate rows:
  - *Add Manually* — `DialogRiskItem`, a single-item form (Hazard/Effect/Free Analysis/Control/Controlled Analysis/Evaluation), reused for both creating a new row and (via double-click on an existing row) editing one in place.
  - *Use Generic Risks* — `DialogSelectGenericRisks`, a modal that embeds `TableRisks` (the same checkbox-list widget the old embedded selector used, just in a dialog instead of inline) over the generic library (`globalData.allRiskAssessments`); every `RiskItem` from the checked assessments is deep-copied in.
  - *Import from Excel* — `RiskItemsTable._parseRiskItemsFile()`, built on the shared `utils.parseTabularFile()` reader (see below); invalid rows are skipped and reported, not fatal.
- **Delete Selected Items** — removes checked rows after confirmation.
- **Print Preview** — calls `ReportGenerator.riskAssessmentReport(riskAssessment=...)` directly on the in-progress table.

Every addition path (manual, generic-picker, Excel import) and every in-place edit runs through the same dedup check — `riskItemKey()` (exact match, case/whitespace-insensitive, across all 6 fields): a new item identical to one already present is silently rejected (with a message), and an edit that would make a row identical to a *different* existing row is discarded and reverted rather than applied.

**Persistence**: there is no intermediate "preview" state distinct from what's saved — the table *is* the data. On submit, `MainWindow._savePTWRiskAssessment` reads `dlg.riskAssessmentPreviewTable.getRiskItems()` straight from the table and upserts it as a single `RiskAssessment` with `title = str(ptw_id)` and `ptw_id = <the PTW's id>` (`PUT /risks`). Viewing an already-submitted PTW fetches and shows that same row set read-only. PTWs from before this table existed (no `ptw_id` row) just show an empty table — no backfill migration.

On **re-request**, the server additively copies the original PTW's `ptw_id` row set onto the new PTW's `ptw_id` (`risksDb.copyRiskAssessmentForPTW`, run from `POST /ptws/attachments/copy` right after the attachment file copy), so custom rows from the original carry over even if the user doesn't reselect or retype them in the new request.

**Status of `ptw.risks`**: `PTWData` still has a `risks: list[str]` field (generic-title list) and `addRisk()`/`updateRequirements()` still populate it from tool/hazard/control `RISK`-type requirements, but the `validate()` check that used to enforce "selecting X requires risk assessment Y" is commented out — the field is inert and slated for removal along with the `RISK` requirement type, now that risk content is authored directly rather than derived from required generic titles.

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

`getPerforming()` / `getIssuing()` / `getPerformingTimestamp()` / `getIssuingTimestamp()` return the live PA/IA of the currently open run cycle (or `None` once it's been rejected, held, or closed — matching the old fields' behavior of going blank at that point). `getKeepIsolations()` returns the most recent cycle's kept isolation tags regardless of whether that cycle is still open (used both while `WAITING_HLD_CONFIRM`/`HELD`, and read back afterward for reporting).

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

`tools`, `hazards`, and `controls` are each backed by a lookup table in `PTWData` — `ALL_TOOLS`, `ALL_HAZARDS`, `ALL_CONTROLS` — mapping title → `CheckBox`:

- `title` — display name (e.g. `'Power Tools'`, `'Confined Space'`)
- `isRequired(ptwType)` / `isRestricted(ptwType)` — per-permit-type rules, e.g. `'Non-Ex Tools'` is restricted for Cold Work; the `'Electrical / Mechanical Spark'` hazard is required for Spark permits and restricted for Cold Work
- `requirements` — a list of `Requirement` objects (`TOOL` / `HAZARD` / `CONTROL` / `RISK` / `ATTACH` / `DOC`) that must also be satisfied once this item is selected, e.g. selecting the `'Scaffolding'` hazard also requires the `'Working at Height'` hazard; selecting `'Power Tools'` requires the `'Power Tools Checklist'` attachment

**`updateRequirements()`** (client-only, called from `WidgetPTW.checkRequirement()`) walks these tables to auto-check required items, auto-uncheck restricted ones, and cascade-add linked requirements — keeping the checkbox UI in sync as the user picks a permit type. This method only exists to drive the live UI; it is never called server-side.

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

Maintenance and Work Instructions (MIWI) are PDF documents describing the steps for a specific job, stored per-department on the server: `server/miwi/<department>/` (e.g. `server/miwi/Turbo/`). MIWIs are not copied for every PTW, instead a PTW is linked to the MIWI to minimize used space.

**Uploads** always land in the uploading user's own department folder — `POST /miwi` takes the department from the client-supplied field (the uploader's own department), whitelisted against the `UserDepartments` enum, and creates the folder on demand.

**Reading is unrestricted by role** — any authenticated user can list (`GET /miwis`) or download (`GET /miwi`) a MIWI from any department, including the legacy flat files, since a PTW may need review by people outside its own department. `department` only narrows/prefers results when supplied (`server/app.py` — `_resolveMiwiPath`); it's never enforced against the caller's own department for these read endpoints. Only **uploading** (`POST /miwi`) is confined to the uploader's own department, per above.

A handful of legacy files still sit directly under `server/miwi/` (uploaded before the per-department layout existed) and are only reachable by approver-type roles until sorted into department folders manually.

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

`POST /ptws` runs `PTWData.validate()` (required/restricted/requirements rules for tools, hazards, controls, plus required attachments — see [Tools, Hazards & Controls Rules](#tools-hazards--controls-rules)) before persisting; a failing submission is rejected with `400` and never written to the database.

`/ptws/run`, `/ptws/hold`, `/ptws/close` (the IA's response) and `/ptws/hold-request`, `/ptws/close-request` (the PA's stop request) all accept an optional `comment` field in the JSON body, stored on the relevant `RunCycle` (`run_ia_comment`/`stop_pa_comment`/`stop_ia_comment` — see [Running Cycle](#2-running-cycle)); `/ptws/run-request` has no comment field, matching `RunCycle.run_pa`/`run_pa_timestamp` having none either.

### Real-Time Events (SSE)
| Method | Endpoint   | Description                                              |
|--------|------------|----------------------------------------------------------|
| GET    | `/events`  | SSE stream; pushes PTW change events to the client       |

The server broadcasts role-filtered events over this stream. The client connects via `SSEListener` (a QThread). Event types:

| Event               | Triggered by                                 |
|---------------------|----------------------------------------------|
| `new_ptw`           | New PTW created                              |
| `ptw_deleted`       | PTW deleted                                  |
| `ptw_approval`      | Approval action submitted                    |
| `ptw_archived`      | PTW archived                                 |
| `ptw_run_request`   | PA sends run request                         |
| `ptw_run`           | IA accepts/rejects run request               |
| `ptw_hold_request`  | PA sends hold request                        |
| `ptw_hold`          | IA accepts/rejects hold request              |
| `ptw_close_request` | PA sends close request                       |
| `ptw_close`         | IA accepts/rejects close request             |
| `new_ic`            | New IC created (broadcast to `ISSUING` only — the creator's own view updates via a local optimistic add instead, see [Isolation Management](#isolation-management)) |
| `ic_approval`       | Approve/reject action recorded on an IC's approval chain (unrestricted broadcast, like `ptw_approval`) |
| `ic_isolate_request` / `ic_isolate_confirm` / `ic_isolate_execute` | Isolate cycle: request / IA confirm-or-return / isolator execute |
| `ic_deisolate_request` / `ic_deisolate_confirm` / `ic_deisolate_execute` | De-isolate cycle: request / IA confirm-or-return / isolator execute |
| `ic_link_ptw` / `ic_unlink_ptw` | A PTW was linked to / unlinked from an IC (either side can have initiated it) |

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
| POST   | `/ics`                  | Create a new IC (`requestor_department`/`requestor`/`requestor_timestamp` are stamped server-side from the caller, not trusted from the payload; `execution_department` is required from the client — 400 if missing, or if `Self`-type and it doesn't match `requestor_department`) | Any non-guest   |
| POST   | `/ics/approvals`        | Submit an approve/reject action on the IC's approval chain (mirrors `/ptws/approvals`) | Caller's `getApprovalStatus(role, department)` must currently be `Requested` (i.e. it's their turn) |
| POST   | `/ics/isolate-request`  | User requests the approved IC's isolation be carried out (`Approved`→`Isolate Confirming`) | Any non-guest |
| POST   | `/ics/isolate-confirm`  | Issuing confirms or returns the isolate request | `ISSUING` |
| POST   | `/ics/isolate-execute`  | Isolator carries out the isolation, optional per-item lock #/lock box # (`Pending`→`Active`) | `ISOLATOR` whose department matches the IC's `execution_department` |
| POST   | `/ics/deisolate-request`| User requests de-isolation (`Active`→`Deisolate Confirming`) | Any non-guest |
| POST   | `/ics/deisolate-confirm`| Issuing confirms or returns the de-isolate request | `ISSUING` |
| POST   | `/ics/deisolate-execute`| Isolator carries out the de-isolation → `Closed` | `ISOLATOR` whose department matches the IC's `execution_department` |
| POST   | `/ics/link-ptw`         | Link a PTW to an IC (either side can supply the id it already has), gated by `canLinkPTW`, symmetric write to both `IC.linked_ptws` and `PTWData.linked_ics` | Any non-guest |
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

---

## Database Schema

Database name: `ptw_database` (PostgreSQL, localhost). `server/dev-scripts/init_db.py` is the one-time script that creates the database and every table below in this final shape — run it once before starting the server for the first time. The `*Db.py` classes (`usersDb.py`/`ptwDb.py`/`risksDb.py`/`ICDb.py`) assume their table already exists; they no longer `CREATE TABLE`/`ALTER TABLE` on every server startup the way they used to while the schema was still evolving (table/column renames, drops, splits — that churn is done, so a fresh database now gets the end result directly instead of walking through it). `UsersDb` is the one exception: its constructor still seeds the initial `admin` account if `users` is empty, since that's data seeding rather than schema.

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

**Three `PTWData` fields are deliberately not columns here.** `approval_status` and `running_status` are both recomputed by `__updateStatus()` from `approvals`/`run_cycles` on every read (see [Running Cycle](#2-running-cycle)), so a stored copy would just be a stale duplicate — this also removed the old `prev_running_status` column entirely, since the replay-forward derivation never needs a "revert to" snapshot the way the old direct-SQL-write transitions did. `attachs` only ever holds the client's local, not-yet-uploaded staging list (used by `validate()`'s required-attachment check) — the actual attachment filenames live only in the `ptw-{id}-attachments/` folder on disk (see [Attachments](#attachments)); `ReportGenerator.ptwReport()` fetches that live listing via `GET /ptws/attachments` rather than trusting `ptw.attachs`. `is_archived` is the one exception that IS a real column — archiving isn't something a run cycle's fields can encode.

**There is no more `isolations` table.** It (and the plain `Isolation.linked_ptws`/`held_by`/`primary_ptw`/`latest_ptw`/`is_physically_isolated`/`linkPTW`/`holdPTW`/`unlinkPTW` state it backed) was removed entirely 2026-07-25 along with `server/IsolationDb.py` and the client's global "Isolations" browse tab — see [Isolation Management](#isolation-management). `PTWData.isolations` still exists but is a plain `JSONB[]` column on `ptws` holding declarative `type`/`tag`/`description` records only, same as always.

### `ics`

Created by `server/dev-scripts/init_db.py` in the shape below (renamed from `isolation_certificates` 2026-07-25; `department` split into `requestor_department`/`execution_department` 2026-07-26; `pid_documents` added 2026-07-28, see [P&ID / Wiring Highlighting](#pid--wiring-highlighting) — all migrations that a live install needed to get here have already run, so a fresh database just gets this final shape directly, see [Database Schema](#database-schema) above).

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
linked_ptws                     TEXT[]
held_by                         TEXT[]
```

`linked_ptws`/`held_by` are the IC's own runtime linkage state — fully implemented (link+unlink, symmetric with `PTWData.linked_ics`), see [Isolation Management](#isolation-management). `primary_ptw`/`latest_ptw`/`is_physically_isolated` columns existed at one point but were removed 2026-07-25 (`latest_ptw` was always derivable as `linked_ptws[-1]`, `is_physically_isolated` as `bool(linked_ptws or held_by)`, and `primary_ptw` had no clean replacement and wasn't worth keeping) — they're absent from the schema above and from any already-migrated install; a fresh database created by `init_db.py` never has them at all.

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

The desktop client is structured around role-based main windows. After login, `MainWindow.py` routes the user to the appropriate role-specific window (e.g., `IssuingMainWindow`, `SafetyMainWindow`, `AdminMainWindow`, etc...).

### Global Data Cache

`GlobalData` maintains an in-memory cache of:
- `allUsers` — dict of username → SecuredUser
- `allPTWs` — list of PTWData objects (non-archived)
- `archivedPTWs` — list of PTWData objects (archived permits)
- `ics` — dict of id → IC (renamed from `isolationCertificates` 2026-07-25; there is no more `isolations` dict — the plain-tag registry it backed was removed the same day)
- `allRiskAssessments` — dict of title → RiskAssessment (generic library only; a PTW's own specific row set is fetched on demand via `GET /risks/ptw`, never cached globally)
- `allMIWIs` — list of MIWI filenames

`allPTWs` is refreshed on login and after any mutation. `archivedPTWs` is fetched **on-demand only** (not automatically refreshed) to reduce server overhead — archived permits are stable and rarely queried.

### Key Client Modules

| Module                      | Purpose                                                          |
|-----------------------------|------------------------------------------------------------------|
| `main.py`                   | Entry point; launches QApplication                               |
| `Login.py`                  | Login screen; handles password reset flow                        |
| `MainWindow.py`             | Post-login router; loads role-specific window                    |
| `clientRequests.py`         | HTTP wrapper; all server calls return `(err, data)`              |
| `RequestWorker.py`          | `@async_request` decorator — moves any request off the GUI thread via `QThread`; marshals result back via queued signal |
| `RefreshOverlay.py`         | `RefreshOverlay` — dims a window/dialog and blocks input while a refresh is in flight; refcounted `showBusy()`/`hideBusy()`, auto-tracks its parent's size via an event filter, plays an animated bouncing-logo sprite (baked offline by `dev-scripts/generate_refresh_overlay_frames.py` into `assets/sh-logo-bounce-frames.png`) |
| `GlobalData.py`             | Client-side data cache                                           |
| `SSEListener.py`            | QThread that connects to `/events` and emits real-time PTW events|
| `PTWData.py`                | Mirrored data model classes (client-side copy)                   |
| `Isolation.py`              | Client-side model: `Isolation` (declarative type/tag/description only, no runtime state — used inside a PTW's own required-isolations list) + `IC` (renamed from `IsolationCertificate` 2026-07-25; the formal request document — approval chain, `getStatus()`, type coloring, and all runtime PTW-linkage state: `linked_ptws`/`held_by`) |
| `utils.py`                  | Shared helpers: `resource_path`, `objToDict`, `dictToObj`, `parseTabularFile` |
| `User.py`                   | User model                                                       |
| `WidgetPTW.py`              | Full PTW form (create/view/edit); `DialogPTW` is tabbed (Basic Info / Tools / Hazards / Controls / Risks / Isolation / MIWI-MOS / Attachments / **History** / **IC Linkage** — the last two only in readonly mode, mirroring `DialogIC`'s History/PTW Linkage split). History renders the approval log and the running cycle as two side-by-side `Timeline` panes — a vertical rail of colored dots (green=approved, orange=returned/rejected, gray=pending) connected by a continuous line, each dot's row scrollable via `QScrollArea`. The Approval Timeline reads `ptw.approvals`; the Running Timeline (`_buildRunningTimelinePane`/`_runCycleRequestEntry`/`_runCycleResponseEntry`) reads `ptw.run_cycles`, rendering each `RunCycle` as a "Run Cycle #N" header followed by its Run Requested/Run Approved-or-Rejected rows, and — once a hold or close has actually been requested on that cycle — its Hold/Close Requested and Hold/Close Approved-or-Rejected rows (gray "Pending" only for whichever step the *current*, still-open cycle hasn't reached yet; earlier, already-finished cycles never show a pending row). IC Linkage groups `ptw.linked_ics` by looking up each id's type in `globalData.ics`, one row per `IC.Types` value, each row with **View** and (non-Guest) **Unlink** buttons. |
| `UiUtils.py`                 | Reusable UI helpers shared across dialogs: `TabButton` (colored tab-bar button), `lightenColor` (accent-color helper), `Timeline`/`TimelineEntry` (vertical rail of colored dots + content, used for approval/isolation history panes) — extracted here since both `WidgetPTW.py` and `DialogIC.py` import them |
| `TablePTWs.py`              | Table listing all PTWs with filters; supports Excel export; `filterColumn(label, values)` sets a specific column filter programmatically (used by the home dashboard's location segments) |
| `TableUsers.py`             | Admin user management table; supports bulk user import from Excel; also has `filterColumn(label, values)` (used by the Admin dashboard's department segments) |
| `DonutChart.py`             | Reusable donut-chart widget (`DonutChart`/`DonutSegment`) for the home-page dashboard — clickable/hoverable ring + legend, fixed categorical palette |
| `ImportUsersExcel.py`       | Parses bulk-user Excel/CSV imports + DialogUsersPreview dialog   |
| `TableRisks.py`             | Generic risk assessment CRUD list (Safety admin tab); also embedded read-only+checkboxes inside `DialogSelectGenericRisks` |
| `RiskPreview.py`            | `DialogRiskItem` (single-item editor), `RiskItemsTable` (the flat table used for a PTW's risk assessment in all modes — add/delete/import/generic-pick, with dedup), `DialogSelectGenericRisks`, `RiskAssessmentPreview()` popup/embedded factory |
| `TableIsolations.py`        | Embedded editable required-isolations list for a PTW form (`TablePTWIsolations`) — type/tag/description only. The old global all-isolation-points browser (`TableIsolationsBrowser`) was removed 2026-07-25 along with the registry it displayed. |
| `TableICs.py`               | (renamed from `TableIsolationCertificates.py` 2026-07-25) IC list, one instance per tab (Requested/Under Review/Pending/Active/Sanctioned/Closed), mirrors `TablePTWs`; IC#/Status/Type/L.T./Requestor/Request Time/Requestor Dept./Execution Dept./Location/Equipment/Reason columns, L.T. rendered as an icon badge like Fast Track |
| `DialogIC.py`               | (renamed from `DialogIsolationCertificate.py` 2026-07-25) IC create/view dialog, tabbed like `WidgetPTW.DialogPTW` (Basic Info / Isolation Items / P&ID / Wiring / History / PTW Linkage — the last two only in readonly mode); `new`/`readOnly` flags mirror `WidgetPTW.DialogPTW`. PTW Linkage rows have **View** and (non-Guest) **Unlink** buttons. |
| `TableIsolationItems.py`    | Embedded editable isolation-item list inside the IC dialog, mirrors `TablePTWIsolations`; Description column stretches to fill remaining width; `itemsChanged` signal (add/edit/bulk-delete) drives the P&ID resync prompt; double-click opens `DialogIsolationItem` in edit or view mode |
| `DialogIsolationItem.py`    | Isolation-item add/edit/view dialog (tag/description/state/lock #/lock box #); lock fields are always read-only — set by the isolator on confirmation, not the requestor; `item=`/`readonly=` params drive edit-existing vs. view-only |
| `WidgetPidWiring.py`        | P&ID/Wiring tab embedded inside the IC dialog — document picker, zoom/pan preview, live manual highlight editing. See [P&ID / Wiring Highlighting](#pid--wiring-highlighting) |
| `PidWiringHighlighter.py`   | Pure logic (no UI): `computeHighlights()` (native text search + OCR fallback), `burnInHighlights()` (physically draws highlights into a new copy of the file), shared PDF render/load helpers |
| `OcrConfig.py`              | Points `pytesseract` at the Tesseract binary bundled into the Nuitka build (`client/tesseract-bin/`, staged in `.github/workflows/build.yml`) when running frozen; no-op in dev |
| `TableAttachments.py`       | PTW attachment management                                        |
| `TabServerLogs.py`          | Admin-only log viewer: collapsible file panels, lazy load, level filter, color-coded lines |
| `CheckableComboBox.py`      | Reusable multi-select checkbox combo box with `filterChanged` signal |
| `SearchableComboBox.py`     | Reusable editable combo box with fuzzy-match autocomplete; accepts free text not in its list |
| `DialogUser.py`             | Create/edit user dialog                                          |
| `DialogIsolation.py`        | Create/edit isolation dialog                                     |
| `DialogSelectIsolations.py` | Dialog to choose isolations when requesting hold                 |
| `DialogSettings.py`         | App settings (server URL, etc.)                                  |
| `ReportGenerator.py`        | Generates printable PDF permit reports and Excel exports         |

### Role-Specific Windows (all inside `MainWindow.py`)

All role-specific views are implemented as classes within `MainWindow.py`. After login, the file routes to the appropriate class based on the user's role:

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
- **Home page** (`buildHomePage()` / `updateHomeDashboard()`) — a template-method pair (same override pattern as `refreshGUI()`), invoked once `setAvailableTabs` knows the role's full button set. The base `MainWindow.buildHomePage()` builds a live [`DonutChart`](client/DonutChart.py) dashboard: a donut of PTWs in the approval cycle (Requested/Under Review/Returned/Approved) and one of Running PTWs split by location — each only appears if at least one of its underlying tabs is reachable by the role at all (sidebar *or* topbar). Clicking a segment (or its legend row) calls the corresponding sidebar button's `.click()`; location segments additionally call `TablePTWs.filterColumn('Location', {location})` to pre-filter the target tab. `updateHomeDashboard()` is re-run after every data refresh (`refreshPtwUserGUI`) to keep segment counts current. `AdminMainWindow` (no PTW tabs) overrides both hooks with a Users-by-Department donut instead, using `TableUsers.filterColumn('Department', {dept})` the same way.

---

## Known Issues / Notes

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for the full backlog of open bugs and security items with fix guidance.

- **File storage is local filesystem** — attachments and MIWI documents are stored on the server's local disk. Regular backups of `server/miwi/` (per-department subfolders) and `server/ptw-*-attachments/` are recommended.
