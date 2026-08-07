from collections import Counter
from functools import partial
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QMessageBox
import qtawesome as qta

from dialogs.DialogUser import DialogUser
from GlobalData import globalData
from models.User import User
from widgets.DonutChart import DonutChart, DonutSegment, DEPARTMENT_COLOR_CYCLE
from windows.MainWindow import MainWindow


class AdminMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Admin Window")

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUsers, self.btnServerLogs, self.btnBackups],
            ],
            {
                '&Users': [self.btnUsers, self.btnServerLogs, self.btnBackups],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))
        self.btnFAB.setToolTip("Add New User [Ctrl+N]")

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.addNewUserDialog)
    
    def btnFABHandler(self):
        self.addNewUserDialog()
    
    def addNewUserDialog(self):
        if not self.btnFAB.isVisible():
            return

        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("Add Users")
        msgBox.setText("How would you like to add new user(s)?")
        btnManual = msgBox.addButton("&Type Manually", QMessageBox.ButtonRole.AcceptRole)
        btnImport = msgBox.addButton("Import from E&xcel", QMessageBox.ButtonRole.ActionRole)
        btnManual.setIcon(qta.icon('fa6s.keyboard'))
        btnImport.setIcon(qta.icon('fa6s.file-excel'))
        msgBox.addButton(QMessageBox.StandardButton.Cancel)
        msgBox.exec()
        clicked = msgBox.clickedButton()

        if clicked == btnManual:
            newUser = User()
            dlg = DialogUser(self, False, True, self.loggedUser, newUser, 'New User')
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.tabAllUsers.addUser(newUser)
        elif clicked == btnImport:
            self.tabAllUsers.importUsersFromExcel()

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabAllUsers])

    def buildHomePage(self):
        self._homeUsersChart = DonutChart("Users")
        row = QHBoxLayout()
        row.addWidget(self._homeUsersChart, 1)
        self._homeContentLayout.addLayout(row, 1)
        self.updateHomeDashboard()

    def updateHomeDashboard(self):
        counts = Counter(u.getDepartment() for u in globalData.allUsers.values() if u.getDepartment())
        self._homeUsersChart.setSegments([
            DonutSegment(dept, counts[dept], DEPARTMENT_COLOR_CYCLE[i % len(DEPARTMENT_COLOR_CYCLE)],
                         partial(self._openUsersFilteredByDept, dept))
            for i, dept in enumerate(sorted(counts))
        ])

    def _openUsersFilteredByDept(self, dept: str):
        self.btnUsers.click()
        self.tabAllUsers.filterColumn('Department', {dept})

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, "Error", f"Failed to refresh data: {err}")
                return

            self.tabAllUsers.clear()
            for user in globalData.allUsers.values():
                self.tabAllUsers.addUserToGUI(user)

            self.updateHomeDashboard()

            QApplication.beep()
            self.statusBar().showMessage("GUI refreshed successfully.", 2000)

        self._refreshOverlay.showBusy()
        globalData.refresh(self.loggedUser, None, refreshUsers=True, callback=on_done)
        self.tabServerLogs.refresh()
        self.tabBackups.refresh()
