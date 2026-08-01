import json
from psycopg2.extras import RealDictCursor

from models.PTW import PTW
from utils import dictToObj, objToDict
from db.commonDb import CommonDB


class PtwsDb:
    """Assumes the `ptws` table already exists — run server/dev-scripts/init_db.py once before
    first starting the server."""

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
                return PTW().setAll(namespace=dictToObj(row))
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
                        NOT is_archived AND
                        (%s IS NULL OR department ILIKE %s) AND
                        (%s IS NULL OR requestor  ILIKE %s)''',
                        (department, department, requestor, requestor)
                    )
                    rows = cursor.fetchall()
            for row in rows:
                ptw = PTW().setAll(namespace=dictToObj(row))
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
                        is_archived AND
                        (%s IS NULL OR department ILIKE %s)''',
                        (department, department)
                    )
                    rows = cursor.fetchall()
            for row in rows:
                ptws.append(PTW().setAll(namespace=dictToObj(row)))
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

    def updatePTWApprovals(self, ptwId: str, approval: PTW.Approval):
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
                    f'UPDATE ptws SET is_archived = TRUE WHERE id IN ({placeholders})',
                    tuple(ptwIds)
                )
            conn.commit()

    def _appendRunCycle(self, ptwId: str, cycle: dict):
        """Appends a brand-new RunCycle (a fresh run request). running_status is derived
        from run_cycles on read (PTW.__updateRunningStatus), so there's nothing else
        to update here."""
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE ptws SET run_cycles = array_append(run_cycles, %s::jsonb) WHERE id = %s',
                    (json.dumps(cycle), ptwId)
                )
            conn.commit()

    def _patchLastRunCycle(self, ptwId: str, patch: dict):
        """Merges new fields into the most recent RunCycle (still in progress), leaving earlier fields intact."""
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE ptws SET run_cycles[cardinality(run_cycles)] = run_cycles[cardinality(run_cycles)] || %s::jsonb WHERE id = %s',
                    (json.dumps(patch), ptwId)
                )
            conn.commit()

    def requestToRunPTW(self, ptwId: str, pa: str, ts: str):
        cycle = objToDict(PTW.RunCycle(run_pa=pa, run_pa_timestamp=ts))
        self._appendRunCycle(ptwId, cycle)

    def runAcceptPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'run_ia': ia, 'run_ia_action': PTW.RunCycle.Actions.APPROVED, 'run_ia_comment': comment, 'run_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)

    def runRejectPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'run_ia': ia, 'run_ia_action': PTW.RunCycle.Actions.REJECTED, 'run_ia_comment': comment, 'run_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)

    def requestToClsPTW(self, ptwId: str, pa: str, ts: str, comment: str = None):
        patch = {'stop_pa': pa, 'stop_pa_request': PTW.RunCycle.StopTypes.CLOSE, 'stop_pa_comment': comment, 'stop_pa_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)

    def clsAcceptPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTW.RunCycle.Actions.APPROVED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)

    def clsRejectPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTW.RunCycle.Actions.REJECTED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)

    def requestToHldPTW(self, ptwId: str, pa: str, ts: str, comment: str = None, heldICs: list[str] = []):
        patch = {
            'stop_pa': pa, 'stop_pa_request': PTW.RunCycle.StopTypes.HOLD, 'stop_pa_comment': comment, 'stop_pa_timestamp': ts,
            'held_ics': heldICs,
        }
        self._patchLastRunCycle(ptwId, patch)

    def hldAcceptPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTW.RunCycle.Actions.APPROVED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)

    def hldRejectPTW(self, ptwId: str, ia: str, ts: str, comment: str = None):
        patch = {'stop_ia': ia, 'stop_ia_action': PTW.RunCycle.Actions.REJECTED, 'stop_ia_comment': comment, 'stop_ia_timestamp': ts}
        self._patchLastRunCycle(ptwId, patch)
