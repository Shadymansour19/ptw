import json
from psycopg2.extras import RealDictCursor

from Isolation import IC
from utils import dictToObj
from commonDb import CommonDB


class ICDb:
    """Assumes the `ics` table already exists — run server/dev-scripts/init_db.py once before
    first starting the server."""

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
