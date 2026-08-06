from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QMessageBox
from models.User import User, UserRoles, UserDepartments

_THEME_OPTIONS = ["Default (System)", "Light", "Dark"]
_THEME_MAP = {None: "Default (System)", "light": "Light", "dark": "Dark"}
_THEME_REVERSE = {"Default (System)": None, "Light": "light", "Dark": "dark"}

SETTINGS_CLOSE_BEHAVIOR_KEY = "app/closeBehavior"
_CLOSE_BEHAVIOR_OPTIONS = ["Always ask", "Minimize to tray", "Exit completely"]
_CLOSE_BEHAVIOR_MAP = {"": "Always ask", "tray": "Minimize to tray", "exit": "Exit completely"}
_CLOSE_BEHAVIOR_REVERSE = {v: k for k, v in _CLOSE_BEHAVIOR_MAP.items()}


class DialogSettings(QDialog):
    def __init__(self, parent, loggedUser: User):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)
        self.loggedUser = loggedUser
        self.new_theme = loggedUser.getTheme()

        self.txtUsername = QLineEdit()
        self.txtPassword = QLineEdit()
        self.txtName = QLineEdit()
        self.txtRole = QComboBox()
        self.txtDepartment = QComboBox()
        self.txtEmail = QLineEdit()
        self.txtExt = QLineEdit()
        self.cmbTheme = QComboBox()
        self.cmbCloseBehavior = QComboBox()

        self.txtRole.addItems([role for role in UserRoles])
        self.txtDepartment.addItems([dept for dept in UserDepartments])
        self.cmbTheme.addItems(_THEME_OPTIONS)
        self.cmbCloseBehavior.addItems(_CLOSE_BEHAVIOR_OPTIONS)
        self.txtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.txtUsername.setText(loggedUser.getUsername())
        self.txtPassword.setPlaceholderText("Leave blank to keep current password")
        self.txtName.setText(loggedUser.getName())
        self.txtRole.setCurrentText(loggedUser.getRole())
        self.txtDepartment.setCurrentText(loggedUser.getDepartment())
        self.txtEmail.setText(loggedUser.getEmail())
        self.txtExt.setText(loggedUser.getExt())
        self.cmbTheme.setCurrentText(_THEME_MAP.get(loggedUser.getTheme(), "Default (System)"))
        savedCloseBehavior = QSettings("PTW", "PTW").value(SETTINGS_CLOSE_BEHAVIOR_KEY, "", type=str)
        self.cmbCloseBehavior.setCurrentText(_CLOSE_BEHAVIOR_MAP.get(savedCloseBehavior, "Always ask"))

        lyt.addRow("Username:", self.txtUsername)
        lyt.addRow("Password:", self.txtPassword)
        lyt.addRow("Name:", self.txtName)
        lyt.addRow("Role:", self.txtRole)
        lyt.addRow("Department:", self.txtDepartment)
        lyt.addRow("Email:", self.txtEmail)
        lyt.addRow("EXT:", self.txtExt)
        lyt.addRow("Theme:", self.cmbTheme)
        lyt.addRow("On close:", self.cmbCloseBehavior)

        self.txtUsername.setEnabled(False)
        self.txtRole.setEnabled(False)
        self.txtDepartment.setEnabled(False)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.collectData)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

    def collectData(self):
        new_pass = self.txtPassword.text()
        if new_pass and len(new_pass) < 8:
            QMessageBox.critical(self, "Error", "Password must be at least 8 characters!")
            return
        self.loggedUser.setPassword(new_pass or None)
        self.loggedUser.setName(self.txtName.text())
        self.loggedUser.setDepartment(self.txtDepartment.currentText())
        self.loggedUser.setEmail(self.txtEmail.text())
        self.loggedUser.setExt(self.txtExt.text())
        self.new_theme = _THEME_REVERSE[self.cmbTheme.currentText()]
        if not self.loggedUser.getName():
            QMessageBox.critical(self, "Error", "Name can't be empty!")
        else:
            QSettings("PTW", "PTW").setValue(
                SETTINGS_CLOSE_BEHAVIOR_KEY, _CLOSE_BEHAVIOR_REVERSE[self.cmbCloseBehavior.currentText()]
            )
            self.accept()