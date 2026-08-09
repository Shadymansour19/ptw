"""Generic PostgreSQL access layer shared by every `*Db.py` class.

Provides `CommonDB`: database creation/connection-pool setup, a pooled
connection context manager, and generic dict-driven insert/update/delete
helpers that introspect a table's columns and handle JSONB(-array) values.
Table-specific query logic lives in the individual `*Db.py` modules (e.g.
`ptwDb.py`), which build on top of these primitives.
"""

import os
import psycopg2
from psycopg2 import *
from psycopg2.extras import *
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from contextlib import contextmanager


class CommonDB:
    """Shared database-access layer: owns the process-wide connection pool and
    provides generic, table-agnostic dict-to-SQL helpers (insert/update/delete)
    used by every `*Db.py` class instead of each writing raw SQL by hand."""

    pool: ThreadedConnectionPool = None

    @classmethod
    def ensure_database_exists(cls):
        """Create the target database (named by DB_NAME, default
        'ptw_database') if it doesn't already exist. Connects to the default
        'postgres' database in autocommit mode (CREATE DATABASE can't run
        inside a transaction) using DB_HOST/DB_USER/DB_PASSWORD from the
        environment. Intended to run once at server startup, before the
        connection pool is initialized."""
        db_name = os.environ.get('DB_NAME', 'ptw_database')
        host     = os.environ.get('DB_HOST', 'localhost')
        user     = os.environ.get('DB_USER', 'postgres')
        password = os.environ.get('DB_PASSWORD')

        conn = psycopg2.connect(host=host, database='postgres', user=user, password=password)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if not cursor.fetchone():
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"[DB] Created database: {db_name}")
        else:
            print(f"[DB] Database already exists: {db_name}")
        cursor.close()
        conn.close()

    @classmethod
    def init_pool(cls, minconn=2, maxconn=10):
        """Create the class-wide `ThreadedConnectionPool` (default 2-10
        connections) against DB_HOST/DB_NAME/DB_USER/DB_PASSWORD from the
        environment. Must be called once at startup before `get_conn()` is
        used."""
        cls.pool = ThreadedConnectionPool(
            minconn, maxconn,
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'ptw_database'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD')
        )

    @classmethod
    @contextmanager
    def get_conn(cls):
        """Context manager yielding a pooled connection: checks one out of
        `cls.pool`, rolls it back and re-raises on any exception, and always
        returns it to the pool afterward (never closes it outright)."""
        conn = cls.pool.getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            cls.pool.putconn(conn)

    def addRecordFromDict(conn, table: str, data: dict, primaryKey: str = None):
        """Insert a row into `table` built from `data`, silently dropping any
        keys that aren't real columns on that table. A value that is a list of
        dicts (e.g. a JSONB[] column such as `ptws.approvals`) is wrapped with
        `Json(...)` per element and cast `::jsonb[]`; every other value is
        passed through as-is. If `primaryKey` is given, it's excluded from the
        INSERT and appended as `RETURNING <primaryKey>`, and its generated
        value (e.g. a new `id`) is returned; otherwise nothing is returned.
        Commits on success; rolls back and raises a generic Exception
        (without the original cause) on failure."""
        columns = list(data.keys())
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
            tableCols = [row[0] for row in cursor.fetchall()]
            columns = list(set(columns) & set(tableCols))
        except Exception as e:
            raise e

        types = []
        values = []
        for k in columns:
            if isinstance(data[k], list) and all(isinstance(i, dict) for i in data[k]):
                types.append('%s::jsonb[]')
                values.append([Json(d) for d in data[k]])
            else:
                types.append('%s')
                values.append(data[k])

        if primaryKey is None:
            query = f"INSERT INTO {table} (" + ', '.join(columns) + ") VALUES (" + ', '.join(types) + ')'
        else:
            idx = columns.index(primaryKey)
            columns.pop(idx)
            values.pop(idx)
            types.pop(idx)
            query = f"INSERT INTO {table} (" + ', '.join(columns) + ") VALUES (" + ', '.join(types) + f') RETURNING {primaryKey}'

        try:
            cursor.execute(query, tuple(values))
            conn.commit()
            if primaryKey is not None:
                return cursor.fetchone()[0]
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error adding data {data} to table {table}")

    def updateRecordFromDict(conn, table: str, data: dict, primaryKey: str):
        """Update the row of `table` identified by `data[primaryKey]`, setting
        every other key in `data` as a column (keys that aren't real columns
        on `table` are popped from `data` in place and skipped). As in
        `addRecordFromDict`, a list-of-dicts value is cast `::jsonb[]` via
        `Json(...)` per element; other values are passed through as-is.
        Commits on success; rolls back and raises a generic Exception on
        failure."""
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
            tableCols = [row[0] for row in cursor.fetchall()]
            for k in set(data.keys()) - set(tableCols):
                data.pop(k)
        except Exception as e:
            raise e

        columns = [k for k in data if k != primaryKey]
        set_clauses = ', '.join(
            f"{k} = %s::jsonb[]" if isinstance(data[k], list) and all(isinstance(i, dict) for i in data[k]) else f"{k} = %s"
            for k in columns
        )
        values = [[Json(d) for d in data[k]] if isinstance(data[k], list) and all(isinstance(i, dict) for i in data[k]) else data[k] for k in columns]
        values.append(data[primaryKey])
        query = f"UPDATE {table} SET {set_clauses} WHERE {primaryKey} = %s"
        try:
            cursor.execute(query, tuple(values))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error updating data {data} in table {table}")

    def deleteRecord(conn, table: str, primaryKey: str, primaryKeyVal: str):
        """Delete the row of `table` where `primaryKey` equals `primaryKeyVal`.
        Commits on success; rolls back and raises on failure, with the
        original error message included."""
        cursor = conn.cursor()
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {primaryKey} = %s", (primaryKeyVal,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error deleting from table {table}: " + str(e))
