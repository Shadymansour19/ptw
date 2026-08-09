"""Data access layer for the `ics` (Isolation Certificate) table."""

import json
from psycopg2.extras import RealDictCursor

from models.Isolation import IC
from utils import dictToObj
from db.commonDb import CommonDB


class ICDb:
    """Data access layer for IC (Isolation Certificate) records.

    Assumes the `ics` table already exists — run server/dev-scripts/init_db.py once before
    first starting the server."""

    def addICFromDict(self, icDict: dict):
        """Insert a new IC row from a plain dict and return the generated id."""
        with CommonDB.get_conn() as conn:
            return CommonDB.addRecordFromDict(conn, 'ics', icDict, 'id')

    def updateICFromDict(self, icDict: dict):
        """Update an existing IC row (matched by 'id') from a plain dict.

        Returns:
            None on success, or the caught exception on failure.
        """
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.updateRecordFromDict(conn, 'ics', icDict, 'id')
            return None
        except Exception as e:
            return e

    def getICById(self, icId: int):
        """Fetch a single IC by id.

        Returns:
            An IC instance, or None if no row matches.

        Raises:
            Exception: wrapping any underlying database error.
        """
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
        """Fetch all ICs, optionally filtered by requestor department (case-insensitive).

        Args:
            department: if given, only ICs whose requestor_department matches
                (ILIKE) are returned; None returns every IC.

        Returns:
            dict mapping IC id to IC instance.

        Raises:
            Exception: wrapping any underlying database error.
        """
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
        """Append a single approval entry to the IC's `approvals` array column."""
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE ics SET approvals = array_append(approvals, %s) WHERE id = %s',
                    (json.dumps(approval.__dict__), icId)
                )
            conn.commit()

    def deleteIC(self, icId: int):
        """Delete the IC row with the given id.

        Returns:
            None on success, or the caught exception on failure.
        """
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'ics', 'id', icId)
            return None
        except Exception as e:
            return e
