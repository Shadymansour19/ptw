import json
from psycopg2.extras import RealDictCursor

from PTWData import PTWData
from utils import dictToObj, objToDict
from commonDb import CommonDB


class PtwsDb:
    def __init__(self):
        with CommonDB.get_conn() as conn:
            try:
                ptwSample = PTWData()
                columns = list(objToDict(ptwSample).keys())
                types = [
                    'SERIAL PRIMARY KEY' if columns[i] == 'id' else
                    'JSONB[]' if columns[i] in ['approvals', 'isolations', 'run_cycles'] else
                    'TEXT[]' if isinstance(getattr(ptwSample, columns[i]), list) else
                    'VARCHAR(300) NOT NULL' if columns[i] == 'description' else
                    'BOOLEAN NOT NULL DEFAULT FALSE' if isinstance(getattr(ptwSample, columns[i]), bool) else
                    'VARCHAR(100)'
                    for i in range(len(columns))
                ]
                query = "CREATE TABLE IF NOT EXISTS ptws (" + ", ".join(columns[i] + ' ' + types[i] for i in range(len(columns))) + ")"
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing ptws database: " + str(e))

    def addPTWFromDict(self, ptwDict: dict):
        with CommonDB.get_conn() as conn:
            return CommonDB.addRecordFromDict(conn, 'ptws', ptwDict, 'id')

    def updatePTWFromDict(self, ptwDict: dict):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.updateRecordFromDict(conn, 'ptws', ptwDict, 'id')
            return None
        except Exception as e:
            return e

    def getPTWById(self, ptwId: int):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM ptws WHERE id = %s", (ptwId,))
                    row = cursor.fetchone()
            if row:
                return PTWData().setAll(namespace=dictToObj(row))
            return None
        except Exception as e:
            raise Exception("Error fetching PTW from database: " + str(e))

    def getAllPTWs(self, department: str = None, requestor: str = None) -> dict:
        ptws = {}
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
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
            raise Exception("Error fetching PTWs from database: " + str(e))
        return ptws

    def getArchivedPTWs(self, department: str = None):
        ptws = []
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
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
            raise Exception("Error fetching archived PTWs from database: " + str(e))
        return ptws

    def deletePTW(self, ptwId: str):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'ptws', 'id', ptwId)
            return None
        except Exception as e:
            return e

    def updatePTWApprovals(self, ptwId: str, approval: PTWData.Approval):
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE ptws SET approvals = array_append(approvals, %s) WHERE id = %s',
                    (json.dumps(approval.__dict__), ptwId)
                )
            conn.commit()

    def archivePTWs(self, ptwIds: list[str]):
        with CommonDB.get_conn() as conn:
            placeholders = ', '.join(['%s'] * len(ptwIds))
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    f'UPDATE ptws SET running_status = %s WHERE id IN ({placeholders})',
                    (PTWData.RunningStatus.ARCHIVED, *ptwIds)
                )
            conn.commit()

    def _appendRunCycle(self, ptwId: str, cycle: dict, runningStatus: str):
        """Appends a brand-new RunCycle (a fresh run request) and advances running_status."""
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE ptws SET run_cycles = array_append(run_cycles, %s::jsonb), prev_running_status = running_status, running_status = %s WHERE id = %s',
                    (json.dumps(cycle), runningStatus, ptwId)
                )
            conn.commit()

    def _patchLastRunCycle(self, ptwId: str, patch: dict, runningStatus: str = None, revertToPrev: bool = False):
        """Merges new fields into the most recent RunCycle (still in progress), leaving earlier fields intact."""
        setClauses = ['run_cycles[cardinality(run_cycles)] = run_cycles[cardinality(run_cycles)] || %s::jsonb']
        params = [json.dumps(patch)]
        if revertToPrev:
            setClauses.append('prev_running_status = running_status')
            setClauses.append('running_status = prev_running_status')
        else:
            setClauses.append('prev_running_status = running_status')
            setClauses.append('running_status = %s')
            params.append(runningStatus)
        params.append(ptwId)
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(f'UPDATE ptws SET {", ".join(setClauses)} WHERE id = %s', tuple(params))
            conn.commit()

    def requestToRunPTW(self, ptwId: str, pa: str, ts: str):
        cycle = objToDict(PTWData.RunCycle(run_pa=pa, run_pa_timestamp=ts))
        self._appendRunCycle(ptwId, cycle, PTWData.RunningStatus.WAITING_RUN_CONFIRM)

    def runAcceptPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'run_ia': ia, 'run_ia_action': PTWData.RunCycle.Actions.APPROVED, 'run_ia_comment': comment, 'run_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, runningStatus=PTWData.RunningStatus.RUNNING)

    def runRejectPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'run_ia': ia, 'run_ia_action': PTWData.RunCycle.Actions.REJECTED, 'run_ia_comment': comment, 'run_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, revertToPrev=True)

    def requestToClsPTW(self, ptwId: str, pa: str, ts: str, comment: str = None):
        patch = {'stop_pa': pa, 'stop_pa_request': PTWData.RunCycle.StopTypes.CLOSE, 'stop_pa_comment': comment, 'stop_pa_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, runningStatus=PTWData.RunningStatus.WAITING_CLS_CONFIRM)

    def clsAcceptPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTWData.RunCycle.Actions.APPROVED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, runningStatus=PTWData.RunningStatus.CLOSED)

    def clsRejectPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTWData.RunCycle.Actions.REJECTED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, revertToPrev=True)

    def requestToHldPTW(self, ptwId: str, pa: str, ts: str, comment: str = None, keepTags: list[str] = []):
        patch = {
            'stop_pa': pa, 'stop_pa_request': PTWData.RunCycle.StopTypes.HOLD, 'stop_pa_comment': comment, 'stop_pa_timestamp': ts,
            'keep_isolations': keepTags,
        }
        self._patchLastRunCycle(ptwId, patch, runningStatus=PTWData.RunningStatus.WAITING_HLD_CONFIRM)

    def hldAcceptPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTWData.RunCycle.Actions.APPROVED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, runningStatus=PTWData.RunningStatus.HELD)

    def hldRejectPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTWData.RunCycle.Actions.REJECTED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch, revertToPrev=True)
