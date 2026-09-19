"""API-test harness: the real Flask app, the real DB layer, a throwaway PostgreSQL database.

Import-time behaviour of the server is the one thing this has to work around: `core.py`
connects to PostgreSQL (and `exit(1)`s if it can't) the moment it's imported, reading its
connection settings from the environment / `server/.env`. So, before anything from the
server tree is imported, `ptw_test_db.configure_env()` (tests/common) forces DB_NAME to the
test database and PTW_DATA_DIR to a temp dir, and the database is created with the
project's own `init_db.py`. If PostgreSQL is unreachable the whole `api/` directory is
skipped, not failed.

Each test then starts from empty `ptws`/`ics`/`risks` tables (users are created once per
session - bcrypt is slow - with a reduced work factor) and a refreshed in-memory cache.
"""

import base64
from types import SimpleNamespace

import pytest

import ptw_test_db
from ptw_test_db import USERS, PASSWORD, GUEST, EX_USERS  # noqa: F401  (re-exported for tests)

SETTINGS = ptw_test_db.configure_env()
_unreachable = ptw_test_db.postgres_reachable(SETTINGS)
if _unreachable:  # pragma: no cover - environment dependent
    pytest.skip(f"PostgreSQL not reachable ({_unreachable}); skipping API tests", allow_module_level=True)
ptw_test_db.ensure_test_database(SETTINGS)
ptw_test_db.patch_bcrypt()

# Importing `app` pulls in core (DB pool + cache), every blueprint, and their background threads.
import app as _app_module  # noqa: E402
import core  # noqa: E402
import sse  # noqa: E402
from GlobalData import globalData  # noqa: E402

flask_app = _app_module.app
flask_app.config['TESTING'] = True
DATA_DIR = SETTINGS['data_dir']


def auth(username, password=None):
    """HTTP Basic Auth headers for `username`. Defaults to the shared test password, or to
    an empty password for the GUEST pseudo-user (which is how a guest is recognised)."""
    if password is None:
        password = '' if username == GUEST else PASSWORD
    token = base64.b64encode(f'{username}:{password}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


@pytest.fixture(scope='session', autouse=True)
def _session_users():
    ptw_test_db.reset_users(core)
    yield
    import shutil
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_db():
    """Empty PTW/IC/risk tables and resync the in-memory cache before every test."""
    ptw_test_db.reset_tables(core, globalData)
    yield


@pytest.fixture(autouse=True)
def sent_mail(monkeypatch):
    """Record instead of sending: every Flask-Mail message the server tries to send lands here."""
    box = []
    monkeypatch.setattr(core.mail, 'send', lambda msg: box.append(msg))
    yield box


@pytest.fixture
def client():
    return flask_app.test_client()


@pytest.fixture
def server():
    """Handles onto the live server internals for white-box assertions."""
    return SimpleNamespace(app=flask_app, core=core, globalData=globalData, sse=sse, ptwDB=core.ptwDB,
                           userDB=core.userDB, icDB=core.icDB, data_dir=DATA_DIR)
