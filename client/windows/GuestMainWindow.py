from PyQt6.QtGui import QKeySequence, QShortcut
import qtawesome as qta

from windows.MainWindow import MainWindow


class GuestMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Guest Window")

        self.tabRequestedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnRequestedPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
            ],
            {
                '&PTWs': [self.btnRequestedPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setToolTip("Request New PTW [Ctrl+N]")
        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRequestedPTWs, self.tabWelcome])

    def btnFABHandler(self):
        if self.btnFAB.isVisible():
            self.addPTWDialog()
    
    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI()
