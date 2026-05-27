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
    ADMIN = 'Admin'


class UserDepartments(enum.StrEnum):
    TURBO = 'Turbo'
    MECH = 'Mech'
    ELEC = 'Elec'
    IT = 'IT'
    PROD = 'Prod'
    SAFETY = 'Safety'


class SecuredUser:
    def __init__(self, username: str='', name: str='', role: UserRoles=None, department: str='', email: str='', ext: str=''):
        self.username = username
        self.name = name
        self.role = role
        self.department = department
        self.email = email
        self.ext = ext
    
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