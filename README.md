# PTW — Permit To Work System

A desktop-based **Permit To Work (PTW)** management system built for industrial operations. It enforces a structured, multi-stage safety workflow that governs when and how maintenance or hazardous work is authorized, executed, and closed — with full audit trails, equipment isolation tracking, and role-based access control.

---

## Screenshots

**Home Dashboard:**
![Home](screenshots/home.png) 

**PTW List:**
![PTW List](screenshots/ptw-list.png)

**PTW List Filtered:**
![PTW List Filtered](screenshots/ptw-list-filtered.png)

**Isolations:**
![Isolations](screenshots/isolations.png) 

**New PTW Form:**
![New PTW](screenshots/new-ptw.png)

**Server Logs:**
![Server Logs](screenshots/server-logs.png) 

---

## Features

- **Multi-stage approval workflow** — Coordinator → Issuing → Safety → Management chain (PDH → PGM → SOD → DFGM)
- **Full running lifecycle** — Run / Hold / Close with two-party confirmation (Performing Authority + Issuing Authority)
- **Equipment isolation management** — Tracks shared isolation points across multiple concurrent PTWs; enforces primary/latest ownership rules
- **Color-coded permit types** — Cold Work (blue), Spark (yellow), Hot Work (red), HydroCarbon (black), Excavation (gray), Confined Space (green)
- **Risk assessment library** — Safety team maintains reusable risk assessment documents linked to permits
- **PDF permit reports** — Printable PDF generation for each PTW
- **Excel export** — Export the PTW list to a formatted, color-coded `.xlsx` spreadsheet
- **Real-time notifications** — Server-Sent Events (SSE) push PTW changes to all connected clients instantly; no polling required
- **Archived permits** — Closed PTWs can be archived; archived data is fetched on-demand only to reduce server overhead
- **File attachments** — Per-permit document uploads (medical certificates, tool checklists, technical drawings)
- **MIWI documents** — Shared Maintenance & Work Instruction PDFs referenced across permits
- **Role-based UI** — Each of 10 roles gets a tailored interface showing only relevant actions and data
- **Password reset via email** — 6-digit verification code sent via Gmail SMTP, expires in 15 minutes
- **Multi-language support** — Language switching built into the UI
- **Server activity logging** — rotating log files (10 MB, 5 backups) with DEBUG/INFO/WARNING/ERROR/CRITICAL levels; log lines include timestamp, level, and source location
- **Admin log viewer** — dedicated tab for Admins with collapsible per-file panels, lazy loading, per-level color coding, and a level filter
- **Light/dark theme** — full UI theme switching (system / light / dark) with preference saved server-side per user

---

## Technology Stack

| Layer         | Technology                            |
|---------------|---------------------------------------|
| Client UI     | Python 3.12+, PyQt6, qtawesome        |
| HTTP Client   | `requests` (Basic Auth + SSE stream)  |
| Server        | Python 3.12+, Flask                   |
| Database      | PostgreSQL (psycopg2)                 |
| Email         | Flask-Mail (Gmail SMTP)               |
| Credentials   | `keyring`                             |
| Reports       | ReportLab (PDF), Pillow, qrcode       |
| Excel Export  | `openpyxl`                            |
| Distribution  | Nuitka `--onedir` → zipped for release (Windows + Linux) |

---

## PTW Types

| Code | Name           | Color  | Use Case                     |
|------|----------------|--------|------------------------------|
| CW   | Cold Work      | Blue   | Non-spark generating work    |
| SP   | Spark          | Yellow | Work that may produce sparks |
| HT   | Hot Work       | Red    | Open flame / welding         |
| HC   | HydroCarbon    | Black  | Work near HC systems         |
| EX   | Excavation     | Gray   | Ground excavation work       |
| CS   | Confined Space | Green  | Work inside confined spaces  |

---

## User Roles

| Role | Responsibilities |
|---|---|
| **User** | Creates PTWs; requests run, hold, and close |
| **Coordinator** | Reviews and approves PTWs in the coordination stage |
| **Issuing** | Authorizes execution; accepts/rejects run, hold, close confirmations |
| **Safety** | Safety approvals; creates and manages risk assessments |
| **PDH** | Production/Plant Department Head approval |
| **PGM** | Production General Manager approval |
| **SOD** | System/Operation Director approval |
| **DFGM** | Direct Field General Manager — highest approval authority |
| **Isolator** | Manages physical equipment isolations |
| **Admin** | Full system access; manages all users |

---

## PTW Lifecycle

### Approval Cycle

```
Coordinator → Issuing → Safety → [PDH → PGM → SOD → DFGM]
```


**Statuses:** `UNDER_REVIEW` → `APPROVED` / `RETURNED` / `REJECTED`

### Running Cycle

Once approved, the permit enters a state machine driven by the Performing Authority (PA) and Issuing Authority (IA):

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
    │         │ [Archive]
    │         │
    │         ▼
    │      ARCHIVED
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

---

## Isolation Management

Isolations are safety locks placed on equipment to prevent accidental energization during active work.

**Types:** Mechanical · Electrical · Self · Protective System · Other

