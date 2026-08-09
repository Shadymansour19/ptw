"""Login screen: username/password authentication, optional remembered-credential storage via
keyring, the forgot-password/reset flow, and guest login entry.

`LoginWindow` has its own `closeEvent` (quitting the whole app) since there is no system-tray
or background-notification concept before a user is logged in.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QSize, QSettings
from PyQt6.QtWidgets import (QLineEdit, QToolButton, QDialog, QFormLayout, QLabel,
                              QPushButton, QCheckBox, QDialogButtonBox,
                              QMessageBox, QMainWindow, QWidget, QSizePolicy, QApplication,
                              QHBoxLayout)
import keyring
from keyring.errors import KeyringError
import qtawesome as qta

from widgets.SearchableComboBox import SearchableComboBox
from widgets.RefreshOverlay import RefreshOverlay


SERVICE_NAME = "PTW-login-credentials"
SETTINGS_REMEMBERED_USERS_KEY = "login/rememberedUsernames"


class PasswordLineEdit(QLineEdit):
    """A QLineEdit for entering a password, with a built-in eye-icon button overlaid on
    its right edge to toggle showing the password in plain text."""

    def __init__(self, parent=None):
        """Build the line edit in password-echo mode with the show/hide toggle button overlaid."""
        super().__init__(parent)

        self._visible = False
        self._icons = [qta.icon('fa6.eye'), qta.icon('fa6.eye-slash')]

        self._btn = QToolButton(self)
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setToolTip("Show / hide password")
        self._btn.clicked.connect(self._toggle_visibility)

        btn_size = 28
        self._btn.setFixedSize(btn_size, btn_size)
        self._btn.setStyleSheet(
            "QToolButton {"
            "  border: none;"
            "  background: transparent;"
            "  padding: 0;"
            "}"
            "QToolButton:hover { background: rgba(0,0,0,0.06); border-radius: 4px; }"
            "QToolButton:pressed { background: rgba(0,0,0,0.12); border-radius: 4px; }"
        )

        self.setEchoMode(QLineEdit.EchoMode.Password)
        self._update_icon()
        self._adjust_text_margins()

    def _toggle_visibility(self):
        """Slot for the eye-icon button click: flip between masked and plain-text echo mode
        and update the icon to match."""
        self._visible = not self._visible
        self.setEchoMode(QLineEdit.EchoMode.Normal if self._visible else QLineEdit.EchoMode.Password)
        self._update_icon()

    def _update_icon(self):
        """Set the toggle button's icon (eye / eye-slash) to match the current visibility state."""
        self._btn.setIcon(self._icons[0] if self._visible else self._icons[1])
        self._btn.setIconSize(QSize(18, 18))

    def _adjust_text_margins(self):
        """Reserve space on the right of the text field so typed text never runs under the
        overlaid toggle button."""
        btn_w = self._btn.width()
        self.setTextMargins(0, 0, btn_w + 4, 0)

    def resizeEvent(self, event):
        """Qt event handler: keep the toggle button pinned inside the field's right edge
        whenever the widget is resized."""
        super().resizeEvent(event)
        btn_w = self._btn.width()
        btn_h = self._btn.height()
        x = self.width() - btn_w - 4
        y = (self.height() - btn_h) // 2
        self._btn.move(x, y)



