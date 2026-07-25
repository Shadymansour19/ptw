import threading


class GlobalData:
    def __init__(self):
        self._lock = threading.RLock()
        self.allUsers: dict = {}
        self.allPTWs: dict = {}
        self.ics: dict = {}

    @property
    def lock(self):
        return self._lock

    def refresh(self, userDB, ptwDB, icDB) -> str:
        try:
            allUsers = userDB.getAllSecuredUsers()
            with self._lock:
                self.allUsers = allUsers
            allPTWs = ptwDB.getAllPTWs()
            ics = icDB.getAllICs()
        except Exception as e:
            return str(e)
        with self._lock:
            self.allPTWs = allPTWs
            self.ics = ics
        return None


globalData = GlobalData()
