from PyQt6.QtWidgets import QApplication, QMessageBox

from GlobalData import globalData
from models.User import User
from windows.MainWindow import MainWindow


class IsolatorMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
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
        super().stackTabChanged()
        self.btnFAB.setVisible(False)

    def btnFABHandler(self):
        pass

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, "Error", f"Failed to refresh data: {err}")
                return
            self.refreshICsGUI()
            QApplication.beep()
            self.statusBar().showMessage("GUI refreshed successfully.", 2000)

        self._refreshOverlay.showBusy()
        globalData.refresh(self.loggedUser, None, refreshUsers=True, refreshICs=True, callback=on_done)
