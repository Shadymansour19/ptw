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
        """Merges new fields into the most recent RunCycle — but only while that cycle is
        still open (PTW.RunCycle.isOpen()), which every legitimate caller here requires
        anyway (a run-response/stop-request/stop-response is only ever valid against a cycle
        that hasn't already been rejected or fully stopped). Guards against two cases that
        would otherwise be silently wrong:

        - run_cycles is empty (PTW never run at all) — letting the UPDATE through on an empty
          array silently corrupts it: Postgres reads run_cycles[cardinality(run_cycles)] (i.e.
          run_cycles[0]) as NULL out-of-bounds, and NULL || jsonb is itself NULL (verified
          empirically), so the assignment leaves run_cycles as a 1-element array holding a
          single SQL NULL — which then crashes every future read of this PTW
          (PTW.RunCycle().setAll() iterating a None entry).
        - the last cycle exists but is already closed (rejected run, or a stop already
          approved) — the UPDATE would succeed without crashing, but the patched fields land
          on a cycle __updateRunningStatus() already skips during replay, so the request is
          silently lost: no error, no visible effect, nothing for an IA to ever act on.

        Either way, raise cleanly so the caller (a run/hold/close route) surfaces a real error
        instead of writing a bad or inert row."""
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT run_cycles[cardinality(run_cycles)] AS last_cycle FROM ptws WHERE id = %s', (ptwId,))
                row = cursor.fetchone()
                lastCycle = row['last_cycle'] if row else None
                if not lastCycle or not PTW.RunCycle().setAll(lastCycle).isOpen():
                    raise ValueError(f"PTW #{ptwId} has no open run cycle to update")
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

    def _hasOpenRunCycle(self, ptwId: str) -> bool:
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT run_cycles[cardinality(run_cycles)] AS last_cycle FROM ptws WHERE id = %s', (ptwId,))
                row = cursor.fetchone()
        lastCycle = row['last_cycle'] if row else None
        return lastCycle is not None and PTW.RunCycle().setAll(lastCycle).isOpen()

    def requestToClsPTW(self, ptwId: str, pa: str, ts: str, comment: str = None):
        if self._hasOpenRunCycle(ptwId):
            patch = {'stop_pa': pa, 'stop_pa_request': PTW.RunCycle.StopTypes.CLOSE, 'stop_pa_comment': comment, 'stop_pa_timestamp': ts}
            self._patchLastRunCycle(ptwId, patch)
        else:
            # No open cycle to attach a stop request to — the PTW was never run at all, or its
            # only run attempt was rejected. Append a fresh cycle carrying just the close
            # request (no run_pa/run_ia — it never ran), mirroring how resuming from HELD
            # always appends a new cycle rather than patching a dead one. __updateRunningStatus()
            # resolves stop_pa_request=CLOSE with no run_ia_action into WAITING_CLS_CONFIRM the
            # same as any other cycle, so this still goes through ordinary IA accept/reject —
            # never running it doesn't skip that sign-off, it just means there's no run
            # request/response above the close request/response on this particular cycle.
            cycle = objToDict(PTW.RunCycle(stop_pa=pa, stop_pa_request=PTW.RunCycle.StopTypes.CLOSE, stop_pa_comment=comment, stop_pa_timestamp=ts))
            self._appendRunCycle(ptwId, cycle)

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
