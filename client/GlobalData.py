"""Client-side in-memory cache of server data (users, PTWs, ICs, risk assessments, MIWIs).

Holds the single shared `globalData` instance that role-specific windows and dialogs
read from instead of hitting the network directly. `refresh()` re-fetches selected
pieces of the cache from the server; `upsertPTW`/`removePTW`/`upsertIC`/`removeIC`
apply single-record, SSE-driven patches without a full refresh.
"""

from network.RequestWorker import async_request

class GlobalData:
    """Container for the client's cached copy of server-side data, refreshed on
    login/mutation and patched incrementally as SSE events arrive."""

    def __init__(self):
        """Initialize every cache field to an empty container, ready for the first refresh().

        Fields:
            allUsers: dict[str, SecuredUser] - all users, keyed by username.
            allRiskAssessments: dict[str, RiskAssessment] - generic risk assessment
                library, keyed by title; a PTW's own specific risk rows are fetched
                on demand instead and never cached here.
            allPTWs: dict[int, PTW] - all non-archived PTWs, keyed by id; refreshed
                on login and after any mutation.
            archivedPTWs: dict[int, PTW] - archived PTWs, keyed by id; fetched
                on-demand only (refreshArchivedPTWs/refreshAll), never auto-refreshed.
            allMIWIs: list[str] - MIWI filenames.
            ics: dict[int, IC] - all Isolation Certificates, keyed by id.
        """
        self.allUsers: dict = {}                # dict[str, SecuredUser]
        self.allRiskAssessments: dict = {}      # dict[str, RiskAssessment]
        self.allPTWs: dict = {}                 # dict[int, PTW] - non-archived PTWs
        self.archivedPTWs: dict = {}            # dict[int, PTW]
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
        """Re-fetch selected caches from the server and replace the corresponding fields in place.

        Runs off the GUI thread via the `@async_request` decorator (`network/RequestWorker.py`).
        Each `refreshX` flag (or `refreshAll`, which forces every flag on) independently controls
        whether that piece of data is re-fetched; `archivedPTWs` is only touched when
        `refreshArchivedPTWs`/`refreshAll` is explicitly requested, never as part of a routine
        refresh, to avoid the server overhead of pulling stable, rarely-queried archived permits.

        Args:
            loggedUser: the currently authenticated user, used to authorize each request.
            department: optional department to scope the PTW/IC/MIWI queries to.

        Returns:
            An error message string if any requested fetch failed (stops before later fetches
            in the sequence), otherwise None.
        """
        from network.clientRequests import ClientRequests

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

    def upsertPTW(self, ptw):
        """Patch a single PTW into the cache without a full refresh (SSE-driven update)."""
        self.allPTWs[ptw.id] = ptw

    def removePTW(self, ptwId):
        """Remove a PTW from the cache by id (SSE-driven delete); a no-op if it's not cached."""
        self.allPTWs.pop(ptwId, None)

    def upsertIC(self, ic):
        """Patch a single IC into the cache without a full refresh (SSE-driven update)."""
        self.ics[ic.id] = ic

    def removeIC(self, icId):
        """Remove an IC from the cache by id (SSE-driven delete); a no-op if it's not cached."""
        self.ics.pop(icId, None)

globalData = GlobalData()
