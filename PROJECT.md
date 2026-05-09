# PTW System — Permit To Work

## Overview

This is a desktop-based **Permit To Work (PTW)** management system built for industrial operations (Rashpetco). It enforces a structured, multi-stage safety workflow that governs when and how maintenance or hazardous work is authorized, executed, and closed. The system tracks approvals, manages equipment isolations, and provides a full audit trail for every permit.

The application runs as a **PyQt6 desktop client** communicating with a **Flask REST API server** backed by **PostgreSQL**.

---

## Technology Stack

| Layer      | Technology                     |
|------------|-------------------------------|
| Client UI  | Python 3.10+, PyQt6            |
| HTTP Client| requests (Basic Auth)          |
| Server     | Python 3.10+, Flask            |
| Database   | PostgreSQL (psycopg2)          |
| Email      | Flask-Mail (Gmail SMTP)        |
| Credentials| keyring                        |
| Reports    | ReportGenerator (custom PDF)   |

---

## PTW Types

Each PTW is classified by the nature of the work. The type drives visual theming in the UI:

| Code | Name         | Background | Text  | Use Case                    |
|------|--------------|------------|-------|-----------------------------|
| CW   | Cold Work    | Blue       | White | Non-spark generating work   |
| SP   | Spark        | Yellow     | Black | Work that may produce sparks|
| HT   | Hot Work     | Red        | White | Open flame / welding        |
| HC   | HydroCarbon  | Black      | White | Work near HC systems        |

---

## Locations & Departments

**Locations:** Phase VII, Phase V, Scarab, Simian

**Departments:** Turbo, Mech (Mechanical), Elec (Electrical), IT, Prod (Production), Safety

---

## User Roles

The system defines 10 roles with distinct permissions:

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
| Admin       | Full system access; manages users                              |

---

## PTW Lifecycle

A PTW passes through two major cycles: the **Approval Cycle** and the **Running Cycle**.

### 1. Approval Cycle

After a PTW is created, it enters an approval chain. Multiple approvers must review and vote. The chain typically goes:

```
Coordinator → Issuing → Safety → [PDH → PGM → SOD → DFGM]
```

Higher-level management approval (PDH through DFGM) may be required depending on the nature and risk of the work.

Each approval action is recorded with the approver's username, timestamp, action taken, and an optional comment.

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

| Status               | Meaning                                                    |
|----------------------|------------------------------------------------------------|
| NOT_RUNNING          | PTW approved but work not yet started                      |
| WAITING_RUN_CONFIRM  | Run request sent to Issuing Authority; awaiting confirmation         |
| RUNNING              | Work is actively in progress                               |
| WAITING_CLS_CONFIRM  | Close request sent to Issuing Authority; awaiting confirmation       |
| CLOSED               | Work complete; permit closed (final state)                 |
| WAITING_HLD_CONFIRM  | Hold request sent to Issuing Authority; awaiting confirmation        |
| HELD                 | Work paused; selected isolations maintained                |

---

## Isolation Management

Isolations are safety locks placed on equipment to prevent accidental energization during work. The system manages isolations at two levels:

### Isolation Types

| Type             | Description                         |
|------------------|-------------------------------------|
| Mechanical       | Physical valve/block isolations     |
| Electrical       | Electrical lockout/tagout            |
| Self             | Self-managed isolation by performer |
| Protective System| Protection system isolation         |
| Other            | Other isolation types               |

### Active Isolation Tracking

When a PTW transitions to **RUNNING**, all of its isolations are linked into the `active_isolations` table. The `ActiveIsolation` record tracks:

- `linked_ptws`: list of all PTW IDs currently using this isolation
- `primary_ptw`: the first PTW that linked this isolation. It is responsible to perform the isolation.
- `latest_ptw`: the most recently linked PTW. It is responsible to perform the de-isolation.

**Shared Isolation Rule:** A single physical isolation point may be required by multiple PTWs simultaneously. The system detects this: only the `primary_ptw` owns the isolation responsibility. All other PTWs that share it are visible via `linked_ptws`. This prevents conflicting de-isolation actions.

