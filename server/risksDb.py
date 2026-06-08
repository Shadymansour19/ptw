from psycopg2.extras import RealDictCursor

from PTWData import RiskAssessment, RiskItem
from commonDb import CommonDB


class RisksDb:
    def __init__(self):
        with CommonDB.get_conn() as conn:
            try:
                riskItemSample = RiskItem()
                columns = list(riskItemSample.__dict__.keys())
                columns.extend(['title', 'date'])
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS risks (" +
                        ", ".join(col + ' VARCHAR(300) NOT NULL' for col in columns) + ")"
                    )
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing risks database: " + str(e))

    def addRiskAssessmentFromDict(self, riskAssessment: dict):
        try:
            title = riskAssessment['title']
            date  = riskAssessment['date']
            with CommonDB.get_conn() as conn:
                for riskItemDict in riskAssessment['risks']:
                    riskItemDict['title'] = title
                    riskItemDict['date'] = date
                    CommonDB.addRecordFromDict(conn, 'risks', riskItemDict)
            return None
        except Exception as e:
            return str(e)

    def updateRiskAssessmentFromDict(self, riskAssessment: dict):
        try:
            title = riskAssessment['title']
            date  = riskAssessment['date']
            with CommonDB.get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM risks WHERE title = %s", (title,))
                for riskItemDict in riskAssessment['risks']:
                    row = {**riskItemDict, 'title': title, 'date': date}
                    columns = list(row.keys())
                    placeholders = ', '.join(['%s'] * len(columns))
                    cursor.execute(
                        f"INSERT INTO risks ({', '.join(columns)}) VALUES ({placeholders})",
                        tuple(row[c] for c in columns)
                    )
                conn.commit()
            return None
        except Exception as e:
            return str(e)

    def deleteRiskAssessment(self, title: str) -> str:
        try:
            with CommonDB.get_conn() as conn:
                CommonDB.deleteRecord(conn, 'risks', 'title', title)
            return None
        except Exception as e:
            return str(e)

    def getAllRiskAssessments(self) -> dict:
        risks: dict[str, RiskAssessment] = {}
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
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
            raise Exception(f"Error fetching risks from database: {str(e)}")
        return risks
