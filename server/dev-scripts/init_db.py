"""One-time database initialization: creates the ptw_database (if it doesn't already
exist) and every table (`users`, `ptws`, `ics`, `risks`) in their current, final schema.

Replaces running the server once just to let each *Db class's constructor lazily
CREATE TABLE itself, and replaces the pile of ad-hoc ALTER TABLE statements that used
to live in those constructors to migrate already-deployed installs (table/column
renames, dropped columns, etc.) — those migrations are done; a fresh database no longer
needs to walk through them, it just gets the end result directly.

Safe to run more than once (every statement is IF NOT EXISTS / idempotent).

Run once, before starting the server for the first time: python server/dev-scripts/init_db.py
"""

import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

DB_NAME = os.environ.get('DB_NAME', 'ptw_database')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD')


def ensure_database_exists():
    conn = psycopg2.connect(host=DB_HOST, database='postgres', user=DB_USER, password=DB_PASSWORD)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
            if cur.fetchone():
                print(f"Database already exists: {DB_NAME}")
            else:
                cur.execute(f'CREATE DATABASE "{DB_NAME}"')
                print(f"Created database: {DB_NAME}")
    finally:
        conn.close()


def init_tables():
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    username    VARCHAR(50) PRIMARY KEY,
                    password    VARCHAR(100) NOT NULL,
                    name        VARCHAR(100) NOT NULL,
                    role        VARCHAR(50) NOT NULL,
                    department  VARCHAR(100),
                    email       VARCHAR(100),
                    ext         VARCHAR(50),
                    theme       VARCHAR(20),
                    is_active   BOOLEAN NOT NULL DEFAULT TRUE
                )
            """)
            print("Ensured table: users")

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ptws (
                    id                    SERIAL PRIMARY KEY,
                    type                  VARCHAR(100),
                    request_date          VARCHAR(100),
                    location              VARCHAR(100),
                    equipment             VARCHAR(100),
                    area_class            VARCHAR(100),
                    department            VARCHAR(100),
                    description           VARCHAR(300) NOT NULL,
                    fast_track            BOOLEAN NOT NULL DEFAULT FALSE,
                    requestor             VARCHAR(100),
                    run_cycles            JSONB[],
                    miwi                  VARCHAR(100),
                    mos                   VARCHAR(100),
                    tools                 TEXT[],
                    isolations            JSONB[],
                    hazards               TEXT[],
                    controls              TEXT[],
                    risks                 TEXT[],
                    linked_ics            TEXT[],
                    approvals             JSONB[],
                    is_archived           BOOLEAN NOT NULL DEFAULT FALSE
                )
            """)
            print("Ensured table: ptws")
            # No `attachs` column: attachment filenames are never persisted here, only read
            # live from the ptw-{id}-attachments/ folder (see ReportGenerator.ptwReport).
            # No `approval_status`/`running_status` column: PTW.__updateStatus() recomputes
            # both from `approvals`/`run_cycles` on every read, so they're always correct
            # without being stored. `is_archived` is the one bit that IS stored — archiving
            # isn't something a run cycle's fields can encode.

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ics (
                    id                              SERIAL PRIMARY KEY,
                    type                            VARCHAR(100),
                    requestor_department            VARCHAR(100),
                    execution_department            VARCHAR(100),
                    requestor                       VARCHAR(100),
                    requestor_timestamp             VARCHAR(100),
                    approvals                       JSONB[],
                    location                        VARCHAR(100),
                    equipment                       VARCHAR(100),
                    reason                          VARCHAR(300) NOT NULL,
                    items                           JSONB[],
                    pid_documents                   JSONB[],
                    isolate_asap                    BOOLEAN NOT NULL DEFAULT FALSE,
                    isolate_requestor               VARCHAR(100),
                    isolate_requestor_timestamp     VARCHAR(100),
                    isolate_issuing                 VARCHAR(100),
                    isolate_issuing_timestamp       VARCHAR(100),
                    isolate_issuing_action          VARCHAR(100),
                    isolate_isolator                VARCHAR(100),
                    isolate_isolator_timestamp      VARCHAR(100),
                    sanction_requestor               VARCHAR(100),
                    sanction_requestor_timestamp     VARCHAR(100),
                    sanction_issuing                 VARCHAR(100),
                    sanction_issuing_timestamp       VARCHAR(100),
                    sanction_isolator                VARCHAR(100),
                    sanction_isolator_timestamp      VARCHAR(100),
                    reisolate_requestor               VARCHAR(100),
                    reisolate_requestor_timestamp     VARCHAR(100),
                    reisolate_issuing                 VARCHAR(100),
                    reisolate_issuing_timestamp       VARCHAR(100),
                    reisolate_isolator                VARCHAR(100),
                    reisolate_isolator_timestamp      VARCHAR(100),
                    deisolate_requestor               VARCHAR(100),
                    deisolate_requestor_timestamp     VARCHAR(100),
                    deisolate_issuing                 VARCHAR(100),
                    deisolate_issuing_timestamp       VARCHAR(100),
                    deisolate_issuing_action          VARCHAR(100),
                    deisolate_isolator                VARCHAR(100),
                    deisolate_isolator_timestamp      VARCHAR(100),
                    long_term                       BOOLEAN NOT NULL DEFAULT FALSE,
                    long_term_reason                VARCHAR(300) NOT NULL,
                    is_psic                          BOOLEAN NOT NULL DEFAULT FALSE,
                    psic_reasons                     TEXT[],
                    psic_moc_number                  VARCHAR(100),
                    psic_system_description          VARCHAR(300) NOT NULL,
                    psic_isolation_method            VARCHAR(300) NOT NULL,
                    psic_control_measures            VARCHAR(300) NOT NULL,
                    linked_ptws                     TEXT[],
                    held_by                         TEXT[]
                )
            """)
            print("Ensured table: ics")
            # is_psic ("Protective System IC") is independent of `type` - any IC type can be
            # flagged PSIC. psic_reasons/psic_moc_number/psic_system_description/
            # psic_isolation_method/psic_control_measures are only meaningful when is_psic is
            # set; the three VARCHAR(300) NOT NULL fields are kept non-null the same way
            # long_term_reason is - the client always writes an empty string rather than
            # leaving them unset, per DialogIC.accept().

            cur.execute("""
                CREATE TABLE IF NOT EXISTS risks (
                    hazard          VARCHAR(300) NOT NULL,
                    effect          VARCHAR(300) NOT NULL,
                    free_analysis   VARCHAR(300) NOT NULL,
                    ctrl            VARCHAR(1000) NOT NULL,
                    ctrl_analysis   VARCHAR(300) NOT NULL,
                    eval            VARCHAR(300) NOT NULL,
                    title           VARCHAR(300) NOT NULL,
                    date            VARCHAR(300) NOT NULL,
                    ptw_id          INTEGER
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_risks_ptw_id ON risks (ptw_id)")
            print("Ensured table: risks (+ idx_risks_ptw_id)")
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    ensure_database_exists()
    init_tables()
    print("Database initialization complete.")
