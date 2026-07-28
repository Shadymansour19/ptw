import enum
from types import SimpleNamespace
from datetime import datetime

from User import UserRoles
from GlobalData import globalData


class Isolation:
    """Declarative record of an isolation required by a PTW — type/tag/description only.
    No runtime linkage state; that now lives entirely on IC (see below)."""
    class Types(enum.StrEnum):
        MECHANICAL = 'Mechanical'
        ELECTRICAL = 'Electrical'
        SELF       = 'Self'
        PROTECTIVE = 'Protective System'
        OTHER      = 'Other'

    def __init__(self, type: str = '', tag: str = '', description: str = ''):
        self.type = type
        self.tag = tag
        self.description = description

    def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
        if namespace:
            self.__dict__.update(vars(namespace))
        elif data:
            for k, v in data.items():
                if hasattr(self, k):
                    try:
                        setattr(self, k, v)
                    except Exception:
                        pass
        return self

    def __str__(self):
        return f"{self.type} - {self.description if self.description else ''} {self.tag}"


class IC:
    class IsolationItem:
        class States(enum.StrEnum):
            OPEN  = enum.auto()
            CLOSE = enum.auto()

        def __init__(self, tag: str = '', description: str = '', state: str = ''):
            self.tag = tag
            self.description = description
            self.state = state
            self.lock_num = ''
            self.lock_box_num = ''

        def setLockNum(self, lockNum):
            self.lock_num = lockNum
            return self

        def setLockBoxNum(self, lockBoxNum):
            self.lock_box_num = lockBoxNum
            return self

        def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
            if namespace:
                self.__dict__.update(vars(namespace))
            elif data:
                for k, v in data.items():
                    if hasattr(self, k):
                        try:
                            setattr(self, k, v)
                        except Exception:
                            pass
            return self


    class Highlight:
        def __init__(self, tag: str = '', page: int = 0, rect=None, state: str = '', manual: bool = False):
            self.tag = tag
            self.page = page          # 0-based page index
            self.rect = rect or [0.0, 0.0, 0.0, 0.0]  # [x, y, w, h], fractional 0..1 of page size
            self.state = state        # IC.IsolationItem.States value at highlight-time
            self.manual = manual      # unused today; reserved for future manual override editing

        def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
            if namespace:
                self.__dict__.update(vars(namespace))
            elif data:
                for k, v in data.items():
                    if hasattr(self, k):
                        try:
                            setattr(self, k, v)
                        except Exception:
                            pass
            return self

    class PidWiringDocument:
        @staticmethod
        def _asHighlight(h) -> 'IC.Highlight':
            """highlights arrives in three possible shapes depending on the caller: an already-
            built IC.Highlight (in-memory, e.g. from PidWiringHighlighter.computeHighlights), a
            plain dict (raw JSON), or a SimpleNamespace (nested inside a DB row's namespace, via
            dictToObj) - tolerate all three rather than assuming one."""
            if isinstance(h, IC.Highlight):
                return h
            if isinstance(h, SimpleNamespace):
                return IC.Highlight().setAll(namespace=h)
            return IC.Highlight().setAll(h)

        def __init__(self, filename: str = '', original_filename: str = '', page_count: int = 1, ocr_used: bool = False, highlights=None):
            self.filename = filename                    # the highlighted/burned-in file - served to the app and to external viewers
            self.original_filename = original_filename  # pristine upload, kept only so highlights can be recomputed later
            self.page_count = page_count
            self.ocr_used = ocr_used
            self.highlights: list['IC.Highlight'] = [IC.PidWiringDocument._asHighlight(h) for h in (highlights or [])]

        def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
            if namespace:
                self.__dict__.update(vars(namespace))
                self.highlights = [IC.PidWiringDocument._asHighlight(h) for h in self.highlights]
            elif data:
                for k, v in data.items():
                    if hasattr(self, k):
                        try:
                            if k == 'highlights':
                                self.highlights = [IC.PidWiringDocument._asHighlight(h) for h in v]
                            else:
                                setattr(self, k, v)
                        except Exception:
                            pass
            return self


    class Types(enum.StrEnum):
        MECHANICAL = 'Mechanical'
        ELECTRICAL = 'Electrical'
        SELF       = 'Self'
        PROTECTIVE = 'Protective System'
        OTHER      = 'Other'

    class Status(enum.StrEnum):
        REQUESTED  = 'Requested'
        RETURNED   = 'Returned'
        APPROVED   = 'Approved'
        ISOLATE_CONFIRMING = 'Isolate Confirming'
        PENDING    = 'Pending'
        ACTIVE     = 'Active'
        DEISOLATE_CONFIRMING = 'Deisolate Confirming'
        CLOSING    = 'Closing'
        SANCTIONED = 'Sanctioned'
        CLOSED     = 'Closed'

    class ApprovalActions(enum.StrEnum):
        APPROVED = 'Approved'
        RETURNED = 'Returned'

    class Approval:
        def __init__(self, action=None, username: str = None, timestamp: str = None, comment: str = None):
            self.action = action
            self.username = username
            self.timestamp = timestamp
            self.comment = comment

        def setAll(self, data: dict):
            for k, v in data.items():
                if hasattr(self, k):
                    try:
                        setattr(self, k, v)
                    except Exception:
                        pass
            return self

        def __str__(self):
            user = globalData.allUsers.get(self.username)
            if user is None:
                return f"{self.action} by [deleted user: {self.username}] at {self.timestamp}"
            if user.getRole() == UserRoles.USER:
                return f"{self.action} by {user.getRole()} {user.getName()} ({user.getDepartment()}) at {self.timestamp}"
            return f"{self.action} by {user.getRole()} {user.getName()} at {self.timestamp}"

    class Approver:
        def __init__(self, role: 'UserRoles', department=None):
            self.role = role
            self.department = department

        def matchesRoleDept(self, role, department) -> bool:
            return role == self.role and (self.department is None or self.department == department)

        def matchesUser(self, user) -> bool:
            return user is not None and self.matchesRoleDept(user.getRole(), user.getDepartment())

        def __eq__(self, other):
            return isinstance(other, IC.Approver) and self.role == other.role and self.department == other.department

        def __hash__(self):
            return hash((self.role, self.department))

        def __str__(self):
            if self.role == UserRoles.USER:
                return str(self.department) if self.department else str(self.role)
            return str(self.role)

    def __init__(self, data: dict = {}):
        self.id : str = data.get('id')
        self.type : str = data.get('type')
        self.requestor_department : str = data.get('requestor_department')
        self.execution_department : str = data.get('execution_department')
        self.requestor : str = data.get('requestor')
        self.requestor_timestamp : str = data.get('requestor_timestamp') or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.approvals : list['IC.Approval'] = [IC.Approval().setAll(a) for a in data.get('approvals', [])]
        self.location : str = data.get('location')
        self.equipment : str = data.get('equipment')
        self.reason : str = data.get('reason')
        self.items : list[IC.IsolationItem] = [IC.IsolationItem().setAll(iso) for iso in data.get('items', [])]
        self.pid_documents : list[IC.PidWiringDocument] = [IC.PidWiringDocument().setAll(d) for d in data.get('pid_documents', [])]

        # ============== isolation usernames & timestamps =================
        # isolate_requestor/timestamp are set later, when someone requests the isolation
        # actually be carried out (automatically if isolate_asap, else manually after
        # approval) - NOT at IC creation, which is tracked by requestor/requestor_timestamp above.
        self.isolate_asap: bool = data.get('isolate_asap', False)
        self.isolate_requestor = data.get('isolate_requestor')
        self.isolate_requestor_timestamp = data.get('isolate_requestor_timestamp')
        self.isolate_issuing = data.get('isolate_issuing')
        self.isolate_issuing_timestamp = data.get('isolate_issuing_timestamp')
        self.isolate_issuing_action = data.get('isolate_issuing_action', '')
        self.isolate_isolator = data.get('isolate_isolator')
        self.isolate_isolator_timestamp = data.get('isolate_isolator_timestamp')
        
        # ============== sanction for test usernames & timestamps =================
        self.sanction_requestor = data.get('sanction_requestor')
        self.sanction_requestor_timestamp = data.get('sanction_requestor_timestamp')
        self.sanction_issuing = data.get('sanction_issuing')
        self.sanction_issuing_timestamp = data.get('sanction_issuing_timestamp')
        self.sanction_isolator = data.get('sanction_isolator')
        self.sanction_isolator_timestamp = data.get('sanction_isolator_timestamp')
        
        # ============== re-isolation usernames & timestamps =================
        self.reisolate_requestor = data.get('reisolate_requestor')
        self.reisolate_requestor_timestamp = data.get('reisolate_requestor_timestamp')
        self.reisolate_issuing = data.get('reisolate_issuing')
        self.reisolate_issuing_timestamp = data.get('reisolate_issuing_timestamp')
        self.reisolate_isolator = data.get('reisolate_isolator')
        self.reisolate_isolator_timestamp = data.get('reisolate_isolator_timestamp')
        
        # ============== de-isolation usernames & timestamps =================
        self.deisolate_requestor = data.get('deisolate_requestor')
        self.deisolate_requestor_timestamp = data.get('deisolate_requestor_timestamp')
        self.deisolate_issuing = data.get('deisolate_issuing')
        self.deisolate_issuing_timestamp = data.get('deisolate_issuing_timestamp')
        self.deisolate_issuing_action = data.get('deisolate_issuing_action', '')
        self.deisolate_isolator = data.get('deisolate_isolator')
        self.deisolate_isolator_timestamp = data.get('deisolate_isolator_timestamp')
        
        self.long_term: bool = data.get('long_term', False)
        self.long_term_reason: str = data.get('long_term_reason')
        self.linked_ptws: list = []
        self.held_by: list = []

    def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
        if namespace:
            self.__dict__.update(vars(namespace))
            self.approvals = [IC.Approval().setAll(a.__dict__) for a in self.approvals]
            self.items = [IC.IsolationItem().setAll(i.__dict__) for i in self.items]
            self.pid_documents = [IC.PidWiringDocument().setAll(d.__dict__) for d in self.pid_documents]
        elif data:
            for k, v in data.items():
                if hasattr(self, k):
                    try:
                        if k == 'approvals':
                            self.approvals = [IC.Approval().setAll(a) for a in v]
                        elif k == 'items':
                            self.items = [IC.IsolationItem().setAll(i) for i in v]
                        elif k == 'pid_documents':
                            self.pid_documents = [IC.PidWiringDocument().setAll(d) for d in v]
                        else:
                            setattr(self, k, v)
                    except Exception:
                        pass
        return self

    def __str__(self):
        return f"{self.id} - {self.type} {self.reason if self.reason else ''}"

    def requiredApprovers(self) -> list[list['IC.Approver']]:
        stages = [[IC.Approver(UserRoles.ISSUING)]]
        if self.type == IC.Types.PROTECTIVE:
            stages.extend([
                [IC.Approver(UserRoles.PDH)],
                [IC.Approver(UserRoles.PGM)],
                [IC.Approver(UserRoles.SOD)],
                [IC.Approver(UserRoles.DFGM)],
            ])
        return stages

    def _stageSatisfied(self, stage: list['IC.Approver']) -> bool:
        approvedBy = [globalData.allUsers.get(a.username) for a in self.approvals if a.action == IC.ApprovalActions.APPROVED]
        return all(any(approver.matchesUser(user) for user in approvedBy) for approver in stage)

    def _pendingStageIndex(self) -> int:
        """Index of the first not-yet-satisfied approval stage, or len(stages) if fully approved."""
        stages = self.requiredApprovers()
        for i, stage in enumerate(stages):
            if not self._stageSatisfied(stage):
                return i
        return len(stages)

    def pendingApprovers(self) -> list['IC.Approver']:
        """Flattened Approvers still needed, across the current and any later stage."""
        approvedBy = [globalData.allUsers.get(a.username) for a in self.approvals if a.action == IC.ApprovalActions.APPROVED]
        stages = self.requiredApprovers()
        return [
            approver
            for stage in stages[self._pendingStageIndex():]
            for approver in stage
            if not any(approver.matchesUser(user) for user in approvedBy)
        ]

    def getApprovalStatus(self, role=None, department=None):
        """No role -> overall approval-chain status. With role/department -> that
        viewer's status: the action they already took, 'Requested' if it's their
        turn right now, or None if they're not an approver for this certificate."""
        if role is None:
            if any(a.action == IC.ApprovalActions.RETURNED for a in self.approvals):
                return IC.Status.RETURNED
            if self._pendingStageIndex() >= len(self.requiredApprovers()):
                return IC.Status.APPROVED
            return IC.Status.REQUESTED

        for approval in self.approvals[::-1]:
            user = globalData.allUsers.get(approval.username)
            if user is not None and user.getRole() == role and user.getDepartment() == department:
                return approval.action

        stages = self.requiredApprovers()
        pending = self._pendingStageIndex()
        if pending < len(stages) and any(approver.matchesRoleDept(role, department) for approver in stages[pending]):
            return IC.Status.REQUESTED
        return None

    def getStatus(self) -> 'IC.Status':
        if self.deisolate_isolator:
            return self.Status.CLOSED
        if self.sanction_isolator and not self.reisolate_isolator:
            return self.Status.SANCTIONED
        if self.isolate_isolator or self.reisolate_isolator:
            if self.deisolate_requestor:
                if self.deisolate_issuing_action == IC.ApprovalActions.APPROVED:
                    return self.Status.CLOSING
                if self.deisolate_issuing_action != IC.ApprovalActions.RETURNED:
                    return self.Status.DEISOLATE_CONFIRMING
            return self.Status.ACTIVE
        if self.isolate_requestor:
            if self.isolate_issuing_action == IC.ApprovalActions.APPROVED:
                return self.Status.PENDING
            if self.isolate_issuing_action != IC.ApprovalActions.RETURNED:
                return self.Status.ISOLATE_CONFIRMING
        return self.getApprovalStatus()

    def isWindingDown(self) -> bool:
        """True once a sanction-for-test or de-isolate cycle is underway, or once closed —
        the certificate is past the point where new PTWs should be linked to it."""
        return self.getStatus() in (
            IC.Status.SANCTIONED,
            IC.Status.DEISOLATE_CONFIRMING,
            IC.Status.CLOSING,
            IC.Status.CLOSED,
        )

    def canLinkPTW(self, ptw) -> bool:
        """IC must not be winding down, and the target PTW must be in the window
        between its own approval and it actually starting work — approved, but not yet
        run/held/closed (or requested to be)."""
        if self.isWindingDown():
            return False
        from PTWData import PTWData
        return ptw is not None and ptw.approval_status == PTWData.ApprovalStatus.APPROVED and ptw.running_status == PTWData.RunningStatus.NOT_RUNNING

    def linkPTW(self, ptwId):
        ptwId = str(ptwId)
        try:
            self.held_by.remove(ptwId)
        except ValueError:
            pass
        if ptwId not in self.linked_ptws:
            self.linked_ptws.append(ptwId)

    def unlinkPTW(self, ptwId):
        ptwId = str(ptwId)
        try:
            self.linked_ptws.remove(ptwId)
        except ValueError:
            pass
        try:
            self.held_by.remove(ptwId)
        except ValueError:
            pass