**Isolation lifecycle during state transitions:**

- **PTW → RUNNING:** All PTW isolations are linked (`linkPTW`)
- **PTW → HELD:** Only isolations listed in `keep_isolations` remain linked; others are unlinked (`unlinkPTW`)
- **PTW → CLOSED:** All PTW isolations are unlinked

The `isReallyActive()` method returns `True` if `linked_ptws` is non-empty — meaning the isolation is still physically required by at least one active PTW.

The system pre-loads a library all known isolation points (tags like `XV-7227A`, `LV-1409E`, etc.) covering mechanical, electrical, protective, and self-isolations across all plant areas.

---

## Risk Assessments

Safety department create and maintain risk assessment documents that can be referenced in PTWs.

Each `RiskAssessment` contains:
- `title`: unique assessment name
- `date`: creation date
- `risks`: list of `RiskItem` entries

Each `RiskItem` documents:
- `hazard`: the identified hazard
- `effect`: potential consequence
- `free_analysis`: analysis prior to applying controls
- `ctrl`: control measure applied
- `ctrl_analysis`: analysis after applying controls
- `eval`: final risk evaluation/rating

Only users with the **Safety** role can create or update risk assessments. Deleting a risk assessment is applicable but NOT allowed to keep already done PTWs valid.

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
```

### Work Authorization

```
performing              — Username of person performing the work
issuing                 — Username of the issuing authority
performing_timestamp    — Timestamp when performing party signed
issuing_timestamp       — Timestamp when issuing party signed
```

### Close Workflow Fields

```
close_performing            — Username requesting closure
close_issuing               — Username approving closure
close_performing_timestamp
close_issuing_timestamp
```

### Hold Workflow Fields

```
hold_performing             — Username requesting hold
hold_issuing                — Username approving hold
hold_performing_timestamp
hold_issuing_timestamp
keep_isolations             — List of isolation tags to keep active during hold
```

### Safety & Work Instructions

```
miwi        — Maintenance and Work Instructions,document (PDF)
mos         — Method of Statement, manually typed as a text of steps.
attachs     — List of uploaded attachment filenames
tools       — Selected tools: Hand Tools, Power Tools, Non-Ex Tools, Test Tools, Pneumatic Tools
hazards     — Identified hazards: Confined Space, Working at Height, etc...
controls    — Safety controls: Initial Gas Test, Continuous Gas Test, etc...
risks       — List of referenced risk assessment titles
isolations  — List of Isolation objects (type, tag, description)
```

### Status Fields

```
approval_status        — Current approval state (UNDER_REVIEW, APPROVED, RETURNED, REJECTED)
running_status         — Current execution state (NOT_RUNNING through CLOSED)
prev_running_status    — Previous status (used when a request is rejected, to restore state)
approvals              — Ordered list of Approval records (full audit trail)
```

---

## Attachments

Each PTW has its own attachment directory on the server: `ptw-{id}-attachments/`. Files can be uploaded, downloaded, deleted, or copied between PTWs. Common attachments include medical certificates, tool checklists, and technical documents.

## MIWI Documents

Maintenance and Work Instructions (MIWI) are PDF documents stored in `server/miwi/`. They describe the steps for a specific job. Any authenticated user can download them; any authenticated user can upload new ones. MIWIs are not copied for every PTW, instead a PTW is linked to the MIWI to minimize used space.

---

## Authentication & Security

- All API endpoints require HTTP Basic Auth (username + password).
- Passwords are stored in plain text in the database (no hashing — this is an identified weakness to be fixed in upcoming versions).
- **Password Reset** flow: user requests a reset → server sends a 6-digit verification code to the user's registered email via Gmail SMTP → code expires after 15 minutes → user submits new password with code.
- Role-based access control is enforced at the API layer for sensitive operations (user management, risk assessment management).

---

## API Reference

### Authentication
| Method | Endpoint                  | Description                        |
|--------|---------------------------|------------------------------------|
| POST   | `/login`                  | Authenticate user                  |
| POST   | `/reset-password-request` | Send verification code to email    |
| POST   | `/reset-password`         | Reset password with code           |

### Users
| Method | Endpoint    | Description                             | Auth Required    |
|--------|-------------|-----------------------------------------|------------------|
| GET    | `/users`    | Get all users (secured view)            | Any              |
| GET    | `/user`     | Get a specific user                     | Any              |
| GET    | `/usernames`| Get all usernames                       | Any              |
| POST   | `/users`    | Create a new user                       | Admin only       |
| PUT    | `/users`    | Update a user                           | Admin or self    |
| DELETE | `/users`    | Delete a user                           | Admin only       |

### PTWs
| Method | Endpoint                    | Description                               |
|--------|-----------------------------|-------------------------------------------|
| GET    | `/ptws`                     | Get all PTWs (filterable by dept/requestor)|
| POST   | `/ptws`                     | Create new PTW                            |
| DELETE | `/ptws`                     | Delete a PTW                              |
| POST   | `/ptws/approvals`           | Submit an approval action                 |
| POST   | `/ptws/run-request`         | PA requests to start work          |
| POST   | `/ptws/run`                 | IA accepts or rejects run request     |
| POST   | `/ptws/hold-request`        | PA requests to hold work           |
| POST   | `/ptws/hold`                | IA accepts or rejects hold request    |
| POST   | `/ptws/close-request`       | PA requests to close permit        |
| POST   | `/ptws/close`               | IA accepts or rejects close request   |

### Attachments
| Method | Endpoint                    | Description                          |
|--------|-----------------------------|--------------------------------------|
| POST   | `/ptws/attachments`         | Upload files to a PTW                |
| GET    | `/ptws/attachments`         | List or download PTW attachments     |
| DELETE | `/ptws/attachments`         | Delete attachments except for `keep-list`       |
| POST   | `/ptws/attachments/copy`    | Copy attachments from one PTW to another |

### Isolations
| Method | Endpoint      | Description                     |
|--------|---------------|---------------------------------|
| GET    | `/isolations` | Get all active isolation records|

### Risk Assessments
| Method | Endpoint | Description                        | Auth Required |
|--------|----------|------------------------------------|---------------|
| GET    | `/risks` | Get all risk assessments           | Any           |
| POST   | `/risks` | Create new risk assessment         | Safety only   |
| PUT    | `/risks` | Update a risk assessment           | Safety only   |
| DELETE | `/risks` | Delete a risk assessment           | Safety only   |

### MIWI Documents
| Method | Endpoint  | Description                   |
|--------|-----------|-------------------------------|
| GET    | `/miwi`   | Download a MIWI PDF by name   |
| GET    | `/miwis`  | List all MIWI filenames       |
| POST   | `/miwi`   | Upload a new MIWI PDF         |

---

## Database Schema

Database name: `ptw_database` (PostgreSQL, localhost)

### `users`
```sql
username    VARCHAR(50)  PRIMARY KEY
password    VARCHAR(100) NOT NULL
name        VARCHAR(100) NOT NULL
role        VARCHAR(50)  NOT NULL
department  VARCHAR(100)
email       VARCHAR(100)
ext         VARCHAR(50)
```

### `ptws`
```sql
id                          SERIAL PRIMARY KEY
type                        VARCHAR(100)
date                        VARCHAR(100)
location                    VARCHAR(100)
equipment                   VARCHAR(100)
area_class                  VARCHAR(100)
department                  VARCHAR(100)
description                 VARCHAR(300)
requestor                   VARCHAR(100)
performing                  VARCHAR(100)
issuing                     VARCHAR(100)
performing_timestamp        VARCHAR(100)
issuing_timestamp           VARCHAR(100)
close_performing            VARCHAR(100)
close_issuing               VARCHAR(100)
close_performing_timestamp  VARCHAR(100)
close_issuing_timestamp     VARCHAR(100)
hold_performing             VARCHAR(100)
hold_issuing                VARCHAR(100)
hold_performing_timestamp   VARCHAR(100)
hold_issuing_timestamp      VARCHAR(100)
keep_isolations             TEXT[]
prev_running_status         VARCHAR(100)
miwi                        VARCHAR(100)
mos                         VARCHAR(100)
tools                       TEXT[]
hazards                     TEXT[]
controls                    TEXT[]
risks                       TEXT[]
approval_status             VARCHAR(100)
running_status              VARCHAR(100)
approvals                   JSONB[]
isolations                  JSONB[]
attachs                     TEXT[]
```

### `active_isolations`
```sql
tag          VARCHAR  PRIMARY KEY
type         VARCHAR(100)
description  VARCHAR(100)
linked_ptws  TEXT[]
primary_ptw  VARCHAR(100)
latest_ptw   VARCHAR(100)
```

### `risks`
```sql
title          VARCHAR(300) NOT NULL
date           VARCHAR(100) NOT NULL
hazard         VARCHAR(300) NOT NULL
effect         VARCHAR(300)
free_analysis  VARCHAR(300)
ctrl           VARCHAR(300)
ctrl_analysis  VARCHAR(300)
eval           VARCHAR(300)
```

---

## Client Architecture

The desktop client is structured around role-based main windows. After login, `MainWindow.py` routes the user to the appropriate role-specific window (e.g., `IssuingMainWindow`, `SafetyMainWindow`, `AdminMainWindow`, etc...).

### Global Data Cache

`GlobalData` maintains an in-memory cache of:
- `allUsers` — dict of username → SecuredUser
- `allPTWs` — list of PTWData objects
- `activeIsolations` — dict of tag → ActiveIsolation
- `allRisks` — list of RiskAssessment objects
- `allMiwis` — list of MIWI filenames

The cache is refreshed on login and after any mutation operation.

### Key Client Modules

| Module                      | Purpose                                            |
|-----------------------------|---------------------------------------------------|
| `main.py`                   | Entry point; launches QApplication                 |
| `Login.py`                  | Login screen; handles password reset flow          |
| `MainWindow.py`             | Post-login router; loads role-specific window      |
| `clientRequests.py`         | HTTP wrapper; all server calls return `(err, data)`|
| `GlobalData.py`             | Client-side data cache                             |
| `PTWData.py`                | Mirrored data model classes (client-side copy)     |
| `User.py`                   | User model                                         |
| `WidgetPTW.py`              | Full PTW form (create/view/edit)                   |
| `TablePTWs.py`              | Table listing all PTWs with filters                |
| `TableUsers.py`             | Admin user management table                        |
| `TableRisks.py`             | Risk assessment list and editor                    |
| `TableIsolation.py`         | All available isolation points table               |
| `TableActiveIsolations.py`  | Currently active (linked) isolations view          |
| `TableAttachments.py`       | PTW attachment management                          |
| `DialogUser.py`             | Create/edit user dialog                            |
| `DialogIsolation.py`        | Create/edit isolation dialog                       |
| `DialogRisk.py`             | Risk item creation dialog                          |
| `DialogSelectIsolations.py` | Dialog to choose isolations when requesting hold   |
| `DialogSettings.py`         | App settings (server URL, etc.)                    |
| `ReportGenerator.py`        | Generates printable PDF permit reports             |

### Role-Specific Windows (all inside `MainWindow.py`)

All role-specific views are implemented as classes within `MainWindow.py`. After login, the file routes to the appropriate class based on the user's role:

- `AdminMainWindow` — full access
- `UserMainWindow` — create PTWs, manage own permits
- `CoordinatorMainWindow` — PTW approval coordination
- `IssuingMainWindow` — run/hold/close confirmation
- `SafetyMainWindow` — risk assessments, safety approvals
- `PDHMainWindow`, `PGMMainWindow`, `SODMainWindow`, `DFGMMainWindow` — management approvals

---

## Known Issues / Notes

1. **Passwords stored in plain text** — no hashing is applied before storage.
2. **File storage is local filesystem** — attachments and MIWI documents are stored on the server's local disk. Regular backups of `server/miwi/` and `server/ptw-*-attachments/` are recommended.
