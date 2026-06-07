from psycopg2.extras import RealDictCursor

from PTWData import Isolation
from utils import dictToObj, objToDict
from commonDb import CommonDB


class IsolationDb:
    def __init__(self):
        with CommonDB.get_conn() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS isolations (
                            tag                    VARCHAR(30)  PRIMARY KEY,
                            type                   VARCHAR(30)  NOT NULL,
                            description            VARCHAR(300) NOT NULL,
                            primary_ptw            VARCHAR(30)  NOT NULL,
                            latest_ptw             VARCHAR(30)  NOT NULL,
                            linked_ptws            TEXT[]       NOT NULL DEFAULT '{}',
                            is_physically_isolated BOOLEAN      NOT NULL DEFAULT FALSE,
                            held_by                TEXT[]       NOT NULL DEFAULT '{}'
                        )
                    """)
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing isolations database: " + str(e))

    def updateIsolation(self, iso):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT EXISTS(SELECT 1 FROM isolations WHERE tag = %s)", (iso.tag,))
                    exists = cursor.fetchone()['exists']
                if exists:
                    CommonDB.updateRecordFromDict(conn, 'isolations', objToDict(iso), 'tag')
                else:
                    CommonDB.addRecordFromDict(conn, 'isolations', objToDict(iso))
            return None
        except Exception as e:
            return e

    def getIsolation(self, tag: str):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM isolations WHERE tag = %s", (tag,))
                    row = cursor.fetchone()
            if row:
                return Isolation().setAll(namespace=dictToObj(row))
            return None
        except Exception as e:
            raise Exception("Error fetching isolation from database: " + str(e))

    def getAllIsolations(self, ptwId: str = None):
        isos = {}
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        'SELECT * FROM isolations WHERE (%s IS NULL OR %s = ANY(linked_ptws))',
                        (ptwId, ptwId)
                    )
                    rows = cursor.fetchall()
            for row in rows:
                iso = Isolation().setAll(namespace=dictToObj(row))
                isos[iso.tag] = iso
        except Exception as e:
            raise Exception("Error fetching isolations from database: " + str(e))
        return isos

    def deleteIsolation(self, tag: str):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'isolations', 'tag', tag)
            return None
        except Exception as e:
            return e
