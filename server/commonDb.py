import os
import psycopg2
from psycopg2 import *
from psycopg2.extras import *
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from contextlib import contextmanager


class CommonDB:
    pool: ThreadedConnectionPool = None

    @classmethod
    def ensure_database_exists(cls):
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
        conn = cls.pool.getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            cls.pool.putconn(conn)

    def addRecordFromDict(conn, table: str, data: dict, primaryKey: str = None):
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
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
            tableCols = [row[0] for row in cursor.fetchall()]
            for k in set(data.keys()) - set(tableCols):
                data.pop(k)
        except Exception as e:
            raise e

        set_clauses = ', '.join([f"{k} = %s" for k in data if k != primaryKey])
        values = [v for k, v in data.items() if k != primaryKey]
        values.append(data[primaryKey])
        query = f"UPDATE {table} SET {set_clauses} WHERE {primaryKey} = %s"
        try:
            cursor.execute(query, tuple(values))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error updating data {data} in table {table}")

    def deleteRecord(conn, table: str, primaryKey: str, primaryKeyVal: str):
        cursor = conn.cursor()
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {primaryKey} = %s", (primaryKeyVal,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error deleting from table {table}: " + str(e))
