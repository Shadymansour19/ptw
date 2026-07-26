import json
from psycopg2.extras import RealDictCursor

from Isolation import IC
from utils import dictToObj, objToDict
from commonDb import CommonDB


class ICDb:
    def __init__(self):
        with CommonDB.get_conn() as conn:
            try:
                icSample = IC()
                columns = list(objToDict(icSample).keys())
                types = [
                    'SERIAL PRIMARY KEY' if columns[i] == 'id' else
                    'JSONB[]' if columns[i] in ('items', 'approvals') else
                    'TEXT[]' if isinstance(getattr(icSample, columns[i]), list) else
                    'VARCHAR(300) NOT NULL' if columns[i] in ('reason', 'long_term_reason') else
                    'BOOLEAN NOT NULL DEFAULT FALSE' if isinstance(getattr(icSample, columns[i]), bool) else
                    'VARCHAR(100)'
                    for i in range(len(columns))
                ]
                query = "CREATE TABLE IF NOT EXISTS ics (" + ", ".join(columns[i] + ' ' + types[i] for i in range(len(columns))) + ")"
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("ALTER TABLE IF EXISTS isolation_certificates RENAME TO ics")
                    cursor.execute(query)
                    cursor.execute("ALTER TABLE ics DROP COLUMN IF EXISTS primary_ptw")
                    cursor.execute("ALTER TABLE ics DROP COLUMN IF EXISTS latest_ptw")
                    cursor.execute("ALTER TABLE ics DROP COLUMN IF EXISTS is_physically_isolated")
                    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'ics'")
                    existingCols = {row['column_name'] for row in cursor.fetchall()}
                    if 'department' in existingCols and 'requestor_department' not in existingCols:
                        cursor.execute("ALTER TABLE ics RENAME COLUMN department TO requestor_department")
                    cursor.execute("ALTER TABLE ics ADD COLUMN IF NOT EXISTS execution_department VARCHAR(100)")
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing ics database: " + str(e))

    def addICFromDict(self, icDict: dict):
        with CommonDB.get_conn() as conn:
            return CommonDB.addRecordFromDict(conn, 'ics', icDict, 'id')

    def updateICFromDict(self, icDict: dict):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.updateRecordFromDict(conn, 'ics', icDict, 'id')
            return None
        except Exception as e:
            return e

    def getICById(self, icId: int):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM ics WHERE id = %s", (icId,))
                    row = cursor.fetchone()
            if row:
                return IC().setAll(namespace=dictToObj(row))
            return None
        except Exception as e:
            raise Exception("Error fetching IC from database: " + str(e))

    def getAllICs(self, department: str = None) -> dict:
        ics = {}
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        'SELECT * FROM ics WHERE (%s IS NULL OR requestor_department ILIKE %s)',
                        (department, department)
                    )
                    rows = cursor.fetchall()
            for row in rows:
                ic = IC().setAll(namespace=dictToObj(row))
                ics[ic.id] = ic
        except Exception as e:
            raise Exception("Error fetching ICs from database: " + str(e))
        return ics

    def updateICApprovals(self, icId: int, approval: 'IC.Approval'):
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE ics SET approvals = array_append(approvals, %s) WHERE id = %s',
                    (json.dumps(approval.__dict__), icId)
                )
            conn.commit()

    def deleteIC(self, icId: int):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'ics', 'id', icId)
            return None
        except Exception as e:
            return e
