"""One-time fix-up for already-deployed databases: backfills every nullable list/array
column in `ptws` and `ics` from NULL to an empty array, and sets each column's default
to '{}' going forward (matches the DEFAULT now declared in init_db.py's CREATE TABLE
for fresh installs).

A NULL value in one of these columns used to crash PTW.setAll()/IC.setAll()'s list
comprehensions over the object-typed ones (approvals/isolations/run_cycles/gas_tests
on PTW; approvals/items/pid_documents on IC). Since GlobalData.refresh() loads PTWs
before ICs in the same try/except, a single bad PTW row silently emptied the
in-memory PTW *and* IC caches for every user on every server start/periodic refresh —
this is what caused "can't get PTWs from server" even though the DB had plenty.

The code no longer crashes on NULL (server/models/PTW.py and server/models/Isolation.py
now normalize None to [] for every list-typed column), but existing NULL rows are
backfilled here anyway so the stored data reflects "empty" explicitly, and new rows
get '{}' rather than NULL even if a column is omitted from an INSERT.

Safe to run more than once.

Run once against the live database: python server/dev-scripts/backfill_null_list_columns.py
"""

import os
from dotenv import load_dotenv
import psycopg2

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env'))

DB_NAME = os.environ.get('DB_NAME', 'ptw_database')
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD')

# (table, column) for every nullable list/array column across the schema.
LIST_COLUMNS = [
    ('ptws', 'run_cycles'),
    ('ptws', 'tools'),
    ('ptws', 'isolations'),
    ('ptws', 'hazards'),
    ('ptws', 'controls'),
    ('ptws', 'risks'),
    ('ptws', 'linked_ics'),
    ('ptws', 'approvals'),
    ('ptws', 'gas_tests'),
    ('ics', 'approvals'),
    ('ics', 'items'),
    ('ics', 'pid_documents'),
    ('ics', 'psic_reasons'),
    ('ics', 'linked_ptws'),
    ('ics', 'held_by'),
]


def main():
    conn = psycopg2.connect(host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD)
    try:
        with conn.cursor() as cur:
            for table, column in LIST_COLUMNS:
                cur.execute(f"SELECT count(*) FROM {table} WHERE {column} IS NULL")
                null_count = cur.fetchone()[0]

                cur.execute(f"UPDATE {table} SET {column} = '{{}}' WHERE {column} IS NULL")
                cur.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT '{{}}'")
                print(f"{table}.{column}: {null_count} NULL row(s) backfilled, default set to '{{}}'")
        conn.commit()
    finally:
        conn.close()


if __name__ == '__main__':
    main()
