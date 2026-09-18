"""API-test harness: the real Flask app, the real DB layer, a throwaway PostgreSQL database.

Import-time behaviour of the server is the one thing this has to work around: `core.py`
connects to PostgreSQL (and `exit(1)`s if it can't) the moment it's imported, reading its
connection settings from the environment / `server/.env`. So, before anything from the
server tree is imported, this file:

  1. copies DB_HOST/DB_USER/DB_PASSWORD from `server/.env` into the environment (only if
     not already set), and forces DB_NAME to a *test* database (`ptw_test`, override with
     PTW_TEST_DB_NAME). It refuses to run if that resolves to the same name as the real
     database.
  2. points PTW_DATA_DIR (attachments, MIWIs, logs, backups) at a fresh temp directory.
  3. creates the test database and its tables with the project's own `init_db.py`.
  4. skips the whole `api/` directory (rather than erroring) if PostgreSQL is unreachable.

Each test then starts from empty `ptws`/`ics`/`risks` tables (users are created once per
session - bcrypt is slow - with a reduced work factor) and a refreshed in-memory cache.
"""

import base64
import importlib.util
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

TESTS_SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(TESTS_SERVER_DIR))
SERVER_DIR = os.path.join(ROOT, 'server')

# ---- 1. environment ---------------------------------------------------------------------
from dotenv import dotenv_values  # noqa: E402

_dotenv = dotenv_values(os.path.join(SERVER_DIR, '.env'))
TEST_DB = os.environ.get('PTW_TEST_DB_NAME', 'ptw_test')
REAL_DB = os.environ.get('DB_NAME') or _dotenv.get('DB_NAME') or 'ptw_database'
if TEST_DB == REAL_DB:
    raise pytest.UsageError(
        f"PTW_TEST_DB_NAME ({TEST_DB!r}) must differ from the real DB_NAME - refusing to run API tests "
        "against the production database.")
for key in ('DB_HOST', 'DB_USER', 'DB_PASSWORD'):
    if key not in os.environ and _dotenv.get(key):
        os.environ[key] = _dotenv[key]
os.environ['DB_NAME'] = TEST_DB

# ---- 2. data dir ------------------------------------------------------------------------
DATA_DIR = tempfile.mkdtemp(prefix='ptw-test-data-')
os.environ['PTW_DATA_DIR'] = DATA_DIR
os.environ.setdefault('MAIL_USERNAME', 'ptw-tests@example.invalid')
os.environ.setdefault('MAIL_PASSWORD', 'unused')

# ---- 3./4. database ---------------------------------------------------------------------
import psycopg2  # noqa: E402

try:
    psycopg2.connect(host=os.environ.get('DB_HOST', 'localhost'), database='postgres',
                     user=os.environ.get('DB_USER', 'postgres'), password=os.environ.get('DB_PASSWORD'),
                     connect_timeout=3).close()
except Exception as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"PostgreSQL not reachable ({exc}); skipping API tests", allow_module_level=True)

_spec = importlib.util.spec_from_file_location('ptw_init_db', os.path.join(SERVER_DIR, 'dev-scripts', 'init_db.py'))
_init_db = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_init_db)
assert _init_db.DB_NAME == TEST_DB


def _create_test_database():
    """The project's own init_db.ensure_database_exists(), with one fallback: a local
    PostgreSQL whose template1 has a collation-version mismatch (a common state after an OS
    libc upgrade) refuses CREATE DATABASE from template1, so retry from template0."""
    try:
        _init_db.ensure_database_exists()
    except psycopg2.Error as exc:
        if 'collation version mismatch' not in str(exc):
            raise
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        conn = psycopg2.connect(host=_init_db.DB_HOST, database='postgres', user=_init_db.DB_USER, password=_init_db.DB_PASSWORD)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{TEST_DB}" TEMPLATE template0')
        finally:
            conn.close()


_create_test_database()
_init_db.init_tables()

