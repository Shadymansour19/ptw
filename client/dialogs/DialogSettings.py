"""Logged-in user's own Settings dialog: profile fields, theme, and close-behavior preference."""

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QComboBox, QDialogButtonBox, QMessageBox
from models.User import User, UserRoles, UserDepartments
from helper.i18n import t

_THEME_OPTIONS = ["Default (System)", "Light", "Dark"]
_THEME_MAP = {None: "Default (System)", "light": "Light", "dark": "Dark"}
_THEME_REVERSE = {"Default (System)": None, "Light": "light", "Dark": "dark"}

_LANGUAGE_OPTIONS = ["Default (System)", "English", "Arabic"]
_LANGUAGE_MAP = {None: "Default (System)", "en": "English", "ar": "Arabic"}
_LANGUAGE_REVERSE = {"Default (System)": None, "English": "en", "Arabic": "ar"}

SETTINGS_CLOSE_BEHAVIOR_KEY = "app/closeBehavior"
_CLOSE_BEHAVIOR_OPTIONS = ["Always ask", "Minimize to tray", "Exit completely"]
_CLOSE_BEHAVIOR_MAP = {"": "Always ask", "tray": "Minimize to tray", "exit": "Exit completely"}
_CLOSE_BEHAVIOR_REVERSE = {v: k for k, v in _CLOSE_BEHAVIOR_MAP.items()}


class DialogSettings(QDialog):
    """Edit the logged-in user's own profile (name, password, department, email, extension),
    theme, language, and the "on close" behavior preference (always ask / minimize to tray /
    exit), the latter stored locally via QSettings and consulted by MainWindow.closeEvent()."""

    def __init__(self, parent, loggedUser: User):
        """Build the form, prefilled from `loggedUser` and the saved close-behavior QSettings value.

        Args:
            parent: Parent widget.
            loggedUser: The currently logged-in user; mutated in place on accept
                (password/name/department/email/extension only - role and
                department combos are shown but disabled).
        """
        super().__init__(parent)
        self.setWindowTitle(t("Settings"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)
        self.loggedUser = loggedUser
        self.new_theme = loggedUser.getTheme()
        self.new_language = loggedUser.getLanguage()

        self.txtUsername = QLineEdit()
        self.txtPassword = QLineEdit()
        self.txtName = QLineEdit()
        self.txtRole = QComboBox()
        self.txtDepartment = QComboBox()
        self.txtEmail = QLineEdit()
        self.txtExt = QLineEdit()
        self.cmbTheme = QComboBox()
        self.cmbLanguage = QComboBox()
        self.cmbCloseBehavior = QComboBox()

        self.txtRole.addItems([role for role in UserRoles])
        self.txtDepartment.addItems([dept for dept in UserDepartments])
        self.cmbTheme.addItems(_THEME_OPTIONS)
        self.cmbLanguage.addItems(_LANGUAGE_OPTIONS)
        self.cmbCloseBehavior.addItems(_CLOSE_BEHAVIOR_OPTIONS)
        self.txtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.txtUsername.setText(loggedUser.getUsername())
        self.txtPassword.setPlaceholderText(t("Leave blank to keep current password"))
        self.txtName.setText(loggedUser.getName())
        self.txtRole.setCurrentText(loggedUser.getRole())
        self.txtDepartment.setCurrentText(loggedUser.getDepartment())
        self.txtEmail.setText(loggedUser.getEmail())
        self.txtExt.setText(loggedUser.getExt())
        self.cmbTheme.setCurrentText(_THEME_MAP.get(loggedUser.getTheme(), "Default (System)"))
        self.cmbLanguage.setCurrentText(_LANGUAGE_MAP.get(loggedUser.getLanguage(), "Default (System)"))
        savedCloseBehavior = QSettings("PTW", "PTW").value(SETTINGS_CLOSE_BEHAVIOR_KEY, "", type=str)
        self.cmbCloseBehavior.setCurrentText(_CLOSE_BEHAVIOR_MAP.get(savedCloseBehavior, "Always ask"))

        lyt.addRow(t("Username:"), self.txtUsername)
        lyt.addRow(t("Password:"), self.txtPassword)
        lyt.addRow(t("Name:"), self.txtName)
        lyt.addRow(t("Role:"), self.txtRole)
        lyt.addRow(t("Department:"), self.txtDepartment)
        lyt.addRow(t("Email:"), self.txtEmail)
        lyt.addRow(t("EXT:"), self.txtExt)
        lyt.addRow(t("Theme:"), self.cmbTheme)
        lyt.addRow(t("Language:"), self.cmbLanguage)
        lyt.addRow(t("On close:"), self.cmbCloseBehavior)

        self.txtUsername.setEnabled(False)
        self.txtRole.setEnabled(False)
        self.txtDepartment.setEnabled(False)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.collectData)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

    def collectData(self):
        """Apply the form fields to `loggedUser`, persist the close-behavior choice, and accept.

        Triggered by the OK button. Validates the new password's minimum length
        (if one was entered) and that the name isn't blank before saving the
        close-behavior preference to QSettings and calling accept(); otherwise
        shows an error and leaves the dialog open.
        """
        new_pass = self.txtPassword.text()
        if new_pass and len(new_pass) < 8:
            QMessageBox.critical(self, t("Error"), t("Password must be at least 8 characters!"))
            return
        self.loggedUser.setPassword(new_pass or None)
        self.loggedUser.setName(self.txtName.text())
        self.loggedUser.setDepartment(self.txtDepartment.currentText())
        self.loggedUser.setEmail(self.txtEmail.text())
        self.loggedUser.setExt(self.txtExt.text())
        self.new_theme = _THEME_REVERSE[self.cmbTheme.currentText()]
        self.new_language = _LANGUAGE_REVERSE[self.cmbLanguage.currentText()]
        if not self.loggedUser.getName():
            QMessageBox.critical(self, t("Error"), t("Name can't be empty!"))
        else:
            QSettings("PTW", "PTW").setValue(
                SETTINGS_CLOSE_BEHAVIOR_KEY, _CLOSE_BEHAVIOR_REVERSE[self.cmbCloseBehavior.currentText()]
            )
            self.accept()