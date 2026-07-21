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
                    'JSONB[]' if columns[i] == 'items' else
                    'TEXT[]' if isinstance(getattr(certSample, columns[i]), list) else
                    'VARCHAR(300) NOT NULL' if columns[i] in ('reason', 'long_term_reason') else
                    'BOOLEAN NOT NULL DEFAULT FALSE' if isinstance(getattr(certSample, columns[i]), bool) else
                    'VARCHAR(100)'
                    for i in range(len(columns))
                ]
                query = "CREATE TABLE IF NOT EXISTS isolation_certificates (" + ", ".join(columns[i] + ' ' + types[i] for i in range(len(columns))) + ")"
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query)
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

    def deleteCertificate(self, certId: int):
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'isolation_certificates', 'id', certId)
            return None
        except Exception as e:
            return e