**Shared isolation rule:** A single physical isolation point may be required by multiple concurrent PTWs. The system tracks:
- `primary_ptw` — the first PTW that linked the isolation (responsible for *applying* it)
- `latest_ptw` — the most recently linked PTW (responsible for *removing* it)
- `linked_ptws` — all PTWs currently depending on this isolation point

**Lifecycle:**
- PTW → `RUNNING`: all its isolations are linked
- PTW → `HELD`: only `keep_isolations` tags remain linked; others are released
- PTW → `CLOSED`: all its isolations are unlinked

---

## Project Structure

```
ptw/
├── .github/workflows/build.yml  # CI/CD — builds Windows + Linux binaries via Nuitka
├── client/                      # PyQt6 desktop application
│   ├── main.py                  # Entry point
│   ├── Login.py                 # Login & password reset
│   ├── MainWindow.py            # Role-based window router
│   ├── GlobalData.py            # Client-side data cache
│   ├── clientRequests.py        # HTTP API wrapper
│   ├── SSEListener.py           # Real-time event listener (QThread)
│   ├── PTWData.py               # Client-side data models
│   ├── utils.py                 # Shared helpers (resource_path, objToDict, dictToObj)
│   ├── WidgetPTW.py             # Full PTW form (create/view/edit)
│   ├── TablePTWs.py             # PTW list with filters + Excel export
│   ├── TabServerLogs.py         # Admin log viewer tab (collapsible, color-coded, filterable)
│   ├── CheckableComboBox.py     # Reusable multi-select checkbox combo box
│   ├── ReportGenerator.py       # PDF and Excel report generation
│   ├── assets/                  # Bundled images and icons
│   ├── fonts/                   # Bundled fonts
│   └── ...                      # Dialogs, tables
│
└── server/                      # Flask REST API
    ├── app.py                   # All route handlers + SSE broadcast
    ├── PTWData.py               # Core data models & enums
    ├── utils.py                 # Shared helpers (objToDict, dictToObj)
    ├── ptwDb.py                 # PTW database operations
    ├── usersDb.py               # User database operations
    ├── IsolationDb.py           # Isolation database operations
    ├── risksDb.py               # Risk assessment DB operations
    ├── GlobalData.py            # Server-side in-memory cache
    ├── miwi/                    # MIWI PDF documents
    └── logs/                    # Rotating server log files (gitignored)
```

---

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL
- Gmail account (for password reset emails)

### Database

Create the PostgreSQL database:

```sql
CREATE DATABASE ptw_database;
```

Then create the required tables (`users`, `ptws`, `active_isolations`, `risks`) — see [PROJECT.md](PROJECT.md) for the full schema.

### Server

```bash
cd server
pip install flask flask-mail psycopg2 python-dotenv bcrypt
python app.py
```

Create a `server/.env` file with your credentials:

```ini
DB_HOST=localhost
DB_NAME=ptw_database
DB_USER=postgres
DB_PASSWORD=yourpassword
MAIL_USERNAME=your@gmail.com
MAIL_PASSWORD=your_app_password
```

> **First deployment:** if the database already has plain-text passwords, run the migration script once before starting the server:
> ```bash
> python migrate_hash_passwords.py
> ```

### Client

```bash
cd client
pip install PyQt6 qtawesome requests keyring reportlab pillow qrcode pypdf openpyxl bcrypt
python main.py
```

On first launch, open **Settings** and point the client at your server URL.

---

## API Overview

| Category | Endpoints |
|---|---|
| Auth | `POST /login` · `POST /reset-password-request` · `POST /reset-password` |
| Users | `GET/POST/PUT/DELETE /users` |
| PTWs | `GET/POST/DELETE /ptws` |
| Approvals | `POST /ptws/approvals` |
| Run cycle | `POST /ptws/run-request` · `POST /ptws/run` |
| Hold cycle | `POST /ptws/hold-request` · `POST /ptws/hold` |
| Close cycle | `POST /ptws/close-request` · `POST /ptws/close` |
| Attachments | `GET/POST/DELETE /ptws/attachments` · `POST /ptws/attachments/copy` |
| Isolations | `GET /isolations` |
| Risks | `GET/POST/PUT/DELETE /risks` |
| MIWI docs | `GET /miwi` · `GET /miwis` · `POST /miwi` |
| Archive | `GET /ptws/archive` · `POST /ptws/archive` |
| Events (SSE) | `GET /events` |

Full API reference in [PROJECT.md](PROJECT.md).

---

## Building for Distribution

Pre-built releases for Windows and Linux are produced automatically via GitHub Actions on every version tag:

```bash
git tag v1.x.x
git push origin v1.x.x
```

Download `PTW-windows.zip` and `PTW-linux.zip` from the **Releases** page. Extract the zip and run `PTW.exe` (Windows) or `PTW` (Linux) from the extracted folder.

Builds use **Nuitka** (`--onedir`) for native compilation — the app folder is zipped before upload. To trigger a manual build without a tag: **Actions → Build PTW → Run workflow**.

---

## Known Limitations

See [KNOWN_ISSUES.md](KNOWN_ISSUES.md) for the full security and bug backlog with fix guidance.

