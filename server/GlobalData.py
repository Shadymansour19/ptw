import threading


class GlobalData:
    def __init__(self):
        self._lock = threading.RLock()
        self.allUsers: dict = {}
        self.allPTWs: dict = {}
        self.isolations: dict = {}
        self.isolationCertificates: dict = {}

    @property
    def lock(self):
        return self._lock

    def refresh(self, userDB, ptwDB, isoDB, certDB) -> str:
        try:
            allUsers = userDB.getAllSecuredUsers()
            with self._lock:
                self.allUsers = allUsers
            allPTWs = ptwDB.getAllPTWs()
            isolations = isoDB.getAllIsolations()
            isolationCertificates = certDB.getAllCertificates()
        except Exception as e:
            return str(e)
        with self._lock:
            self.allPTWs = allPTWs
            self.isolations = isolations
            self.isolationCertificates = isolationCertificates
        return None


globalData = GlobalData()
