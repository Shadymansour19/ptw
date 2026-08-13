"""Main window for the Safety role - reviews PTWs from a safety perspective and manages
risk assessments."""

from PyQt6.QtGui import QKeySequence, QShortcut
import qtawesome as qta

from windows.MainWindow import MainWindow
from helper.i18n import t


class SafetyMainWindow(MainWindow):
    """Safety role window: Under Review/Meeting/Running PTW tabs (with safety-specific
    accept/request-edits options) plus a Risks tab for managing risk assessments. No IC
    tabs. The FAB (and Ctrl+N) opens the new-risk-assessment dialog instead of a PTW."""

    def __init__(self, loggedUser):
        """Build the Safety window: wire PTW tab options, sidebar/topbar, and the
        new-risk-assessment FAB with its Ctrl+N shortcut."""
        super().__init__(loggedUser)
        self.setWindowTitle(t("PTW (Permit To Work) - Safety Window"))

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
                'PTWs': [self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnRunningPTWs],
                'Risks': [self.btnRisks],
                'View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))
        self.btnFAB.setToolTip(t("New Risk [Ctrl+N]"))

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.addNewRiskDialog)
    
    def btnFABHandler(self):
        """Open the new-risk-assessment dialog when the FAB is clicked (or Ctrl+N pressed)."""
        self.addNewRiskDialog()
    

    def addNewRiskDialog(self):
        """Open the new-risk-assessment dialog on the Risks tab, if the FAB is visible."""
        if not self.btnFAB.isVisible():
            return
        
        self.tabRisks.addNewRiskAssessmentDialog()

    def stackTabChanged(self):
        """Show the FAB only on the Risks tab."""
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRisks])
    
    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload PTW/user data from the server and rebuild the PTW tabs.

        Args:
            refreshArchivedPTWs: Ignored - Safety has no archived-PTWs tab.
        """
        super().refreshPtwUserGUI()
