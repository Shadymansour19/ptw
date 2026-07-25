import enum
from types import SimpleNamespace
from datetime import datetime
from PyQt6.QtGui import QColor

from User import UserRoles
from GlobalData import globalData


class Isolation:
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
        self.linked_ptws: list = []
        self.primary_ptw: str = ''
        self.latest_ptw: str = ''
        self.is_physically_isolated: bool = False
        self.held_by: list = []

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

    def linkPTW(self, ptwId):
        ptwId = str(ptwId)
        try:
            self.held_by.remove(ptwId)
        except ValueError:
            pass
        if not self.linked_ptws and not self.held_by:
            self.primary_ptw = ptwId
        if ptwId not in self.linked_ptws:
            self.linked_ptws.append(ptwId)
            self.latest_ptw = ptwId
        self.is_physically_isolated = True

    def holdPTW(self, ptwId):
        try:
            self.linked_ptws.remove(str(ptwId))
        except Exception:
            pass
        if self.linked_ptws:
            self.latest_ptw = self.linked_ptws[-1]
        if str(ptwId) not in self.held_by:
            self.held_by.append(str(ptwId))
        # is_physically_isolated stays True — held PTW keeps isolation in place
        self.is_physically_isolated = True

    def unlinkPTW(self, ptwId):
        try:
            self.linked_ptws.remove(str(ptwId))
        except Exception as e:
            print(f"couldn't remove PTW# {ptwId} from linked PTWs to isolation {self.tag}: {e}")
        if self.linked_ptws:
            self.latest_ptw = self.linked_ptws[-1]
        if not self.linked_ptws and not self.held_by:
            self.is_physically_isolated = False

    def isReallyActive(self):
        return self.is_physically_isolated


