# Automated tests

Two independent halves, because `server/` and `client/` both define a top-level `models`
package and cannot be imported into one Python process:

```
tests/
  common/ptw_factory.py   builders for PTW / IC / approval / run-cycle fixtures (used by both halves)
  common/ptw_test_db.py   throwaway-database bootstrap + the fixed test users (server context)
  common/live_server.py   test-only server process the client contract tests spawn
  server/                 rootdir for the server half   ->  pytest tests/server
    unit/                 pure domain logic, no database (approval chain, run cycle, gas test,
                          validation, IC status, model round-trips, small model pieces)
    api/                  Flask test client against a throwaway PostgreSQL database (auth,
                          permission matrix, PTW lifecycle, IC lifecycle + auto de-isolation,
                          risk assessments, user accounts, password reset, attachments/MIWI,
                          admin logs + backups (real pg_dump), mail, SSE)
  client/                 rootdir for the client half   ->  pytest tests/client
    unit/                 client/server model parity, i18n, spreadsheet import, Arabic text
                          shaping, the async request worker, OCR bundle resolution
    gui/                  role windows + per-tab menu options, tab routing, every dialog
                          (PTW/IC/gas test/users/settings/alarms/...), MainWindow's action
                          handlers (run/hold/close/gas-test/approve/IC lifecycle/linking),
                          alarms, SSE patching, login window + role routing, tables, widgets
                          - all headless Qt
    reports/              PDF and Excel generation (permit, IC, MOS, risk assessment, QR
                          codes), read back with pypdf / openpyxl
    contract/             the real client request layer + SSE listener + cache refresh
                          against a live test server
  run_all.sh              runs both halves
```

## Running

```bash
tests/run_all.sh                      # everything
pytest tests/server                   # server only (unit + api)
pytest tests/server/unit              # no database needed
QT_QPA_PLATFORM=offscreen pytest tests/client
pytest tests/client -m gui            # only headless-Qt tests
```

Coverage (`--cov=server` / `--cov=client`): server 85%, client 79%.

Running `pytest` from the repo root fails on purpose with a message explaining the split.

Dependencies beyond the app's own: `pytest`, `pytest-qt`, `freezegun`, `pypdf`.

## Server API tests and the database

`tests/server/api/conftest.py` reads `DB_HOST` / `DB_USER` / `DB_PASSWORD` from `server/.env`
(environment variables win), forces `DB_NAME=ptw_test` (override with `PTW_TEST_DB_NAME`) and
refuses to run if that equals the real database name. The test database and its tables are
created with the project's own `server/dev-scripts/init_db.py`. `PTW_DATA_DIR` is pointed at a
fresh temp directory so attachments, MIWIs, logs and backups never touch real data.

Every test starts from empty `ptws` / `ics` / `risks` tables and a refreshed in-memory cache.
Users are created once per session with a bcrypt cost of 4 (the hash carries its cost, so
verification is cheap too). Flask-Mail's `send` is replaced by a recorder; nothing is ever
emailed.

If PostgreSQL is not reachable the `api/` directory is skipped, not failed.

## Client contract tests and the live server

`tests/client/contract/` exercises the real `ClientRequests` functions over real HTTP. The
`live_server` fixture spawns `tests/common/live_server.py` in a separate interpreter (the
client process cannot import the server tree), on a port chosen when the client conftest is
imported, so `PTW_SERVER_URL` already points there when the request modules bind it. That
server uses the same throwaway database and user set as the API tests, disables outgoing
mail, and adds `POST /__test__/reset`, which the `contract` fixture calls before each test.
If PostgreSQL is unreachable the contract tests are skipped.

## Client tests

`QT_QPA_PLATFORM=offscreen` is set by the client conftest, so no display is required. The
`offline_window` fixture builds a real role window with the SSE listener and the server
refresh stubbed; the window populates from whatever the test put into `globalData`.
Windows are torn down without `close()` (that would prompt about the tray).

`tests/client/unit/test_model_parity.py` loads `server/models` into the client process
under a separate module namespace and compares every derived value (statuses, pending
approvers, validation messages, required docs, ...) for a set of fixtures. A failure there
means one copy of `PTW.py` / `Isolation.py` / `User.py` was edited without the other.

## Known failures documented as `xfail(strict=True)`

These flip to a hard failure the moment the bug is fixed, so the marker gets removed:

- `tests/client/contract/test_client_requests.py::TestPtwLifecycle::test_return_ptw_endpoint`
  `ClientRequests.returnPTW` posts to `/ptws/return`, a route the server does not have.
  Nothing in the GUI calls it (returns go through `updateApprovalPTW`); delete it or add
  the route.
- `tests/server/api/test_risks.py::TestGenericLibrary::test_hse_creates_updates_deletes`
  `RisksDb.updateRiskAssessmentFromDict` deletes old rows with
  `WHERE title = %s AND ptw_id = %s`; for a library assessment `ptw_id` is `NULL`, and
  `= NULL` never matches in SQL, so nothing is deleted and every edit *appends* its items
  instead of replacing them - a library assessment grows every time it's saved. Needs
  `ptw_id IS NOT DISTINCT FROM %s` (or a separate `IS NULL` branch).
- `tests/client/gui/test_tables.py::TestTableAttachments::test_default_attachment_lists_are_independent_between_instances`
  `TableAttachments.__init__`'s `attachments: list[Attachment] = []` parameter is a shared
  mutable default, so attachments staged in one instance built without an explicit
  `attachments=` argument leak into every later instance built the same way.
- `tests/client/reports/test_more_reports.py::TestQrHelpers::test_oversized_payload_degrades_error_correction_then_truncates`
  `ReportGenerator._qrWithLogoFromRows` (`client/reports/ReportGenerator.py:100`) only
  catches `qrcode.exceptions.DataOverflowError` in its three-tier fallback, but the
  installed qrcode 8.2 raises a plain `ValueError` from `QRCode.best_fit()` first - so an
  oversized payload (e.g. a very long Arabic description) crashes the report instead of
  degrading the QR code as documented.

## Also found, not xfail-tracked (pre-existing, not exercised by a specific test)

- `ReportGenerator._makeQrWithLogo` / `_makeQrWithLogoIC` write the QR code PNG with
  `tempfile.NamedTemporaryFile(delete=False, ...)` and never remove it after embedding it
  in the PDF - every report generated, in production too, leaks one PNG into the OS temp
  directory.

## Not covered here (and why)

- Windows-only paths (keyring, `.ps1` scripts, Nuitka/PyInstaller builds): need a Windows runner.
- Real SMTP delivery, the nginx/TLS layer, SSE reconnect after a server restart: deployment/staging checks.
- `WidgetPidWiring`'s own upload/OCR/highlight-burn pipeline (only `PidWiringHighlighter`'s
  pure geometry/colour logic is covered): needs real PDFs/images and a display.
- A handful of MainWindow view/print delegating methods (`viewPTW`, `printPTW`,
  `exportPTWs`, ...) that open `DialogPTW`/`DialogIC`/`ReportGenerator` rather than making
  a request: the dialogs and report generation they delegate to are covered directly.
- Whether the UI *looks* right: tests assert structure and routing, not pixels.
