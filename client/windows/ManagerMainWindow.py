"""Main window shared by the four manager approval roles - PDH, PGM, SOD, and DFGM."""

import qtawesome as qta

from GlobalData import globalData
from models.User import User
from windows.MainWindow import MainWindow


class ManagerMainWindow(MainWindow):
    """Single shared window class parameterized by role: `main.py` instantiates it as
    `ManagerMainWindow(loggedUser, role)` for whichever of PDH/PGM/SOD/DFGM the user is -
    it is not four separate classes. PTW tabs cover Under Review/Returned/Approved/
    Running/Held/Closed/Archived; the only IC tab is Under Review, since managers are
    only ever involved in a PSIC's approval chain (after Issuing). The FAB prints the
    PTWs in whichever tab is currently open."""

    def __init__(self, loggedUser: User, role: str):
        """Build the manager window for the given `role` label, wiring PTW/IC tab
        options and the print-current-tab FAB."""
        super().__init__(loggedUser)
        self.setWindowTitle(f"PTW (Permit To Work) - {role} Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewHeldICsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        # Managers are only ever involved in a PSIC's approval
        # chain (after Issuing), so Under Review is the only IC tab they need.
        self.tabUnderReviewICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionAcceptIC, self.optionRequestEditsIC])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs],
                [self.btnCertUnderReview],
            ],
            {
                '&PTWs': [
                    self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs,
                ],
                '&ICs': [self.btnCertUnderReview],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon('fa6s.print', color='white'))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        """Show the FAB except on the Welcome and Under Review ICs tabs; lazily fetch
        archived PTWs the first time that tab is opened."""
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabUnderReviewICs)
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload PTW/user/IC data from the server and rebuild the PTW and IC tabs."""
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)

    def btnFABHandler(self):
        """Print the PTWs listed in the currently active tab."""
        self.printPTWs()
