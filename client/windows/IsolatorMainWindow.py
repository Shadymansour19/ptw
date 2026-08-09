"""Main window for the Isolator role - manages physical equipment isolations (ICs) only."""

from PyQt6.QtWidgets import QApplication, QMessageBox

from GlobalData import globalData
from models.User import User
from windows.MainWindow import MainWindow


class IsolatorMainWindow(MainWindow):
    """Isolator role window: no PTW tabs at all, only IC tabs - Pending (with Complete
    Isolation), Active (view-only), Closing (with Complete De-isolation), and Sanctioned.
    The FAB is permanently hidden since this role has no create/print quick-action."""

    def __init__(self, loggedUser: User):
        """Build the Isolator window: wire IC tab options, sidebar/topbar, and hide the FAB."""
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Isolator Window")

        self.tabPendingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionExecuteIsolateIC])
        self.tabActiveICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabClosingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionExecuteDeisolateIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC, self.optionPrintIC])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnCertPending, self.btnCertActive, self.btnCertClosing, self.btnCertSanctioned],
            ],
            {
                '&ICs': [self.btnCertPending, self.btnCertActive, self.btnCertClosing, self.btnCertSanctioned],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setVisible(False)

    def stackTabChanged(self):
        """Keep the FAB hidden regardless of which tab becomes active."""
        super().stackTabChanged()
        self.btnFAB.setVisible(False)

    def btnFABHandler(self):
        """No-op - the FAB is never shown for this role."""
        pass

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload user and IC data from the server and rebuild the IC tabs.

        Args:
            refreshArchivedPTWs: Ignored - Isolator has no PTW tabs.
        """
        def on_done(err, _):
            """Hide the busy overlay, then rebuild the IC tabs or report the error."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, "Error", f"Failed to refresh data: {err}")
                return
            self.refreshICsGUI()
            QApplication.beep()
            self.statusBar().showMessage("GUI refreshed successfully.", 2000)

        self._refreshOverlay.showBusy()
        globalData.refresh(self.loggedUser, None, refreshUsers=True, refreshICs=True, callback=on_done)
