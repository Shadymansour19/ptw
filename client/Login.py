from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QSize
from PyQt6.QtWidgets import (QLineEdit, QToolButton, QDialog, QFormLayout, QLabel,
                              QStackedWidget, QPushButton, QCheckBox, QDialogButtonBox,
                              QMessageBox, QMainWindow, QWidget, QSizePolicy, QApplication, QStyle)
import keyring
from keyring.errors import KeyringError
import qtawesome as qta


SERVICE_NAME = "PTW-login-credentials"


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
        

class LoginWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PTW Login")
        
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint)

        container = QWidget()
        self.setCentralWidget(container)

        self.boxUsername = QLineEdit()
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

        self.boxUsername.returnPressed.connect(self.login)
        self.boxPassword.returnPressed.connect(self.login)
        self.btnForgotPassword.clicked.connect(self.forgotPassword)

        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # self.btns.button(QDialogButtonBox.StandardButton.Ok).setText("Login")
        self.btns.accepted.connect(self.login)
        self.btns.rejected.connect(self.close)

        mainLayout = QFormLayout()
        mainLayout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        container.setLayout(mainLayout)

        mainLayout.addRow("Username", self.boxUsername)
        mainLayout.addRow("Password", self.boxPassword)
        mainLayout.addRow(self.btnForgotPassword)
        mainLayout.addRow(self.btnRememberMe)

        mainLayout.setAlignment(self.btnRememberMe, Qt.AlignmentFlag.AlignCenter)
        mainLayout.setAlignment(self.btnForgotPassword, Qt.AlignmentFlag.AlignCenter)

        try:
            username, password = self.retrieveLoginCredentials()
            self.boxUsername.setText(username)
            self.boxPassword.setText(password)
        except KeyringError as e:
            pass

        mainLayout.addRow(self.btns)

        self.adjustSize()
        self.setFixedHeight(self.height())
        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

    def showHidePassword(self):
        self.boxPassword.setEchoMode(QLineEdit.EchoMode.Normal if self.btnShowPassword.isChecked() else QLineEdit.EchoMode.Password)

    def storeLoginCredentials(self, username: str, password: str):
        try:
            keyring.set_password(SERVICE_NAME, 'username', username)
            keyring.set_password(SERVICE_NAME, 'password', password)
        except KeyringError as e:
            raise e

    def retrieveLoginCredentials(self) -> tuple[str, str]:
        try:
            username = keyring.get_password(SERVICE_NAME, 'username')
            password = keyring.get_password(SERVICE_NAME, 'password')
            return username, password
        except KeyringError as e:
            raise e
        
    def forgotPassword(self):
        from clientRequests import ClientRequests

        username = self.boxUsername.text()
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
    

    def login(self):
        from MainWindow import MainWindow, AdminMainWindow, UserMainWindow, CoordinatorMainWindow, IssuingMainWindow, SafetyMainWindow, ManagerMainWindow
        from clientRequests import ClientRequests
        from User import UserRoles

        username = self.boxUsername.text()
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
        
        mainWindow = None
        if user.getRole() == UserRoles.USER:
            mainWindow = UserMainWindow(user)
        elif user.getRole() == UserRoles.COORDINATOR:
            mainWindow = CoordinatorMainWindow(user)
        elif user.getRole() == UserRoles.ISSUING:
            mainWindow = IssuingMainWindow(user)
        elif user.getRole() == UserRoles.SAFETY:
            mainWindow = SafetyMainWindow(user)
        elif user.getRole() == UserRoles.PGM:
            mainWindow = ManagerMainWindow(user, "PGM")
        elif user.getRole() == UserRoles.PDH:
            mainWindow = ManagerMainWindow(user, "PDH")
        elif user.getRole() == UserRoles.SOD:
            mainWindow = ManagerMainWindow(user, "SOD")
        elif user.getRole() == UserRoles.DFGM:
            mainWindow = ManagerMainWindow(user, "DFGM")
        elif user.getRole() == UserRoles.ADMIN:
            mainWindow = AdminMainWindow(user)
        else:
            mainWindow = MainWindow(user)

        if mainWindow:
            mainWindow.show()
            self.close()
            return
        else:
            QMessageBox.warning(self, "Error", "Your user role is not recognized. Please contact the administrator.")
