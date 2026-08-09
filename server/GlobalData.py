"""In-memory, process-wide cache of users, PTWs, and ICs, shared by every route
handler and refreshed from the database on login, periodically, and on demand."""

import threading


class GlobalData:
    """Thread-safe, in-memory cache of secured users, PTWs, and ICs, backed by an
    RLock so route handlers can read/patch it without hitting the database."""

    def __init__(self):
        """Initialize empty caches and the guarding RLock."""
        self._lock = threading.RLock()
        self.allUsers: dict = {}
        self.allPTWs: dict = {}
        self.ics: dict = {}

    @property
    def lock(self):
        """Return the RLock guarding this cache's dicts."""
        return self._lock

    def refresh(self, userDB, ptwDB, icDB) -> str:
        """Reload allUsers, allPTWs, and ics from the database in full.

        Returns:
            None on success, or the stringified exception on failure.
        """
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
