import enum
from types import SimpleNamespace
from datetime import datetime


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
        REJECTED   = 'Rejected'
        PENDING    = 'Pending'
        ACTIVE     = 'Active'
        SANCTIONED = 'Sanctioned'
        CLOSED     = 'Closed'

    def __init__(self, data: dict = {}):
        self.id : str = data.get('id')
        self.type : str = data.get('type')
        self.department : str = data.get('department')
        self.location : str = data.get('location')
        self.equipment : str = data.get('equipment')
        self.reason : str = data.get('reason')
        self.items : list[IsolationCertificate.IsolationItem] = [IsolationCertificate.IsolationItem().setAll(iso) for iso in data.get('items', [])]

        # ============== isolation usernames & timestamps =================
        self.isolate_requestor = data.get('isolate_requestor')
        self.isolate_requestor_timestamp = data.get('isolate_requestor_timestamp') or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.isolate_issuing = data.get('isolate_issuing')
        self.isolate_issuing_timestamp = data.get('isolate_issuing_timestamp')
        self.isolate_issuing_action = data.get('isolate_issuing_action', '')
        self.isolate_isolator = data.get('isolate_isolator')
        self.isolate_isolator_timestamp = data.get('isolate_isolator_timestamp')

        # ============== sanction for test usernames & timestamps =================
        self.sanction_requestor = data.get('sanction_requestor')
        self.sanction_requestor_timestamp = data.get('sanction_requestor_timestamp') or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.sanction_issuing = data.get('sanction_issuing')
        self.sanction_issuing_timestamp = data.get('sanction_issuing_timestamp')
        self.sanction_isolator = data.get('sanction_isolator')
        self.sanction_isolator_timestamp = data.get('sanction_isolator_timestamp')

        # ============== re-isolation usernames & timestamps =================
        self.reisolate_requestor = data.get('reisolate_requestor')
        self.reisolate_requestor_timestamp = data.get('reisolate_requestor_timestamp') or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.reisolate_issuing = data.get('reisolate_issuing')
        self.reisolate_issuing_timestamp = data.get('reisolate_issuing_timestamp')
        self.reisolate_isolator = data.get('reisolate_isolator')
        self.reisolate_isolator_timestamp = data.get('reisolate_isolator_timestamp')

        # ============== de-isolation usernames & timestamps =================
        self.deisolate_requestor = data.get('deisolate_requestor')
        self.deisolate_requestor_timestamp = data.get('deisolate_requestor_timestamp') or datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.deisolate_issuing = data.get('deisolate_issuing')
        self.deisolate_issuing_timestamp = data.get('deisolate_issuing_timestamp')
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
        elif data:
            for k, v in data.items():
                if hasattr(self, k):
                    try:
                        setattr(self, k, v)
                    except Exception:
                        pass
        return self

    def __str__(self):
        return f"{self.id} - {self.type} {self.reason if self.reason else ''} {self.primary_ptw}"

    def getStatus(self) -> 'IsolationCertificate.Status':
        if self.deisolate_isolator:
            return self.Status.CLOSED
        if self.sanction_isolator and not self.reisolate_isolator:
            return self.Status.SANCTIONED
        if self.isolate_issuing_action == 'Rejected':
            return self.Status.REJECTED
        if self.isolate_isolator or self.reisolate_isolator:
            return self.Status.ACTIVE
        if self.isolate_issuing_action == 'Approved':
            return self.Status.PENDING
        return self.Status.REQUESTED