class ResetPasswordDialog(QDialog):
    """Modal dialog for the forgot-password flow: triggers sending a verification code to the
    user's registered email, then collects that code plus a new password (entered twice)."""

    def __init__(self, username: str, parent=None):
        """Build the dialog for `username`, immediately request a verification code from the
        server, and keep the code/password fields disabled until the send is confirmed."""
        super().__init__(parent)
        self.setWindowTitle("Reset Password")

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.boxUsername = QLineEdit()
        self.boxCode = QLineEdit()
        self.boxNewPassword = PasswordLineEdit()
        self.boxConfirmPassword = PasswordLineEdit()
        self.lblStatus = QLabel()

        self.boxUsername.setText(username)
        self.boxUsername.setReadOnly(True)
        self.boxCode.setPlaceholderText("Enter verification code")
        self.boxNewPassword.setPlaceholderText("Enter a new password")
        self.boxConfirmPassword.setPlaceholderText("Repeat your new password")

        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btns.accepted.connect(self.resetPassword)
        self.btns.rejected.connect(self.reject)

        lyt.addRow("Username", self.boxUsername)
        lyt.addRow("6-digit Code", self.boxCode)
        lyt.addRow("New Password", self.boxNewPassword)
        lyt.addRow("Confirm Password", self.boxConfirmPassword)
        lyt.addRow(self.lblStatus)
        lyt.addRow(self.btns)

        self._refreshOverlay = RefreshOverlay(self)
        self._setFormEnabled(False)

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                self.lblStatus.setText("Error sending verification code. Please try again later.")
                QMessageBox.warning(self, "Error", err)
                self._setFormEnabled(False)
                self.reject()
            else:
                self.lblStatus.setText("Verification code sent. Check your email.")
                self._setFormEnabled(True)
                self.boxCode.setFocus()

        from network.clientRequests import ClientRequests
        self._refreshOverlay.showBusy()
        ClientRequests.requestResetPassword(username, callback=on_done)

    def _setFormEnabled(self, enabled: bool):
        """Enable or disable the code/new-password/confirm-password fields and the OK button together."""
        self.boxCode.setEnabled(enabled)
        self.boxNewPassword.setEnabled(enabled)
        self.boxConfirmPassword.setEnabled(enabled)
        self.btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)

    def resetPassword(self):
        """Slot for the OK button (`btns.accepted`): validate that a new password was entered
        and matches its confirmation, then accept the dialog for the caller to submit the reset."""
        self.verificationCode = self.boxCode.text()
        self.newPassword = self.boxNewPassword.text()
        confirmPassword = self.boxConfirmPassword.text()

        if not self.newPassword:
            QMessageBox.warning(self, "Error", "Please enter a new password.")
            return

        if self.newPassword != confirmPassword:
            QMessageBox.warning(self, "Error", "Passwords do not match.")
            return

        self.accept()


class GuestDetailsDialog(QDialog):
    """Modal dialog prompting an unauthenticated guest for a display name and department,
    used to build an ephemeral GUEST-role session."""

    def __init__(self, departments, parent=None):
        """Build the guest-details form: a free-text name field and a department combo box
        populated from `departments`."""
        super().__init__(parent)
        self.setWindowTitle("Continue as Guest")

        self.boxName = QLineEdit()
        self.boxName.setPlaceholderText("Enter your full name")

        self.boxDepartment = SearchableComboBox()
        self.boxDepartment.setItems([str(dept) for dept in departments])

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        lyt.addRow("Name", self.boxName)
        lyt.addRow("Department", self.boxDepartment)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._onAccept)
        btns.rejected.connect(self.reject)
        lyt.addRow(btns)

    def _onAccept(self):
        """Slot for the OK button (`btns.accepted`): reject with a warning if no name was
        entered, otherwise accept the dialog."""
        if not self.boxName.text().strip():
            QMessageBox.warning(self, "Error", "Please enter your name.")
            return
        self.accept()

    def getName(self) -> str:
        """Return the entered guest name, stripped of surrounding whitespace."""
        return self.boxName.text().strip()

    def getDepartment(self):
        """Return the selected/entered department text."""
        return self.boxDepartment.currentText()


