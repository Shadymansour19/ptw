import os
import psycopg2
from psycopg2.extras import RealDictCursor
from PTWData import dictToObj, objToDict, ActiveIsolation
from commonDb import CommonDB

class IsolationDb:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'ptw_database'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD')
        )
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
    
    def updateIsolation(self, iso):
        try:
            self.cursor.execute("SELECT EXISTS(SELECT 1 FROM active_isolations WHERE tag = %s)", (iso.tag,))
            exists = self.cursor.fetchone()['exists']
            if exists:
                CommonDB.updateRecordFromDict(self.conn, 'active_isolations', objToDict(iso), 'tag')
            else:
                CommonDB.addRecordFromDict(self.conn, 'active_isolations', objToDict(iso))
            return None
        except Exception as e:
            print(str(e))
            return e

    def getIsolation(self, tag: str):
        try:
            self.cursor.execute("SELECT * FROM active_isolations WHERE tag = %s", (tag,))
            row = self.cursor.fetchone()
            if row:
                iso = ActiveIsolation().setAll(namespace=dictToObj(row))
                return iso
            else:
                return None
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching PTW from database: " + str(e))
    
    def getAllIsolations(self, ptwId: str = None):
        isos = {}
        try:
            self.cursor.execute('''SELECT * FROM active_isolations WHERE (%s IS NULL OR %s = ANY(linked_ptws))''', (ptwId, ptwId))
            rows = self.cursor.fetchall()
            for row in rows:
                iso = ActiveIsolation().setAll(namespace=dictToObj(row))
                isos[iso.tag] = iso
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching PTWs from database: " + str(e))
        return isos
    
    def deleteIsolation(self, tag: str):
        try:
            CommonDB.deleteRecord(self.conn, 'active_isolations', 'tag', tag)
            return None
        except Exception as e:
            return e
    