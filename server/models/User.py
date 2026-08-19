"""Server-side user model: role/department enums and the User/SecuredUser data classes.

Mirrors client/models/User.py.
"""

import enum


class UserRoles(enum.StrEnum):
    """The 11 permission roles a user account can hold, enforced by the API layer for access control."""

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
    """The fixed set of department values selectable for a real user account.

    Guests self-report a free-text department instead of choosing from this list.
    """

    TURBO = 'Turbo'
    MECH = 'Mech'
    ELEC = 'Elec'
    IT = 'IT'
    PROD = 'Prod'
    SAFETY = 'Safety'
    INST = 'Instrumentation'
    HVAC = 'HVAC'
    CVL = 'Civil'
    TELECOM = 'Telecom'
    PROJECT  = 'Project'
    CATHODIC_PROTECTION = 'Cathodic Protection'
    PTRJ = 'Petrojet'
    PTRM = 'Petromaint'
    EGAS = 'Egypt Gas'
    CTR = 'Contractor'


class SecuredUser:
    """Redacted user view returned by user-listing endpoints, e.g. `getSecuredUser`/`getAllSecuredUsers`.

    Holds only the public profile fields — notably no `password` — so it is
    the shape safe to serialize back to any authenticated client; the server
    never returns a password hash in any API response.
    """

    def __init__(self, username: str='', name: str='', role: UserRoles=None, department: str='', email: str='', ext: str='', is_active: bool=True):
        """Initialize the profile fields, all defaulting to empty/inactive-safe values."""
        self.username = username
        self.name = name
        self.role = role
        self.department = department
        self.email = email
        self.ext = ext
        self.is_active = is_active

    def setAll(self, data: dict):
        """Bulk-assign matching attributes from `data` (e.g. a DB row), ignoring unknown keys and failed assignments.

        Returns:
            self, for chaining.
        """
        for k,v in data.items():
            if hasattr(self, k):
                try:
                    setattr(self, k, v)
                except Exception as e:
                    pass
        return self

    def setUsername(self, username: str):
        """Set the username and return self for chaining."""
        self.username = username
        return self
    
    def setName(self, name: str):
        """Set the display name and return self for chaining."""
        self.name = name
        return self
    
    def setRole(self, role: UserRoles):
        """Set the role and return self for chaining."""
        self.role = role
        return self
    
    def setDepartment(self, department: str):
        """Set the department and return self for chaining."""
        self.department = department
        return self

    def setEmail(self, email: str):
        """Set the email address and return self for chaining."""
        self.email = email
        return self
    
    def setExt(self, ext: str):
        """Set the phone extension and return self for chaining."""
        self.ext = ext
        return self

    def setIsActive(self, is_active: bool):
        """Set the active flag and return self for chaining."""
        self.is_active = is_active
        return self

    def getUsername(self):
        """Return the username."""
        return self.username
    
    def getName(self):
        """Return the display name."""
        return self.name
    
    def getRole(self):
        """Return the role."""
        return self.role
    
    def getDepartment(self):
        """Return the department."""
        return self.department
    
    def getEmail(self):
        """Return the email address."""
        return self.email
    
    def getExt(self):
        """Return the phone extension."""
        return self.ext

    def getIsActive(self):
        """Return whether the account is active."""
        return self.is_active


class User(SecuredUser):
    """Full user model backing the `users` table, adding the bcrypt password hash, theme
    preference, and the must-change-password flag.

    Used internally for authentication (`getVerifiedUser`) and persistence;
    outward-facing responses about *other* users use `SecuredUser` instead so
    the password hash never leaves the server. `must_change_password` lives
    here rather than on `SecuredUser` for the same reason: whether an account
    is being forced to change its password is only relevant/visible to that
    account's own session (returned via the login response), never surfaced
    to other users browsing the user list.
    """

    def __init__(self, username = '', password = '', name = '', role = None, department = '', email = ''):
        """Initialize the base profile fields plus password, a null theme/language, and
        must_change_password defaulting to False."""
        super().__init__(username, name, role, department, email)
        self.password = password
        self.theme: str | None = None
        self.language: str | None = None
        self.must_change_password: bool = False

    def setPassword(self, password: str):
        """Set the password (hash) and return self for chaining."""
        self.password = password
        return self

    def getPassword(self):
        """Return the password (hash)."""
        return self.password

    def setTheme(self, theme: str | None):
        """Set the client UI theme preference and return self for chaining."""
        self.theme = theme
        return self

    def getTheme(self) -> str | None:
        """Return the client UI theme preference, or None if unset."""
        return self.theme

    def setLanguage(self, language: str | None):
        """Set the client UI language preference (e.g. 'en'/'ar') and return self for chaining."""
        self.language = language
        return self

    def getLanguage(self) -> str | None:
        """Return the client UI language preference, or None if unset (falls back to the OS locale)."""
        return self.language

    def setMustChangePassword(self, must_change_password: bool):
        """Set the must-change-password flag and return self for chaining."""
        self.must_change_password = must_change_password
        return self

    def getMustChangePassword(self) -> bool:
        """Return whether this account must change its password before proceeding past login."""
        return self.must_change_password