class LoginWindow(QMainWindow):
    """Main login window: username/password authentication (with optional remembered
    credentials via keyring), the forgot-password flow, and guest login; emits
    `on_login_success` once a user is authenticated (real or guest)."""

    on_login_success = pyqtSignal(object)
    
    def __init__(self, parent=None):
        """Build the login window's UI (username/password fields, remember-me checkbox,
        forgot-password link, Login/Guest/Cancel buttons) and load any remembered usernames
        into the username combo."""
        super().__init__(parent)
        self.setWindowTitle("PTW Login")
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)

        container = QWidget()
        self.setCentralWidget(container)

        self.boxUsername = SearchableComboBox()
        self.boxPassword = PasswordLineEdit()
        self.btnRememberMe = QCheckBox('Remember me')
        self.btnForgotPassword = QPushButton('Forgot Password?')
        
        self.btnRememberMe.setChecked(True)
        self.boxUsername.setPlaceholderText("Enter username")
        self.boxPassword.setPlaceholderText("Enter password")
        self.btnForgotPassword.setStyleSheet('''
            QPushButton { border: none; background: transparent; color: palette(link); }
            QPushButton:hover { text-decoration: underline;}
            QPushButton:pressed { color: palette(highlight); }
        ''')
        self.btnForgotPassword.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnForgotPassword.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

        self.boxUsername.lineEdit().returnPressed.connect(self.login)
        self.boxUsername.itemSelected.connect(self._onUsernameSelected)
        self.boxPassword.returnPressed.connect(self.login)
        self.btnForgotPassword.clicked.connect(self.forgotPassword)

        self.btnCancel = QPushButton(qta.icon('fa5s.times'), "&Cancel")
        self.btnLogin = QPushButton(qta.icon('fa6s.arrow-right-to-bracket'), "&Login")
        self.btnGuest = QPushButton(qta.icon('fa5s.user'), "Login as a &Guest")

        self.btnCancel.clicked.connect(self.close)
        self.btnLogin.clicked.connect(self.login)
        self.btnGuest.clicked.connect(self.loginAsGuest)

        btnLayout = QHBoxLayout()
        btnLayout.addWidget(self.btnCancel)
        btnLayout.addWidget(self.btnLogin)
        btnLayout.addWidget(self.btnGuest)

        mainLayout = QFormLayout()
        mainLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        container.setLayout(mainLayout)

        mainLayout.addRow("Username", self.boxUsername)
        mainLayout.addRow("Password", self.boxPassword)
        mainLayout.addRow(self.btnForgotPassword)
        mainLayout.addRow(self.btnRememberMe)

        mainLayout.setAlignment(self.btnRememberMe, Qt.AlignmentFlag.AlignCenter)
        mainLayout.setAlignment(self.btnForgotPassword, Qt.AlignmentFlag.AlignCenter)

        self._populateRememberedUsers()

        mainLayout.addRow(btnLayout)

        self.adjustSize()
        self.setFixedHeight(self.height())
        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

        self._refreshOverlay = RefreshOverlay(self)

    def showHidePassword(self):
        """Set the password field's echo mode to plain-text or masked based on `btnShowPassword`'s checked state."""
        self.boxPassword.setEchoMode(QLineEdit.EchoMode.Normal if self.btnShowPassword.isChecked() else QLineEdit.EchoMode.Password)

    def _rememberedUsernames(self) -> list[str]:
        """Return the list of previously remembered usernames stored in QSettings."""
        value = QSettings("PTW", "PTW").value(SETTINGS_REMEMBERED_USERS_KEY, [], type=list)
        return [str(v) for v in value] if value else []

    def storeLoginCredentials(self, username: str, password: str):
        """Save `username`/`password` in the OS keyring and move `username` to the front
        of the remembered-usernames list in QSettings."""
        try:
            keyring.set_password(SERVICE_NAME, username, password)
        except KeyringError as e:
            raise e

        usernames = self._rememberedUsernames()
        if username in usernames:
            usernames.remove(username)
        usernames.insert(0, username)
        QSettings("PTW", "PTW").setValue(SETTINGS_REMEMBERED_USERS_KEY, usernames)

    def retrieveLoginCredentials(self, username: str) -> str:
        """Look up and return `username`'s stored password from the OS keyring (None if absent)."""
        try:
            return keyring.get_password(SERVICE_NAME, username)
        except KeyringError as e:
            raise e

    def forgetLoginCredentials(self, username: str):
        """Remove `username` from the remembered-usernames list and delete its stored
        password from the OS keyring."""
        usernames = self._rememberedUsernames()
        if username in usernames:
            usernames.remove(username)
            QSettings("PTW", "PTW").setValue(SETTINGS_REMEMBERED_USERS_KEY, usernames)
        try:
            keyring.delete_password(SERVICE_NAME, username)
        except KeyringError:
            pass

    def _populateRememberedUsers(self):
        """Refill the username combo from the remembered-usernames list and pre-fill the
        password field for the most recently used username."""
        usernames = self._rememberedUsernames()
        self.boxUsername.setItems(usernames)
        self.boxPassword.clear()
        if usernames:
            self._fillPasswordFor(usernames[0])

    def _fillPasswordFor(self, username: str):
        """Look up `username`'s stored password via the keyring and set it in the password
        field (blank if unavailable)."""
        try:
            password = self.retrieveLoginCredentials(username)
        except KeyringError:
            password = None
        self.boxPassword.setText(password or '')

    def _onUsernameSelected(self, username: str):
        """Slot for the username combo's `itemSelected` signal: fill in the stored password
        if `username` is remembered, otherwise clear the password field."""
        if username in self._rememberedUsernames():
            self._fillPasswordFor(username)
        else:
            self.boxPassword.clear()

    def forgotPassword(self):
        """Slot for the Forgot Password button: open `ResetPasswordDialog` for the entered
        username and, once its fields are accepted, submit the reset request to the server."""
        from network.clientRequests import ClientRequests

        username = self.boxUsername.currentText()
        if not username:
            QMessageBox.warning(self, "Error", "Please enter your username to reset your password.")
            return

        dlg = ResetPasswordDialog(username, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, "Error", err)
            else:
                QMessageBox.information(self, "Success", "Your password has been reset successfully. You can now log in with your new password.")

        self._refreshOverlay.showBusy()
        ClientRequests.resetPassword(username, dlg.newPassword, dlg.verificationCode, callback=on_done)
    
    def reset(self):
        """Reset the window to its just-opened state: repopulate remembered usernames and
        focus the username field. Called when returning to this window after a logout."""
        self._populateRememberedUsers()
        self.boxUsername.setFocus()

    def closeEvent(self, event):
        """Qt event handler for the window's close button: accept the close and quit the
        whole application, since there is no tray/background concept before login."""
        event.accept()
        QApplication.instance().quit()

    def login(self):
        """Slot for the Login button (and Enter in either field): submit the entered
        credentials to the server, and on success optionally remember them, apply the
        user's saved theme, and emit `on_login_success`."""
        from network.clientRequests import ClientRequests

        username = self.boxUsername.currentText()
        password : str = self.boxPassword.text()

        def on_done(err, user):
            self._refreshOverlay.hideBusy()
            if err is not None:
                QMessageBox.warning(self, "Error", err)
                return

            if self.btnRememberMe.isChecked():
                try:
                    self.storeLoginCredentials(username, password)
                except KeyringError as e:
                    QMessageBox.warning(self, "Error", str(e))

            theme = user.getTheme()
            if theme == 'dark':
                QApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
            elif theme == 'light':
                QApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)

            self.on_login_success.emit(user)

        self._refreshOverlay.showBusy()
        ClientRequests.login(username, password, callback=on_done)

    def loginAsGuest(self):
        """Slot for the Login as Guest button: prompt for a name and department via
        `GuestDetailsDialog`, then emit `on_login_success` with an ephemeral GUEST-role
        `User` built from that input."""
        from models.User import User, UserRoles, UserDepartments

        dlg = GuestDetailsDialog(list(UserDepartments), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = dlg.getName()
        department = dlg.getDepartment()
        user = User(username=name, name=name, role=UserRoles.GUEST, department=department, email='')

        self.on_login_success.emit(user)