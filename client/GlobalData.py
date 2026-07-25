from RequestWorker import async_request

class GlobalData:
    def __init__(self):
        self.allUsers: dict = {}                # dict[str, SecuredUser]
        self.allRiskAssessments: dict = {}      # dict[str, RiskAssessment]
        self.allPTWs: list = []                 # list[PTWData] - non-archived PTWs
        self.archivedPTWs: list = []            # list[PTWData]
        self.allMIWIs: list = []                # list[str]
        self.ics: dict = {}                     # dict[int, IC]

    @async_request
    def refresh(
        self,
        loggedUser,
        department = None,
        refreshUsers: bool = False,
        refreshRiskAssessments: bool = False,
        refreshPTWs: bool = False,
        refreshArchivedPTWs: bool = False,
        refreshMIWIs: bool = False,
        refreshICs: bool = False,
        refreshAll: bool = False,
    ) -> str:
        from clientRequests import ClientRequests

        if refreshUsers or refreshAll:
            err, allUsers = ClientRequests.getAllUsers(loggedUser)
            if err:
                return err
            self.allUsers = allUsers

        if refreshRiskAssessments or refreshAll:
            err, allRiskAssessments = ClientRequests.getAllRiskAssessments(loggedUser)
            if err:
                return err
            self.allRiskAssessments = allRiskAssessments

        if refreshPTWs or refreshAll:
            err, allPTWs = ClientRequests.getAllPTWs(loggedUser, department=department)
            if err:
                return err
            self.allPTWs = allPTWs

        if refreshArchivedPTWs or refreshAll:
            err, archivedPTWs = ClientRequests.getArchivedPTWs(loggedUser, department=department)
            if err:
                return err
            self.archivedPTWs = archivedPTWs

        if refreshICs or refreshAll:
            err, allICs = ClientRequests.getAllICs(loggedUser, department=department)
            if err:
                return err
            self.ics = allICs

        if refreshMIWIs or refreshAll:
            err, allMIWIs = ClientRequests.getAllMIWIs(loggedUser, department=department)
            if err:
                return err
            self.allMIWIs = allMIWIs

        return None

globalData = GlobalData()
