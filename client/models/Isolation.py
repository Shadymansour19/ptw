"""Client-side isolation models: the declarative `Isolation` record attached to a
PTW's required-isolations list, and the full `IC` (Isolation Certificate) model -
approval chain, PSIC fields, isolate/de-isolate execution cycles, status
derivation, P&ID/wiring documents, and PTW linkage. Row/tab coloring helpers
(QColor-based) live here only; the server-side twin of this file has no UI
concerns."""

import enum
from types import SimpleNamespace
from datetime import datetime
from PyQt6.QtGui import QColor

from models.User import UserRoles
from GlobalData import globalData


# PSIC ("Protective System IC") reason options - defined client-side only, not enforced
# by the server as a fixed enum; the server just stores whatever list of strings is sent
# (see POST /ics/approvals, Coordinator's PSIC-terms validation - non-empty is all it
# checks). No server-side twin of these three constants is needed, unlike the rest of
# this file.
PSIC_REASONS = ['ESD', 'Fire Protection', 'Fire Detection', 'Gas Detection', 'Protection System', 'Other']
PSIC_REASON_GRID_COLS = 3

# Sample per-tag isolation data for the "autofill from tag" convenience feature - stands in
# for a real per-tag data source, which doesn't exist yet.
PSIC_TAG_SAMPLES = {
    'XV-3615E': {
        'reasons': ['ESD'],
        'system_description': "UT-C Control Valve — part of the Unit UT-C emergency shutdown loop.",
        'isolation_method': "Close XV-3615E and secure in the closed position with a mechanical lock-out device.",
        'control_measures': "Verify zero-energy state with a local pressure/position check; apply lock-out tag; log in the isolation register before work starts.",
    },
    'SDV-6514': {
        'reasons': ['ESD', 'Fire Protection'],
        'system_description': "FL-A Breaker — feeds the flare header's shutdown valve actuator.",
        'isolation_method': "Open SDV-6514's supply breaker and rack it out.",
        'control_measures': "Verify de-energized with a voltage tester; apply electrical lock-out and danger tag; notify the Electrical shift lead.",
    },
    'EV-5333': {
        'reasons': ['Protection System'],
        'system_description': "IN-A Feeder Panel — supplies the instrument air system's protective shutdown solenoid.",
        'isolation_method': "Isolate EV-5333 at the feeder panel and remove the fuse.",
        'control_measures': "Confirm zero air pressure downstream; apply lock-out tag on the panel; retain the fuse with the permit holder.",
    },
}


class Isolation:
    """Declarative record of an isolation required by a PTW — type/tag/description only.
    No runtime linkage state; that now lives entirely on IC (see below)."""
    class Types(enum.StrEnum):
        """Classification of a declarative isolation tag (unrelated to `IC.Types`;
        `Protective System` here is just a tag-classification value, not a PSIC)."""
        MECHANICAL = 'Mechanical'
        ELECTRICAL = 'Electrical'
        SELF       = 'Self'
        PROTECTIVE = 'Protective System'
        OTHER      = 'Other'

    def __init__(self, type: str = '', tag: str = '', description: str = ''):
        """Set the type/tag/description fields directly from the given values."""
        self.type = type
        self.tag = tag
        self.description = description

    def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
        """Bulk-assign matching attributes from a dict or SimpleNamespace and return self."""
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
        """Render as "type - description tag" for list/combo display."""
        return f"{self.type} - {self.description if self.description else ''} {self.tag}"


