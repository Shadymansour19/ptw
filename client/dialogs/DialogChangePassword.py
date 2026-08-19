"""Mandatory password-change dialog, shown after a successful login when the account's
must_change_password flag is set - gates entry into the app until a new password is set."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QLabel, QDialogButtonBox, QMessageBox

from Login import PasswordLineEdit
from helper.i18n import t


class DialogChangePassword(QDialog):
    """Modal, mandatory password-change prompt shown before the main window opens.

    No Cancel button - the only way past it is entering a valid new password
    (min 8 characters) and its confirmation; closing the window (accept()
    never called) is treated by the caller the same as backing out of login.
    """

    def __init__(self, parent, username: str):
        """Build the form for `username`; `newPassword` is set once accept() succeeds."""
        super().__init__(parent)
        self.setWindowTitle(t("Change Password"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.lblInfo = QLabel(t("Your password must be changed before you can continue, {0}.").format(username))
        self.lblInfo.setWordWrap(True)
        self.boxNewPassword = PasswordLineEdit()
        self.boxConfirmPassword = PasswordLineEdit()
        self.boxNewPassword.setPlaceholderText(t("Enter a new password"))
        self.boxConfirmPassword.setPlaceholderText(t("Repeat your new password"))

        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.btns.button(QDialogButtonBox.StandardButton.Ok).setText(t("Change Password"))
        self.btns.accepted.connect(self._validate)

        lyt.addRow(self.lblInfo)
        lyt.addRow(t("New Password:"), self.boxNewPassword)
        lyt.addRow(t("Confirm Password:"), self.boxConfirmPassword)
        lyt.addRow(self.btns)

    def _validate(self):
        """Slot for the OK button: check the new password's length and that it matches its
        confirmation before storing it in `newPassword` and accepting."""
        newPassword = self.boxNewPassword.text()
        confirmPassword = self.boxConfirmPassword.text()

        if len(newPassword) < 8:
            QMessageBox.critical(self, t("Error"), t("Password must be at least 8 characters!"))
            return
        if newPassword != confirmPassword:
            QMessageBox.critical(self, t("Error"), t("Passwords do not match."))
            return

        self.newPassword = newPassword
        self.accept()
