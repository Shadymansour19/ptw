import os
import psycopg2
from psycopg2.extras import RealDictCursor
from PTWData import PTWData
from utils import dictToObj, objToDict
from commonDb import CommonDB
import json

class PtwsDb:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'ptw_database'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD')
        )

        try:
            ptwSample = PTWData()
            columns = list(objToDict(ptwSample).keys())
            columns.remove('approval_status')
            types = [
                'SERIAL PRIMARY KEY' if columns[i] == 'id' else
                'JSONB[]' if columns[i] == 'approvals' else
                'TEXT[]' if isinstance(getattr(ptwSample, columns[i]), list) else
                'VARCHAR(300) NOT NULL' if columns[i] == 'description' else
                'VARCHAR(100)'
                for i in range(len(columns))
            ]
            query = "CREATE TABLE IF NOT EXISTS ptws (" + ", ".join(columns[i] + ' ' + types[i] for i in range(len(columns))) + ")"
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query)
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error initializing ptws database: " + str(e))

    def addPTWFromDict(self, ptwDict: dict):
        try:
            return CommonDB.addRecordFromDict(self.conn, 'ptws', ptwDict, 'id')
        except Exception as e:
            raise e

    def updatePTWFromDict(self, ptwDict: dict):
        try:
            CommonDB.updateRecordFromDict(self.conn, 'ptws', ptwDict, 'id')
            return None
        except Exception as e:
            return e

    def getPTWById(self, ptwId: int):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM ptws WHERE id = %s", (ptwId,))
                row = cursor.fetchone()
            if row:
                return PTWData().setAll(namespace=dictToObj(row))
            return None
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching PTW from database: " + str(e))

    def getAllPTWs(self, department: str = None, requestor: str = None) -> dict:
        ptws = {}
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    SELECT * FROM ptws WHERE
                    running_status != %s AND
                    (%s IS NULL OR department ILIKE %s) AND
                    (%s IS NULL OR requestor  ILIKE %s)''',
                    (PTWData.RunningStatus.ARCHIVED, department, department, requestor, requestor)
                )
                rows = cursor.fetchall()
            for row in rows:
                ptw = PTWData().setAll(namespace=dictToObj(row))
                ptws[ptw.id] = ptw
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching PTWs from database: " + str(e))
        return ptws

    def getArchivedPTWs(self, department: str = None):
        ptws = []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    SELECT * FROM ptws WHERE
                    running_status = %s AND
                    (%s IS NULL OR department ILIKE %s)''',
                    (PTWData.RunningStatus.ARCHIVED, department, department)
                )
                rows = cursor.fetchall()
            for row in rows:
                ptws.append(PTWData().setAll(namespace=dictToObj(row)))
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching archived PTWs from database: " + str(e))
        return ptws

    def deletePTW(self, ptwId: str):
        try:
            CommonDB.deleteRecord(self.conn, 'ptws', 'id', ptwId)
            return None
        except Exception as e:
            return e

    def updatePTWApprovals(self, ptwId: str, approval: PTWData.Approval):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET approvals = array_append(approvals, %s) WHERE id = %s', (json.dumps(approval.__dict__), ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def archivePTWs(self, ptwIds: list[str]):
        try:
            placeholders = ', '.join(['%s'] * len(ptwIds))
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f'UPDATE ptws SET running_status = %s WHERE id IN ({placeholders})', (PTWData.RunningStatus.ARCHIVED, *ptwIds))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def requestToRunPTW(self, ptwId: str, pa: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET performing = %s, prev_running_status = running_status, running_status = %s, performing_timestamp = %s WHERE id = %s', (pa, PTWData.RunningStatus.WAITING_RUN_CONFIRM, ts, ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def runAcceptPTW(self, ptwId: str, ia: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET issuing = %s, prev_running_status = running_status, running_status = %s, issuing_timestamp = %s WHERE id = %s', (ia, PTWData.RunningStatus.RUNNING, ts, ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def runRejectPTW(self, ptwId: str, ia: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET issuing = %s, performing = %s, prev_running_status = running_status, running_status = prev_running_status, issuing_timestamp = %s, performing_timestamp = %s WHERE id = %s', ('', '', '', '', ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def requestToClsPTW(self, ptwId: str, pa: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET close_performing = %s, prev_running_status = running_status, running_status = %s, close_performing_timestamp = %s WHERE id = %s', (pa, PTWData.RunningStatus.WAITING_CLS_CONFIRM, ts, ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def clsAcceptPTW(self, ptwId: str, ia: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''UPDATE ptws SET
                        close_issuing = %s, prev_running_status = running_status, running_status = %s, close_issuing_timestamp = %s,
                        performing = %s, issuing = %s, performing_timestamp = %s, issuing_timestamp = %s
                        WHERE id = %s
                    ''',
                    (ia, PTWData.RunningStatus.CLOSED, ts, '', '', '', '', ptwId)
                )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def clsRejectPTW(self, ptwId: str, ia: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET close_issuing = %s, close_performing = %s, prev_running_status = running_status, running_status = prev_running_status, close_issuing_timestamp = %s, close_performing_timestamp = %s WHERE id = %s', ('', '', '', '', ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def requestToHldPTW(self, ptwId: str, pa: str, ts: str, keepTags: list[str] = []):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''UPDATE ptws SET
                    prev_running_status = running_status, running_status = %s,
                    hold_performing = %s, hold_performing_timestamp = %s, keep_isolations = %s
                    WHERE id = %s
                ''', (PTWData.RunningStatus.WAITING_HLD_CONFIRM, pa, ts, keepTags, ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def hldAcceptPTW(self, ptwId: str, ia: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''UPDATE ptws SET
                        hold_issuing = %s, prev_running_status = running_status, running_status = %s, hold_issuing_timestamp = %s,
                        performing = %s, issuing = %s, performing_timestamp = %s, issuing_timestamp = %s
                        WHERE id = %s
                    ''',
                    (ia, PTWData.RunningStatus.HELD, ts, '', '', '', '', ptwId)
                )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))

    def hldRejectPTW(self, ptwId: str, ia: str, ts: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('UPDATE ptws SET prev_running_status = running_status, running_status = prev_running_status, keep_isolations = %s WHERE id = %s', ([], ptwId))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error updating PTW in database: " + str(e))
