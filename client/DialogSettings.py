from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from User import User, UserRoles, UserDepartments


class DialogSettings(QDialog):
    def __init__(self, parent, loggedUser: User):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)
        self.loggedUser = loggedUser

        self.txtUsername = QLineEdit()
        self.txtPassword = QLineEdit()
        self.txtName = QLineEdit()
        self.txtRole = QComboBox()
        self.txtDepartment = QComboBox()
        self.txtEmail = QLineEdit()
        self.txtExt = QLineEdit()

        self.txtRole.addItems([role for role in UserRoles])
        self.txtDepartment.addItems([dept for dept in UserDepartments])
        self.txtPassword.setEchoMode(QLineEdit.EchoMode.Password)

        self.txtUsername.setText(loggedUser.getUsername())
        self.txtPassword.setText(loggedUser.getPassword())
        self.txtName.setText(loggedUser.getName())
        self.txtRole.setCurrentText(loggedUser.getRole())
        self.txtDepartment.setCurrentText(loggedUser.getDepartment())
        self.txtEmail.setText(loggedUser.getEmail())
        self.txtExt.setText(loggedUser.getExt())

        lyt.addRow("Username:", self.txtUsername)
        lyt.addRow("Password:", self.txtPassword)
        lyt.addRow("Name:", self.txtName)
        lyt.addRow("Role:", self.txtRole)
        lyt.addRow("Department:", self.txtDepartment)
        lyt.addRow("Email:", self.txtEmail)
        lyt.addRow("EXT:", self.txtExt)

        self.txtUsername.setEnabled(False)
        self.txtRole.setEnabled(False)
        self.txtDepartment.setEnabled(False)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.collectData)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)
    
    def collectData(self):
        self.loggedUser.setPassword(self.txtPassword.text())
        self.loggedUser.setName(self.txtName.text())
        self.loggedUser.setDepartment(self.txtDepartment.currentText())
        self.loggedUser.setEmail(self.txtEmail.text())
        self.loggedUser.setExt(self.txtExt.text())
        if len(self.loggedUser.getPassword()) < 6:
            QMessageBox.critical(self, "Error", "Password must be at least 6 characters!")
        elif not self.loggedUser.getName():
            QMessageBox.critical(self, "Error", "Name can't be empty!")
        else:
            self.accept()