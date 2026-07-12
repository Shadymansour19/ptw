from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QLineEdit, QComboBox, QLabel, QDialogButtonBox, QMessageBox
import secrets

from User import User, SecuredUser, UserRoles, UserDepartments
from GlobalData import globalData


class DialogUser(QDialog):
    def __init__(self, parent, readonly: bool, isNew: bool, loggedUser: User, toEditUser: User | SecuredUser, label: str=""):
        super().__init__(parent)
        self.setWindowTitle(label)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        self.loggedUser = loggedUser
        self.toEditUser = toEditUser
        self.isNew = isNew
        self.readonly = readonly

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.txtUsername = QLineEdit()
        self.txtPassword = QLineEdit()
        self.txtName = QLineEdit()
        self.txtRole = QComboBox()
        self.txtDepartment = QComboBox()
        self.txtEmail = QLineEdit()
        self.txtExt = QLineEdit()
        self.lblUserExists = QLabel()
        self.lblUserExists.setStyleSheet('QLabel { border: none; color: red; }')
        self.lblUserExists.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.txtRole.addItems([role for role in UserRoles])
        self.txtDepartment.addItems([dept for dept in UserDepartments])

        self.txtUsername.setText(self.toEditUser.getUsername())
        self.txtName.setText(self.toEditUser.getName())
        self.txtRole.setCurrentText(self.toEditUser.getRole())
        self.txtDepartment.setCurrentText(self.toEditUser.getDepartment())
        self.txtEmail.setText(self.toEditUser.getEmail())
        self.txtExt.setText(self.toEditUser.getExt())

        self.txtUsername.setEnabled(isNew)
        self.txtPassword.setReadOnly(True)
        self.txtUsername.setStyleSheet("QLineEdit[error='True'] { border: 1px solid red; border-radius: 2px; }")

        if readonly:
            self.txtUsername.setReadOnly(True)
            self.txtName.setReadOnly(True)
            self.txtRole.setEnabled(False)
            self.txtDepartment.setEnabled(False)
            self.txtEmail.setReadOnly(True)
            self.txtExt.setReadOnly(True)

        lyt.addRow("Username:", self.txtUsername)
        if isNew:
            lyt.addRow(self.lblUserExists)
            password = secrets.token_urlsafe(12)
            lyt.addRow("Password:", self.txtPassword)
            self.txtPassword.setText(password)
        lyt.addRow("Name:", self.txtName)
        lyt.addRow("Role:", self.txtRole)
        lyt.addRow("Department:", self.txtDepartment)
        lyt.addRow("Email:", self.txtEmail)
        lyt.addRow("EXT:", self.txtExt)

        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btns.accepted.connect(self.collectData)
        self.btns.rejected.connect(self.reject)
        self.txtUsername.textChanged.connect(self.checkUsername)
        lyt.addWidget(self.btns)
        self.checkUsername()

    def checkUsername(self):
        username = self.txtUsername.text()
        err = username != self.toEditUser.getUsername() and username in globalData.allUsers
        self.btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not err)
        self.lblUserExists.setText("Username already exists" if err else "")
        self.txtUsername.setProperty('error', str(err))
        self.txtUsername.style().unpolish(self.txtUsername)
        self.txtUsername.style().polish(self.txtUsername)

    def collectData(self):
        if self.readonly:
            self.accept()
            return
        
        self.toEditUser.setUsername(self.txtUsername.text().strip())
        if self.isNew:
            self.toEditUser.setPassword(self.txtPassword.text().strip())
        self.toEditUser.setName(self.txtName.text().strip())
        self.toEditUser.setRole(self.txtRole.currentText())
        self.toEditUser.setDepartment(self.txtDepartment.currentText())
        self.toEditUser.setEmail(self.txtEmail.text().strip())
        self.toEditUser.setExt(self.txtExt.text().strip())

        if not self.toEditUser.getUsername():
            QMessageBox.critical(self, "Error", "Username can't by empty!")
        elif self.isNew and self.toEditUser.getUsername() in globalData.allUsers:
            QMessageBox.critical(self, "Error", "Username already exists!")
        elif self.isNew and len(self.toEditUser.getPassword()) < 6:
            QMessageBox.critical(self, "Error", "Password must be at least 6 characters!")
        elif not self.toEditUser.getName():
            QMessageBox.critical(self, "Error", "Name can't be empty!")
        else:
            self.accept()