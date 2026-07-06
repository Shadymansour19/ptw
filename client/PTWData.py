from datetime import datetime
import enum
from PyQt6.QtGui import QFont, QColor
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

    ALL_ISOLATIONS: dict[str, Isolation] = {
        'XV-7227A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7227A',  description='MC-A 1nd Stage ASV'), 
        'XV-7227B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7227B',  description='MC-B 1nd Stage ASV'), 
        'XV-7227C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7227C',  description='MC-C 1nd Stage ASV'), 
        'XV-7227D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7227D',  description='MC-D 1nd Stage ASV'), 
        'XV-7227E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7227E',  description='MC-E 1nd Stage ASV'), 
        'XV-7231A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7231A',  description='MC-A 2nd Stage ASV'), 
        'XV-7231B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7231B',  description='MC-B 2nd Stage ASV'), 
        'XV-7231C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7231C',  description='MC-C 2nd Stage ASV'), 
        'XV-7231D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7231D',  description='MC-D 2nd Stage ASV'), 
        'XV-7231E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-7231E',  description='MC-E 2nd Stage ASV'), 
        '1M1':          Isolation(type=Isolation.Types.ELECTRICAL,  tag='1M1',       description='BC-A Enclosure Lighting'),
        'LV-1409E':     Isolation(type=Isolation.Types.SELF,        tag='LV-1409E',  description='LP-B Control Valve'),
        'LV-9935':      Isolation(type=Isolation.Types.OTHER,       tag='LV-9935',   description='FL-A Inlet Valve'),
        'FV-4582A':     Isolation(type=Isolation.Types.OTHER,       tag='FV-4582A',  description='CD-A Separator'),
        'SDV-9928C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-9928C', description='EX-E Flow Transmitter'),
        'XV-3615E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-3615E',  description='UT-C Control Valve'),
        'SDV-6514':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='SDV-6514',  description='FL-A Breaker'),
        'EV-5333':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-5333',   description='IN-A Feeder Panel'),
        'FV-5803E':     Isolation(type=Isolation.Types.OTHER,       tag='FV-5803E',  description='UT-E Pressure Transmitter'),
        'FV-1750E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-1750E',  description='MP-A Level Transmitter'),
        'LV-7227B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-7227B',  description='UT-B Breaker'),
        'EV-4432E':     Isolation(type=Isolation.Types.SELF,        tag='EV-4432E',  description='BC-E Safety Valve'),
        'FT-5010A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-5010A',  description='FL-C Separator'),
        'MOV-6313':     Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-6313',  description='MC-C Feeder Panel'),
        'BDV-2084A':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-2084A', description='UT-B Compressor'),
        'TV-8517A':     Isolation(type=Isolation.Types.SELF,        tag='TV-8517A',  description='HP-B Separator'),
        'FT-5304E':     Isolation(type=Isolation.Types.OTHER,       tag='FT-5304E',  description='FL-E Feeder Panel'),
        'EV-4593A':     Isolation(type=Isolation.Types.OTHER,       tag='EV-4593A',  description='EX-A Outlet Valve'),
        'LV-3504E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-3504E',  description='FL-E Bypass Valve'),
        'TV-7252D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-7252D',  description='IN-C Separator'),
        'XV-2876E':     Isolation(type=Isolation.Types.OTHER,       tag='XV-2876E',  description='MP-C Isolation Valve'),
        'PZV-8123A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-8123A', description='MC-C Heat Exchanger'),
        'PCV-9317':     Isolation(type=Isolation.Types.SELF,        tag='PCV-9317',  description='IN-E Pressure Transmitter'),
        'HV-7126A':     Isolation(type=Isolation.Types.OTHER,       tag='HV-7126A',  description='IN-A Filter'),
        'CV-9005':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-9005',   description='UT-C Level Transmitter'),
        'PSV-4946D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-4946D', description='BC-D Bypass Valve'),
        'FT-3060A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-3060A',  description='IN-B Flow Transmitter'),
        'PT-7932A':     Isolation(type=Isolation.Types.OTHER,       tag='PT-7932A',  description='LP-C Feeder Panel'),
        'EV-8177D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-8177D',  description='BC-B Level Transmitter'),
        'FV-6539':      Isolation(type=Isolation.Types.OTHER,       tag='FV-6539',   description='IN-B Drum'),
        'MOV-1117':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-1117',  description='LP-A Outlet Valve'),
        'CV-2160D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-2160D',  description='MP-D Pressure Transmitter'),
        'FT-3167E':     Isolation(type=Isolation.Types.OTHER,       tag='FT-3167E',  description='CD-D Level Transmitter'),
        'TT-7669A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-7669A',  description='BC-D Breaker'),
        'SV-7735C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-7735C',  description='BC-A Feeder Panel'),
        'CV-2790A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-2790A',  description='LP-E Pump'),
        'HV-7912A':     Isolation(type=Isolation.Types.SELF,        tag='HV-7912A',  description='EX-B Bypass Valve'),
        'HS-2604':      Isolation(type=Isolation.Types.OTHER,       tag='HS-2604',   description='MC-A Level Transmitter'),
        'PCV-7658C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-7658C', description='LP-D Outlet Valve'),
        'PCV-7209':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-7209',  description='MP-D Temp Element'),
        'SV-8973A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-8973A',  description='MP-B Outlet Valve'),
        'LT-9883':      Isolation(type=Isolation.Types.SELF,        tag='LT-9883',   description='MC-A Drum'),
        'TT-9238D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-9238D',  description='MC-E Bypass Valve'),
        'PCV-2122D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PCV-2122D', description='LP-D Isolation Valve'),
        'LT-5033D':     Isolation(type=Isolation.Types.OTHER,       tag='LT-5033D',  description='MC-E Bypass Valve'),
        'SV-9565B':     Isolation(type=Isolation.Types.SELF,        tag='SV-9565B',  description='LP-C Level Transmitter'),
        'BDV-7484A':    Isolation(type=Isolation.Types.SELF,        tag='BDV-7484A', description='EX-C Bypass Valve'),
        'XV-8508D':     Isolation(type=Isolation.Types.OTHER,       tag='XV-8508D',  description='BC-A Separator'),
        'SDV-9288B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-9288B', description='UT-A Level Transmitter'),
        'EV-5669A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-5669A',  description='IN-C Filter'),
        'PT-1128E':     Isolation(type=Isolation.Types.OTHER,       tag='PT-1128E',  description='MP-A Control Valve'),
        'BDV-2891':     Isolation(type=Isolation.Types.OTHER,       tag='BDV-2891',  description='HP-C Temp Element'),
        'ESD-4450E':    Isolation(type=Isolation.Types.SELF,        tag='ESD-4450E', description='LP-C Heat Exchanger'),
        'TT-5114':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-5114',   description='FL-C Outlet Valve'),
        'XV-6464A':     Isolation(type=Isolation.Types.SELF,        tag='XV-6464A',  description='HP-D Separator'),
        'SV-1158':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-1158',   description='HP-E Outlet Valve'),
        'EV-3426C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-3426C',  description='MC-C Breaker'),
        'PSV-6862A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-6862A', description='BC-C Separator'),
        'SV-3532A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-3532A',  description='HP-D Inlet Valve'),
        'PCV-6442C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-6442C', description='MP-B Isolation Valve'),
        'TV-1634C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-1634C',  description='LP-D Breaker'),
        'PZV-4728A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-4728A', description='LP-D Motor Control'),
        'BDV-2137B':    Isolation(type=Isolation.Types.SELF,        tag='BDV-2137B', description='IN-D Separator'),
        'CV-1452':      Isolation(type=Isolation.Types.SELF,        tag='CV-1452',   description='HP-E Flow Transmitter'),
        'PSV-2776D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-2776D', description='UT-C Junction Box'),
        'ESD-9379':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-9379',  description='CD-B Flow Transmitter'),
        'PSV-8144':     Isolation(type=Isolation.Types.OTHER,       tag='PSV-8144',  description='IN-B Breaker'),
        'SV-2146E':     Isolation(type=Isolation.Types.SELF,        tag='SV-2146E',  description='CD-C Isolation Valve'),
        'PZV-9308B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-9308B', description='UT-D Temp Element'),
        'FT-3085A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-3085A',  description='FL-B Filter'),
        'LT-5930C':     Isolation(type=Isolation.Types.OTHER,       tag='LT-5930C',  description='MC-C Temp Element'),
        'SDV-8043D':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-8043D', description='UT-D Pump'),
        'HS-4501D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-4501D',  description='HP-A Temp Element'),
        'PT-6491':      Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-6491',   description='MP-B Pressure Transmitter'),
        'HV-1400':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-1400',   description='EX-E Bypass Valve'),
        'HS-7790E':     Isolation(type=Isolation.Types.OTHER,       tag='HS-7790E',  description='LP-D Compressor'),
        'TV-4997A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-4997A',  description='BC-D Level Transmitter'),
        'PCV-9486C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PCV-9486C', description='IN-B Isolation Valve'),
        'HS-3184C':     Isolation(type=Isolation.Types.OTHER,       tag='HS-3184C',  description='IN-E Motor Control'),
        'HS-9270C':     Isolation(type=Isolation.Types.OTHER,       tag='HS-9270C',  description='EX-B Compressor'),
        'HS-5246A':     Isolation(type=Isolation.Types.SELF,        tag='HS-5246A',  description='IN-D Level Transmitter'),
        'BDV-8206':     Isolation(type=Isolation.Types.SELF,        tag='BDV-8206',  description='LP-C Motor Control'),
        'CV-9849':      Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-9849',   description='HP-B Feeder Panel'),
        'HV-4505':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-4505',   description='FL-C Separator'),
        'HS-7812':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-7812',   description='FL-D Drum'),
        'XV-7232C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-7232C',  description='UT-C Feeder Panel'),
        'SV-9818E':     Isolation(type=Isolation.Types.OTHER,       tag='SV-9818E',  description='CD-B Compressor'),
        'MOV-5471C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-5471C', description='MC-D Motor Control'),
        'TV-3704C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-3704C',  description='CD-E Inlet Valve'),
        'TV-1444':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-1444',   description='HP-D Safety Valve'),
        'PSV-5262C':    Isolation(type=Isolation.Types.SELF,        tag='PSV-5262C', description='LP-D Motor Control'),
        'CV-7211B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-7211B',  description='MP-A Compressor'),
        'XV-9837':      Isolation(type=Isolation.Types.SELF,        tag='XV-9837',   description='LP-A Outlet Valve'),
        'XV-5051A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-5051A',  description='CD-B Level Transmitter'),
        'HV-8758E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HV-8758E',  description='CD-B Pump'),
        'BDV-7043A':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-7043A', description='CD-A Safety Valve'),
        'PZV-2771D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-2771D', description='MP-E Feeder Panel'),
        'TV-4249':      Isolation(type=Isolation.Types.OTHER,       tag='TV-4249',   description='LP-A Temp Element'),
        'ESD-2983D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-2983D', description='UT-E Junction Box'),
        'EV-2129D':     Isolation(type=Isolation.Types.SELF,        tag='EV-2129D',  description='MC-D Compressor'),
        'LV-8102B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-8102B',  description='HP-D Safety Valve'),
        'PT-5425D':     Isolation(type=Isolation.Types.OTHER,       tag='PT-5425D',  description='EX-D Junction Box'),
        'LT-5397B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-5397B',  description='BC-C Pump'),
        'MOV-8613D':    Isolation(type=Isolation.Types.OTHER,       tag='MOV-8613D', description='FL-C Inlet Valve'),
        'TT-6325A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-6325A',  description='LP-C Flow Transmitter'),
        'CV-5581D':     Isolation(type=Isolation.Types.SELF,        tag='CV-5581D',  description='IN-A Heat Exchanger'),
        'SDV-2402A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='SDV-2402A', description='EX-E Level Transmitter'),
        'TT-9041C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-9041C',  description='BC-C Level Transmitter'),
        'TV-4986B':     Isolation(type=Isolation.Types.OTHER,       tag='TV-4986B',  description='UT-D Separator'),
        'PT-6632C':     Isolation(type=Isolation.Types.OTHER,       tag='PT-6632C',  description='UT-C Pump'),
        'BDV-6023B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-6023B', description='BC-B Motor Control'),
        'LV-9779E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-9779E',  description='LP-B Compressor'),
        'BDV-9595D':    Isolation(type=Isolation.Types.SELF,        tag='BDV-9595D', description='BC-B Temp Element'),
        'MOV-6912A':    Isolation(type=Isolation.Types.SELF,        tag='MOV-6912A', description='MC-E Control Valve'),
        'BDV-1745':     Isolation(type=Isolation.Types.OTHER,       tag='BDV-1745',  description='MP-B Compressor'),
        'LV-1200D':     Isolation(type=Isolation.Types.SELF,        tag='LV-1200D',  description='EX-D Pump'),
        'CV-4020':      Isolation(type=Isolation.Types.SELF,        tag='CV-4020',   description='EX-A Bypass Valve'),
        'TV-9056':      Isolation(type=Isolation.Types.OTHER,       tag='TV-9056',   description='MC-B Control Valve'),
        'LT-5978':      Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-5978',   description='BC-E Junction Box'),
        'ESD-4697D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-4697D', description='EX-D Temp Element'),
        'LT-8025B':     Isolation(type=Isolation.Types.OTHER,       tag='LT-8025B',  description='CD-A Filter'),
        'LV-4404E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-4404E',  description='MP-A Safety Valve'),
        'MOV-3847D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-3847D', description='HP-A Junction Box'),
        'HS-8699B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-8699B',  description='LP-C Temp Element'),
        'HS-2166E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-2166E',  description='MP-E Pressure Transmitter'),
        'SV-2880D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-2880D',  description='HP-C Control Valve'),
        'FV-1977A':     Isolation(type=Isolation.Types.SELF,        tag='FV-1977A',  description='CD-E Temp Element'),
        'HS-3037C':     Isolation(type=Isolation.Types.SELF,        tag='HS-3037C',  description='FL-C Heat Exchanger'),
        'FT-9090C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-9090C',  description='CD-A Junction Box'),
        'CV-5102':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-5102',   description='LP-E Drum'),
        'XV-5415D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-5415D',  description='HP-D Heat Exchanger'),
        'HS-5557A':     Isolation(type=Isolation.Types.OTHER,       tag='HS-5557A',  description='FL-D Bypass Valve'),
        'TT-6700C':     Isolation(type=Isolation.Types.SELF,        tag='TT-6700C',  description='UT-A Safety Valve'),
        'CV-7744E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-7744E',  description='MP-D Separator'),
        'PSV-8451':     Isolation(type=Isolation.Types.SELF,        tag='PSV-8451',  description='MP-C Isolation Valve'),
        'TV-9431':      Isolation(type=Isolation.Types.OTHER,       tag='TV-9431',   description='EX-D Outlet Valve'),
        'SDV-9494B':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-9494B', description='EX-D Outlet Valve'),
        'SDV-5375D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-5375D', description='MP-D Compressor'),
        'LV-1472E':     Isolation(type=Isolation.Types.OTHER,       tag='LV-1472E',  description='LP-B Temp Element'),
        'FT-1224D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-1224D',  description='BC-B Isolation Valve'),
        'HS-2924E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-2924E',  description='EX-C Heat Exchanger'),
        'BDV-7807C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-7807C', description='LP-D Separator'),
        'HV-7284A':     Isolation(type=Isolation.Types.OTHER,       tag='HV-7284A',  description='IN-B Bypass Valve'),
        'BDV-7798B':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-7798B', description='MP-A Temp Element'),
        'PZV-9022A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-9022A', description='IN-D Breaker'),
        'CV-9903C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-9903C',  description='UT-B Level Transmitter'),
        'LT-7274A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LT-7274A',  description='MC-C Compressor'),
        'TV-7325E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-7325E',  description='EX-A Control Valve'),
        'PT-6439':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-6439',   description='BC-E Pump'),
        'XV-3361C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-3361C',  description='BC-D Flow Transmitter'),
        'CV-7512E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-7512E',  description='UT-E Feeder Panel'),
        'CV-8994D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-8994D',  description='CD-A Level Transmitter'),
        'PZV-4727E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-4727E', description='FL-A Isolation Valve'),
        'HS-3725E':     Isolation(type=Isolation.Types.SELF,        tag='HS-3725E',  description='MC-A Motor Control'),
        'PSV-5806B':    Isolation(type=Isolation.Types.SELF,        tag='PSV-5806B', description='FL-B Level Transmitter'),
        'PT-7751D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-7751D',  description='HP-B Bypass Valve'),
        'ESD-7267D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-7267D', description='EX-E Control Valve'),
        'MOV-8555E':    Isolation(type=Isolation.Types.SELF,        tag='MOV-8555E', description='EX-C Inlet Valve'),
        'HS-5712E':     Isolation(type=Isolation.Types.OTHER,       tag='HS-5712E',  description='HP-A Pump'),
        'EV-5901E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-5901E',  description='MP-D Temp Element'),
        'SDV-7302C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='SDV-7302C', description='LP-D Drum'),
        'EV-5847E':     Isolation(type=Isolation.Types.SELF,        tag='EV-5847E',  description='MC-D Flow Transmitter'),
        'XV-1803D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-1803D',  description='MP-B Filter'),
        'EV-4588E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-4588E',  description='CD-C Control Valve'),
        'LV-1645B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-1645B',  description='MC-E Breaker'),
        'HV-2476B':     Isolation(type=Isolation.Types.SELF,        tag='HV-2476B',  description='FL-B Pressure Transmitter'),
        'HV-9837B':     Isolation(type=Isolation.Types.OTHER,       tag='HV-9837B',  description='IN-C Safety Valve'),
        'BDV-8894B':    Isolation(type=Isolation.Types.SELF,        tag='BDV-8894B', description='BC-D Bypass Valve'),
        'HV-4696E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-4696E',  description='IN-C Bypass Valve'),
        'TV-1228B':     Isolation(type=Isolation.Types.OTHER,       tag='TV-1228B',  description='BC-D Breaker'),
        'BDV-7242E':    Isolation(type=Isolation.Types.SELF,        tag='BDV-7242E', description='BC-B Compressor'),
        'XV-6374D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-6374D',  description='BC-D Temp Element'),
        'SV-2911A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-2911A',  description='MC-C Compressor'),
        'LV-2592A':     Isolation(type=Isolation.Types.OTHER,       tag='LV-2592A',  description='HP-D Pump'),
        'EV-9850C':     Isolation(type=Isolation.Types.OTHER,       tag='EV-9850C',  description='HP-D Isolation Valve'),
        'TT-7686B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-7686B',  description='UT-B Pump'),
        'HS-4868B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-4868B',  description='UT-E Breaker'),
        'PSV-7523B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-7523B', description='BC-D Bypass Valve'),
        'SDV-1349':     Isolation(type=Isolation.Types.SELF,        tag='SDV-1349',  description='LP-B Drum'),
        'SDV-2124D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-2124D', description='CD-B Level Transmitter'),
        'CV-3417D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-3417D',  description='MP-B Control Valve'),
        'FT-5106A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-5106A',  description='MC-B Inlet Valve'),
        'EV-4898D':     Isolation(type=Isolation.Types.SELF,        tag='EV-4898D',  description='MC-B Flow Transmitter'),
        'PSV-3076E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-3076E', description='IN-A Bypass Valve'),
        'TT-8344B':     Isolation(type=Isolation.Types.OTHER,       tag='TT-8344B',  description='CD-A Pump'),
        'PT-4629D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-4629D',  description='IN-C Pump'),
        'XV-1996C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-1996C',  description='FL-A Compressor'),
        'HS-2204':      Isolation(type=Isolation.Types.SELF,        tag='HS-2204',   description='CD-B Bypass Valve'),
        'HV-5505D':     Isolation(type=Isolation.Types.OTHER,       tag='HV-5505D',  description='IN-C Feeder Panel'),
        'ESD-9692B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-9692B', description='IN-E Junction Box'),
        'LV-2874E':     Isolation(type=Isolation.Types.OTHER,       tag='LV-2874E',  description='LP-D Pump'),
        'MOV-7779B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-7779B', description='FL-D Isolation Valve'),
        'CV-7992B':     Isolation(type=Isolation.Types.SELF,        tag='CV-7992B',  description='UT-B Compressor'),
        'FV-2494':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-2494',   description='FL-A Breaker'),
        'HV-1982D':     Isolation(type=Isolation.Types.OTHER,       tag='HV-1982D',  description='IN-C Isolation Valve'),
        'SV-6793E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-6793E',  description='MC-C Filter'),
        'PZV-6761':     Isolation(type=Isolation.Types.OTHER,       tag='PZV-6761',  description='IN-B Control Valve'),
        'TT-4674':      Isolation(type=Isolation.Types.SELF,        tag='TT-4674',   description='IN-C Isolation Valve'),
        'BDV-4705C':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-4705C', description='CD-E Separator'),
        'XV-5381':      Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-5381',   description='MP-C Motor Control'),
        'EV-1100A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-1100A',  description='CD-D Bypass Valve'),
        'HV-1502':      Isolation(type=Isolation.Types.OTHER,       tag='HV-1502',   description='LP-D Junction Box'),
        'HS-6585A':     Isolation(type=Isolation.Types.SELF,        tag='HS-6585A',  description='MP-C Drum'),
        'ESD-2391':     Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-2391',  description='HP-E Outlet Valve'),
        'FV-5458C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-5458C',  description='EX-E Pump'),
        'SV-5475A':     Isolation(type=Isolation.Types.OTHER,       tag='SV-5475A',  description='BC-C Junction Box'),
        'LV-5640E':     Isolation(type=Isolation.Types.OTHER,       tag='LV-5640E',  description='EX-E Temp Element'),
        'PSV-4612C':    Isolation(type=Isolation.Types.OTHER,       tag='PSV-4612C', description='MC-A Pressure Transmitter'),
        'PZV-4460A':    Isolation(type=Isolation.Types.SELF,        tag='PZV-4460A', description='MP-C Isolation Valve'),
        'XV-9149E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-9149E',  description='HP-B Feeder Panel'),
        'FT-4770D':     Isolation(type=Isolation.Types.OTHER,       tag='FT-4770D',  description='UT-A Feeder Panel'),
        'PSV-8147':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-8147',  description='BC-C Drum'),
        'SV-7626E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-7626E',  description='MP-A Feeder Panel'),
        'XV-6321A':     Isolation(type=Isolation.Types.OTHER,       tag='XV-6321A',  description='EX-C Bypass Valve'),
        'SV-2734A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-2734A',  description='CD-D Heat Exchanger'),
        'FV-7484B':     Isolation(type=Isolation.Types.SELF,        tag='FV-7484B',  description='LP-C Safety Valve'),
        'FV-9363E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-9363E',  description='IN-E Pressure Transmitter'),
        'EV-6752E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-6752E',  description='LP-A Control Valve'),
        'BDV-4232A':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-4232A', description='HP-A Safety Valve'),
        'TT-8601D':     Isolation(type=Isolation.Types.OTHER,       tag='TT-8601D',  description='EX-E Filter'),
        'CV-6179A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-6179A',  description='BC-D Pump'),
        'PZV-5500D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-5500D', description='UT-E Bypass Valve'),
        'PZV-8565C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-8565C', description='MC-C Temp Element'),
        'FV-2479D':     Isolation(type=Isolation.Types.OTHER,       tag='FV-2479D',  description='IN-D Pump'),
        'LT-1672C':     Isolation(type=Isolation.Types.OTHER,       tag='LT-1672C',  description='LP-C Filter'),
        'TT-9214A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-9214A',  description='EX-A Motor Control'),
        'FV-9266E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-9266E',  description='MC-B Pump'),
        'HS-9586D':     Isolation(type=Isolation.Types.OTHER,       tag='HS-9586D',  description='HP-C Breaker'),
        'PZV-7347C':    Isolation(type=Isolation.Types.SELF,        tag='PZV-7347C', description='CD-A Motor Control'),
        'FV-6401':      Isolation(type=Isolation.Types.OTHER,       tag='FV-6401',   description='FL-C Flow Transmitter'),
        'ESD-3463B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-3463B', description='CD-B Breaker'),
        'PZV-7421A':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-7421A', description='BC-C Separator'),
        'TV-6381A':     Isolation(type=Isolation.Types.OTHER,       tag='TV-6381A',  description='BC-D Heat Exchanger'),
        'EV-1298B':     Isolation(type=Isolation.Types.SELF,        tag='EV-1298B',  description='HP-B Motor Control'),
        'TT-4145A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-4145A',  description='HP-A Temp Element'),
        'LV-9317D':     Isolation(type=Isolation.Types.OTHER,       tag='LV-9317D',  description='MC-C Filter'),
        'HV-7172A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-7172A',  description='HP-E Safety Valve'),
        'HS-1715C':     Isolation(type=Isolation.Types.SELF,        tag='HS-1715C',  description='LP-D Filter'),
        'PZV-8355A':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-8355A', description='LP-C Compressor'),
        'SDV-7026E':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-7026E', description='EX-D Temp Element'),
        'TV-9239D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-9239D',  description='HP-B Filter'),
        'HV-5096':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-5096',   description='UT-E Isolation Valve'),
        'PT-3042B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-3042B',  description='HP-C Pump'),
        'PT-3414C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-3414C',  description='LP-D Breaker'),
        'XV-7797':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-7797',   description='IN-C Level Transmitter'),
        'TV-2337B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-2337B',  description='MC-C Isolation Valve'),
        'CV-3392A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-3392A',  description='MP-D Control Valve'),
        'TT-8349D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-8349D',  description='BC-A Flow Transmitter'),
        'SDV-3449D':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-3449D', description='IN-D Isolation Valve'),
        'PZV-4893B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-4893B', description='MC-B Junction Box'),
        'ESD-8489':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-8489',  description='EX-E Separator'),
        'XV-9443D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-9443D',  description='HP-C Junction Box'),
        'XV-6780A':     Isolation(type=Isolation.Types.OTHER,       tag='XV-6780A',  description='FL-B Bypass Valve'),
        'PT-6908':      Isolation(type=Isolation.Types.OTHER,       tag='PT-6908',   description='IN-E Heat Exchanger'),
        'FT-1333C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-1333C',  description='MC-D Breaker'),
        'BDV-1266B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-1266B', description='UT-B Isolation Valve'),
        'LT-6447A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-6447A',  description='UT-E Motor Control'),
        'PCV-8612E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-8612E', description='HP-B Bypass Valve'),
        'HS-1605B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-1605B',  description='MC-B Outlet Valve'),
        'CV-6080D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-6080D',  description='IN-D Flow Transmitter'),
        'PSV-4131B':    Isolation(type=Isolation.Types.SELF,        tag='PSV-4131B', description='MC-C Flow Transmitter'),
        'LV-7029C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-7029C',  description='EX-D Motor Control'),
        'PCV-9129E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-9129E', description='UT-E Flow Transmitter'),
        'FV-7955':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-7955',   description='CD-B Separator'),
        'PZV-6262':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-6262',  description='UT-C Temp Element'),
        'HS-7981A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-7981A',  description='UT-D Outlet Valve'),
        'EV-8126B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-8126B',  description='BC-D Breaker'),
        'PT-3621':      Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-3621',   description='CD-D Outlet Valve'),
        'HV-2101A':     Isolation(type=Isolation.Types.SELF,        tag='HV-2101A',  description='UT-D Drum'),
        'PSV-3513E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-3513E', description='UT-C Pump'),
        'FV-3255D':     Isolation(type=Isolation.Types.SELF,        tag='FV-3255D',  description='FL-C Flow Transmitter'),
        'MOV-2858':     Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-2858',  description='EX-E Feeder Panel'),
        'FT-2929B':     Isolation(type=Isolation.Types.SELF,        tag='FT-2929B',  description='EX-B Filter'),
        'PZV-9047A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-9047A', description='HP-A Pump'),
        'PCV-8292':     Isolation(type=Isolation.Types.SELF,        tag='PCV-8292',  description='UT-A Separator'),
        'FT-5757B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-5757B',  description='HP-C Heat Exchanger'),
        'MOV-2988A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-2988A', description='LP-D Inlet Valve'),
        'EV-7044C':     Isolation(type=Isolation.Types.OTHER,       tag='EV-7044C',  description='HP-E Bypass Valve'),
        'FV-6067C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-6067C',  description='IN-D Junction Box'),
        'LT-2208A':     Isolation(type=Isolation.Types.SELF,        tag='LT-2208A',  description='BC-D Pump'),
        'PT-6644A':     Isolation(type=Isolation.Types.OTHER,       tag='PT-6644A',  description='CD-B Control Valve'),
        'SV-9238':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-9238',   description='IN-B Temp Element'),
        'PCV-3653B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-3653B', description='UT-E Temp Element'),
        'FV-5105A':     Isolation(type=Isolation.Types.OTHER,       tag='FV-5105A',  description='MP-B Temp Element'),
        'ESD-9740':     Isolation(type=Isolation.Types.OTHER,       tag='ESD-9740',  description='HP-E Drum'),
        'HV-3804E':     Isolation(type=Isolation.Types.OTHER,       tag='HV-3804E',  description='CD-C Drum'),
        'PSV-1464':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-1464',  description='CD-C Pressure Transmitter'),
        'LT-7825D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-7825D',  description='EX-E Temp Element'),
        'PZV-8912A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-8912A', description='MP-D Bypass Valve'),
        'PSV-3589C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-3589C', description='EX-D Pressure Transmitter'),
        'CV-3353B':     Isolation(type=Isolation.Types.SELF,        tag='CV-3353B',  description='UT-D Control Valve'),
        'EV-9437D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-9437D',  description='UT-B Pump'),
        'LV-5382C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-5382C',  description='HP-A Outlet Valve'),
        'PZV-7293D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-7293D', description='LP-B Motor Control'),
        'LT-6123A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-6123A',  description='EX-E Pump'),
        'TT-6055C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-6055C',  description='BC-D Heat Exchanger'),
        'HS-4944A':     Isolation(type=Isolation.Types.OTHER,       tag='HS-4944A',  description='UT-A Outlet Valve'),
        'PZV-9108D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-9108D', description='MP-E Inlet Valve'),
        'LV-8060A':     Isolation(type=Isolation.Types.SELF,        tag='LV-8060A',  description='UT-D Breaker'),
        'PSV-7563':     Isolation(type=Isolation.Types.OTHER,       tag='PSV-7563',  description='IN-B Breaker'),
        'FT-5728':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-5728',   description='IN-D Separator'),
        'BDV-2946A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-2946A', description='FL-C Motor Control'),
        'FT-6990A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-6990A',  description='CD-E Feeder Panel'),
        'PT-1659':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-1659',   description='HP-C Compressor'),
        'PT-8487A':     Isolation(type=Isolation.Types.OTHER,       tag='PT-8487A',  description='IN-B Motor Control'),
        'ESD-6218A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-6218A', description='CD-C Drum'),
        'CV-9311D':     Isolation(type=Isolation.Types.OTHER,       tag='CV-9311D',  description='EX-E Temp Element'),
        'TT-1272B':     Isolation(type=Isolation.Types.SELF,        tag='TT-1272B',  description='BC-D Drum'),
        'PZV-1436D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-1436D', description='MP-E Drum'),
        'MOV-1841D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-1841D', description='HP-E Filter'),
        'TV-3421E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-3421E',  description='MC-E Isolation Valve'),
        'SDV-1310C':    Isolation(type=Isolation.Types.SELF,        tag='SDV-1310C', description='FL-B Junction Box'),
        'SDV-7723D':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-7723D', description='EX-A Control Valve'),
        'PT-4397D':     Isolation(type=Isolation.Types.SELF,        tag='PT-4397D',  description='EX-E Feeder Panel'),
        'CV-3837C':     Isolation(type=Isolation.Types.OTHER,       tag='CV-3837C',  description='UT-E Breaker'),
        'BDV-8932A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-8932A', description='MP-E Temp Element'),
        'MOV-5876B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-5876B', description='EX-C Compressor'),
        'EV-5480B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-5480B',  description='CD-E Feeder Panel'),
        'TV-6654A':     Isolation(type=Isolation.Types.SELF,        tag='TV-6654A',  description='MC-C Bypass Valve'),
        'EV-8247E':     Isolation(type=Isolation.Types.SELF,        tag='EV-8247E',  description='EX-B Pressure Transmitter'),
        'FT-5442D':     Isolation(type=Isolation.Types.SELF,        tag='FT-5442D',  description='HP-A Filter'),
        'LT-4920A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-4920A',  description='IN-B Level Transmitter'),
        'PSV-2641C':    Isolation(type=Isolation.Types.SELF,        tag='PSV-2641C', description='EX-A Control Valve'),
        'XV-3587C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-3587C',  description='EX-B Temp Element'),
        'CV-5676E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-5676E',  description='BC-E Level Transmitter'),
        'FT-1611A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-1611A',  description='HP-A Feeder Panel'),
        'TT-4052E':     Isolation(type=Isolation.Types.SELF,        tag='TT-4052E',  description='MC-A Temp Element'),
        'LT-2758B':     Isolation(type=Isolation.Types.SELF,        tag='LT-2758B',  description='EX-E Heat Exchanger'),
        'TT-3198D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-3198D',  description='MP-B Isolation Valve'),
        'CV-3662E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-3662E',  description='MP-B Inlet Valve'),
        'CV-5833D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-5833D',  description='HP-E Feeder Panel'),
        'SV-9442B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-9442B',  description='FL-A Safety Valve'),
        'HV-8822B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-8822B',  description='MC-C Feeder Panel'),
        'MOV-8319B':    Isolation(type=Isolation.Types.SELF,        tag='MOV-8319B', description='MP-E Drum'),
        'XV-5285E':     Isolation(type=Isolation.Types.SELF,        tag='XV-5285E',  description='LP-A Isolation Valve'),
        'HS-6026A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-6026A',  description='IN-C Isolation Valve'),
        'PZV-7021D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PZV-7021D', description='LP-B Compressor'),
        'HV-8454E':     Isolation(type=Isolation.Types.OTHER,       tag='HV-8454E',  description='UT-D Separator'),
        'TT-9806E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-9806E',  description='LP-E Bypass Valve'),
        'PT-8319D':     Isolation(type=Isolation.Types.SELF,        tag='PT-8319D',  description='BC-E Isolation Valve'),
        'PSV-9972D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-9972D', description='CD-E Control Valve'),
        'PCV-6375D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-6375D', description='BC-B Drum'),
        'TT-2489D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-2489D',  description='MC-D Control Valve'),
        'PT-7806C':     Isolation(type=Isolation.Types.OTHER,       tag='PT-7806C',  description='MC-E Pump'),
        'PZV-1356C':    Isolation(type=Isolation.Types.SELF,        tag='PZV-1356C', description='MC-B Drum'),
        'FV-1742C':     Isolation(type=Isolation.Types.SELF,        tag='FV-1742C',  description='BC-E Outlet Valve'),
        'FV-8734':      Isolation(type=Isolation.Types.SELF,        tag='FV-8734',   description='FL-B Control Valve'),
        'SV-7135C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-7135C',  description='FL-D Bypass Valve'),
        'FT-3178E':     Isolation(type=Isolation.Types.SELF,        tag='FT-3178E',  description='BC-B Separator'),
        'TV-9664A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-9664A',  description='MC-A Temp Element'),
        'HS-9920C':     Isolation(type=Isolation.Types.OTHER,       tag='HS-9920C',  description='FL-B Level Transmitter'),
        'HS-6671A':     Isolation(type=Isolation.Types.SELF,        tag='HS-6671A',  description='LP-A Outlet Valve'),
        'SV-1256A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-1256A',  description='BC-A Filter'),
        'PSV-8314D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-8314D', description='LP-A Feeder Panel'),
        'HS-4839D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-4839D',  description='MC-B Heat Exchanger'),
        'PZV-4836E':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-4836E', description='UT-E Filter'),
        'CV-4881B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-4881B',  description='IN-B Junction Box'),
        'PZV-5508':     Isolation(type=Isolation.Types.OTHER,       tag='PZV-5508',  description='CD-B Junction Box'),
        'FT-9120':      Isolation(type=Isolation.Types.SELF,        tag='FT-9120',   description='FL-E Motor Control'),
        'SV-7688A':     Isolation(type=Isolation.Types.SELF,        tag='SV-7688A',  description='FL-B Separator'),
        'TT-4948A':     Isolation(type=Isolation.Types.SELF,        tag='TT-4948A',  description='HP-D Outlet Valve'),
        'FT-7761C':     Isolation(type=Isolation.Types.OTHER,       tag='FT-7761C',  description='IN-B Feeder Panel'),
        'MOV-5177A':    Isolation(type=Isolation.Types.SELF,        tag='MOV-5177A', description='BC-D Breaker'),
        'FV-9775E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-9775E',  description='MC-C Feeder Panel'),
        'ESD-1647':     Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-1647',  description='CD-E Pressure Transmitter'),
        'TT-4422B':     Isolation(type=Isolation.Types.SELF,        tag='TT-4422B',  description='MC-B Pressure Transmitter'),
        'LV-8846A':     Isolation(type=Isolation.Types.OTHER,       tag='LV-8846A',  description='LP-D Level Transmitter'),
        'FT-6269B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-6269B',  description='EX-E Breaker'),
        'PZV-5285B':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-5285B', description='EX-D Isolation Valve'),
        'TT-6246A':     Isolation(type=Isolation.Types.SELF,        tag='TT-6246A',  description='UT-D Outlet Valve'),
        'LT-4625E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-4625E',  description='MC-C Separator'),
        'LT-7841B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-7841B',  description='LP-C Level Transmitter'),
        'TV-5026C':     Isolation(type=Isolation.Types.OTHER,       tag='TV-5026C',  description='UT-C Compressor'),
        'TT-8550A':     Isolation(type=Isolation.Types.SELF,        tag='TT-8550A',  description='HP-B Separator'),
        'TT-4015D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-4015D',  description='IN-A Bypass Valve'),
        'PSV-1104C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-1104C', description='LP-A Control Valve'),
        'XV-4583D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-4583D',  description='UT-A Filter'),
        'ESD-8916E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-8916E', description='MC-A Separator'),
        'FT-7739':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-7739',   description='IN-C Separator'),
        'PZV-1280D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-1280D', description='HP-A Isolation Valve'),
        'PT-3439A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-3439A',  description='CD-E Flow Transmitter'),
        'EV-5379C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-5379C',  description='UT-D Pump'),
        'LT-4984E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-4984E',  description='MP-A Outlet Valve'),
        'FV-7640C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-7640C',  description='IN-D Outlet Valve'),
        'XV-3807':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-3807',   description='FL-C Drum'),
        'LV-9653':      Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-9653',   description='LP-E Compressor'),
        'BDV-1762':     Isolation(type=Isolation.Types.SELF,        tag='BDV-1762',  description='IN-E Outlet Valve'),
        'PCV-6152':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-6152',  description='CD-B Feeder Panel'),
        'FV-5903A':     Isolation(type=Isolation.Types.OTHER,       tag='FV-5903A',  description='LP-E Feeder Panel'),
        'FT-6435C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-6435C',  description='BC-E Breaker'),
        'PSV-2600C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-2600C', description='BC-C Filter'),
        'ESD-7499B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-7499B', description='MP-D Compressor'),
        'MOV-6829D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-6829D', description='FL-B Drum'),
        'TV-2404D':     Isolation(type=Isolation.Types.SELF,        tag='TV-2404D',  description='LP-A Bypass Valve'),
        'BDV-3526C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-3526C', description='FL-C Breaker'),
        'LV-2499':      Isolation(type=Isolation.Types.SELF,        tag='LV-2499',   description='EX-C Flow Transmitter'),
        'LV-3170':      Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-3170',   description='FL-D Separator'),
        'FT-9395C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-9395C',  description='MC-A Breaker'),
        'FT-2524D':     Isolation(type=Isolation.Types.OTHER,       tag='FT-2524D',  description='UT-D Inlet Valve'),
        'PZV-7779C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-7779C', description='IN-B Drum'),
        'PT-3778E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-3778E',  description='HP-B Flow Transmitter'),
        'PZV-5397C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PZV-5397C', description='BC-B Junction Box'),
        'BDV-7899B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-7899B', description='BC-C Flow Transmitter'),
        'MOV-9123D':    Isolation(type=Isolation.Types.OTHER,       tag='MOV-9123D', description='LP-D Isolation Valve'),
        'HV-5991':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-5991',   description='UT-E Feeder Panel'),
        'CV-8212B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-8212B',  description='CD-B Temp Element'),
        'CV-4290C':     Isolation(type=Isolation.Types.SELF,        tag='CV-4290C',  description='HP-D Motor Control'),
        'PZV-9044D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PZV-9044D', description='UT-D Flow Transmitter'),
        'TV-6980':      Isolation(type=Isolation.Types.OTHER,       tag='TV-6980',   description='LP-E Separator'),
        'PCV-1440E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-1440E', description='LP-D Temp Element'),
        'FV-7703E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-7703E',  description='HP-C Level Transmitter'),
        'BDV-3525E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-3525E', description='FL-A Pump'),
        'ESD-8851D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-8851D', description='IN-E Junction Box'),
        'FT-1602B':     Isolation(type=Isolation.Types.OTHER,       tag='FT-1602B',  description='CD-A Isolation Valve'),
        'MOV-6816A':    Isolation(type=Isolation.Types.OTHER,       tag='MOV-6816A', description='MC-E Feeder Panel'),
        'CV-8052':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-8052',   description='BC-C Level Transmitter'),
        'PT-9499D':     Isolation(type=Isolation.Types.OTHER,       tag='PT-9499D',  description='CD-B Pump'),
        'EV-7408C':     Isolation(type=Isolation.Types.OTHER,       tag='EV-7408C',  description='IN-B Breaker'),
        'XV-8909':      Isolation(type=Isolation.Types.SELF,        tag='XV-8909',   description='FL-A Isolation Valve'),
        'HV-6707B':     Isolation(type=Isolation.Types.SELF,        tag='HV-6707B',  description='EX-B Heat Exchanger'),
        'TT-6706C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-6706C',  description='EX-D Motor Control'),
        'FV-5919':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-5919',   description='MC-C Isolation Valve'),
        'PCV-4996D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-4996D', description='IN-B Motor Control'),
        'FT-7985C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-7985C',  description='FL-B Safety Valve'),
        'SV-7481':      Isolation(type=Isolation.Types.OTHER,       tag='SV-7481',   description='LP-D Drum'),
        'SV-7370':      Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-7370',   description='LP-C Bypass Valve'),
        'LT-2667D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-2667D',  description='UT-C Pressure Transmitter'),
        'HS-2867B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-2867B',  description='IN-C Filter'),
        'TV-7431D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-7431D',  description='UT-C Pump'),
        'ESD-3826E':    Isolation(type=Isolation.Types.SELF,        tag='ESD-3826E', description='CD-E Bypass Valve'),
        'HV-6131':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-6131',   description='MP-A Safety Valve'),
        'EV-3316D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-3316D',  description='FL-E Control Valve'),
        'LT-7286C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-7286C',  description='EX-E Safety Valve'),
        'FT-3733C':     Isolation(type=Isolation.Types.SELF,        tag='FT-3733C',  description='HP-B Motor Control'),
        'HS-1878B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-1878B',  description='EX-B Pressure Transmitter'),
        'TV-9281E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-9281E',  description='FL-D Junction Box'),
        'HS-9006A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-9006A',  description='CD-A Level Transmitter'),
        'PZV-1535B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PZV-1535B', description='IN-C Safety Valve'),
        'HS-9115D':     Isolation(type=Isolation.Types.OTHER,       tag='HS-9115D',  description='BC-E Isolation Valve'),
        'BDV-9898B':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-9898B', description='MC-D Separator'),
        'SDV-7965':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-7965',  description='MP-A Pump'),
        'BDV-6711':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-6711',  description='BC-B Pressure Transmitter'),
        'LT-6744E':     Isolation(type=Isolation.Types.OTHER,       tag='LT-6744E',  description='FL-B Filter'),
        'HV-4385A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HV-4385A',  description='CD-C Separator'),
        'BDV-9827A':    Isolation(type=Isolation.Types.SELF,        tag='BDV-9827A', description='MP-C Drum'),
        'BDV-9428E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-9428E', description='HP-D Outlet Valve'),
        'BDV-3078E':    Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-3078E', description='LP-B Motor Control'),
        'MOV-7434C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-7434C', description='CD-C Junction Box'),
        'TV-8405':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-8405',   description='FL-E Flow Transmitter'),
        'EV-8449C':     Isolation(type=Isolation.Types.SELF,        tag='EV-8449C',  description='CD-A Bypass Valve'),
        'HS-6869':      Isolation(type=Isolation.Types.OTHER,       tag='HS-6869',   description='FL-B Junction Box'),
        'SDV-9105B':    Isolation(type=Isolation.Types.SELF,        tag='SDV-9105B', description='MP-C Separator'),
        'LT-3139D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LT-3139D',  description='UT-A Outlet Valve'),
        'LV-8529':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='LV-8529',   description='HP-D Pump'),
        'XV-8009A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-8009A',  description='MP-B Flow Transmitter'),
        'FV-6905B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-6905B',  description='UT-B Outlet Valve'),
        'TV-6005E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-6005E',  description='FL-A Isolation Valve'),
        'XV-4496C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-4496C',  description='HP-E Level Transmitter'),
        'PT-8291':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-8291',   description='UT-A Junction Box'),
        'HV-8826':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-8826',   description='FL-A Isolation Valve'),
        'LV-6133B':     Isolation(type=Isolation.Types.SELF,        tag='LV-6133B',  description='HP-D Control Valve'),
        'HV-2120D':     Isolation(type=Isolation.Types.OTHER,       tag='HV-2120D',  description='MC-E Safety Valve'),
        'HS-6753E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-6753E',  description='HP-D Filter'),
        'HS-4559':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-4559',   description='HP-A Drum'),
        'TV-6759C':     Isolation(type=Isolation.Types.SELF,        tag='TV-6759C',  description='HP-B Flow Transmitter'),
        'FV-5065D':     Isolation(type=Isolation.Types.OTHER,       tag='FV-5065D',  description='CD-E Temp Element'),
        'XV-5942A':     Isolation(type=Isolation.Types.OTHER,       tag='XV-5942A',  description='CD-E Pressure Transmitter'),
        'TV-5842E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-5842E',  description='LP-D Feeder Panel'),
        'LV-4949C':     Isolation(type=Isolation.Types.OTHER,       tag='LV-4949C',  description='BC-E Inlet Valve'),
        'EV-6185A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-6185A',  description='CD-D Breaker'),
        'FT-3830C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-3830C',  description='MC-E Bypass Valve'),
        'XV-5295A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-5295A',  description='MC-D Heat Exchanger'),
        'PZV-9209C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-9209C', description='FL-A Separator'),
        'FT-3501B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-3501B',  description='MP-A Heat Exchanger'),
        'SDV-3545D':    Isolation(type=Isolation.Types.SELF,        tag='SDV-3545D', description='FL-E Bypass Valve'),
        'PZV-8167E':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PZV-8167E', description='MC-B Bypass Valve'),
        'SV-2900C':     Isolation(type=Isolation.Types.OTHER,       tag='SV-2900C',  description='CD-A Temp Element'),
        'PCV-2956':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-2956',  description='MC-B Compressor'),
        'EV-9568D':     Isolation(type=Isolation.Types.SELF,        tag='EV-9568D',  description='HP-C Control Valve'),
        'BDV-2934':     Isolation(type=Isolation.Types.SELF,        tag='BDV-2934',  description='FL-C Heat Exchanger'),
        'FV-5308E':     Isolation(type=Isolation.Types.OTHER,       tag='FV-5308E',  description='BC-D Pump'),
        'PT-6900':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-6900',   description='CD-B Breaker'),
        'PCV-5179':     Isolation(type=Isolation.Types.OTHER,       tag='PCV-5179',  description='BC-B Heat Exchanger'),
        'XV-1721':      Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-1721',   description='MC-D Breaker'),
        'TV-3458A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-3458A',  description='IN-D Level Transmitter'),
        'CV-5067C':     Isolation(type=Isolation.Types.SELF,        tag='CV-5067C',  description='MP-A Drum'),
        'EV-2956D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-2956D',  description='HP-B Heat Exchanger'),
        'PSV-7568':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-7568',  description='MP-C Motor Control'),
        'FV-8483':      Isolation(type=Isolation.Types.SELF,        tag='FV-8483',   description='LP-C Drum'),
        'PZV-4974C':    Isolation(type=Isolation.Types.SELF,        tag='PZV-4974C', description='CD-D Pressure Transmitter'),
        'FT-5016A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-5016A',  description='FL-A Level Transmitter'),
        'FT-6675E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-6675E',  description='UT-A Feeder Panel'),
        'PZV-2703A':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-2703A', description='LP-D Compressor'),
        'PSV-3332E':    Isolation(type=Isolation.Types.SELF,        tag='PSV-3332E', description='BC-A Level Transmitter'),
        'PT-7767E':     Isolation(type=Isolation.Types.SELF,        tag='PT-7767E',  description='EX-A Drum'),
        'LV-9280A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-9280A',  description='BC-E Drum'),
        'PSV-8126E':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-8126E', description='LP-C Flow Transmitter'),
        'CV-7438E':     Isolation(type=Isolation.Types.SELF,        tag='CV-7438E',  description='UT-D Flow Transmitter'),
        'MOV-2223A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-2223A', description='CD-A Control Valve'),
        'LV-3693C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-3693C',  description='UT-D Isolation Valve'),
        'FT-6870A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-6870A',  description='MP-D Flow Transmitter'),
        'LV-2481A':     Isolation(type=Isolation.Types.SELF,        tag='LV-2481A',  description='CD-A Pressure Transmitter'),
        'CV-3430':      Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-3430',   description='UT-D Heat Exchanger'),
        'PSV-5896B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-5896B', description='MC-D Pump'),
        'FT-5093':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-5093',   description='BC-B Isolation Valve'),
        'XV-2010A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-2010A',  description='LP-D Breaker'),
        'FV-5240':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-5240',   description='BC-B Pump'),
        'HV-2506B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HV-2506B',  description='MC-D Outlet Valve'),
        'PCV-8096E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-8096E', description='EX-A Feeder Panel'),
        'SV-3831B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-3831B',  description='HP-C Flow Transmitter'),
        'HS-3435':      Isolation(type=Isolation.Types.OTHER,       tag='HS-3435',   description='CD-E Level Transmitter'),
        'PZV-9173C':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-9173C', description='EX-A Bypass Valve'),
        'BDV-7275A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-7275A', description='LP-E Level Transmitter'),
        'FT-1319C':     Isolation(type=Isolation.Types.SELF,        tag='FT-1319C',  description='EX-E Compressor'),
        'EV-9231B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-9231B',  description='MP-B Inlet Valve'),
        'CV-4588':      Isolation(type=Isolation.Types.SELF,        tag='CV-4588',   description='MC-D Heat Exchanger'),
        'EV-4813A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-4813A',  description='LP-B Flow Transmitter'),
        'FT-1916A':     Isolation(type=Isolation.Types.OTHER,       tag='FT-1916A',  description='FL-C Safety Valve'),
        'PCV-4875D':    Isolation(type=Isolation.Types.SELF,        tag='PCV-4875D', description='UT-E Inlet Valve'),
        'EV-3328D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-3328D',  description='EX-E Temp Element'),
        'PCV-9035':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PCV-9035',  description='MC-B Filter'),
        'MOV-1326D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-1326D', description='MC-C Filter'),
        'SDV-3137B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-3137B', description='UT-A Inlet Valve'),
        'HV-3320':      Isolation(type=Isolation.Types.OTHER,       tag='HV-3320',   description='UT-A Breaker'),
        'TV-2655B':     Isolation(type=Isolation.Types.SELF,        tag='TV-2655B',  description='UT-B Safety Valve'),
        'SV-8982E':     Isolation(type=Isolation.Types.SELF,        tag='SV-8982E',  description='HP-E Filter'),
        'EV-4657E':     Isolation(type=Isolation.Types.OTHER,       tag='EV-4657E',  description='HP-D Temp Element'),
        'PZV-3086A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-3086A', description='CD-D Drum'),
        'PSV-3983D':    Isolation(type=Isolation.Types.SELF,        tag='PSV-3983D', description='CD-B Drum'),
        'LV-9129A':     Isolation(type=Isolation.Types.SELF,        tag='LV-9129A',  description='BC-B Breaker'),
        'CV-3750E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-3750E',  description='UT-D Inlet Valve'),
        'BDV-4435A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-4435A', description='UT-C Isolation Valve'),
        'XV-1788C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-1788C',  description='FL-B Junction Box'),
        'TT-7204B':     Isolation(type=Isolation.Types.OTHER,       tag='TT-7204B',  description='FL-A Compressor'),
        'LT-4695A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LT-4695A',  description='BC-A Temp Element'),
        'XV-6221B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-6221B',  description='BC-C Safety Valve'),
        'TV-3636E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-3636E',  description='IN-A Motor Control'),
        'ESD-8909E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-8909E', description='FL-B Filter'),
        'SV-3573':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-3573',   description='UT-B Pressure Transmitter'),
        'SV-9849B':     Isolation(type=Isolation.Types.SELF,        tag='SV-9849B',  description='MP-B Isolation Valve'),
        'PSV-7437D':    Isolation(type=Isolation.Types.OTHER,       tag='PSV-7437D', description='EX-B Outlet Valve'),
        'EV-1062C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-1062C',  description='MP-E Compressor'),
        'SDV-2589':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-2589',  description='HP-C Bypass Valve'),
        'TT-2892B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-2892B',  description='EX-D Flow Transmitter'),
        'FV-9914C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-9914C',  description='UT-D Breaker'),
        'PCV-8303':     Isolation(type=Isolation.Types.SELF,        tag='PCV-8303',  description='EX-D Flow Transmitter'),
        'MOV-5400D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-5400D', description='HP-A Bypass Valve'),
        'EV-9871C':     Isolation(type=Isolation.Types.OTHER,       tag='EV-9871C',  description='LP-E Outlet Valve'),
        'TV-9561C':     Isolation(type=Isolation.Types.OTHER,       tag='TV-9561C',  description='EX-E Level Transmitter'),
        'TT-5896':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-5896',   description='MC-E Drum'),
        'PT-3415':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-3415',   description='HP-B Pressure Transmitter'),
        'SDV-3067':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SDV-3067',  description='BC-D Pressure Transmitter'),
        'HV-5225B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HV-5225B',  description='BC-D Separator'),
        'TV-6343B':     Isolation(type=Isolation.Types.OTHER,       tag='TV-6343B',  description='EX-A Filter'),
        'LT-9561C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-9561C',  description='FL-B Control Valve'),
        'LT-2641':      Isolation(type=Isolation.Types.OTHER,       tag='LT-2641',   description='BC-C Separator'),
        'EV-7732B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-7732B',  description='EX-E Filter'),
        'TT-1613A':     Isolation(type=Isolation.Types.SELF,        tag='TT-1613A',  description='FL-B Filter'),
        'ESD-7581':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-7581',  description='UT-B Outlet Valve'),
        'TT-5400B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-5400B',  description='UT-C Temp Element'),
        'BDV-9054E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-9054E', description='LP-B Temp Element'),
        'HS-6257B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-6257B',  description='CD-A Pressure Transmitter'),
        'HS-4463C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-4463C',  description='IN-C Outlet Valve'),
        'PT-3604':      Isolation(type=Isolation.Types.SELF,        tag='PT-3604',   description='IN-D Control Valve'),
        'PT-1474A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-1474A',  description='LP-A Level Transmitter'),
        'PSV-8478':     Isolation(type=Isolation.Types.SELF,        tag='PSV-8478',  description='LP-C Breaker'),
        'HS-9275C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-9275C',  description='MC-B Breaker'),
        'TT-8308A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-8308A',  description='CD-E Breaker'),
        'EV-3679B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-3679B',  description='MP-A Feeder Panel'),
        'PSV-3669D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-3669D', description='LP-B Pressure Transmitter'),
        'BDV-7709D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-7709D', description='MC-D Control Valve'),
        'PCV-1138A':    Isolation(type=Isolation.Types.SELF,        tag='PCV-1138A', description='CD-C Flow Transmitter'),
        'SV-7168B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-7168B',  description='MP-B Pump'),
        'PZV-9530D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-9530D', description='CD-A Inlet Valve'),
        'PT-7131D':     Isolation(type=Isolation.Types.OTHER,       tag='PT-7131D',  description='CD-C Temp Element'),
        'LV-8892':      Isolation(type=Isolation.Types.SELF,        tag='LV-8892',   description='MP-C Flow Transmitter'),
        'BDV-5895A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-5895A', description='IN-B Outlet Valve'),
        'ESD-7620E':    Isolation(type=Isolation.Types.SELF,        tag='ESD-7620E', description='HP-A Compressor'),
        'PZV-5250C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-5250C', description='FL-A Drum'),
        'LT-4111B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-4111B',  description='IN-D Breaker'),
        'PT-5918A':     Isolation(type=Isolation.Types.OTHER,       tag='PT-5918A',  description='HP-C Isolation Valve'),
        'TT-3096E':     Isolation(type=Isolation.Types.SELF,        tag='TT-3096E',  description='IN-B Motor Control'),
        'FV-4641B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-4641B',  description='MP-D Motor Control'),
        'EV-5269D':     Isolation(type=Isolation.Types.SELF,        tag='EV-5269D',  description='EX-A Compressor'),
        'PSV-2166C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-2166C', description='IN-A Feeder Panel'),
        'PT-5888C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-5888C',  description='HP-B Pressure Transmitter'),
        'CV-7704D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-7704D',  description='HP-C Safety Valve'),
        'FV-8988B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-8988B',  description='UT-A Inlet Valve'),
        'HS-5481A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-5481A',  description='CD-B Compressor'),
        'FV-3120D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-3120D',  description='FL-D Junction Box'),
        'TT-7280':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-7280',   description='IN-B Breaker'),
        'XV-6279D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-6279D',  description='MC-A Level Transmitter'),
        'MOV-6641B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-6641B', description='BC-D Heat Exchanger'),
        'LT-6015A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-6015A',  description='MC-C Temp Element'),
        'HS-9524D':     Isolation(type=Isolation.Types.OTHER,       tag='HS-9524D',  description='UT-D Control Valve'),
        'CV-9031B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-9031B',  description='HP-D Inlet Valve'),
        'MOV-4675E':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-4675E', description='LP-A Drum'),
        'PT-3768':      Isolation(type=Isolation.Types.SELF,        tag='PT-3768',   description='MC-D Flow Transmitter'),
        'FT-1796D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-1796D',  description='BC-A Outlet Valve'),
        'LV-7828C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-7828C',  description='BC-E Flow Transmitter'),
        'TT-3508A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-3508A',  description='MP-D Isolation Valve'),
        'PT-5423D':     Isolation(type=Isolation.Types.OTHER,       tag='PT-5423D',  description='HP-D Isolation Valve'),
        'PT-2928B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-2928B',  description='BC-D Pressure Transmitter'),
        'ESD-4272B':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-4272B', description='LP-C Junction Box'),
        'PZV-3627':     Isolation(type=Isolation.Types.OTHER,       tag='PZV-3627',  description='EX-B Compressor'),
        'CV-4842':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-4842',   description='BC-A Drum'),
        'TT-3443':      Isolation(type=Isolation.Types.OTHER,       tag='TT-3443',   description='BC-A Flow Transmitter'),
        'MOV-8483B':    Isolation(type=Isolation.Types.SELF,        tag='MOV-8483B', description='EX-A Isolation Valve'),
        'PCV-1646B':    Isolation(type=Isolation.Types.SELF,        tag='PCV-1646B', description='UT-D Isolation Valve'),
        'LV-1751':      Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-1751',   description='HP-C Breaker'),
        'HS-5395E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-5395E',  description='UT-C Safety Valve'),
        'LV-7566C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-7566C',  description='MP-D Compressor'),
        'SV-3732':      Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-3732',   description='MC-B Isolation Valve'),
        'SV-8908D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-8908D',  description='HP-E Feeder Panel'),
        'EV-1472E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-1472E',  description='EX-D Isolation Valve'),
        'SV-8220':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-8220',   description='MP-C Inlet Valve'),
        'PT-4669E':     Isolation(type=Isolation.Types.SELF,        tag='PT-4669E',  description='IN-E Filter'),
        'LV-8091E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-8091E',  description='EX-C Feeder Panel'),
        'HV-1894':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-1894',   description='IN-D Compressor'),
        'PCV-2226C':    Isolation(type=Isolation.Types.SELF,        tag='PCV-2226C', description='LP-C Flow Transmitter'),
        'PSV-9305A':    Isolation(type=Isolation.Types.OTHER,       tag='PSV-9305A', description='FL-D Level Transmitter'),
        'FV-8521C':     Isolation(type=Isolation.Types.OTHER,       tag='FV-8521C',  description='EX-A Compressor'),
        'HS-6178':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-6178',   description='MC-A Feeder Panel'),
        'SV-1587D':     Isolation(type=Isolation.Types.OTHER,       tag='SV-1587D',  description='MC-A Filter'),
        'ESD-5990D':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-5990D', description='LP-D Motor Control'),
        'EV-1889A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-1889A',  description='UT-E Filter'),
        'ESD-8751E':    Isolation(type=Isolation.Types.SELF,        tag='ESD-8751E', description='EX-A Isolation Valve'),
        'MOV-1035B':    Isolation(type=Isolation.Types.SELF,        tag='MOV-1035B', description='MP-E Heat Exchanger'),
        'EV-2741':      Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-2741',   description='EX-B Junction Box'),
        'LV-5166D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LV-5166D',  description='LP-A Feeder Panel'),
        'SDV-8488A':    Isolation(type=Isolation.Types.SELF,        tag='SDV-8488A', description='BC-D Outlet Valve'),
        'LT-3018C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LT-3018C',  description='CD-E Control Valve'),
        'TT-1071D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-1071D',  description='IN-D Drum'),
        'TT-9328A':     Isolation(type=Isolation.Types.OTHER,       tag='TT-9328A',  description='HP-B Isolation Valve'),
        'TV-6273D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-6273D',  description='FL-E Level Transmitter'),
        'BDV-7518B':    Isolation(type=Isolation.Types.SELF,        tag='BDV-7518B', description='EX-B Control Valve'),
        'SV-9393B':     Isolation(type=Isolation.Types.OTHER,       tag='SV-9393B',  description='UT-E Pressure Transmitter'),
        'SDV-4435D':    Isolation(type=Isolation.Types.SELF,        tag='SDV-4435D', description='UT-B Safety Valve'),
        'PT-9888E':     Isolation(type=Isolation.Types.SELF,        tag='PT-9888E',  description='BC-C Separator'),
        'TT-7839E':     Isolation(type=Isolation.Types.OTHER,       tag='TT-7839E',  description='MP-D Inlet Valve'),
        'PT-2744':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-2744',   description='HP-A Outlet Valve'),
        'SDV-5374A':    Isolation(type=Isolation.Types.SELF,        tag='SDV-5374A', description='MP-B Outlet Valve'),
        'PZV-4342D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-4342D', description='UT-D Isolation Valve'),
        'ESD-4675E':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-4675E', description='FL-B Heat Exchanger'),
        'PZV-1769C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-1769C', description='FL-C Separator'),
        'PSV-1212E':    Isolation(type=Isolation.Types.SELF,        tag='PSV-1212E', description='LP-E Pump'),
        'MOV-7025D':    Isolation(type=Isolation.Types.OTHER,       tag='MOV-7025D', description='CD-B Pressure Transmitter'),
        'PZV-8353A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-8353A', description='HP-B Heat Exchanger'),
        'LV-7180':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-7180',   description='MP-E Flow Transmitter'),
        'HV-3636D':     Isolation(type=Isolation.Types.SELF,        tag='HV-3636D',  description='MC-C Pump'),
        'HV-1654A':     Isolation(type=Isolation.Types.SELF,        tag='HV-1654A',  description='CD-A Filter'),
        'PZV-9037D':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-9037D', description='UT-A Motor Control'),
        'PT-4603A':     Isolation(type=Isolation.Types.OTHER,       tag='PT-4603A',  description='BC-E Safety Valve'),
        'SV-9897D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-9897D',  description='BC-C Level Transmitter'),
        'SDV-6437B':    Isolation(type=Isolation.Types.SELF,        tag='SDV-6437B', description='MP-B Filter'),
        'PT-8780D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-8780D',  description='BC-C Pump'),
        'MOV-4994':     Isolation(type=Isolation.Types.SELF,        tag='MOV-4994',  description='FL-A Feeder Panel'),
        'BDV-9851E':    Isolation(type=Isolation.Types.SELF,        tag='BDV-9851E', description='MC-E Breaker'),
        'PT-9335C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-9335C',  description='MC-C Pressure Transmitter'),
        'CV-9419':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-9419',   description='HP-E Separator'),
        'XV-2072A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-2072A',  description='FL-A Pressure Transmitter'),
        'FT-8130E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-8130E',  description='HP-A Pump'),
        'CV-1620':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-1620',   description='MC-B Flow Transmitter'),
        'FT-2154D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-2154D',  description='MP-D Feeder Panel'),
        'HS-7626C':     Isolation(type=Isolation.Types.SELF,        tag='HS-7626C',  description='MC-D Isolation Valve'),
        'FT-1096E':     Isolation(type=Isolation.Types.OTHER,       tag='FT-1096E',  description='BC-E Outlet Valve'),
        'FV-6860D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-6860D',  description='MP-C Filter'),
        'FV-5612C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-5612C',  description='FL-A Compressor'),
        'PCV-9740A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-9740A', description='FL-E Temp Element'),
        'HV-5883E':     Isolation(type=Isolation.Types.SELF,        tag='HV-5883E',  description='MC-E Separator'),
        'HV-3019':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='HV-3019',   description='CD-E Feeder Panel'),
        'FT-9970':      Isolation(type=Isolation.Types.SELF,        tag='FT-9970',   description='LP-C Pressure Transmitter'),
        'SV-9397A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-9397A',  description='HP-B Filter'),
        'BDV-4183':     Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-4183',  description='CD-A Separator'),
        'HS-2198B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-2198B',  description='MP-A Pressure Transmitter'),
        'LT-8982B':     Isolation(type=Isolation.Types.SELF,        tag='LT-8982B',  description='HP-B Isolation Valve'),
        'PZV-2143A':    Isolation(type=Isolation.Types.SELF,        tag='PZV-2143A', description='EX-D Motor Control'),
        'ESD-6008E':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-6008E', description='HP-E Drum'),
        'EV-6182C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-6182C',  description='MC-C Level Transmitter'),
        'MOV-8145B':    Isolation(type=Isolation.Types.SELF,        tag='MOV-8145B', description='HP-C Compressor'),
        'HS-8296B':     Isolation(type=Isolation.Types.SELF,        tag='HS-8296B',  description='EX-E Isolation Valve'),
        'PCV-2343B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-2343B', description='IN-B Flow Transmitter'),
        'FV-2235':      Isolation(type=Isolation.Types.OTHER,       tag='FV-2235',   description='MC-E Drum'),
        'TV-4485':      Isolation(type=Isolation.Types.OTHER,       tag='TV-4485',   description='MP-E Separator'),
        'TT-3435B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-3435B',  description='LP-E Temp Element'),
        'HV-8613D':     Isolation(type=Isolation.Types.OTHER,       tag='HV-8613D',  description='BC-D Breaker'),
        'PT-1173E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-1173E',  description='CD-B Heat Exchanger'),
        'HV-8310A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-8310A',  description='CD-E Control Valve'),
        'TT-6878':      Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-6878',   description='EX-B Bypass Valve'),
        'BDV-7052A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-7052A', description='LP-E Breaker'),
        'TV-8695C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-8695C',  description='MC-C Isolation Valve'),
        'PT-5480E':     Isolation(type=Isolation.Types.SELF,        tag='PT-5480E',  description='CD-E Drum'),
        'PCV-7171E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-7171E', description='UT-E Bypass Valve'),
        'PT-5121C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-5121C',  description='IN-D Breaker'),
        'EV-8976C':     Isolation(type=Isolation.Types.OTHER,       tag='EV-8976C',  description='MC-E Control Valve'),
        'HS-3713A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-3713A',  description='IN-C Pressure Transmitter'),
        'HV-4062A':     Isolation(type=Isolation.Types.SELF,        tag='HV-4062A',  description='CD-A Level Transmitter'),
        'SV-6410E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-6410E',  description='EX-D Compressor'),
        'SDV-3641E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='SDV-3641E', description='MC-B Outlet Valve'),
        'HV-3639A':     Isolation(type=Isolation.Types.OTHER,       tag='HV-3639A',  description='MC-E Control Valve'),
        'PSV-3725B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-3725B', description='IN-D Filter'),
        'LT-1305E':     Isolation(type=Isolation.Types.SELF,        tag='LT-1305E',  description='BC-B Pump'),
        'ESD-8723C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-8723C', description='LP-D Filter'),
        'HV-3979D':     Isolation(type=Isolation.Types.OTHER,       tag='HV-3979D',  description='MP-B Motor Control'),
        'HS-2127A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-2127A',  description='FL-B Isolation Valve'),
        'XV-4315D':     Isolation(type=Isolation.Types.OTHER,       tag='XV-4315D',  description='FL-B Filter'),
        'LV-3906C':     Isolation(type=Isolation.Types.OTHER,       tag='LV-3906C',  description='CD-A Separator'),
        'PT-2925':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-2925',   description='HP-E Separator'),
        'XV-8069D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-8069D',  description='UT-A Heat Exchanger'),
        'SV-4759C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-4759C',  description='UT-E Drum'),
        'LV-7971A':     Isolation(type=Isolation.Types.SELF,        tag='LV-7971A',  description='EX-B Bypass Valve'),
        'PZV-9908C':    Isolation(type=Isolation.Types.SELF,        tag='PZV-9908C', description='LP-A Inlet Valve'),
        'LT-9561':      Isolation(type=Isolation.Types.OTHER,       tag='LT-9561',   description='MC-D Pressure Transmitter'),
        'CV-7698B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-7698B',  description='HP-D Drum'),
        'BDV-5281D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-5281D', description='CD-C Filter'),
        'BDV-7511A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-7511A', description='IN-E Compressor'),
        'PCV-7065D':    Isolation(type=Isolation.Types.OTHER,       tag='PCV-7065D', description='EX-C Temp Element'),
        'LT-6641E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LT-6641E',  description='HP-A Level Transmitter'),
        'HS-3650':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-3650',   description='IN-D Motor Control'),
        'FT-1852A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-1852A',  description='MC-A Control Valve'),
        'TT-8133':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-8133',   description='MP-B Breaker'),
        'FV-1618E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-1618E',  description='FL-E Heat Exchanger'),
        'PZV-1941A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-1941A', description='EX-A Pressure Transmitter'),
        'PT-5685A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-5685A',  description='CD-E Heat Exchanger'),
        'MOV-3776E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-3776E', description='UT-B Inlet Valve'),
        'PCV-2422B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PCV-2422B', description='UT-D Feeder Panel'),
        'LT-4281D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-4281D',  description='BC-A Separator'),
        'PZV-6703B':    Isolation(type=Isolation.Types.SELF,        tag='PZV-6703B', description='LP-E Pressure Transmitter'),
        'HS-7618D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-7618D',  description='MP-B Junction Box'),
        'PT-2744D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-2744D',  description='IN-C Motor Control'),
        'LV-9409B':     Isolation(type=Isolation.Types.OTHER,       tag='LV-9409B',  description='CD-C Pump'),
        'TV-8923A':     Isolation(type=Isolation.Types.SELF,        tag='TV-8923A',  description='EX-D Drum'),
        'XV-8896':      Isolation(type=Isolation.Types.SELF,        tag='XV-8896',   description='BC-D Level Transmitter'),
        'MOV-6172C':    Isolation(type=Isolation.Types.SELF,        tag='MOV-6172C', description='IN-E Inlet Valve'),
        'BDV-5067B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-5067B', description='FL-C Bypass Valve'),
        'FT-3924C':     Isolation(type=Isolation.Types.SELF,        tag='FT-3924C',  description='UT-B Drum'),
        'BDV-3994E':    Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-3994E', description='EX-B Level Transmitter'),
        'MOV-5348A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='MOV-5348A', description='LP-B Filter'),
        'EV-3555':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-3555',   description='BC-D Filter'),
        'XV-9871':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-9871',   description='UT-E Motor Control'),
        'TT-5501C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-5501C',  description='IN-C Feeder Panel'),
        'MOV-3101':     Isolation(type=Isolation.Types.OTHER,       tag='MOV-3101',  description='FL-D Separator'),
        'PSV-9232B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-9232B', description='HP-D Isolation Valve'),
        'PT-8537B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='PT-8537B',  description='MC-B Feeder Panel'),
        'LT-2650B':     Isolation(type=Isolation.Types.SELF,        tag='LT-2650B',  description='CD-C Safety Valve'),
        'FT-5306A':     Isolation(type=Isolation.Types.SELF,        tag='FT-5306A',  description='EX-E Motor Control'),
        'EV-4013C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-4013C',  description='LP-D Breaker'),
        'EV-7563B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-7563B',  description='HP-E Control Valve'),
        'LT-4744':      Isolation(type=Isolation.Types.SELF,        tag='LT-4744',   description='LP-E Junction Box'),
        'TV-4212A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-4212A',  description='EX-A Safety Valve'),
        'SV-9185A':     Isolation(type=Isolation.Types.OTHER,       tag='SV-9185A',  description='IN-C Compressor'),
        'PZV-5111D':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-5111D', description='MC-D Isolation Valve'),
        'PCV-1983A':    Isolation(type=Isolation.Types.SELF,        tag='PCV-1983A', description='EX-A Pump'),
        'CV-5256B':     Isolation(type=Isolation.Types.SELF,        tag='CV-5256B',  description='IN-E Flow Transmitter'),
        'EV-1324C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-1324C',  description='UT-E Pressure Transmitter'),
        'LT-9821A':     Isolation(type=Isolation.Types.SELF,        tag='LT-9821A',  description='UT-C Heat Exchanger'),
        'TT-8322':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-8322',   description='CD-C Pump'),
        'HV-3745E':     Isolation(type=Isolation.Types.SELF,        tag='HV-3745E',  description='FL-E Drum'),
        'TV-2168':      Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-2168',   description='UT-B Motor Control'),
        'CV-5773E':     Isolation(type=Isolation.Types.SELF,        tag='CV-5773E',  description='CD-D Flow Transmitter'),
        'HS-6950E':     Isolation(type=Isolation.Types.OTHER,       tag='HS-6950E',  description='IN-D Junction Box'),
        'PCV-4012':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-4012',  description='LP-C Bypass Valve'),
        'SDV-3734C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='SDV-3734C', description='BC-A Compressor'),
        'FT-1881':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-1881',   description='IN-A Isolation Valve'),
        'BDV-3544':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-3544',  description='MP-B Level Transmitter'),
        'PZV-8260E':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PZV-8260E', description='HP-E Safety Valve'),
        'XV-1575E':     Isolation(type=Isolation.Types.SELF,        tag='XV-1575E',  description='UT-D Pump'),
        'FT-5463D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='FT-5463D',  description='HP-E Safety Valve'),
        'LT-8480E':     Isolation(type=Isolation.Types.OTHER,       tag='LT-8480E',  description='FL-E Separator'),
        'PZV-6688C':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-6688C', description='LP-A Pump'),
        'PZV-6992C':    Isolation(type=Isolation.Types.SELF,        tag='PZV-6992C', description='HP-C Inlet Valve'),
        'XV-9574A':     Isolation(type=Isolation.Types.SELF,        tag='XV-9574A',  description='MP-D Separator'),
        'XV-9059C':     Isolation(type=Isolation.Types.SELF,        tag='XV-9059C',  description='MC-D Temp Element'),
        'ESD-4788':     Isolation(type=Isolation.Types.OTHER,       tag='ESD-4788',  description='UT-B Junction Box'),
        'FT-8161C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-8161C',  description='HP-D Feeder Panel'),
        'MOV-5308':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-5308',  description='LP-E Filter'),
        'BDV-5664E':    Isolation(type=Isolation.Types.OTHER,       tag='BDV-5664E', description='MP-D Pressure Transmitter'),
        'FV-3988A':     Isolation(type=Isolation.Types.SELF,        tag='FV-3988A',  description='BC-D Filter'),
        'HS-5458E':     Isolation(type=Isolation.Types.OTHER,       tag='HS-5458E',  description='EX-B Motor Control'),
        'XV-3492':      Isolation(type=Isolation.Types.OTHER,       tag='XV-3492',   description='MC-B Isolation Valve'),
        'PZV-5410A':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-5410A', description='MC-B Bypass Valve'),
        'HV-1241C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-1241C',  description='UT-D Temp Element'),
        'TT-7084C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-7084C',  description='UT-A Control Valve'),
        'PSV-5366C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-5366C', description='IN-D Safety Valve'),
        'SDV-5097C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='SDV-5097C', description='BC-B Feeder Panel'),
        'HS-5049E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-5049E',  description='LP-D Isolation Valve'),
        'PT-4415C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-4415C',  description='MP-C Safety Valve'),
        'PSV-9534':     Isolation(type=Isolation.Types.SELF,        tag='PSV-9534',  description='EX-C Pressure Transmitter'),
        'EV-1853E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-1853E',  description='BC-B Junction Box'),
        'CV-1246A':     Isolation(type=Isolation.Types.SELF,        tag='CV-1246A',  description='CD-A Feeder Panel'),
        'MOV-1146':     Isolation(type=Isolation.Types.OTHER,       tag='MOV-1146',  description='EX-E Control Valve'),
        'EV-2466A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-2466A',  description='EX-A Filter'),
        'CV-1983':      Isolation(type=Isolation.Types.SELF,        tag='CV-1983',   description='HP-E Isolation Valve'),
        'HV-8992A':     Isolation(type=Isolation.Types.SELF,        tag='HV-8992A',  description='IN-C Pump'),
        'SDV-1349E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='SDV-1349E', description='UT-B Flow Transmitter'),
        'PSV-8951E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-8951E', description='IN-C Separator'),
        'TT-4109D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-4109D',  description='IN-C Motor Control'),
        'HS-5510D':     Isolation(type=Isolation.Types.OTHER,       tag='HS-5510D',  description='HP-A Heat Exchanger'),
        'HV-8362B':     Isolation(type=Isolation.Types.SELF,        tag='HV-8362B',  description='IN-C Pump'),
        'XV-9289C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-9289C',  description='MC-E Breaker'),
        'ESD-4912B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-4912B', description='IN-D Pressure Transmitter'),
        'PT-9151D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-9151D',  description='CD-C Motor Control'),
        'SV-6276':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-6276',   description='IN-A Outlet Valve'),
        'HV-3926':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-3926',   description='BC-D Pressure Transmitter'),
        'LV-1521D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-1521D',  description='EX-E Filter'),
        'LT-5193':      Isolation(type=Isolation.Types.SELF,        tag='LT-5193',   description='LP-E Bypass Valve'),
        'XV-4419E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-4419E',  description='BC-D Outlet Valve'),
        'EV-7814B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-7814B',  description='CD-C Heat Exchanger'),
        'PSV-2153B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-2153B', description='LP-E Isolation Valve'),
        'LV-4784D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-4784D',  description='LP-B Heat Exchanger'),
        'MOV-3931D':    Isolation(type=Isolation.Types.OTHER,       tag='MOV-3931D', description='FL-A Drum'),
        'EV-8515E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-8515E',  description='BC-B Safety Valve'),
        'FT-7579D':     Isolation(type=Isolation.Types.SELF,        tag='FT-7579D',  description='HP-E Filter'),
        'HS-6772B':     Isolation(type=Isolation.Types.OTHER,       tag='HS-6772B',  description='UT-C Junction Box'),
        'SV-6299D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='SV-6299D',  description='CD-E Pressure Transmitter'),
        'TV-5162B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-5162B',  description='EX-D Inlet Valve'),
        'PSV-5660D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-5660D', description='IN-B Temp Element'),
        'XV-5920A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='XV-5920A',  description='UT-A Flow Transmitter'),
        'FT-9376D':     Isolation(type=Isolation.Types.OTHER,       tag='FT-9376D',  description='CD-B Isolation Valve'),
        'PSV-8542B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-8542B', description='HP-C Breaker'),
        'LT-5093A':     Isolation(type=Isolation.Types.SELF,        tag='LT-5093A',  description='MP-A Drum'),
        'TV-4562E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-4562E',  description='UT-D Safety Valve'),
        'TT-2562D':     Isolation(type=Isolation.Types.SELF,        tag='TT-2562D',  description='MC-E Feeder Panel'),
        'FV-1916B':     Isolation(type=Isolation.Types.SELF,        tag='FV-1916B',  description='FL-D Isolation Valve'),
        'MOV-1187E':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-1187E', description='MC-C Heat Exchanger'),
        'PSV-6231D':    Isolation(type=Isolation.Types.OTHER,       tag='PSV-6231D', description='HP-C Heat Exchanger'),
        'MOV-3509':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-3509',  description='EX-E Drum'),
        'PT-2475A':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-2475A',  description='MP-D Control Valve'),
        'HV-6507':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-6507',   description='CD-A Separator'),
        'TV-5301':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-5301',   description='IN-D Control Valve'),
        'HV-8879D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-8879D',  description='EX-D Drum'),
        'SDV-9589A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='SDV-9589A', description='BC-C Junction Box'),
        'CV-2467':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='CV-2467',   description='FL-C Breaker'),
        'SDV-6254B':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-6254B', description='MC-C Safety Valve'),
        'EV-8245D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-8245D',  description='EX-A Level Transmitter'),
        'SDV-7124A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='SDV-7124A', description='BC-A Level Transmitter'),
        'ESD-3419B':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='ESD-3419B', description='UT-A Temp Element'),
        'HS-8719':      Isolation(type=Isolation.Types.SELF,        tag='HS-8719',   description='LP-E Pressure Transmitter'),
        'SDV-9952D':    Isolation(type=Isolation.Types.SELF,        tag='SDV-9952D', description='IN-D Filter'),
        'HV-1301C':     Isolation(type=Isolation.Types.OTHER,       tag='HV-1301C',  description='IN-A Flow Transmitter'),
        'PCV-1984B':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-1984B', description='CD-C Outlet Valve'),
        'HS-1136':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-1136',   description='MP-C Isolation Valve'),
        'XV-5792E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-5792E',  description='LP-D Heat Exchanger'),
        'LV-6168C':     Isolation(type=Isolation.Types.OTHER,       tag='LV-6168C',  description='IN-A Safety Valve'),
        'SDV-9202C':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-9202C', description='MC-A Level Transmitter'),
        'PT-5995B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-5995B',  description='FL-B Inlet Valve'),
        'EV-6765B':     Isolation(type=Isolation.Types.SELF,        tag='EV-6765B',  description='LP-E Flow Transmitter'),
        'PSV-5221C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-5221C', description='IN-C Level Transmitter'),
        'HV-6599C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-6599C',  description='BC-D Heat Exchanger'),
        'ESD-4726C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-4726C', description='CD-B Junction Box'),
        'PZV-6395C':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-6395C', description='HP-B Control Valve'),
        'LT-9869E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='LT-9869E',  description='HP-C Heat Exchanger'),
        'HV-8046A':     Isolation(type=Isolation.Types.OTHER,       tag='HV-8046A',  description='HP-C Bypass Valve'),
        'FT-9732E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-9732E',  description='HP-C Control Valve'),
        'XV-6221C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-6221C',  description='MP-D Flow Transmitter'),
        'HV-4079':      Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-4079',   description='HP-A Filter'),
        'ESD-5372D':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-5372D', description='CD-B Filter'),
        'MOV-4783E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-4783E', description='UT-A Compressor'),
        'HV-9230D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-9230D',  description='UT-B Feeder Panel'),
        'TT-8763A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-8763A',  description='LP-B Outlet Valve'),
        'SV-1245B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='SV-1245B',  description='LP-B Pressure Transmitter'),
        'FV-3901C':     Isolation(type=Isolation.Types.OTHER,       tag='FV-3901C',  description='EX-C Pump'),
        'MOV-8005C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-8005C', description='CD-D Motor Control'),
        'TV-9784D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TV-9784D',  description='IN-A Pump'),
        'HS-1694A':     Isolation(type=Isolation.Types.OTHER,       tag='HS-1694A',  description='IN-D Outlet Valve'),
        'FT-7347D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-7347D',  description='LP-C Pump'),
        'TV-5989B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-5989B',  description='HP-D Temp Element'),
        'ESD-1893E':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-1893E', description='HP-D Pump'),
        'FV-9202':      Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-9202',   description='CD-E Control Valve'),
        'TV-7775B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TV-7775B',  description='MC-B Pump'),
        'LT-4308C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-4308C',  description='MP-C Safety Valve'),
        'LV-2494':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-2494',   description='UT-A Heat Exchanger'),
        'TV-9383D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-9383D',  description='FL-E Feeder Panel'),
        'PSV-3799B':    Isolation(type=Isolation.Types.OTHER,       tag='PSV-3799B', description='HP-B Control Valve'),
        'PCV-1840C':    Isolation(type=Isolation.Types.SELF,        tag='PCV-1840C', description='MP-D Temp Element'),
        'PCV-2926A':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-2926A', description='MC-E Flow Transmitter'),
        'XV-8514C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-8514C',  description='IN-A Filter'),
        'TT-4897A':     Isolation(type=Isolation.Types.OTHER,       tag='TT-4897A',  description='EX-D Junction Box'),
        'HS-2300D':     Isolation(type=Isolation.Types.OTHER,       tag='HS-2300D',  description='MC-B Separator'),
        'BDV-4401':     Isolation(type=Isolation.Types.MECHANICAL,  tag='BDV-4401',  description='HP-A Breaker'),
        'PSV-3381':     Isolation(type=Isolation.Types.OTHER,       tag='PSV-3381',  description='CD-C Motor Control'),
        'FV-1803':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='FV-1803',   description='HP-B Temp Element'),
        'ESD-3906C':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-3906C', description='UT-A Bypass Valve'),
        'PZV-6289B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-6289B', description='BC-D Separator'),
        'FV-5797C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-5797C',  description='BC-C Motor Control'),
        'PT-7779D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='PT-7779D',  description='LP-E Outlet Valve'),
        'LV-9666':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-9666',   description='CD-C Junction Box'),
        'ESD-6185B':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-6185B', description='CD-E Breaker'),
        'HV-9132D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-9132D',  description='EX-B Filter'),
        'MOV-5759A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-5759A', description='BC-A Pump'),
        'LV-4396D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-4396D',  description='FL-A Motor Control'),
        'EV-4478':      Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-4478',   description='MP-C Bypass Valve'),
        'PZV-5919D':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-5919D', description='UT-A Isolation Valve'),
        'CV-6592C':     Isolation(type=Isolation.Types.OTHER,       tag='CV-6592C',  description='CD-A Safety Valve'),
        'SDV-6415B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='SDV-6415B', description='EX-A Control Valve'),
        'TT-3545E':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='TT-3545E',  description='IN-C Pump'),
        'SV-1917D':     Isolation(type=Isolation.Types.SELF,        tag='SV-1917D',  description='CD-C Separator'),
        'FT-1306A':     Isolation(type=Isolation.Types.OTHER,       tag='FT-1306A',  description='UT-C Bypass Valve'),
        'HV-5595':      Isolation(type=Isolation.Types.SELF,        tag='HV-5595',   description='FL-E Safety Valve'),
        'LT-7382A':     Isolation(type=Isolation.Types.OTHER,       tag='LT-7382A',  description='BC-C Motor Control'),
        'PSV-5448C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-5448C', description='EX-B Breaker'),
        'HS-5958A':     Isolation(type=Isolation.Types.OTHER,       tag='HS-5958A',  description='MP-B Isolation Valve'),
        'EV-1612A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-1612A',  description='EX-E Inlet Valve'),
        'TT-9192A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-9192A',  description='UT-D Heat Exchanger'),
        'PZV-6363A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-6363A', description='IN-B Pressure Transmitter'),
        'PSV-8526C':    Isolation(type=Isolation.Types.OTHER,       tag='PSV-8526C', description='BC-A Temp Element'),
        'PSV-2426B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PSV-2426B', description='MC-A Heat Exchanger'),
        'PZV-1368D':    Isolation(type=Isolation.Types.SELF,        tag='PZV-1368D', description='LP-C Pressure Transmitter'),
        'SDV-5695B':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-5695B', description='UT-D Isolation Valve'),
        'BDV-3446A':    Isolation(type=Isolation.Types.SELF,        tag='BDV-3446A', description='BC-A Filter'),
        'FT-9422':      Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-9422',   description='IN-C Separator'),
        'CV-5440A':     Isolation(type=Isolation.Types.SELF,        tag='CV-5440A',  description='CD-B Safety Valve'),
        'FV-6101D':     Isolation(type=Isolation.Types.SELF,        tag='FV-6101D',  description='IN-D Outlet Valve'),
        'HV-1475C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='HV-1475C',  description='BC-D Outlet Valve'),
        'FV-7987C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-7987C',  description='CD-E Pump'),
        'ESD-6826B':    Isolation(type=Isolation.Types.SELF,        tag='ESD-6826B', description='LP-E Bypass Valve'),
        'HS-3159':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='HS-3159',   description='BC-D Temp Element'),
        'HS-8709A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HS-8709A',  description='HP-E Flow Transmitter'),
        'EV-7423A':     Isolation(type=Isolation.Types.SELF,        tag='EV-7423A',  description='UT-D Compressor'),
        'XV-2070C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-2070C',  description='UT-D Pump'),
        'PCV-5624B':    Isolation(type=Isolation.Types.OTHER,       tag='PCV-5624B', description='CD-B Heat Exchanger'),
        'LV-7646E':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LV-7646E',  description='UT-E Bypass Valve'),
        'PZV-9728C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='PZV-9728C', description='CD-D Level Transmitter'),
        'ESD-4992D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-4992D', description='EX-D Bypass Valve'),
        'CV-4411E':     Isolation(type=Isolation.Types.OTHER,       tag='CV-4411E',  description='FL-D Drum'),
        'CV-9921E':     Isolation(type=Isolation.Types.MECHANICAL,  tag='CV-9921E',  description='HP-A Drum'),
        'TT-2873D':     Isolation(type=Isolation.Types.OTHER,       tag='TT-2873D',  description='EX-C Separator'),
        'LV-8294A':     Isolation(type=Isolation.Types.SELF,        tag='LV-8294A',  description='FL-A Filter'),
        'LV-7208B':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-7208B',  description='MC-A Pressure Transmitter'),
        'HV-1003A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-1003A',  description='EX-E Temp Element'),
        'TV-8326A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TV-8326A',  description='UT-C Drum'),
        'PZV-8122E':    Isolation(type=Isolation.Types.SELF,        tag='PZV-8122E', description='BC-E Inlet Valve'),
        'ESD-9362C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-9362C', description='MP-A Breaker'),
        'FT-1870':      Isolation(type=Isolation.Types.OTHER,       tag='FT-1870',   description='UT-A Temp Element'),
        'XV-4854C':     Isolation(type=Isolation.Types.OTHER,       tag='XV-4854C',  description='FL-C Feeder Panel'),
        'TV-7251C':     Isolation(type=Isolation.Types.OTHER,       tag='TV-7251C',  description='LP-B Compressor'),
        'HV-4083D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-4083D',  description='UT-D Control Valve'),
        'PZV-3056A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-3056A', description='BC-A Control Valve'),
        'TT-8155A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='TT-8155A',  description='HP-D Pump'),
        'ESD-7974D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='ESD-7974D', description='EX-E Junction Box'),
        'FT-8373C':     Isolation(type=Isolation.Types.SELF,        tag='FT-8373C',  description='LP-B Junction Box'),
        'ESD-1121D':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-1121D', description='LP-E Flow Transmitter'),
        'SV-9948D':     Isolation(type=Isolation.Types.SELF,        tag='SV-9948D',  description='MC-A Drum'),
        'TT-7038':      Isolation(type=Isolation.Types.OTHER,       tag='TT-7038',   description='EX-A Control Valve'),
        'PT-5578C':     Isolation(type=Isolation.Types.OTHER,       tag='PT-5578C',  description='BC-E Filter'),
        'FV-5017C':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FV-5017C',  description='IN-E Temp Element'),
        'ESD-1864B':    Isolation(type=Isolation.Types.OTHER,       tag='ESD-1864B', description='MC-D Pump'),
        'PT-8687D':     Isolation(type=Isolation.Types.SELF,        tag='PT-8687D',  description='FL-C Temp Element'),
        'PZV-3744':     Isolation(type=Isolation.Types.OTHER,       tag='PZV-3744',  description='MP-E Flow Transmitter'),
        'PSV-8752D':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PSV-8752D', description='CD-A Temp Element'),
        'ESD-1447B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='ESD-1447B', description='BC-B Heat Exchanger'),
        'FV-5552B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FV-5552B',  description='CD-C Flow Transmitter'),
        'BDV-1232E':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-1232E', description='CD-B Drum'),
        'HV-8317B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='HV-8317B',  description='MP-B Compressor'),
        'PCV-9640':     Isolation(type=Isolation.Types.SELF,        tag='PCV-9640',  description='BC-B Filter'),
        'HV-9125C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='HV-9125C',  description='LP-D Safety Valve'),
        'SDV-6653':     Isolation(type=Isolation.Types.SELF,        tag='SDV-6653',  description='BC-A Safety Valve'),
        'HS-7533C':     Isolation(type=Isolation.Types.SELF,        tag='HS-7533C',  description='EX-E Level Transmitter'),
        'TV-7390C':     Isolation(type=Isolation.Types.SELF,        tag='TV-7390C',  description='HP-E Junction Box'),
        'XV-5731C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='XV-5731C',  description='UT-E Outlet Valve'),
        'LV-9704E':     Isolation(type=Isolation.Types.SELF,        tag='LV-9704E',  description='FL-E Flow Transmitter'),
        'CV-5429B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-5429B',  description='MP-E Feeder Panel'),
        'HS-4961E':     Isolation(type=Isolation.Types.OTHER,       tag='HS-4961E',  description='LP-E Motor Control'),
        'PCV-6132D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PCV-6132D', description='MC-A Inlet Valve'),
        'SV-2600D':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='SV-2600D',  description='EX-C Level Transmitter'),
        'PZV-5127A':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PZV-5127A', description='MC-E Bypass Valve'),
        'PSV-4552D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='PSV-4552D', description='BC-A Filter'),
        'HV-7159E':     Isolation(type=Isolation.Types.OTHER,       tag='HV-7159E',  description='HP-A Safety Valve'),
        'BDV-5826C':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='BDV-5826C', description='EX-C Junction Box'),
        'CV-5216A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='CV-5216A',  description='MP-A Feeder Panel'),
        'TV-6450':      Isolation(type=Isolation.Types.SELF,        tag='TV-6450',   description='MP-B Pump'),
        'FV-9056A':     Isolation(type=Isolation.Types.OTHER,       tag='FV-9056A',  description='FL-B Compressor'),
        'LV-3357D':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='LV-3357D',  description='LP-E Isolation Valve'),
        'HS-5243':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='HS-5243',   description='BC-A Drum'),
        'BDV-8305':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='BDV-8305',  description='HP-A Outlet Valve'),
        'TV-5365A':     Isolation(type=Isolation.Types.SELF,        tag='TV-5365A',  description='FL-E Inlet Valve'),
        'PT-9039C':     Isolation(type=Isolation.Types.PROTECTIVE,  tag='PT-9039C',  description='FL-A Separator'),
        'MOV-1054C':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='MOV-1054C', description='BC-E Separator'),
        'EV-6463E':     Isolation(type=Isolation.Types.SELF,        tag='EV-6463E',  description='FL-A Bypass Valve'),
        'EV-9759B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='EV-9759B',  description='EX-C Pressure Transmitter'),
        'PCV-1644C':    Isolation(type=Isolation.Types.MECHANICAL,  tag='PCV-1644C', description='MP-D Isolation Valve'),
        'EV-8970':      Isolation(type=Isolation.Types.PROTECTIVE,  tag='EV-8970',   description='LP-B Outlet Valve'),
        'SDV-1415E':    Isolation(type=Isolation.Types.OTHER,       tag='SDV-1415E', description='LP-D Feeder Panel'),
        'FV-9856E':     Isolation(type=Isolation.Types.SELF,        tag='FV-9856E',  description='EX-E Pump'),
        'XV-1606B':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='XV-1606B',  description='UT-A Feeder Panel'),
        'LV-4468E':     Isolation(type=Isolation.Types.OTHER,       tag='LV-4468E',  description='EX-E Control Valve'),
        'LT-4817':      Isolation(type=Isolation.Types.ELECTRICAL,  tag='LT-4817',   description='HP-D Inlet Valve'),
        'TT-1750A':     Isolation(type=Isolation.Types.MECHANICAL,  tag='TT-1750A',  description='MC-B Outlet Valve'),
        'PZV-2594C':    Isolation(type=Isolation.Types.OTHER,       tag='PZV-2594C', description='HP-E Bypass Valve'),
        'LV-2870C':     Isolation(type=Isolation.Types.OTHER,       tag='LV-2870C',  description='CD-B Bypass Valve'),
        'SDV-7983B':    Isolation(type=Isolation.Types.PROTECTIVE,  tag='SDV-7983B', description='UT-A Drum'),
        'FT-3250B':     Isolation(type=Isolation.Types.MECHANICAL,  tag='FT-3250B',  description='MC-E Safety Valve'),
        'CV-2035':      Isolation(type=Isolation.Types.SELF,        tag='CV-2035',   description='HP-D Safety Valve'),
        'EV-3703C':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-3703C',  description='CD-A Control Valve'),
        'LV-7162A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='LV-7162A',  description='EX-A Inlet Valve'),
        'XV-3939':      Isolation(type=Isolation.Types.OTHER,       tag='XV-3939',   description='MP-D Compressor'),
        'HV-4377A':     Isolation(type=Isolation.Types.SELF,        tag='HV-4377A',  description='IN-D Junction Box'),
        'MOV-3859D':    Isolation(type=Isolation.Types.ELECTRICAL,  tag='MOV-3859D', description='CD-B Compressor'),
        'ESD-2442E':    Isolation(type=Isolation.Types.SELF,        tag='ESD-2442E', description='UT-D Inlet Valve'),
        'FT-4860A':     Isolation(type=Isolation.Types.ELECTRICAL,  tag='FT-4860A',  description='IN-A Filter'),
        'EV-9842D':     Isolation(type=Isolation.Types.MECHANICAL,  tag='EV-9842D',  description='EX-B Flow Transmitter'),
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
        
        def toWidget(self):
            from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout

            _colors = {
                PTWData.ApprovalActions.APPROVED: (QColor('green').name()),
                PTWData.ApprovalActions.RETURNED: (QColor('orange').name()),
            }
            color = _colors.get(self.action, '#333333')

            widget = QWidget()
            widget.setStyleSheet(
                f'QWidget {{ border-left: 4px solid {color}; padding-left: 6px; }}'
            )
            lyt = QVBoxLayout()
            lyt.setContentsMargins(4, 4, 4, 4)
            widget.setLayout(lyt)

            lbl = QLabel(str(self))
            lbl.setFont(QFont("Helvetica", 14))
            lbl.setStyleSheet(f'color: {color}; border: none;')
            lyt.addWidget(lbl)

            if self.comment:
                comment_lbl = QLabel(f"Comment: {self.comment}")
                comment_lbl.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
                comment_lbl.setStyleSheet(f'color: {color}; border: none;')
                comment_lbl.setWordWrap(True)
                lyt.addWidget(comment_lbl)

            return widget
    

    __backgroundColors = {
        Types.CW:   QColor( 30,  90, 160, 200),  # blue
        Types.SP:   QColor(200, 165,   0, 200),  # near-yellow
        Types.HT:   QColor(200,  30,  30, 200),  # red
        Types.HC:   QColor( 20,  20,  20, 200),  # near-black (higher alpha for visibility)
        Types.EX:   QColor(100, 100, 100, 200),  # gray
        Types.CS:   QColor( 30, 160, 100, 200),  # green
    }

    __foregroundColors = {
        Types.CW:   QColor('black'),
        Types.SP:   QColor('black'),
        Types.HT:   QColor('black'),
        Types.HC:   QColor('white'),
        Types.EX:   QColor('black'),
        Types.CS:   QColor('black'),
    }

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
    
    @staticmethod
    def backgroundColorForType(ptwType: Types):
        return PTWData.__backgroundColors.get(ptwType) or PTWData.__backgroundColors.get(PTWData.Types.CW)

    @staticmethod
    def foregroundColorForType(ptwType: Types):
        return PTWData.__foregroundColors.get(ptwType) or PTWData.__foregroundColors.get(PTWData.Types.CW)

    def backgroundColor(self):
        return PTWData.__backgroundColors.get(self.type) or PTWData.__backgroundColors.get(PTWData.Types.CW)

    def foregroundColor(self):
        return PTWData.__foregroundColors.get(self.type) or PTWData.__foregroundColors.get(PTWData.Types.CW)
    
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
        if any(isolation.type == Isolation.Types.PROTECTIVE for isolation in self.isolations) and self.mos:
            requiredApprovers.extend([UserRoles.PDH, UserRoles.PGM, UserRoles.SOD, UserRoles.DFGM])
        elif self.type in [PTWData.Types.HT, PTWData.Types.CS]:
            requiredApprovers.extend([UserRoles.PGM, UserRoles.DFGM])
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
