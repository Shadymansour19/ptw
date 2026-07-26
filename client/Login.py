from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QSize, QSettings
from PyQt6.QtWidgets import (QLineEdit, QToolButton, QDialog, QFormLayout, QLabel,
                              QStackedWidget, QPushButton, QCheckBox, QDialogButtonBox,
                              QMessageBox, QMainWindow, QWidget, QSizePolicy, QApplication, QStyle,
                              QHBoxLayout)
import keyring
from keyring.errors import KeyringError
import qtawesome as qta

from SearchableComboBox import SearchableComboBox


SERVICE_NAME = "PTW-login-credentials"
SETTINGS_REMEMBERED_USERS_KEY = "login/rememberedUsernames"


class PasswordLineEdit(QLineEdit):
    def __init__(self, parent=None):
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
        self._visible = not self._visible
        self.setEchoMode(QLineEdit.EchoMode.Normal if self._visible else QLineEdit.EchoMode.Password)
        self._update_icon()

    def _update_icon(self):
        self._btn.setIcon(self._icons[0] if self._visible else self._icons[1])
        self._btn.setIconSize(QSize(18, 18))

    def _adjust_text_margins(self):
        btn_w = self._btn.width()
        self.setTextMargins(0, 0, btn_w + 4, 0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        btn_w = self._btn.width()
        btn_h = self._btn.height()
        x = self.width() - btn_w - 4
        y = (self.height() - btn_h) // 2
        self._btn.move(x, y)



class _ResetRequestWorker(QObject):
    finished = pyqtSignal(object)

    def __init__(self, username: str):
        super().__init__()
        self._username = username

    def run(self):
        from clientRequests import ClientRequests
        err = ClientRequests.requestResetPassword(self._username)
        self.finished.emit(err)


class ResetPasswordDialog(QDialog):
    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reset Password")

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)


        self.boxUsername = QLineEdit()
        self.boxCode = QLineEdit()
        self.boxNewPassword = PasswordLineEdit()
        self.boxConfirmPassword = PasswordLineEdit()
        self.progressStack = QStackedWidget()
        self.lblStatus = QLabel("Sending verification code…")

        self.icnLoading = QPushButton()
        # self.icnLoading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icnLoading.setStyleSheet('QPushButton { background-color: transparent; border: none; }')
        self._animation = qta.Spin(self.icnLoading)
        self.icnLoading.setIcon(qta.icon('fa6s.spinner', color='green', animation=self._animation))
        self.icnLoading.setIconSize(QSize(32, 32))
        self._animation.start()

        # self.progressBar = QProgressBar()
        # self.progressBar.setRange(0, 0)  # indeterminate

        self.icnDone = QLabel()
        self.icnDone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icnDone.setPixmap(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton).pixmap(QSize(32, 32))
        )
        self.progressStack.addWidget(self.icnLoading)
        self.progressStack.addWidget(self.icnDone)

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
        lyt.addRow(self.progressStack)
        lyt.addRow(self.btns)

        self._setFormEnabled(False)

        self._thread = QThread()
        self._worker = _ResetRequestWorker(username)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._onRequestFinished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.start()

    def _setFormEnabled(self, enabled: bool):
        self.boxCode.setEnabled(enabled)
        self.boxNewPassword.setEnabled(enabled)
        self.boxConfirmPassword.setEnabled(enabled)
        self.btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(enabled)
        self.setCursor(Qt.CursorShape.ArrowCursor if enabled else Qt.CursorShape.WaitCursor)

    def done(self, result):
        if self._thread.isRunning():
            self._worker.finished.disconnect(self._onRequestFinished)
            self._thread.quit()
            self._thread.wait()
        super().done(result)

    def _onRequestFinished(self, err):
        if err:
            self.lblStatus.setText("Error sending verification code. Please try again later.")
            QMessageBox.warning(self, "Error", err)
            self._setFormEnabled(False)
            self.reject()
        else:
            self._animation.stop()
            self.progressStack.setCurrentIndex(1)
            self.lblStatus.setText("Verification code sent. Check your email.")
            self._setFormEnabled(True)
            self.boxCode.setFocus()

    def resetPassword(self):
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
    def __init__(self, departments, parent=None):
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
        if not self.boxName.text().strip():
            QMessageBox.warning(self, "Error", "Please enter your name.")
            return
        self.accept()

    def getName(self) -> str:
        return self.boxName.text().strip()

    def getDepartment(self):
        return self.boxDepartment.currentText()


