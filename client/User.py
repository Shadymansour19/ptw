import enum


class UserRoles(enum.StrEnum):
    USER = 'User'
    COORDINATOR = 'Coordinator'
    ISSUING = 'Issuing'
    SAFETY = 'Safety'
    PDH = 'PDH'
    PGM = 'PGM'
    SOD = 'SOD'
    DFGM = 'DFGM'
    ISOLATOR = 'Isolator'
    GUEST = 'Guest'
    ADMIN = 'Admin'


class UserDepartments(enum.StrEnum):
    TURBO = 'Turbo'
    MECH = 'Mech'
    ELEC = 'Elec'
    IT = 'IT'
    PROD = 'Prod'
    SAFETY = 'Safety'
    INST = 'Instrumentation'
    HVAC = 'HVAC'
    CVL = 'Civil'
    PTRJ = 'Petrojet'
    PTRM = 'Petromaint'
    EGAS = 'Egypt Gas'
    CTR = 'Contractor'


class SecuredUser:
    def __init__(self, username: str='', name: str='', role: UserRoles=None, department: str='', email: str='', ext: str='', is_active: bool=True):
        self.username = username
        self.name = name
        self.role = role
        self.department = department
        self.email = email
        self.ext = ext
        self.is_active = is_active

    def setAll(self, data: dict):
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except Exception as e:
                    pass
        return self

    def setUsername(self, username: str):
        self.username = username
        return self
    
    def setName(self, name: str):
        self.name = name
        return self
    
    def setRole(self, role: UserRoles):
        self.role = role
        return self
    
    def setDepartment(self, department: str):
        self.department = department
        return self

    def setEmail(self, email: str):
        self.email = email
        return self
    
    def setExt(self, ext: str):
        self.ext = ext
        return self

    def setIsActive(self, is_active: bool):
        self.is_active = is_active
        return self

    def getUsername(self):
        return self.username
    
    def getName(self):
        return self.name
    
    def getRole(self):
        return self.role
    
    def getDepartment(self):
        return self.department
    
    def getEmail(self):
        return self.email
    
    def getExt(self):
        return self.ext

    def getIsActive(self):
        return self.is_active


class User(SecuredUser):
    def __init__(self, username = '', password = '', name = '', role = None, department = '', email = ''):
        super().__init__(username, name, role, department, email)
        self.password = password
        self.theme: str | None = None

    def setPassword(self, password: str):
        self.password = password
        return self

    def getPassword(self):
        return self.password

    def setTheme(self, theme: str | None):
        self.theme = theme
        return self

    def getTheme(self) -> str | None:
        return self.theme