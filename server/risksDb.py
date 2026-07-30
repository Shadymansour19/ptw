from psycopg2.extras import RealDictCursor

from PTWData import RiskAssessment, RiskItem
from commonDb import CommonDB


class RisksDb:
    """Assumes the `risks` table already exists — run server/dev-scripts/init_db.py once before
    first starting the server."""

    def addRiskAssessmentFromDict(self, riskAssessment: dict):
        try:
            title = riskAssessment['title']
            date  = riskAssessment['date']
            ptw_id = riskAssessment.get('ptw_id')
            with CommonDB.get_conn() as conn:
                for riskItemDict in riskAssessment['risks']:
                    riskItemDict['title'] = title
                    riskItemDict['date'] = date
                    riskItemDict['ptw_id'] = ptw_id
                    CommonDB.addRecordFromDict(conn, 'risks', riskItemDict)
            return None
        except Exception as e:
            return str(e)

    def updateRiskAssessmentFromDict(self, riskAssessment: dict):
        try:
            title = riskAssessment['title']
            date  = riskAssessment['date']
            ptw_id = riskAssessment.get('ptw_id')
            with CommonDB.get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM risks WHERE title = %s", (title,))
                for riskItemDict in riskAssessment['risks']:
                    row = {**riskItemDict, 'title': title, 'date': date, 'ptw_id': ptw_id}
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
        """Generic risk assessments only (ptw_id IS NULL) — shared library, not tied to any one PTW."""
        risks: dict[str, RiskAssessment] = {}
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM risks WHERE ptw_id IS NULL")
                    rows = cursor.fetchall()
            for row in rows:
                riskItem = RiskItem().setAll(row)
                title = row['title']
                date = row['date']
                if title not in risks:
                    risks[title] = RiskAssessment()
                    risks[title].title = title
                    risks[title].date = date
                    risks[title].ptw_id = None
                risks[title].addRiskItem(riskItem)
        except Exception as e:
            raise Exception(f"Error fetching risks from database: {str(e)}")
        return risks

    def getPTWSpecificRiskAssessment(self, ptw_id: int) -> RiskAssessment:
        """The single risk assessment specific to one PTW (ptw_id column match), or None if it has none."""
        risk: RiskAssessment = None
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM risks WHERE ptw_id = %s", (ptw_id,))
                    rows = cursor.fetchall()
            for row in rows:
                riskItem = RiskItem().setAll(row)
                if risk is None:
                    risk = RiskAssessment()
                    risk.title = row['title']
                    risk.date = row['date']
                    risk.ptw_id = ptw_id
                risk.addRiskItem(riskItem)
        except Exception as e:
            raise Exception(f"Error fetching PTW-specific risk assessment for PTW #{ptw_id}: {str(e)}")
        return risk

    def copyRiskAssessmentForPTW(self, sourcePtwId: int, targetPtwId: int) -> str:
        """Additively copies sourcePtwId's risk rows onto targetPtwId (skipping items targetPtwId
        already has), mirroring how re-request attachment copying adds files without wiping existing ones."""
        try:
            source = self.getPTWSpecificRiskAssessment(sourcePtwId)
            if not source or not source.risks:
                return None
            target = self.getPTWSpecificRiskAssessment(targetPtwId)
            fields = ('hazard', 'effect', 'free_analysis', 'ctrl', 'ctrl_analysis', 'eval')
            def key(item):
                return tuple((getattr(item, f) or '').strip().casefold() for f in fields)
            existingKeys = {key(item) for item in (target.risks if target else [])}
            title = str(targetPtwId)
            date = target.date if target else source.date
            with CommonDB.get_conn() as conn:
                for item in source.risks:
                    itemKey = key(item)
                    if itemKey in existingKeys:
                        continue
                    existingKeys.add(itemKey)
                    row = {f: getattr(item, f) for f in fields}
                    row['title'] = title
                    row['date'] = date
                    row['ptw_id'] = targetPtwId
                    CommonDB.addRecordFromDict(conn, 'risks', row)
            return None
        except Exception as e:
            return str(e)