class LoginWindow(QMainWindow):
    on_login_success = pyqtSignal(object)
    
    def __init__(self, parent=None):
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
        
        # self.btnRememberMe.setChecked(True)
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

    def showHidePassword(self):
        self.boxPassword.setEchoMode(QLineEdit.EchoMode.Normal if self.btnShowPassword.isChecked() else QLineEdit.EchoMode.Password)

    def _rememberedUsernames(self) -> list[str]:
        value = QSettings("PTW", "PTW").value(SETTINGS_REMEMBERED_USERS_KEY, [], type=list)
        return [str(v) for v in value] if value else []

    def storeLoginCredentials(self, username: str, password: str):
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
        try:
            return keyring.get_password(SERVICE_NAME, username)
        except KeyringError as e:
            raise e

    def forgetLoginCredentials(self, username: str):
        usernames = self._rememberedUsernames()
        if username in usernames:
            usernames.remove(username)
            QSettings("PTW", "PTW").setValue(SETTINGS_REMEMBERED_USERS_KEY, usernames)
        try:
            keyring.delete_password(SERVICE_NAME, username)
        except KeyringError:
            pass

    def _populateRememberedUsers(self):
        usernames = self._rememberedUsernames()
        self.boxUsername.setItems(usernames)
        self.boxPassword.clear()
        if usernames:
            self._fillPasswordFor(usernames[0])

    def _fillPasswordFor(self, username: str):
        try:
            password = self.retrieveLoginCredentials(username)
        except KeyringError:
            password = None
        self.boxPassword.setText(password or '')

    def _onUsernameSelected(self, username: str):
        if username in self._rememberedUsernames():
            self._fillPasswordFor(username)
        else:
            self.boxPassword.clear()

    def forgotPassword(self):
        from clientRequests import ClientRequests

        username = self.boxUsername.currentText()
        if not username:
            QMessageBox.warning(self, "Error", "Please enter your username to reset your password.")
            return

        dlg = ResetPasswordDialog(username, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        err = ClientRequests.resetPassword(username, dlg.newPassword, dlg.verificationCode)
        if err:
            QMessageBox.warning(self, "Error", err)
        else:
            QMessageBox.information(self, "Success", "Your password has been reset successfully. You can now log in with your new password.")
    
    def reset(self):
        self._populateRememberedUsers()
        self.boxUsername.setFocus()

    def login(self):
        from clientRequests import ClientRequests

        username = self.boxUsername.currentText()
        password : str = self.boxPassword.text()
        err, user = ClientRequests.login(username, password)

        if err is not None:
            QMessageBox.warning(self, "Error", err)
            return

        if self.btnRememberMe.isChecked():
            try:
                self.storeLoginCredentials(username, password)
            except KeyringError as e:
                QMessageBox.warning(self, "Error", str(e))
        elif username in self._rememberedUsernames():
            self.forgetLoginCredentials(username)

        theme = user.getTheme()
        if theme == 'dark':
            QApplication.styleHints().setColorScheme(Qt.ColorScheme.Dark)
        elif theme == 'light':
            QApplication.styleHints().setColorScheme(Qt.ColorScheme.Light)

        self.on_login_success.emit(user)

    def loginAsGuest(self):
        from User import User, UserRoles, UserDepartments

        dlg = GuestDetailsDialog(list(UserDepartments), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        name = dlg.getName()
        department = dlg.getDepartment()
        user = User(username=name, name=name, role=UserRoles.GUEST, department=department, email='')

        self.on_login_success.emit(user)