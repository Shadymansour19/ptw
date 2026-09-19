"""Throwaway-database bootstrap shared by the server API tests and the live test server
that the client contract tests spawn.

Everything here runs in a *server* context (server/ on sys.path). Import order matters:
`configure_env()` must run before any server module is imported, because `core.py`
connects to PostgreSQL the moment it's imported and reads its settings from the
environment / `server/.env`.
"""

import importlib.util
import os
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERVER_DIR = os.path.join(ROOT, 'server')

PASSWORD = 'pw'
GUEST = 'visitor'   # no account: goes through as a GUEST when no password is sent

# username -> (role value, department value). One per approval slot in the chain, plus the
# odd ones out. Plain strings so this module needs no server imports to be read.
USERS = {
    'user_turbo':   ('User', 'Turbo'),
    'user_turbo2':  ('User', 'Turbo'),
    'user_mech':    ('User', 'Mech'),
    'user_elec':    ('User', 'Elec'),
    'user_inst':    ('User', 'Instrumentation'),
    'user_telecom': ('User', 'Telecom'),
    'user_project': ('User', 'Project'),
    'user_civil':   ('User', 'Civil'),
    'user_cp':      ('User', 'Cathodic Protection'),
    'user_it':      ('User', 'IT'),
    'coord':        ('Coordinator', 'Prod'),
    'issuing':      ('Issuing', 'Prod'),
    'hse':          ('HSE Engineer', 'HSE'),
    'gas':          ('Gas Tester', 'Prod'),
    'pdh':          ('PDH', 'Prod'),
    'pgm':          ('PGM', 'Prod'),
    'sod':          ('SOD', 'Prod'),
    'dfgm':         ('DFGM', 'Prod'),
    'isolator':     ('Isolator', 'Prod'),
    'isolator_mech': ('Isolator', 'Mech'),
    'admin':        ('Admin', 'Admin'),
    'inactive':     ('User', 'Turbo'),
}

# The department users whose approval an Excavation permit needs, in chain order.
EX_USERS = ['user_mech', 'user_elec', 'user_inst', 'user_telecom', 'user_turbo', 'user_project', 'user_civil', 'user_cp']


def configure_env() -> dict:
    """Point the server at the test database and a fresh data dir. Returns the settings used.

    DB_HOST/DB_USER/DB_PASSWORD come from `server/.env` unless already set. DB_NAME is forced
    to `ptw_test` (override: PTW_TEST_DB_NAME) and must differ from the real database name.
    """
    from dotenv import dotenv_values
    dotenv = dotenv_values(os.path.join(SERVER_DIR, '.env'))
    test_db = os.environ.get('PTW_TEST_DB_NAME', 'ptw_test')
    real_db = os.environ.get('DB_NAME') or dotenv.get('DB_NAME') or 'ptw_database'
    if test_db == real_db:
        raise RuntimeError(f"PTW_TEST_DB_NAME ({test_db!r}) must differ from the real DB_NAME - refusing to touch the production database")
    for key in ('DB_HOST', 'DB_USER', 'DB_PASSWORD'):
        if key not in os.environ and dotenv.get(key):
            os.environ[key] = dotenv[key]
    os.environ['DB_NAME'] = test_db
    data_dir = os.environ.get('PTW_DATA_DIR') or tempfile.mkdtemp(prefix='ptw-test-data-')
    os.environ['PTW_DATA_DIR'] = data_dir
    os.environ.setdefault('MAIL_USERNAME', 'ptw-tests@example.invalid')
    os.environ.setdefault('MAIL_PASSWORD', 'unused')
    return {'db_name': test_db, 'data_dir': data_dir,
            'host': os.environ.get('DB_HOST', 'localhost'), 'user': os.environ.get('DB_USER', 'postgres'),
            'password': os.environ.get('DB_PASSWORD')}


def postgres_reachable(settings, timeout=3) -> str | None:
    """None if a connection to the `postgres` maintenance DB works, else the error text."""
    import psycopg2
    try:
        psycopg2.connect(host=settings['host'], database='postgres', user=settings['user'],
                         password=settings['password'], connect_timeout=timeout).close()
        return None
    except Exception as exc:  # pragma: no cover - environment dependent
        return str(exc)


def ensure_test_database(settings):
    """Create the test database and its tables with the project's own init_db.py.

    One fallback: a local PostgreSQL whose template1 has a collation-version mismatch (a
    common state after an OS libc upgrade) refuses CREATE DATABASE from template1, so retry
    from template0.
    """
    import psycopg2
    spec = importlib.util.spec_from_file_location('ptw_init_db', os.path.join(SERVER_DIR, 'dev-scripts', 'init_db.py'))
    init_db = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(init_db)
    assert init_db.DB_NAME == settings['db_name'], (init_db.DB_NAME, settings['db_name'])
    try:
        init_db.ensure_database_exists()
    except psycopg2.Error as exc:
        if 'collation version mismatch' not in str(exc):
            raise
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
        conn = psycopg2.connect(host=init_db.DB_HOST, database='postgres', user=init_db.DB_USER, password=init_db.DB_PASSWORD)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        try:
            with conn.cursor() as cur:
                cur.execute(f'CREATE DATABASE "{settings["db_name"]}" TEMPLATE template0')
        finally:
            conn.close()
    init_db.init_tables()


def patch_bcrypt():
    """Cheap bcrypt for tests: the cost factor is stored inside each hash, so verifying these
    users is cheap too. Must run before UsersDb seeds/adds anyone."""
    import bcrypt
    import db.usersDb as usersDb
    usersDb._hash_password = lambda plain: bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()


def _exec(sql, params=None):
    from db.commonDb import CommonDB
    with CommonDB.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def reset_users(core):
    """Replace the users table with the fixed USERS set (server context)."""
    from models.User import User
    _exec('TRUNCATE users')
    for username, (role, dept) in USERS.items():
        core.userDB.addUser(User(username=username, password=PASSWORD, name=username.replace('_', ' ').title(),
                                 role=role, department=dept, email=f'{username}@example.invalid'))
    core.userDB.setUserActive('inactive', False)


def reset_tables(core, globalData):
    """Empty PTW/IC/risk tables, wipe per-record files, and resync the in-memory cache."""
    import shutil
    _exec('TRUNCATE ptws, ics, risks RESTART IDENTITY')
    import paths
    for d in (paths.PTWS_DIR, paths.ICS_DIR, paths.MIWI_DIR, paths.BACKUP_DIR):
        shutil.rmtree(d, ignore_errors=True)
    # paths.py creates these at import, so the server can assume they exist - keep that true.
    for d in (paths.PTWS_DIR, paths.ICS_DIR, paths.MIWI_DIR):
        os.makedirs(d, exist_ok=True)
    err = globalData.refresh(core.userDB, core.ptwDB, core.icDB)
    if err:
        raise RuntimeError(err)