# Cheap bcrypt for tests: the cost factor is stored inside each hash, so verification of
# these test users is cheap too. Must happen before UsersDb seeds/adds anyone.
import bcrypt  # noqa: E402
import db.usersDb as _usersDb  # noqa: E402

_usersDb._hash_password = lambda plain: bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()

# Importing `app` pulls in core (DB pool + cache), every blueprint, and their background threads.
import app as _app_module  # noqa: E402
import core  # noqa: E402
import sse  # noqa: E402
from GlobalData import globalData  # noqa: E402
from db.commonDb import CommonDB  # noqa: E402
from models.User import User, UserRoles, UserDepartments  # noqa: E402

flask_app = _app_module.app
flask_app.config['TESTING'] = True

PASSWORD = 'pw'

# username -> (role, department). One per approval slot in the chain, plus the odd ones out.
USERS = {
    'user_turbo':   (UserRoles.USER, UserDepartments.TURBO),
    'user_turbo2':  (UserRoles.USER, UserDepartments.TURBO),
    'user_mech':    (UserRoles.USER, UserDepartments.MECH),
    'user_elec':    (UserRoles.USER, UserDepartments.ELEC),
    'user_inst':    (UserRoles.USER, UserDepartments.INST),
    'user_telecom': (UserRoles.USER, UserDepartments.TELECOM),
    'user_project': (UserRoles.USER, UserDepartments.PROJECT),
    'user_civil':   (UserRoles.USER, UserDepartments.CVL),
    'user_cp':      (UserRoles.USER, UserDepartments.CATHODIC_PROTECTION),
    'user_it':      (UserRoles.USER, UserDepartments.IT),
    'coord':        (UserRoles.COORDINATOR, UserDepartments.PROD),
    'issuing':      (UserRoles.ISSUING, UserDepartments.PROD),
    'hse':          (UserRoles.HSE_ENGINEER, UserDepartments.HSE),
    'gas':          (UserRoles.GAS_TESTER, UserDepartments.PROD),
    'pdh':          (UserRoles.PDH, UserDepartments.PROD),
    'pgm':          (UserRoles.PGM, UserDepartments.PROD),
    'sod':          (UserRoles.SOD, UserDepartments.PROD),
    'dfgm':         (UserRoles.DFGM, UserDepartments.PROD),
    'isolator':     (UserRoles.ISOLATOR, UserDepartments.PROD),
    'admin':        (UserRoles.ADMIN, 'Admin'),
    'inactive':     (UserRoles.USER, UserDepartments.TURBO),
}
GUEST = 'visitor'   # no account: goes through as a GUEST when no password is sent

# The department users whose approval an Excavation permit needs, in chain order.
EX_USERS = ['user_mech', 'user_elec', 'user_inst', 'user_telecom', 'user_turbo', 'user_project', 'user_civil', 'user_cp']


def auth(username, password=None):
    """HTTP Basic Auth headers for `username`. Defaults to the shared test password, or to
    an empty password for the GUEST pseudo-user (which is how a guest is recognised)."""
    if password is None:
        password = '' if username == GUEST else PASSWORD
    token = base64.b64encode(f'{username}:{password}'.encode()).decode()
    return {'Authorization': f'Basic {token}'}


def _exec(sql, params=None):
    with CommonDB.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def _reset_users():
    _exec('TRUNCATE users')
    for username, (role, dept) in USERS.items():
        core.userDB.addUser(User(username=username, password=PASSWORD, name=username.replace('_', ' ').title(),
                                 role=role, department=str(dept), email=f'{username}@example.invalid'))
    core.userDB.setUserActive('inactive', False)


@pytest.fixture(scope='session', autouse=True)
def _session_users():
    _reset_users()
    yield
    import shutil
    shutil.rmtree(DATA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_db():
    """Empty PTW/IC/risk tables and resync the in-memory cache before every test."""
    _exec('TRUNCATE ptws, ics, risks RESTART IDENTITY')
    err = globalData.refresh(core.userDB, core.ptwDB, core.icDB)
    assert err is None, err
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