class IsolationCertificate:
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
            return isinstance(other, IsolationCertificate.Approver) and self.role == other.role and self.department == other.department

        def __hash__(self):
            return hash((self.role, self.department))

        def __str__(self):
            if self.role == UserRoles.USER:
                return str(self.department) if self.department else str(self.role)
            return str(self.role)

    def __init__(self, data: dict = {}):
        self.id : str = data.get('id')
        self.type : str = data.get('type')
        self.department : str = data.get('department')
        self.requestor : str = data.get('requestor')
        self.requestor_timestamp : str = data.get('requestor_timestamp') or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.approvals : list['IsolationCertificate.Approval'] = [IsolationCertificate.Approval().setAll(a) for a in data.get('approvals', [])]
        self.location : str = data.get('location')
        self.equipment : str = data.get('equipment')
        self.reason : str = data.get('reason')
        self.items : list[IsolationCertificate.IsolationItem] = [IsolationCertificate.IsolationItem().setAll(iso) for iso in data.get('items', [])]

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
        self.primary_ptw: str = ''
        self.latest_ptw: str = ''
        self.is_physically_isolated: bool = False
        self.held_by: list = []

    def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
        if namespace:
            self.__dict__.update(vars(namespace))
            self.approvals = [IsolationCertificate.Approval().setAll(a.__dict__) for a in self.approvals]
            self.items = [IsolationCertificate.IsolationItem().setAll(i.__dict__) for i in self.items]
        elif data:
            for k, v in data.items():
                if hasattr(self, k):
                    try:
                        if k == 'approvals':
                            self.approvals = [IsolationCertificate.Approval().setAll(a) for a in v]
                        elif k == 'items':
                            self.items = [IsolationCertificate.IsolationItem().setAll(i) for i in v]
                        else:
                            setattr(self, k, v)
                    except Exception:
                        pass
        return self

    def __str__(self):
        return f"{self.id} - {self.type} {self.reason if self.reason else ''} {self.primary_ptw}"

    def requiredApprovers(self) -> list[list['IsolationCertificate.Approver']]:
        stages = [[IsolationCertificate.Approver(UserRoles.ISSUING)]]
        if self.type == IsolationCertificate.Types.PROTECTIVE and not self.primary_ptw:
            stages.extend([
                [IsolationCertificate.Approver(UserRoles.PDH)],
                [IsolationCertificate.Approver(UserRoles.PGM)],
                [IsolationCertificate.Approver(UserRoles.SOD)],
                [IsolationCertificate.Approver(UserRoles.DFGM)],
            ])
        return stages

    def _stageSatisfied(self, stage: list['IsolationCertificate.Approver']) -> bool:
        approvedBy = [globalData.allUsers.get(a.username) for a in self.approvals if a.action == IsolationCertificate.ApprovalActions.APPROVED]
        return all(any(approver.matchesUser(user) for user in approvedBy) for approver in stage)

    def _pendingStageIndex(self) -> int:
        """Index of the first not-yet-satisfied approval stage, or len(stages) if fully approved."""
        stages = self.requiredApprovers()
        for i, stage in enumerate(stages):
            if not self._stageSatisfied(stage):
                return i
        return len(stages)

    def pendingApprovers(self) -> list['IsolationCertificate.Approver']:
        """Flattened Approvers still needed, across the current and any later stage."""
        approvedBy = [globalData.allUsers.get(a.username) for a in self.approvals if a.action == IsolationCertificate.ApprovalActions.APPROVED]
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
            if any(a.action == IsolationCertificate.ApprovalActions.RETURNED for a in self.approvals):
                return IsolationCertificate.Status.RETURNED
            if self._pendingStageIndex() >= len(self.requiredApprovers()):
                return IsolationCertificate.Status.APPROVED
            return IsolationCertificate.Status.REQUESTED

        for approval in self.approvals[::-1]:
            user = globalData.allUsers.get(approval.username)
            if user is not None and user.getRole() == role and user.getDepartment() == department:
                return approval.action

        stages = self.requiredApprovers()
        pending = self._pendingStageIndex()
        if pending < len(stages) and any(approver.matchesRoleDept(role, department) for approver in stages[pending]):
            return IsolationCertificate.Status.REQUESTED
        return None

    def getStatus(self) -> 'IsolationCertificate.Status':
        if self.deisolate_isolator:
            return self.Status.CLOSED
        if self.sanction_isolator and not self.reisolate_isolator:
            return self.Status.SANCTIONED
        if self.isolate_isolator or self.reisolate_isolator:
            if self.deisolate_requestor:
                if self.deisolate_issuing_action == IsolationCertificate.ApprovalActions.APPROVED:
                    return self.Status.CLOSING
                if self.deisolate_issuing_action != IsolationCertificate.ApprovalActions.RETURNED:
                    return self.Status.DEISOLATE_CONFIRMING
            return self.Status.ACTIVE
        if self.isolate_requestor:
            if self.isolate_issuing_action == IsolationCertificate.ApprovalActions.APPROVED:
                return self.Status.PENDING
            if self.isolate_issuing_action != IsolationCertificate.ApprovalActions.RETURNED:
                return self.Status.ISOLATE_CONFIRMING
        return self.getApprovalStatus()

    __backgroundColors = {
        Types.MECHANICAL: QColor(120, 120, 120, 200),  # gray
        Types.ELECTRICAL: QColor(200, 165,   0, 200),  # yellow
        Types.SELF:       QColor( 30, 160, 100, 200),  # green
        Types.PROTECTIVE: QColor(200,  30,  30, 200),  # red
        Types.OTHER:      QColor(150, 150, 150, 150),  # neutral gray
    }

    __foregroundColors = {
        Types.MECHANICAL: QColor('black'),
        Types.ELECTRICAL: QColor('black'),
        Types.SELF:       QColor('black'),
        Types.PROTECTIVE: QColor('black'),
        Types.OTHER:      QColor('black'),
    }

    @staticmethod
    def backgroundColorForType(certType: Types):
        return IsolationCertificate.__backgroundColors.get(certType) or IsolationCertificate.__backgroundColors.get(IsolationCertificate.Types.OTHER)

    @staticmethod
    def foregroundColorForType(certType: Types):
        return IsolationCertificate.__foregroundColors.get(certType) or IsolationCertificate.__foregroundColors.get(IsolationCertificate.Types.OTHER)

    def backgroundColor(self):
        return IsolationCertificate.__backgroundColors.get(self.type) or IsolationCertificate.__backgroundColors.get(IsolationCertificate.Types.OTHER)

    def foregroundColor(self):
        return IsolationCertificate.__foregroundColors.get(self.type) or IsolationCertificate.__foregroundColors.get(IsolationCertificate.Types.OTHER)

    # def linkPTW(self, ptwId):
    #     ptwId = str(ptwId)
    #     try:
    #         self.held_by.remove(ptwId)
    #     except ValueError:
    #         pass
    #     if not self.linked_ptws and not self.held_by:
    #         self.primary_ptw = ptwId
    #     if ptwId not in self.linked_ptws:
    #         self.linked_ptws.append(ptwId)
    #         self.latest_ptw = ptwId

    # def holdPTW(self, ptwId):
    #     try:
    #         self.linked_ptws.remove(str(ptwId))
    #     except Exception:
    #         pass
    #     if self.linked_ptws:
    #         self.latest_ptw = self.linked_ptws[-1]
    #     if str(ptwId) not in self.held_by:
    #         self.held_by.append(str(ptwId))
    #     # is_physically_isolated stays True — held PTW keeps isolation in place
    #     self.is_physically_isolated = True

    # def unlinkPTW(self, ptwId):
    #     try:
    #         self.linked_ptws.remove(str(ptwId))
    #     except Exception as e:
    #         print(f"couldn't remove PTW# {ptwId} from linked PTWs to isolation {self.tag}: {e}")
    #     if self.linked_ptws:
    #         self.latest_ptw = self.linked_ptws[-1]
    #     if not self.linked_ptws and not self.held_by:
    #         self.is_physically_isolated = False

    # def isReallyActive(self):
    #     return self.is_physically_isolated
