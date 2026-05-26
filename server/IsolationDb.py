import os
import psycopg2
from psycopg2.extras import RealDictCursor
from PTWData import Isolation
from utils import dictToObj, objToDict
from commonDb import CommonDB

class IsolationDb:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'ptw_database'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD')
        )

    def updateIsolation(self, iso):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM isolations WHERE tag = %s)", (iso.tag,))
                exists = cursor.fetchone()['exists']
            if exists:
                CommonDB.updateRecordFromDict(self.conn, 'isolations', objToDict(iso), 'tag')
            else:
                CommonDB.addRecordFromDict(self.conn, 'isolations', objToDict(iso))
            return None
        except Exception as e:
            print(str(e))
            return e

    def getIsolation(self, tag: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM isolations WHERE tag = %s", (tag,))
                row = cursor.fetchone()
            if row:
                return Isolation().setAll(namespace=dictToObj(row))
            return None
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching PTW from database: " + str(e))

    def getAllIsolations(self, ptwId: str = None):
        isos = {}
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''SELECT * FROM isolations WHERE (%s IS NULL OR %s = ANY(linked_ptws))''', (ptwId, ptwId))
                rows = cursor.fetchall()
            for row in rows:
                iso = Isolation().setAll(namespace=dictToObj(row))
                isos[iso.tag] = iso
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching PTWs from database: " + str(e))
        return isos

    def deleteIsolation(self, tag: str):
        try:
            CommonDB.deleteRecord(self.conn, 'isolations', 'tag', tag)
            return None
        except Exception as e:
            return e
