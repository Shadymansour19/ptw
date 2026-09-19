# Automated tests

Two independent halves, because `server/` and `client/` both define a top-level `models`
package and cannot be imported into one Python process:

```
tests/
  common/ptw_factory.py   builders for PTW / IC / approval / run-cycle fixtures (used by both halves)
  common/ptw_test_db.py   throwaway-database bootstrap + the fixed test users (server context)
  common/live_server.py   test-only server process the client contract tests spawn
  server/                 rootdir for the server half   ->  pytest tests/server
    unit/                 pure domain logic, no database
    api/                  Flask test client against a throwaway PostgreSQL database
                          (auth, permissions, PTW lifecycle, IC lifecycle + auto de-isolation, mail, SSE)
  client/                 rootdir for the client half   ->  pytest tests/client
    unit/                 client/server model parity, i18n, spreadsheet import
    gui/                  role windows, tab routing, DialogPTW (headless Qt)
    reports/              PDF and Excel generation, read back with pypdf / openpyxl
    contract/             the real client request layer + SSE listener against a live test server
  run_all.sh              runs both halves
```

## Running

```bash
tests/run_all.sh                      # everything
pytest tests/server                   # server only (unit + api)
pytest tests/server/unit              # no database needed
QT_QPA_PLATFORM=offscreen pytest tests/client
pytest tests/client -m gui            # only widget tests
```

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

## Not covered here (and why)

- Windows-only paths (keyring, `.ps1` scripts, Nuitka/PyInstaller builds): need a Windows runner.
- Real SMTP delivery, the nginx/TLS layer, SSE reconnect after a server restart: deployment/staging checks.
- Whether the UI *looks* right: tests assert structure and routing, not pixels.
