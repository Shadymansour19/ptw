class GlobalData:
    def __init__(self):
        self.allUsers: dict = {}                # dict[str, SecuredUser]
        self.allPTWs: list = []                 # list[PTWData]
        self.isolations: dict = {}        # dict[str, Isolation]

    def refresh(self) -> str:
        from usersDb import UsersDb
        from ptwDb import PtwsDb
        from IsolationDb import IsolationDb
        
        try:
            userDB = UsersDb()
            ptwDB = PtwsDb()
            isoDB = IsolationDb()
        except Exception as e:
            return str(e)

        self.allUsers = userDB.getAllSecuredUsers()
        self.allPTWs = ptwDB.getAllPTWs()
        self.isolations = isoDB.getAllIsolations()

        return None

globalData = GlobalData()