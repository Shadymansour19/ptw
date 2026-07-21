from RequestWorker import async_request

class GlobalData:
    def __init__(self):
        self.allUsers: dict = {}                # dict[str, SecuredUser]
        self.allRiskAssessments: dict = {}      # dict[str, RiskAssessment]
        self.allPTWs: list = []                 # list[PTWData] - non-archived PTWs
        self.archivedPTWs: list = []            # list[PTWData]
        self.allMIWIs: list = []                # list[str]
        self.isolations: dict = {}        # dict[str, Isolation]
        self.isolationCertificates: dict = {}   # dict[int, IsolationCertificate]

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
        refreshIsolations: bool = False,
        refreshIsolationCertificates: bool = False,
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

        if refreshIsolations or refreshAll:
            err, allIsolations = ClientRequests.getAllIsolations(loggedUser)
            if err:
                return err
            self.isolations = allIsolations

        if refreshIsolationCertificates or refreshAll:
            err, allIsolationCertificates = ClientRequests.getAllIsolationCertificates(loggedUser, department=department)
            if err:
                return err
            self.isolationCertificates = allIsolationCertificates

        if refreshMIWIs or refreshAll:
            err, allMIWIs = ClientRequests.getAllMIWIs(loggedUser, department=department)
            if err:
                return err
            self.allMIWIs = allMIWIs

        return None

globalData = GlobalData()