"""Main window for the Issuing role - authorizes PTW execution and accepts/rejects
run, hold, and close requests."""

import qtawesome as qta

from GlobalData import globalData
from models.User import User
from windows.MainWindow import MainWindow


class IssuingMainWindow(MainWindow):
    """Issuing role window: the full PTW running-cycle tab set (Waiting Run/Hold/Close
    Confirmation, Running, Held, Closed, plus the approval-side Under Review/Meeting/
    Returned/Approved/Archived tabs) with run-accept/reject and hold/close take-action
    options. Also has the full IC lifecycle tabs except Requested - a non-PSIC IC never
    routes back to Requested once Issuing has acted on it, so that tab would stay empty
    for this role. The FAB prints the PTWs in whichever tab is currently open."""

    def __init__(self, loggedUser: User):
        """Build the Issuing window: wire PTW/IC tab options and the print-current-tab FAB."""
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Issuing Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabMeetingPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionLinkICToPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionRunAcceptPTW, self.optionRunRejectPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewHeldICsOption, self.optionHldTakeActionPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewHeldICsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionClsAcceptPTW, self.optionClsRejectPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        self.tabUnderReviewICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionAcceptIC, self.optionRequestEditsIC, self.optionLinkPTWToIC])
        self.tabApprovedICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabIsolateConfirmingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionConfirmIsolateIC, self.optionReturnIsolateIC, self.optionLinkPTWToIC])
        self.tabPendingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabActiveICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabDeisolateConfirmingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionConfirmDeisolateIC, self.optionReturnDeisolateIC])
        self.tabClosingICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabClosedICs.addOptions([self.optionViewIC, self.optionPrintIC])

        # no Requested button here: a single-stage (non-PSIC) ic never routes to
        # tabCertRequested for the Issuing viewer once they've acted — it goes straight to
        # Pending. Only a rare PSIC ic (needing PDH/PGM/SOD/DFGM after Issuing)
        # would land there for Issuing to track — accepted gap for now, not wired up.
        self._icTabs = [
            self.btnCertUnderReview, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending,
            self.btnCertActive, self.btnCertDeisolateConfirming, self.btnCertClosing, self.btnCertSanctioned, self.btnCertClosed,
        ]
        self._icTabsWidgets = [
            self.tabUnderReviewICs, self.tabApprovedICs, self.tabIsolateConfirmingICs, self.tabPendingICs,
            self.tabActiveICs, self.tabDeisolateConfirmingICs, self.tabClosingICs, self.tabSanctionedICs, self.tabClosedICs,
        ]

        self.setAvailableTabs(
            [   # sidebar: curated, run/hold/close confirmation is Issuing's core job
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnMeetingPTWs],
                [self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs, self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs],
                self._icTabs,
            ],
            {   # topbar: full set
                '&PTWs': [
                    self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs,
                    self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs, self.btnArchivedPTWs,
                ],
                '&ICs': self._icTabs,
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon('fa6s.print', color='white'))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        """Show the FAB except on the Welcome and any IC tab; lazily fetch archived
        PTWs the first time that tab is opened."""
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab not in self._icTabsWidgets)
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload PTW/user/IC data from the server and rebuild the PTW and IC tabs."""
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)

    def btnFABHandler(self):
        """Print the PTWs listed in the currently active tab."""
        self.printPTWs()
