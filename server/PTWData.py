from datetime import datetime
import enum
from typing import Iterable
from types import SimpleNamespace
from GlobalData import globalData
from User import UserRoles, UserDepartments
from Isolation import Isolation


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
    def __init__(self, title: str = None, date: str = None, risks: Iterable = None, ptw_id: int = None):
        self.title = title
        self.date = date
        self.ptw_id = ptw_id
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

    class Approver:
        def __init__(self, role: 'UserRoles', department: 'UserDepartments' = None):
            self.role = role
            self.department = department

        def matchesRoleDept(self, role, department) -> bool:
            return role == self.role and (self.department is None or self.department == department)

        def matchesUser(self, user) -> bool:
            return user is not None and self.matchesRoleDept(user.getRole(), user.getDepartment())

        def __eq__(self, other):
            return isinstance(other, PTWData.Approver) and self.role == other.role and self.department == other.department

        def __hash__(self):
            return hash((self.role, self.department))

        def __str__(self):
            if self.role == UserRoles.USER:
                return str(self.department) if self.department else str(self.role)
            return str(self.role)

    class RunCycle:
        """One pass through the running state machine: a PA run request, the IA's response,
        and — once running — the PA's hold/close request and the IA's response to that.
        A new RunCycle is appended each time a run is requested (including resuming from HELD);
        stop_* fields are filled in later, in place, as the same cycle progresses."""

        class StopTypes(enum.StrEnum):
            HOLD = 'Hold'
            CLOSE = 'Close'

        class Actions(enum.StrEnum):
            APPROVED = 'Approved'
            REJECTED = 'Rejected'

        def __init__(self, run_pa: str = None, run_pa_timestamp: str = None,
                     run_ia: str = None, run_ia_action: str = None, run_ia_comment: str = None, run_ia_timestamp: str = None,
                     stop_pa: str = None, stop_pa_request: str = None, stop_pa_comment: str = None, stop_pa_timestamp: str = None,
                     stop_ia: str = None, stop_ia_action: str = None, stop_ia_comment: str = None, stop_ia_timestamp: str = None,
                     held_ics: list = None):
            self.run_pa = run_pa
            self.run_pa_timestamp = run_pa_timestamp
            self.run_ia = run_ia
            self.run_ia_action = run_ia_action
            self.run_ia_comment = run_ia_comment
            self.run_ia_timestamp = run_ia_timestamp
            self.stop_pa = stop_pa
            self.stop_pa_request = stop_pa_request
            self.stop_pa_comment = stop_pa_comment
            self.stop_pa_timestamp = stop_pa_timestamp
            self.stop_ia = stop_ia
            self.stop_ia_action = stop_ia_action
            self.stop_ia_comment = stop_ia_comment
            self.stop_ia_timestamp = stop_ia_timestamp
            self.held_ics = list(held_ics) if held_ics else []

        def setAll(self, data: dict):
            for k,v in data.items():
                if hasattr(self, k):
                    try:
                        setattr(self, k, v)
                    except Exception as e:
                        pass
            return self

        def isOpen(self) -> bool:
            """Still awaiting further action: the run wasn't rejected, and any stop request hasn't been approved."""
            return self.run_ia_action != PTWData.RunCycle.Actions.REJECTED and self.stop_ia_action != PTWData.RunCycle.Actions.APPROVED


    def __init__(self, data: dict = {}):
        self.id : str = data.get('id')
        self.type : str = data.get('type')
        self.request_date : str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.location : str = data.get('location')
        self.equipment : str = data.get('equipment')
        self.area_class : str = data.get('area_class')
        self.department : str = data.get('department')
        self.description : str = data.get('description')
        self.fast_track : bool = data.get('fast_track', False)
        self.requestor : str = data.get('requestor')
        self.run_cycles : list[PTWData.RunCycle] = [PTWData.RunCycle().setAll(cycle) for cycle in data.get('run_cycles', [])]
        self.miwi : str = data.get('miwi')
        self.mos : str = data.get('mos')
        # Not a `ptws` column — the ptw-{id}-attachments/ folder is the only source of
        # truth for what's actually attached. This only ever holds the client's staged,
        # not-yet-uploaded filenames for validate()'s required-attachment check.
        self.attachs : list[str] = data.get('attachs', [])
        self.tools : list[str] = data.get('tools', [])
        self.isolations : list[Isolation] = [Isolation().setAll(iso) for iso in data.get('isolations', [])]
        self.hazards : list[str] = data.get('hazards', [])
        self.controls : list[str] = data.get('controls', [])
        self.risks : list[str] = data.get('risks', [])
        self.linked_ics : list[str] = data.get('linked_ics', [])
        self.approvals : list[PTWData.Approval] = [PTWData.Approval().setAll(approval) for approval in data.get('approvals', [])]
        # Not a `ptws` column either — __updateStatus() below recomputes this from
        # `approvals` every time, so persisting it would just be a stale duplicate.
        self.approval_status : PTWData.ApprovalStatus = data.get('approval_status') or PTWData.ApprovalStatus.UNDER_REVIEW
        self.running_status : PTWData.RunningStatus = data.get('running_status') or PTWData.RunningStatus.NOT_RUNNING
        self.prev_running_status : PTWData.RunningStatus = data.get('prev_running_status') or PTWData.RunningStatus.NOT_RUNNING
        self.__updateStatus()
    
    def setAll(self, data: dict = {}, namespace : SimpleNamespace = None):
        if namespace:
            self.__dict__.update(vars(namespace))
            self.approvals = [PTWData.Approval().setAll(approval.__dict__) for approval in self.approvals]
            self.isolations = [Isolation().setAll(iso.__dict__) for iso in self.isolations]
            self.run_cycles = [PTWData.RunCycle().setAll(cycle.__dict__) for cycle in self.run_cycles]
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    if k == 'approvals':
                        self.approvals = [PTWData.Approval().setAll(approval) for approval in v]
                    elif k == 'isolations':
                        self.isolations = [Isolation().setAll(iso) for iso in v]
                    elif k == 'run_cycles':
                        self.run_cycles = [PTWData.RunCycle().setAll(cycle) for cycle in v]
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
    
    def setMiwi(self, miwi: str):
        self.miwi = miwi
        return self
    
    def setMos(self, mos: str):
        self.mos = mos
        return self

    def setFastTrack(self, fast_track: bool):
        self.fast_track = fast_track
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
                    # elif requirement.type == PTWData.Requirement.Types.RISK and requirement.description not in self.risks:
                    #     return "'{}' requires risk assessment '{}'".format(item, requirement.description)

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
        self.run_cycles = []
        self.approval_status = PTWData.ApprovalStatus.UNDER_REVIEW
        self.running_status = PTWData.RunningStatus.NOT_RUNNING
        self.prev_running_status = PTWData.RunningStatus.NOT_RUNNING
        return self

    def lastRunCycle(self) -> 'PTWData.RunCycle':
        """The most recent run cycle regardless of whether it's still open, or None if the PTW never ran."""
        return self.run_cycles[-1] if self.run_cycles else None

    def currentRunCycle(self) -> 'PTWData.RunCycle':
        """The run cycle still in progress (run not rejected, stop not yet approved), or None."""
        cycle = self.lastRunCycle()
        return cycle if cycle is not None and cycle.isOpen() else None

    def operativeRunCycle(self) -> 'PTWData.RunCycle':
        """Most recent cycle that actually reached RUNNING, skipping any trailing cycle(s) whose
        run request was rejected — those never changed running/isolation state, so e.g. rejecting
        a resume-from-HELD attempt must not hide the still-relevant data from the cycle that HELD it."""
        for cycle in reversed(self.run_cycles):
            if cycle.run_ia_action == PTWData.RunCycle.Actions.REJECTED:
                continue
            return cycle
        return None

    def getPerforming(self) -> str:
        cycle = self.currentRunCycle()
        return cycle.run_pa if cycle else None

    def getPerformingTimestamp(self) -> str:
        cycle = self.currentRunCycle()
        return cycle.run_pa_timestamp if cycle else None

    def getIssuing(self) -> str:
        cycle = self.currentRunCycle()
        return cycle.run_ia if cycle and cycle.run_ia_action == PTWData.RunCycle.Actions.APPROVED else None

    def getIssuingTimestamp(self) -> str:
        cycle = self.currentRunCycle()
        return cycle.run_ia_timestamp if cycle and cycle.run_ia_action == PTWData.RunCycle.Actions.APPROVED else None

    def getHeldICs(self) -> list[str]:
        cycle = self.operativeRunCycle()
        return cycle.held_ics if cycle else []
    
    def requiredApprovers(self) -> list[list['PTWData.Approver']]:
        requiredApprovers = [
            [PTWData.Approver(UserRoles.COORDINATOR, UserDepartments.PROD)],
        ]
        if self.type == PTWData.Types.EX:
            requiredApprovers.append([
                PTWData.Approver(UserRoles.USER, UserDepartments.MECH),
                PTWData.Approver(UserRoles.USER, UserDepartments.ELEC),
                PTWData.Approver(UserRoles.USER, UserDepartments.INST),
                PTWData.Approver(UserRoles.USER, UserDepartments.TELECOM),
                PTWData.Approver(UserRoles.USER, UserDepartments.TURBO),
                PTWData.Approver(UserRoles.USER, UserDepartments.PROJECT),
                PTWData.Approver(UserRoles.USER, UserDepartments.CVL),
                PTWData.Approver(UserRoles.USER, UserDepartments.CATHODIC_PROTECTION),
            ])
        requiredApprovers.append([
            PTWData.Approver(UserRoles.ISSUING, UserDepartments.PROD),
            PTWData.Approver(UserRoles.SAFETY, UserDepartments.SAFETY),
        ])
        if self.type in [PTWData.Types.HT, PTWData.Types.CS]:
            requiredApprovers.extend([
                [PTWData.Approver(UserRoles.PGM, UserDepartments.PROD)],
                [PTWData.Approver(UserRoles.DFGM)],
            ])
        return requiredApprovers

    def _stageSatisfied(self, stage: list['PTWData.Approver']) -> bool:
        approvedBy = [globalData.allUsers.get(a.username) for a in self.approvals if a.action == PTWData.ApprovalActions.APPROVED]
        return all(any(approver.matchesUser(user) for user in approvedBy) for approver in stage)

    def _pendingStageIndex(self) -> int:
        """Index of the first not-yet-satisfied stage, or len(stages) if fully approved."""
        stages = self.requiredApprovers()
        for i, stage in enumerate(stages):
            if not self._stageSatisfied(stage):
                return i
        return len(stages)

    def pendingApprovers(self) -> list['PTWData.Approver']:
        """Flattened Approvers still needed, across the current and any later stage."""
        approvedBy = [globalData.allUsers.get(a.username) for a in self.approvals if a.action == PTWData.ApprovalActions.APPROVED]
        stages = self.requiredApprovers()
        return [
            approver
            for stage in stages[self._pendingStageIndex():]
            for approver in stage
            if not any(approver.matchesUser(user) for user in approvedBy)
        ]

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
        elif any(approval.action == PTWData.ApprovalActions.RETURNED for approval in self.approvals):
            self.approval_status = PTWData.ApprovalStatus.RETURNED
        elif self._pendingStageIndex() >= len(self.requiredApprovers()):
            self.approval_status = PTWData.ApprovalStatus.APPROVED
        else:
            self.approval_status = PTWData.ApprovalStatus.UNDER_REVIEW

    def getApprovalStatus(self, role = None, department = None):
        if role is None:
            return self.approval_status

        for approval in self.approvals[::-1]:
            user = globalData.allUsers.get(approval.username)
            if user is not None and user.getRole() == role and user.getDepartment() == department:
                return approval.action

        stages = self.requiredApprovers()
        pending = self._pendingStageIndex()
        if pending < len(stages) and any(approver.matchesRoleDept(role, department) for approver in stages[pending]):
            return PTWData.ApprovalStatus.UNDER_REVIEW
        return None

    def canLinkIC(self) -> bool:
        """The PTW-side half of IC.canLinkPTW(ptw): this PTW must be approved, and not
        yet running/held/closed (or requested to be)."""
        return self.approval_status == PTWData.ApprovalStatus.APPROVED and self.running_status == PTWData.RunningStatus.NOT_RUNNING
