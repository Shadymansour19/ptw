import os
import psycopg2
from psycopg2.extras import RealDictCursor
from PTWData import RiskAssessment, RiskItem
from commonDb import CommonDB


class RisksDb:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'ptw_database'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD')
        )

        try:
            riskItemSample = RiskItem()
            columns = list(riskItemSample.__dict__.keys())
            columns.extend(['title', 'date'])
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("CREATE TABLE IF NOT EXISTS risks (" + ", ".join(col + ' VARCHAR(300) NOT NULL' for col in columns) + ")")
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error initializing risks database: " + str(e))

    def addRiskAssessmentFromDict(self, riskAssessment: dict):
        try:
            title = riskAssessment['title']
            date  = riskAssessment['date']
            for riskItemDict in riskAssessment['risks']:
                riskItemDict['title'] = title
                riskItemDict['date'] = date
                CommonDB.addRecordFromDict(self.conn, 'risks', riskItemDict)
            return None
        except Exception as e:
            return str(e)

    def updateRiskAssessmentFromDict(self, riskAssessment: dict):
        return (
            self.deleteRiskAssessment(riskAssessment['title']) or
            self.addRiskAssessmentFromDict(riskAssessment)
        )

    def deleteRiskAssessment(self, title: str) -> str:
        try:
            CommonDB.deleteRecord(self.conn, 'risks', 'title', title)
            return None
        except Exception as e:
            return str(e)

    def getAllRiskAssessments(self) -> dict[str, RiskAssessment]:
        risks: dict[str, RiskAssessment] = {}
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM risks")
                rows = cursor.fetchall()
            for row in rows:
                riskItem = RiskItem().setAll(row)
                title = row['title']
                date = row['date']
                if title not in risks:
                    risks[title] = RiskAssessment()
                    risks[title].title = title
                    risks[title].date = date
                risks[title].addRiskItem(riskItem)
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Error fetching risks from database {str(e)}")
        return risks
