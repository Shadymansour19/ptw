from psycopg2 import *
from psycopg2.extras import *
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv
import os

class CommonDB:
    def ensure_database_exists():
        db_name = os.environ.get('DB_NAME', 'ptw_database')
        host     = os.environ.get('DB_HOST', 'localhost')
        user     = os.environ.get('DB_USER', 'postgres')
        password = os.environ.get('DB_PASSWORD')

        # Connect to the default 'postgres' DB (always exists)
        conn = psycopg2.connect(
            host=host,
            database='postgres',  # <-- not your app DB
            user=user,
            password=password
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)  # Required for CREATE DATABASE

        cursor = conn.cursor()

        # Check if the DB exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()

        if not exists:
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"[DB] Created database: {db_name}")
        else:
            print(f"[DB] Database already exists: {db_name}")

        cursor.close()
        conn.close()

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
                primaryKeyVal = cursor.fetchone()[0]
                return primaryKeyVal
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
            raise Exception(f"Error adding data {data} to table {table}")
        
    
    def deleteRecord(conn, table: str, primaryKey: str, primaryKeyVal: str):
        cursor = conn.cursor()
        try:
            cursor.execute(f"DELETE FROM {table} WHERE {primaryKey} = '{primaryKeyVal}'")
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise Exception(f"Error deleting from table {table}: " + str(e))
