class GlobalData:
    def __init__(self):
        self.allUsers: dict = {}                # dict[str, SecuredUser]
        self.allRiskAssessments: dict = {}      # dict[str, RiskAssessment]
        self.allPTWs: list = []                 # list[PTWData]
        self.allMIWIs: list = []                # list[str]
        self.activeIsolations: dict = {}        # dict[str, ActiveIsolation]

    def refresh(
        self, 
        loggedUser, 
        department = None, 
        refreshUsers: bool = False, 
        refreshRiskAssessments: bool = False, 
        refreshPTWs: bool = False, 
        refreshMIWIs: bool = False, 
        refreshActiveIsolations: bool = False, 
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

        if refreshActiveIsolations or refreshAll:
            err, allIsolations = ClientRequests.getAllActiveIsolations(loggedUser)
            if err:
                return err
            self.activeIsolations = allIsolations

        if refreshMIWIs or refreshAll:
            err, allMIWIs = ClientRequests.getAllMIWIs(loggedUser)
            if err:
                return err
            self.allMIWIs = allMIWIs

        return None

globalData = GlobalData()