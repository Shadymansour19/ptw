from datetime import datetime
import enum
from typing import Iterable
from types import SimpleNamespace
from GlobalData import globalData
from User import UserRoles


class RiskItem:
    def __init__(self, hazard: str = None, effect: str = None, free_analysis: str = None, ctrl: str = None, ctrl_analysis: str = None, eval: str = None):
        self.hazard = hazard
        self.effect = effect
        self.free_analysis = free_analysis
        self.ctrl = ctrl
        self.ctrl_analysis = ctrl_analysis
        self.eval = eval
    
    def setAll(self, data: dict):
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except Exception as e:
                    pass
        return self
    

class RiskAssessment:
    def __init__(self, title: str = None, date: str = None, risks: Iterable = None):
        self.title = title
        self.date = date
        self.risks = list(risks) if risks is not None else []
    
    def setAll(self, data: dict):
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    if k == 'risks':
                        self.risks = [RiskItem().setAll(riskDict) for riskDict in v]
                    else:
                        setattr(self, k, v)
                except Exception as e:
                    pass
        return self
    
    def addRiskItem(self, riskItem):
        self.risks.append(riskItem)
        return self
    

class Attachment:
    def __init__(self, localPath: str = '', remoteName: str = '', uploaded: bool = False):
        self.localPath  = localPath
        self.remoteName = remoteName
        self.uploaded   = uploaded

    def __str__(self):
        return f'localPath: {self.localPath}, remoteName: {self.remoteName}, uploaded: {self.uploaded}'


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