class IC:
    """Isolation Certificate: the formal, independently-approved isolation-request
    document. Wraps a list of isolation `items`, its own approval chain
    (`Approval`/`Approver`/`requiredApprovers()`), optional PSIC (Protective
    System IC) fields, the isolate/de-isolate execution cycles (with usernames
    and timestamps for each requestor/issuing/isolator step), attached P&ID/
    wiring documents, and PTW linkage lists (`linked_ptws`/`held_by`)."""

    class IsolationItem:
        """One isolation point on an IC: tag, description, target state
        (OPEN/CLOSE), and the lock/lock-box numbers set by the isolator."""

        class States(enum.StrEnum):
            """Target state to leave an isolation point in: physically open or closed."""
            OPEN  = enum.auto()
            CLOSE = enum.auto()

        def __init__(self, tag: str = '', description: str = '', state: str = ''):
            """Set tag/description/state; lock fields start blank until the isolator sets them."""
            self.tag = tag
            self.description = description
            self.state = state
            self.lock_num = ''
            self.lock_box_num = ''

        def setLockNum(self, lockNum):
            """Set the lock number and return self for chaining."""
            self.lock_num = lockNum
            return self
        
        def setLockBoxNum(self, lockBoxNum):
            """Set the lock box number and return self for chaining."""
            self.lock_box_num = lockBoxNum
            return self

        def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
            """Bulk-assign matching attributes from a dict or SimpleNamespace and return self."""
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
        """A single burned-in P&ID/wiring highlight box for one isolation item's tag,
        located on a specific page and fractional rectangle of a `PidWiringDocument`."""

        def __init__(self, tag: str = '', page: int = 0, rect=None, state: str = '', manual: bool = False):
            """Set the highlight's tag, page, rectangle, item state, and manual-edit flag."""
            self.tag = tag
            self.page = page          # 0-based page index
            self.rect = rect or [0.0, 0.0, 0.0, 0.0]  # [x, y, w, h], fractional 0..1 of page size
            self.state = state        # IC.IsolationItem.States value at highlight-time
            self.manual = manual      # unused today; reserved for future manual override editing

        def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
            """Bulk-assign matching attributes from a dict or SimpleNamespace and return self."""
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
        """A single uploaded P&ID/wiring diagram (PDF or image) attached to an IC,
        with the isolation items' tags automatically located and highlighted on it."""

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
            """Set the document's filenames, page count, OCR flag, and normalized highlight list."""
            self.filename = filename                    # the highlighted/burned-in file - served to the app and to external viewers
            self.original_filename = original_filename  # pristine upload, kept only so highlights can be recomputed later
            self.page_count = page_count
            self.ocr_used = ocr_used
            self.highlights: list['IC.Highlight'] = [IC.PidWiringDocument._asHighlight(h) for h in (highlights or [])]

        def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
            """Bulk-assign matching attributes from a dict or SimpleNamespace, re-normalizing highlights, and return self."""
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
        """IC classification (distinct from the removed `Protective System` value -
        see the `is_psic` flag instead)."""
        MECHANICAL = 'Mechanical'
        ELECTRICAL = 'Electrical'
        SELF       = 'Self'
        OTHER      = 'Other'

    class Status(enum.StrEnum):
        """Overall IC lifecycle status, as computed by `getStatus()`."""
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
        """Decision recorded for an approval step or an isolate/de-isolate IA confirmation."""
        APPROVED = 'Approved'
        RETURNED = 'Returned'

    class Approval:
        """One recorded action (approve/return) in the IC's approval chain, by whom and when.
        role/department snapshot the actor's role and department at approval time (stamped
        server-side), so replay stays valid even if the user is later deleted or re-roled;
        records predating the snapshot fall back to the live user record (see roleDept())."""

        def __init__(self, action=None, username: str = None, timestamp: str = None, comment: str = None,
                     role: str = None, department: str = None):
            """Set the action, acting user, timestamp, optional comment, and the
            actor's role/department snapshot."""
            self.action = action
            self.username = username
            self.timestamp = timestamp
            self.comment = comment
            self.role = role
            self.department = department

        def roleDept(self) -> tuple:
            """The (role, department) this approval counts for: the snapshot
            taken at approval time, or — for legacy records without one — the
            acting user's current role/department, or (None, None) if that
            user no longer exists."""
            if self.role:
                return self.role, self.department
            user = globalData.allUsers.get(self.username)
            if user is not None:
                return user.getRole(), user.getDepartment()
            return None, None

        def setAll(self, data: dict):
            """Bulk-assign matching attributes from a dict and return self."""
            for k, v in data.items():
                if hasattr(self, k):
                    try:
                        setattr(self, k, v)
                    except Exception:
                        pass
            return self

        def __str__(self):
            """Render a human-readable "action by role name (dept) at timestamp" summary."""
            user = globalData.allUsers.get(self.username)
            if user is None:
                return f"{self.action} by [deleted user: {self.username}] at {self.timestamp}"
            if user.getRole() == UserRoles.USER:
                return f"{self.action} by {user.getRole()} {user.getName()} ({user.getDepartment()}) at {self.timestamp}"
            return f"{self.action} by {user.getRole()} {user.getName()} at {self.timestamp}"

    class Approver:
        """A required approval-chain slot: a role, optionally scoped to a specific department."""

        def __init__(self, role: 'UserRoles', department=None):
            """Set the required role and, optionally, the department it's scoped to."""
            self.role = role
            self.department = department

        def matchesRoleDept(self, role, department) -> bool:
            """Return True if the given role/department satisfies this Approver slot."""
            return role == self.role and (self.department is None or self.department == department)

        def matchesUser(self, user) -> bool:
            """Return True if the given user's role/department satisfies this Approver slot."""
            return user is not None and self.matchesRoleDept(user.getRole(), user.getDepartment())

        def __eq__(self, other):
            """Compare equal to another Approver with the same role and department."""
            return isinstance(other, IC.Approver) and self.role == other.role and self.department == other.department

        def __hash__(self):
            """Hash on (role, department) so Approvers can be used in sets/dicts."""
            return hash((self.role, self.department))

        def __str__(self):
            """Render as the department (for a department-scoped USER slot) or the role name."""
            if self.role == UserRoles.USER:
                return str(self.department) if self.department else str(self.role)
            return str(self.role)

    def __init__(self, data: dict = {}):
        """Build an IC from a data dict (server row or JSON payload), defaulting every
        field to blank/unset for a brand-new certificate.

        Nested lists (`approvals`, `items`, `pid_documents`) are rebuilt into their
        proper model classes. `requestor_timestamp` defaults to now if not supplied
        (this IC is being newly created), unlike the later isolate/sanction/
        reisolate/deisolate requestor timestamps, which must stay unset until that
        specific action actually happens.
        """
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

        # ============== PSIC (Protective System IC) =================
        # Any IC, regardless of type, can be flagged as a PSIC - see requiredApprovers().
        self.is_psic: bool = data.get('is_psic', False)
        self.psic_reasons: list = data.get('psic_reasons', [])
        self.psic_moc_number: str = data.get('psic_moc_number')
        self.psic_system_description: str = data.get('psic_system_description')
        self.psic_isolation_method: str = data.get('psic_isolation_method')
        self.psic_control_measures: str = data.get('psic_control_measures')

        self.linked_ptws: list = []
        self.held_by: list = []

    def setAll(self, data: dict = None, namespace: SimpleNamespace = None):
        """Bulk-assign matching attributes from a dict or SimpleNamespace, rebuilding
        the `approvals`/`items`/`pid_documents` lists into their proper model
        classes, and return self."""
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
        """Render as "id - type reason" for list/log display."""
        return f"{self.id} - {self.type} {self.reason if self.reason else ''}"

    def requiredApprovers(self) -> list[list['IC.Approver']]:
        """Return the ordered approval stages required for this IC: Issuing alone for a
        normal IC, or Issuing, then Coordinator, then PDH/PGM/SOD/DFGM (each its own
        stage) when `is_psic` is set. Issuing is the one who sets `is_psic` in the first
        place (as part of approving their own stage - see MainWindow.acceptIC), and
        Coordinator's approval of their stage is what supplies the PSIC terms
        (psic_reasons/psic_moc_number/psic_system_description/psic_isolation_method/
        psic_control_measures - see MainWindow.acceptIC's Coordinator branch and
        POST /ics/approvals) rather than being a separate action outside the chain."""
        stages = [[IC.Approver(UserRoles.ISSUING)]]
        if self.is_psic:
            stages.extend([
                [IC.Approver(UserRoles.COORDINATOR)],
                [IC.Approver(UserRoles.PDH)],
                [IC.Approver(UserRoles.PGM)],
                [IC.Approver(UserRoles.SOD)],
                [IC.Approver(UserRoles.DFGM)],
            ])
        return stages

    def _approvedRoleDepts(self) -> list[tuple]:
        """(role, department) pairs credited by this IC's APPROVED entries —
        each approval's at-approval-time snapshot where available (see
        Approval.roleDept()), so replay doesn't regress when an approver is
        later deleted or re-roled."""
        pairs = [a.roleDept() for a in self.approvals if a.action == IC.ApprovalActions.APPROVED]
        return [(role, dept) for role, dept in pairs if role is not None]

    def _stageSatisfied(self, stage: list['IC.Approver']) -> bool:
        """Return True if every Approver in the given stage has a matching Approved entry."""
        approvedRoleDepts = self._approvedRoleDepts()
        return all(any(approver.matchesRoleDept(role, dept) for role, dept in approvedRoleDepts) for approver in stage)

    def _pendingStageIndex(self) -> int:
        """Index of the first not-yet-satisfied approval stage, or len(stages) if fully approved."""
        stages = self.requiredApprovers()
        for i, stage in enumerate(stages):
            if not self._stageSatisfied(stage):
                return i
        return len(stages)

    def pendingApprovers(self) -> list['IC.Approver']:
        """Flattened Approvers still needed, across the current and any later stage."""
        approvedRoleDepts = self._approvedRoleDepts()
        stages = self.requiredApprovers()
        return [
            approver
            for stage in stages[self._pendingStageIndex():]
            for approver in stage
            if not any(approver.matchesRoleDept(role, dept) for role, dept in approvedRoleDepts)
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
            aRole, aDept = approval.roleDept()
            if aRole == role and aDept == department:
                return approval.action

        stages = self.requiredApprovers()
        pending = self._pendingStageIndex()
        if pending < len(stages) and any(approver.matchesRoleDept(role, department) for approver in stages[pending]):
            return IC.Status.REQUESTED
        return None

    def getStatus(self) -> 'IC.Status':
        """Derive the IC's current lifecycle status by layering the isolate/de-isolate
        execution cycles on top of the approval chain, in this precedence order:

        1. `deisolate_isolator` set -> CLOSED (terminal; the only path here).
        2. `sanction_isolator` set and `reisolate_isolator` not (yet) set -> SANCTIONED.
        3. `isolate_isolator` or `reisolate_isolator` set (physically isolated):
           - no `deisolate_requestor` -> ACTIVE.
           - `deisolate_requestor` set, `deisolate_issuing_action == Approved` -> CLOSING
             (awaiting isolator's de-isolate execution).
           - `deisolate_requestor` set, action not yet `Returned` -> DEISOLATE_CONFIRMING
             (awaiting IA confirmation).
           - `deisolate_requestor` set, action == `Returned` -> falls back to ACTIVE
             (ready for a fresh de-isolate request).
        4. `isolate_requestor` set (isolation requested but not yet executed):
           - `isolate_issuing_action == Approved` -> PENDING (awaiting isolator execution).
           - action not yet `Returned` -> ISOLATE_CONFIRMING (awaiting IA confirmation).
           - action == `Returned` -> falls through to the approval-chain status below
             (ready for a fresh isolate request).
        5. Otherwise -> whatever `getApprovalStatus()` reports (Requested/Returned/Approved).
        """
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

    __backgroundColors = {
        Types.MECHANICAL: QColor( 20,  20,  20, 200),  # near-black
        Types.ELECTRICAL: QColor(200, 165,   0, 200),  # yellow
        Types.SELF:       QColor( 30, 160, 100, 200),  # green
        Types.OTHER:      QColor(150, 150, 150, 150),  # neutral gray
    }

    __foregroundColors = {
        Types.MECHANICAL: QColor('white'),
        Types.ELECTRICAL: QColor('black'),
        Types.SELF:       QColor('black'),
        Types.OTHER:      QColor('black'),
    }

    # PSIC overrides the type-based color while checked - same red the old
    # `Protective System` type used before it was replaced by is_psic.
    __PSIC_BACKGROUND_COLOR = QColor(200, 30, 30, 200)
    __PSIC_FOREGROUND_COLOR = QColor('black')

    @staticmethod
    def backgroundColorForType(certType: Types, isPsic: bool = False):
        """Return the row/tab background color for a given IC type, overridden to
        the PSIC red whenever `isPsic` is set. Unknown types fall back to OTHER's color."""
        if isPsic:
            return IC.__PSIC_BACKGROUND_COLOR
        return IC.__backgroundColors.get(certType) or IC.__backgroundColors.get(IC.Types.OTHER)

    @staticmethod
    def foregroundColorForType(certType: Types, isPsic: bool = False):
        """Return the row/tab foreground (text) color for a given IC type, overridden
        to the PSIC foreground whenever `isPsic` is set. Unknown types fall back to OTHER's color."""
        if isPsic:
            return IC.__PSIC_FOREGROUND_COLOR
        return IC.__foregroundColors.get(certType) or IC.__foregroundColors.get(IC.Types.OTHER)

    @staticmethod
    def colorForItemState(state) -> QColor:
        """Return the highlight color for an isolation item's state: red for OPEN,
        green for CLOSE, gray otherwise."""
        if state == IC.IsolationItem.States.OPEN:
            return QColor('red')
        if state == IC.IsolationItem.States.CLOSE:
            return QColor('green')
        return QColor('gray')

    def backgroundColor(self):
        """Return this IC's own row/tab background color, per its type and `is_psic` flag."""
        return IC.backgroundColorForType(self.type, self.is_psic)

    def foregroundColor(self):
        """Return this IC's own row/tab foreground color, per its type and `is_psic` flag."""
        return IC.foregroundColorForType(self.type, self.is_psic)

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
        from models.PTW import PTW
        return ptw is not None and ptw.approval_status == PTW.ApprovalStatus.APPROVED and ptw.running_status == PTW.RunningStatus.NOT_RUNNING

    def canUnlinkPTW(self, ptw) -> bool:
        """Reverse of canLinkPTW: this IC must still be short of physically isolated -
        not yet ACTIVE, and not winding down (SANCTIONED/DEISOLATE_CONFIRMING/CLOSING/
        CLOSED) - and the target PTW must be approved but not yet running, or fully
        held (accepted, not just a pending hold request still awaiting IA confirm)."""
        if self.getStatus() == IC.Status.ACTIVE or self.isWindingDown():
            return False
        from models.PTW import PTW
        if ptw is None:
            return False
        return (
            (ptw.approval_status == PTW.ApprovalStatus.APPROVED and ptw.running_status == PTW.RunningStatus.NOT_RUNNING)
            or ptw.running_status == PTW.RunningStatus.HELD
        )

    def linkPTW(self, ptwId):
        """Link the given PTW id to this IC: un-hold it if held, then add it to
        `linked_ptws` if not already present."""
        ptwId = str(ptwId)
        try:
            self.held_by.remove(ptwId)
        except ValueError:
            pass
        if ptwId not in self.linked_ptws:
            self.linked_ptws.append(ptwId)
