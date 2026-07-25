import json
from psycopg2.extras import RealDictCursor

from Isolation import IsolationCertificate
from utils import dictToObj, objToDict
from commonDb import CommonDB


class IsolationCertificateDb:
    def __init__(self):
        with CommonDB.get_conn() as conn:
            try:
                certSample = IsolationCertificate()
                columns = list(objToDict(certSample).keys())
                types = [
                    'SERIAL PRIMARY KEY' if columns[i] == 'id' else
                    'JSONB[]' if columns[i] in ('items', 'approvals') else
                    'TEXT[]' if isinstance(getattr(certSample, columns[i]), list) else
                    'VARCHAR(300) NOT NULL' if columns[i] in ('reason', 'long_term_reason') else
                    'BOOLEAN NOT NULL DEFAULT FALSE' if isinstance(getattr(certSample, columns[i]), bool) else
                    'VARCHAR(100)'
                    for i in range(len(columns))
                ]
                query = "CREATE TABLE IF NOT EXISTS isolation_certificates (" + ", ".join(columns[i] + ' ' + types[i] for i in range(len(columns))) + ")"
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
                    cursor.execute("ALTER TABLE isolation_certificates DROP COLUMN IF EXISTS primary_ptw")
                    cursor.execute("ALTER TABLE isolation_certificates DROP COLUMN IF EXISTS latest_ptw")
                    cursor.execute("ALTER TABLE isolation_certificates DROP COLUMN IF EXISTS is_physically_isolated")
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing isolation_certificates database: " + str(e))

    def addCertificateFromDict(self, certDict: dict):
        with CommonDB.get_conn() as conn:
            return CommonDB.addRecordFromDict(conn, 'isolation_certificates', certDict, 'id')

    def updateCertificateFromDict(self, certDict: dict):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.updateRecordFromDict(conn, 'isolation_certificates', certDict, 'id')
            return None
        except Exception as e:
            return e

    def getCertificateById(self, certId: int):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM isolation_certificates WHERE id = %s", (certId,))
                    row = cursor.fetchone()
            if row:
                return IsolationCertificate().setAll(namespace=dictToObj(row))
            return None
        except Exception as e:
            raise Exception("Error fetching isolation certificate from database: " + str(e))

    def getAllCertificates(self, department: str = None) -> dict:
        certs = {}
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        'SELECT * FROM isolation_certificates WHERE (%s IS NULL OR department ILIKE %s)',
                        (department, department)
                    )
                    rows = cursor.fetchall()
            for row in rows:
                cert = IsolationCertificate().setAll(namespace=dictToObj(row))
                certs[cert.id] = cert
        except Exception as e:
            raise Exception("Error fetching isolation certificates from database: " + str(e))
        return certs

    def updateCertificateApprovals(self, certId: int, approval: 'IsolationCertificate.Approval'):
        with CommonDB.get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    'UPDATE isolation_certificates SET approvals = array_append(approvals, %s) WHERE id = %s',
                    (json.dumps(approval.__dict__), certId)
                )
            conn.commit()

    def deleteCertificate(self, certId: int):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'isolation_certificates', 'id', certId)
            return None
        except Exception as e:
            return e
