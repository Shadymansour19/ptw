"""Main window for the Admin role - full system access, user management only (no
PTW/IC tabs)."""

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
from helper.i18n import t


class AdminMainWindow(MainWindow):
    """Admin role window: full system access, but no PTW or IC tabs at all - just
    Users, Server Logs, and Backups. Overrides the home dashboard with a
    Users-by-Department donut instead of the base PTW donuts. The FAB (and Ctrl+N)
    adds new user(s), manually or via Excel import."""

    def __init__(self, loggedUser: User):
        """Build the Admin window: wire up Users/Server Logs/Backups tabs and the
        add-user FAB with its Ctrl+N shortcut."""
        super().__init__(loggedUser)
        self.setWindowTitle(t("PTW (Permit To Work) - Admin Window"))

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
        self.btnFAB.setToolTip(t("Add New User [Ctrl+N]"))

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.addNewUserDialog)
    
    def btnFABHandler(self):
        """Open the add-user dialog when the FAB is clicked (or Ctrl+N pressed)."""
        self.addNewUserDialog()
    
    def addNewUserDialog(self):
        """Prompt to add user(s) manually or via Excel import, if the FAB is visible.

        Shows a chooser QMessageBox; "Type Manually" opens `DialogUser` for a single
        new user and adds it to the table on accept, "Import from Excel" delegates to
        the users table's bulk-import flow.
        """
        if not self.btnFAB.isVisible():
            return

        msgBox = QMessageBox(self)
        msgBox.setWindowTitle(t("Add Users"))
        msgBox.setText(t("How would you like to add new user(s)?"))
        btnManual = msgBox.addButton(t("&Type Manually"), QMessageBox.ButtonRole.AcceptRole)
        btnImport = msgBox.addButton(t("Import from E&xcel"), QMessageBox.ButtonRole.ActionRole)
        btnManual.setIcon(qta.icon('fa6s.keyboard'))
        btnImport.setIcon(qta.icon('fa6s.file-excel'))
        msgBox.addButton(QMessageBox.StandardButton.Cancel)
        msgBox.exec()
        clicked = msgBox.clickedButton()

        if clicked == btnManual:
            newUser = User()
            dlg = DialogUser(self, False, True, self.loggedUser, newUser, t('New User'))
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.tabAllUsers.addUser(newUser)
        elif clicked == btnImport:
            self.tabAllUsers.importUsersFromExcel()

    def stackTabChanged(self):
        """Show the FAB only on the All Users tab."""
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabAllUsers])

    def buildHomePage(self):
        """Override the base PTW dashboard with a single Users-by-Department donut chart."""
        self._homeUsersChart = DonutChart(t("Users"))
        row = QHBoxLayout()
        row.addWidget(self._homeUsersChart, 1)
        self._homeContentLayout.addLayout(row, 1)
        self.updateHomeDashboard()

    def updateHomeDashboard(self):
        """Recompute per-department user counts and refresh the home donut's segments,
        each clickable to jump to the filtered Users tab."""
        counts = Counter(u.getDepartment() for u in globalData.allUsers.values() if u.getDepartment())
        self._homeUsersChart.setSegments([
            DonutSegment(dept, counts[dept], DEPARTMENT_COLOR_CYCLE[i % len(DEPARTMENT_COLOR_CYCLE)],
                         partial(self._openUsersFilteredByDept, dept))
            for i, dept in enumerate(sorted(counts))
        ])

    def _openUsersFilteredByDept(self, dept: str):
        """Navigate to the Users tab and filter it down to the given department.

        Used as the click handler for a home-dashboard donut segment.
        """
        self.btnUsers.click()
        self.tabAllUsers.filterColumn('Department', {dept})

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload users from the server and rebuild the Users table, dashboard, server
        logs, and backups panels.

        Args:
            refreshArchivedPTWs: Ignored - Admin has no PTW tabs.
        """
        def on_done(err, _):
            """Hide the busy overlay, then rebuild the Users table and dashboard, or
            report the error."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to refresh data:") + f" {err}")
                return

            self.tabAllUsers.clear()
            for user in globalData.allUsers.values():
                self.tabAllUsers.addUserToGUI(user)

            self.updateHomeDashboard()

            QApplication.beep()
            self.statusBar().showMessage(t("GUI refreshed successfully."), 2000)

        self._refreshOverlay.showBusy()
        globalData.refresh(self.loggedUser, None, refreshUsers=True, callback=on_done)
        self.tabServerLogs.refresh()
        self.tabBackups.refresh()
