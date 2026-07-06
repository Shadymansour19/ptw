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
    class Requirement:
        class Types(enum.StrEnum):
            TOOL = enum.auto()
            HAZARD = enum.auto()
            CONTROL = enum.auto()
            ISOLATION = enum.auto()
            RISK = enum.auto()
            ATTACH = enum.auto()
            DOC = enum.auto()
        
        def __init__(self, type: 'PTWData.Requirement.Types', description: str):
            self.type = type
            self.description = description
    
    class CheckBox:
        def __init__(self, title: str, isRequired=None, isRestricted=None, requirements: list['PTWData.Requirement'] = None):
            self.title = title
            self._isRequired = isRequired or (lambda ptwType: False)
            self._isRestricted = isRestricted or (lambda ptwType: False)
            self.requirements = requirements or []

        def isRequired(self, ptwType: 'PTWData.Types') -> bool:
            return self._isRequired(ptwType)

        def isRestricted(self, ptwType: 'PTWData.Types') -> bool:
            return self._isRestricted(ptwType)

        def __str__(self):
            return self.title
    
    ALL_TOOLS: dict[str, CheckBox] = {
        'Hand Tools': CheckBox(
            title='Hand Tools', 
            requirements=[
                Requirement(type=Requirement.Types.RISK, description='Use of Hand Tools'), 
            ], 
        ),
        'Power Tools': CheckBox(
            title='Power Tools', 
            requirements=[
                Requirement(type=Requirement.Types.RISK, description='Use of Power Tools'), 
                Requirement(type=Requirement.Types.ATTACH, description='Power Tools Checklist'), 
            ], 
            isRestricted=lambda ptwType: ptwType in [PTWData.Types.CW, PTWData.Types.CS], 
        ),
        'Non-Ex Tools': CheckBox(
            title='Non-Ex Tools', 
            requirements=[
                Requirement(type=Requirement.Types.RISK, description='Use of Non-Ex Tools'), 
            ], 
            isRestricted=lambda ptwType: ptwType in [PTWData.Types.CW], 
        ),
        'Test Tools': CheckBox(
            title='Test Tools', 
        ),
        'Pneumatic Tools': CheckBox(
            title='Pneumatic Tools', 
            requirements=[
                Requirement(type=Requirement.Types.RISK, description='Use of Pneumatic Tools'), 
            ], 
        ),
        'Camera': CheckBox(
            title='Camera', 
            requirements=[
                Requirement(type=Requirement.Types.RISK, description='Use of Camera'), 
            ], 
        ),
        'Hydraulic Tools': CheckBox(
            title='Hydraulic Tools', 
            requirements=[
                Requirement(type=Requirement.Types.RISK, description='Use of Hydraulic Tools'), 
            ], 
        ),
        'Grit Blasting': CheckBox(
            title='Grit Blasting', 
        ),
    }

    ALL_HAZARDS: dict[str, CheckBox] = {
        'Confined Space': CheckBox(
            title='Confined Space', 
            requirements=[
                Requirement(type=Requirement.Types.ATTACH, description='Confined Space Medical Checks'), 
                Requirement(type=Requirement.Types.DOC, description='Confined Space IOGP'), 
            ], 
        ), 
        'Electrical / Mechanical Spark': CheckBox(
            title='Electrical / Mechanical Spark', 
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Initial Gas Test'), 
                Requirement(type=Requirement.Types.CONTROL, description='Continuous Gas Test'), 
            ], 
            isRequired=lambda ptwType: ptwType in [PTWData.Types.SP], 
            isRestricted=lambda ptwType: ptwType in [PTWData.Types.CW], 
        ),
        'Static Electricity': CheckBox(
            title='Static Electricity', 
        ),
        'Hazardous Substance': CheckBox(
            title='Hazardous Substance', 
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='MSDS'), 
            ], 
        ),
        'Flammable Material': CheckBox(
            title='Flammable Material', 
        ),
        'Trapping / Impact Injuries': CheckBox(
            title='Trapping / Impact Injuries', 
        ),
        'Overside Working': CheckBox(
            title='Overside Working', 
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Close Standby (overside)'), 
            ], 
        ),
        'Gas Cylinders': CheckBox(
            title='Gas Cylinders', 
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='MSDS'), 
            ], 
        ),
        'Pressurized Pipes / Hoses': CheckBox(
            title='Pressurized Pipes / Hoses'
        ),
        'Stored Energy': CheckBox(
            title='Stored Energy'
        ),
        'Safety Device Overridden': CheckBox(
            title='Safety Device Overridden'
        ),
        'Process Trip / Upset': CheckBox(
            title='Process Trip / Upset'
        ),
        'SIMOPS': CheckBox(
            title='SIMOPS'
        ),
        'Moving Vehicle': CheckBox(
            title='Moving Vehicle'
        ),
        'Temp. Equipment': CheckBox(
            title='Temp. Equipment'
        ),
        'Inadequate Lighting': CheckBox(
            title='Inadequate Lighting',
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Additional Lighting'), 
            ],
        ),
        'Heavy / Complex Lifts': CheckBox(
            title='Heavy / Complex Lifts',
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Lifting Plan'), 
            ],
        ),
        'Extreme Temperature': CheckBox(
            title='Extreme Temperature'
        ),
        'Excavation': CheckBox(
            title='Excavation'
        ),
        'Rotating Machinery': CheckBox(
            title='Rotating Machinery'
        ),
        'Noise': CheckBox(
            title='Noise', 
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Hearing Protection'),
            ],
        ),
        'Vibration': CheckBox(
            title='Vibration'
        ),
        'Dropped Objects': CheckBox(
            title='Dropped Objects',
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Housekeeping'), 
                Requirement(type=Requirement.Types.CONTROL, description='Signs / Barriers'), 
            ],
        ),
        'Scaffolding': CheckBox(
            title='Scaffolding',
            requirements=[
                Requirement(type=Requirement.Types.HAZARD, description='Working at Height'), 
            ],
        ), 
        'Working at Height': CheckBox(
            title='Working at Height',
            requirements=[
                Requirement(type=Requirement.Types.ATTACH, description='Working at Height Medical Checks'), 
                Requirement(type=Requirement.Types.DOC, description='Working at Height IOGP'), 
            ],
        ), 
        'Slips / Trips': CheckBox(
            title='Slips / Trips', 
        ),
        'Access / Egress': CheckBox(
            title='Access / Egress',
            requirements=[
                Requirement(type=Requirement.Types.CONTROL, description='Safe Access / Egress'), 
            ],
        ),
    }

    ALL_CONTROLS: dict[str, CheckBox] = {
        'Initial Gas Test': CheckBox(
            title='Initial Gas Test'
        ),
        'Continuous Gas Test': CheckBox(
            title='Continuous Gas Test', 
            requirements=[
                Requirement(type=Requirement.Types.DOC, description='Atmospheric Gas Test'),
            ],
        ),
        'Close Standby (overside)': CheckBox(
            title='Close Standby (overside)', 
        ),
        'Portable Fire Extinguisher': CheckBox(
            title='Portable Fire Extinguisher', 
        ),
        'Equipment Earthing': CheckBox(
            title='Equipment Earthing', 
        ),
        'IS/Ex Rated Equipment': CheckBox(
            title='IS/Ex Rated Equipment', 
        ),
        'Drained': CheckBox(
            title='Drained', 
        ),
        'Vented': CheckBox(
            title='Vented', 
        ),
        'Flushed': CheckBox(
            title='Flushed', 
        ),
        'Purged': CheckBox(
            title='Purged', 
        ),
        'MSDS': CheckBox(
            title='MSDS', 
            requirements=[
                Requirement(type=Requirement.Types.ATTACH, description='MSDS'), 
            ],
        ), 
        'Rescue Plan': CheckBox(
            title='Rescue Plan', 
            requirements=[
                Requirement(type=Requirement.Types.ATTACH, description='Rescue Plan'), 
            ],
        ), 
        'Additional Lighting': CheckBox(
            title='Additional Lighting', 
        ),
        # 'Secure Loose Objects':         [],
        'Housekeeping': CheckBox(
            title='Housekeeping', 
        ),
        'Manual Handing': CheckBox(
            title='Manual Handing', 
        ),
        'Lifting Plan': CheckBox(
            title='Lifting Plan',
            requirements=[ 
                Requirement(type=Requirement.Types.ATTACH, description='Lifting Plan'), 
            ],
        ), 
        'Working at Height Equipment': CheckBox(
            title='Working at Height Equipment', 
        ),
        'Vendor': CheckBox(
            title='Vendor', 
        ),
        'Signs / Barriers': CheckBox(
            title='Signs / Barriers', 
        ),
        'Safe Access / Egress': CheckBox(
            title='Safe Access / Egress', 
        ),
        'Radios': CheckBox(
            title='Radios', 
        ),
        None: CheckBox(title=None), 
        'Fire Retardant Coverall': CheckBox(
            title='Fire Retardant Coverall', 
        ),
        'Breathing Apparatus': CheckBox(
            title='Breathing Apparatus', 
        ),
        'Respirator': CheckBox(
            title='Respirator', 
        ),
        'Safety Harness': CheckBox(
            title='Safety Harness', 
        ),
        'Dust Mask': CheckBox(
            title='Dust Mask', 
        ),
        'Hearing Protection': CheckBox(
            title='Hearing Protection', 
        ),
        'Face Shield': CheckBox(
            title='Face Shield', 
        ),
    }


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

    class ApprovalStatus(enum.StrEnum):
        UNDER_REVIEW = 'Under Review'
        APPROVED = 'Approved'
        RETURNED = 'Returned'
    
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
            user = globalData.allUsers.get(self.username)
            if user is None:
                return f"{self.action} by [deleted user: {self.username}] at {self.timestamp}"
            return f"{self.action} by {user.getRole()} {user.getName()} at {self.timestamp}"
        

    def __init__(self, data: dict = {}):
        self.id : str = data.get('id')
        self.type : str = data.get('type')
        self.request_date : str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
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
        self.request_date = date
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
        if isolation not in self.isolations:
            self.isolations.append(isolation)
        return self
    
    def addHazard(self, hazard: str):
        if hazard not in self.hazards:
            self.hazards.append(hazard)
        return self
    
    def addTool(self, tool: str):
        if tool not in self.tools:
            self.tools.append(tool)
        return self
    
    def addControl(self, control: str):
        if control not in self.controls:
            self.controls.append(control)
        return self

    def removeTool(self, tool: str):
        if tool in self.tools:
            self.tools.remove(tool)
        return self
    
    def removeControl(self, control: str):
        if control in self.controls:
            self.controls.remove(control)
        return self
    
    def removeHazard(self, hazard: str):
        if hazard in self.hazards:
            self.hazards.remove(hazard)
        return self

    def addRisk(self, risk: str):
        if risk not in self.risks:
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

        for category, allCheckBoxes, selected in [
            ('Tool', PTWData.ALL_TOOLS, self.tools),
            ('Hazard', PTWData.ALL_HAZARDS, self.hazards),
            ('Control', PTWData.ALL_CONTROLS, self.controls),
        ]:
            for title, checkBox in allCheckBoxes.items():
                if checkBox.isRequired(self.type) and title not in selected:
                    return "{} '{}' is required for {} permits".format(category, title, self.type)
                if checkBox.isRestricted(self.type) and title in selected:
                    return "{} '{}' is not allowed for {} permits".format(category, title, self.type)
            for item in selected:
                checkBox = allCheckBoxes.get(item)
                if checkBox is None:
                    continue
                for requirement in checkBox.requirements:
                    if requirement.type == PTWData.Requirement.Types.TOOL and requirement.description not in self.tools:
                        return "'{}' requires tool '{}'".format(item, requirement.description)
                    elif requirement.type == PTWData.Requirement.Types.HAZARD and requirement.description not in self.hazards:
                        return "'{}' requires hazard '{}'".format(item, requirement.description)
                    elif requirement.type == PTWData.Requirement.Types.CONTROL and requirement.description not in self.controls:
                        return "'{}' requires control '{}'".format(item, requirement.description)
                    elif requirement.type == PTWData.Requirement.Types.RISK and requirement.description not in self.risks:
                        return "'{}' requires risk assessment '{}'".format(item, requirement.description)

        for required in self.requiredAttachs():
            if not any(attach.startswith(required + '.') for attach in self.attachs):
                return "Missing required attachment: {}".format(required)
        return None
    
    def updateRequirements(self):
        def __handleRequirement(requirement):
            if requirement.type == PTWData.Requirement.Types.TOOL:
                self.addTool(requirement.description)
            elif requirement.type == PTWData.Requirement.Types.CONTROL:
                self.addControl(requirement.description)
            elif requirement.type == PTWData.Requirement.Types.HAZARD:
                self.addHazard(requirement.description)
            elif requirement.type == PTWData.Requirement.Types.RISK:
                self.addRisk(requirement.description)

        for title, checkBox in PTWData.ALL_TOOLS.items():
            if checkBox.isRequired(self.type):
                self.addTool(title)
            elif checkBox.isRestricted(self.type):
                self.removeTool(title)
        
        for title, checkBox in PTWData.ALL_HAZARDS.items():
            if checkBox.isRequired(self.type):
                self.addHazard(title)
            elif checkBox.isRestricted(self.type):
                self.removeHazard(title)
        
        for title, checkBox in PTWData.ALL_CONTROLS.items():
            if checkBox.isRequired(self.type):
                self.addControl(title)
            elif checkBox.isRestricted(self.type):
                self.removeControl(title)
        
        i = 0
        while i < len(self.tools):
            tool = self.tools[i]
            if tool not in PTWData.ALL_TOOLS:
                i += 1
                continue
            for requirement in PTWData.ALL_TOOLS.get(tool).requirements:
                __handleRequirement(requirement)
            i += 1

        i = 0
        while i < len(self.hazards):
            hazard = self.hazards[i]
            if hazard not in PTWData.ALL_HAZARDS:
                i += 1
                continue
            for requirement in PTWData.ALL_HAZARDS.get(hazard).requirements:
                __handleRequirement(requirement)
            i += 1

        i = 0
        while i < len(self.controls):
            ctrl = self.controls[i]
            if ctrl not in PTWData.ALL_CONTROLS:
                i += 1
                continue
            for requirement in PTWData.ALL_CONTROLS.get(ctrl).requirements:
                __handleRequirement(requirement)
            i += 1

    def requiredAttachs(self) -> list[str]:
        docs = []
        for tool in self.tools:
            if tool not in PTWData.ALL_TOOLS:
                continue
            for requirement in PTWData.ALL_TOOLS.get(tool).requirements:
                if requirement.type == PTWData.Requirement.Types.ATTACH:
                    docs.append(requirement.description)
        for ctrl in self.controls:
            if ctrl not in PTWData.ALL_CONTROLS:
                continue
            for requirement in PTWData.ALL_CONTROLS.get(ctrl).requirements:
                if requirement.type == PTWData.Requirement.Types.ATTACH:
                    docs.append(requirement.description)
        for hazard in self.hazards:
            if hazard not in PTWData.ALL_HAZARDS:
                continue
            for requirement in PTWData.ALL_HAZARDS.get(hazard).requirements:
                if requirement.type == PTWData.Requirement.Types.ATTACH:
                    docs.append(requirement.description)
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
        
        approvers = set([globalData.allUsers[approval.username].getRole() for approval in self.approvals if approval.username in globalData.allUsers])
        
        if approvers >= set(self.requiredApprovers()):
            self.approval_status = PTWData.ApprovalStatus.APPROVED
        else:
            self.approval_status = PTWData.ApprovalStatus.UNDER_REVIEW

    def getApprovalStatus(self, role = None):
        if role:
            # Only these roles gate on the previous role's approval; USER/GUEST/ADMIN
            # aren't sequential approvers, so they're never gated (prvRole stays None).
            approvalChain = [UserRoles.COORDINATOR, UserRoles.ISSUING, UserRoles.SAFETY,
                              UserRoles.PDH, UserRoles.PGM, UserRoles.SOD, UserRoles.DFGM, UserRoles.ISOLATOR]
            prvRole = None
            if role in approvalChain:
                idx = approvalChain.index(role)
                if idx > 0:
                    prvRole = approvalChain[idx-1]
            for approval in self.approvals[::-1]:
                user = globalData.allUsers.get(approval.username)
                if user is not None and user.getRole() == role:
                    return approval.action
            if prvRole == None:
                return PTWData.ApprovalStatus.UNDER_REVIEW
            for approval in self.approvals[::-1]:
                user = globalData.allUsers.get(approval.username)
                if user is not None and user.getRole() == prvRole:
                    return PTWData.ApprovalStatus.UNDER_REVIEW if approval.action == PTWData.ApprovalStatus.APPROVED else approval.action
            return None
        return self.approval_status