class PTWData:
    class Types(enum.StrEnum):
        CW = 'Cold'
        SP = 'Spark'
        HT = 'Hot'
        HC = 'HydroCarbon'
        EX = 'Excavation'
        CS = 'Confined Space'

    class AreaClasses(enum.StrEnum):
        HAZ = 'Hazard'
        NHZ = 'Non-Hazard'

    class Locations(enum.StrEnum):
        PHVII  = 'Phase VII'
        PHV    = 'Phase V'
        SCARAB = 'Scarab'
        SIMIAN = 'Simian'

    class ApprovalActions(enum.StrEnum):
        APPROVED = 'Approved'
        RETURNED = 'Returned'
        REJECTED = 'Rejected'

    class ApprovalStatus(enum.StrEnum):
        UNDER_REVIEW = 'Under Review'
        APPROVED = 'Approved'
        RETURNED = 'Returned'
        REJECTED = 'Rejected'
    
    class RunningStatus(enum.StrEnum):
        NOT_RUNNING = 'Not Running'
        WAITING_RUN_CONFIRM = 'Waiting Run Confirm'
        RUNNING = 'Running'
        WAITING_CLS_CONFIRM = 'Waiting Close Confirm'
        CLOSED = 'Closed'
        WAITING_HLD_CONFIRM = 'Waiting Hold Confirm'
        HELD = 'Held'
        ARCHIVED = 'Archived'
    
    class Approval:
        def __init__(self, action = None, username: str = None, timestamp: str = None, comment: str = None):
            self.action = action
            self.username = username
            self.timestamp = timestamp
            self.comment = comment

        def setAll(self, data: dict):
            for k,v in data.items():
                if hasattr(self, k):
                    try:
                        setattr(self, k, v)
                    except Exception as e:
                        pass
            return self
            
        def __str__(self):
            user = globalData.allUsers[self.username]
            return f"{self.action} by {user.getRole()} {user.getName()} at {self.timestamp}"
        

    def __init__(self, data: dict = {}):
        self.id : str = data.get('id')
        self.type : str = data.get('type')
        self.date : str = datetime.now().strftime("%d/%m/%Y")
        self.location : str = data.get('location')
        self.equipment : str = data.get('equipment')
        self.area_class : str = data.get('area_class')
        self.department : str = data.get('department')
        self.description : str = data.get('description')
        self.requestor : str = data.get('requestor')
        self.performing : str = data.get('performing')
        self.issuing : str = data.get('issuing')
        self.performing_timestamp : str = data.get('performing_timestamp')
        self.issuing_timestamp : str = data.get('issuing_timestamp')
        self.close_performing : str = data.get('close_performing')
        self.close_issuing : str = data.get('close_issuing')
        self.close_performing_timestamp : str = data.get('close_performing_timestamp')
        self.close_issuing_timestamp : str = data.get('close_issuing_timestamp')
        self.hold_performing: str = data.get('hold_performing')
        self.hold_performing_timestamp: str = data.get('hold_performing_timestamp')
        self.hold_issuing: str = data.get('hold_issuing')
        self.hold_issuing_timestamp: str = data.get('hold_issuing_timestamp')
        self.keep_isolations : list[str] = data.get('keep_isolations', [])
        self.miwi : str = data.get('miwi')
        self.mos : str = data.get('mos')
        self.attachs : list[str] = data.get('attachs', [])
        self.tools : list[str] = data.get('tools', [])
        self.isolations : list[Isolation] = [Isolation().setAll(iso) for iso in data.get('isolations', [])]
        self.hazards : list[str] = data.get('hazards', [])
        self.controls : list[str] = data.get('controls', [])
        self.risks : list[str] = data.get('risks', [])
        self.approvals : list[PTWData.Approval] = [PTWData.Approval().setAll(approval) for approval in data.get('approvals', [])]
        self.approval_status : PTWData.ApprovalStatus = data.get('approval_status') or PTWData.ApprovalStatus.UNDER_REVIEW
        self.running_status : PTWData.RunningStatus = data.get('running_status') or PTWData.RunningStatus.NOT_RUNNING
        self.prev_running_status : PTWData.RunningStatus = data.get('prev_running_status') or PTWData.RunningStatus.NOT_RUNNING
        self.__updateStatus()
    
    def setAll(self, data: dict = {}, namespace : SimpleNamespace = None):
        if namespace:
            self.__dict__.update(vars(namespace))
            self.approvals = [PTWData.Approval().setAll(approval.__dict__) for approval in self.approvals]
            self.isolations = [Isolation().setAll(iso.__dict__) for iso in self.isolations]
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    if k == 'approvals':
                        self.approvals = [PTWData.Approval().setAll(approval) for approval in v]
                    elif k == 'isolations':
                        self.isolations = [Isolation().setAll(iso) for iso in v]
                    else:
                        setattr(self, k, v)
                except Exception as e:
                    pass
        self.__updateStatus()
        return self
    
    def setId(self, id: int):
        self.id = id
        return self
    
    def setType(self, type: Types):
        self.type = type
        return self
    
    def setLocation(self, location: str):
        self.location = location
        return self
    
    def setEquipment(self, equipment: str):
        self.equipment = equipment
        return self
    
    def setAreaClass(self, areaClass: AreaClasses):
        self.area_class = areaClass
        return self
    
    def setDepartment(self, department: str):
        self.department = department
        return self
    
    def setDescription(self, description: str):
        self.description = description
        return self
    
    def setDate(self, date: str):
        self.date = date
        return self
    
    def setRequestor(self, requestor: str):
        self.requestor = requestor
        return self
    
    def setPerforming(self, performing: str):
        self.performing = performing
        return self

    def setMiwi(self, miwi: str):
        self.miwi = miwi
        return self
    
    def setMos(self, mos: str):
        self.mos = mos
        return self
    
    def addIsolation(self, isolation: Isolation):
        self.isolations.append(isolation)
        return self
    
    def addHazard(self, hazard: str):
        self.hazards.append(hazard)
        return self
    
    def addTool(self, tool: str):
        self.tools.append(tool)
        return self
    
    def addControl(self, control: str):
        self.controls.append(control)
        return self

    def addRisk(self, risk: str):
        self.risks.append(risk)
        return self

    def __str__(self):
        return f"PTW #{self.id} ({self.type}) - {self.department} - {self.requestor} - {self.location} - {self.area_class} - {self.equipment}\nDescription: {self.description}"
    
    def validate(self) -> str:
        for key, field in [
            ('id', self.id),
            ('type', self.type),
            ('requestor', self.requestor),
            ('department', self.department),
            ('location', self.location),
            ('area_class', self.area_class),
            ('equipment', self.equipment),
            ('description', self.description)
        ]:
            if field == '':
                return "{} cannot be empty".format(key.capitalize())
        if not (self.mos or self.miwi):
            return "Must have either MOS or MIWI"
        for required in self.requiredAttachs():
            if required not in self.attachs:
                return "Missing required attachment: {}".format(required)
        return None
    
    def requiredAttachs(self) -> list[str]:
        docs = []
        if 'Power Tools' in self.tools:
            docs.append('Power Tool Checklist')
        if 'Working at Height' in self.hazards:
            docs.append('Working at Height Medical Certificates')
        if 'Confined Space' in self.hazards:
            docs.append('Confined Space Medical Certificates')
        return docs
    
    def requiredDocsToPrint(self) -> list[str]:
        docs = ['toolbox', 'audit']
        if 'Initial Gas Test' in self.controls:
            docs.append('gas-test')
        return docs
    
    def updateApprovals(self, approval):
        self.approvals.append(approval)
        self.__updateStatus()

    def clearApprovals(self):
        self.approvals = []
        self.performing = None
        self.issuing = None
        self.performing_timestamp = None
        self.issuing_timestamp = None
        self.hold_performing = None
        self.hold_issuing = None
        self.hold_performing_timestamp = None
        self.hold_issuing_timestamp = None
        self.close_performing = None
        self.close_issuing = None
        self.close_performing_timestamp = None
        self.close_issuing_timestamp = None
        self.approval_status = PTWData.ApprovalStatus.UNDER_REVIEW
        self.running_status = PTWData.RunningStatus.NOT_RUNNING
        self.prev_running_status = PTWData.RunningStatus.NOT_RUNNING
        return self
    
    def requiredApprovers(self):
        requiredApprovers = [UserRoles.COORDINATOR, UserRoles.ISSUING, UserRoles.SAFETY]
        if self.type == PTWData.Types.HT or any(isolation.type == Isolation.Types.PROTECTIVE for isolation in self.isolations):
            requiredApprovers.extend([UserRoles.PDH, UserRoles.PGM, UserRoles.SOD, UserRoles.DFGM])
        return requiredApprovers
        
    def __updateStatus(self):
        self.__updateApprovalStatus()
        self.__updateRunningStatus()
    
    def __updateRunningStatus(self):
        if self.approval_status != PTWData.ApprovalStatus.APPROVED:
            self.running_status = PTWData.RunningStatus.NOT_RUNNING
            return
        
    def __updateApprovalStatus(self):
        if len(self.approvals) == 0:
            self.approval_status = PTWData.ApprovalStatus.UNDER_REVIEW
            return
        # elif any(approval.action == PTWData.ApprovalActions.REJECTED for approval in self.approvals):
        elif self.approvals[-1].action != PTWData.ApprovalActions.APPROVED:
            self.approval_status = self.approvals[-1].action
            return
        
        approvers = set([globalData.allUsers[approval.username].getRole() for approval in self.approvals])
        
        if approvers >= set(self.requiredApprovers()):
            self.approval_status = PTWData.ApprovalStatus.APPROVED
        else:
            self.approval_status = PTWData.ApprovalStatus.UNDER_REVIEW

    def getApprovalStatus(self, role = None):
        if role:
            prvRole = None
            allRoles = list(UserRoles)
            idx = allRoles.index(role)
            if idx > 1:
                prvRole = allRoles[idx-1]
            for approval in self.approvals[::-1]:
                if globalData.allUsers[approval.username].getRole() == role:
                    return approval.action
            if prvRole == None:
                return PTWData.ApprovalStatus.UNDER_REVIEW
            for approval in self.approvals[::-1]:
                if globalData.allUsers[approval.username].getRole() == prvRole:
                    return PTWData.ApprovalStatus.UNDER_REVIEW if approval.action == PTWData.ApprovalStatus.APPROVED else approval.action
            return None
        return self.approval_status
