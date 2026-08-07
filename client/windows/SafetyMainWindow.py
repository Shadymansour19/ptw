from PyQt6.QtGui import QKeySequence, QShortcut
import qtawesome as qta

from windows.MainWindow import MainWindow


class SafetyMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Safety Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW])
        self.tabMeetingPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionPrintPTW])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnRunningPTWs],
                [self.btnRisks],
            ],
            {
                '&PTWs': [self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnRunningPTWs],
                '&Risks': [self.btnRisks],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))
        self.btnFAB.setToolTip("New Risk [Ctrl+N]")

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.addNewRiskDialog)
    
    def btnFABHandler(self):
        self.addNewRiskDialog()
    

    def addNewRiskDialog(self):
        if not self.btnFAB.isVisible():
            return
        
        self.tabRisks.addNewRiskAssessmentDialog()

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRisks])
    
    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI()
