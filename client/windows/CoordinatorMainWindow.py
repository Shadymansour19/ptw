"""Main window for the Coordinator role - reviews and approves PTWs in the
coordination stage."""

from PyQt6.QtGui import QKeySequence, QShortcut
import qtawesome as qta

from GlobalData import globalData
from models.User import User
from windows.MainWindow import MainWindow
from helper.i18n import t


class CoordinatorMainWindow(MainWindow):
    """Coordinator role window: PTW tabs cover Under Review through Archived. Has
    view-only visibility across every IC tab Issuing has - same breadth, without
    Issuing's accept/request-edits/confirm/return/execute privileges - plus the
    Link-to-PTW action it already has on the PTW side. The FAB (and Ctrl+P) prints
    the PTWs in whichever tab is currently open."""

    def __init__(self, loggedUser: User):
        """Build the Coordinator window: wire PTW/IC tab options and the
        print-current-tab FAB with its Ctrl+P shortcut."""
        super().__init__(loggedUser)
        self.setWindowTitle(t("PTW (Permit To Work) - Coordinator Window"))

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabMeetingPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionLinkICToPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewHeldICsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewHeldICsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        # View-only across every IC tab Issuing has (same breadth of visibility, less
        # privilege — no Accept/Request Edits/Confirm/Return/Execute actions), plus the
        # Link to PTW action Coordinator already has via the PTW side.
        self.tabUnderReviewICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabApprovedICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabIsolateConfirmingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabPendingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabActiveICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabDeisolateConfirmingICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabClosingICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabClosedICs.addOptions([self.optionViewIC, self.optionPrintIC])

        self._icTabs = [
            self.btnCertUnderReview, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending,
            self.btnCertActive, self.btnCertDeisolateConfirming, self.btnCertClosing, self.btnCertSanctioned, self.btnCertClosed,
        ]
        self._icTabsWidgets = [
            self.tabUnderReviewICs, self.tabApprovedICs, self.tabIsolateConfirmingICs, self.tabPendingICs,
            self.tabActiveICs, self.tabDeisolateConfirmingICs, self.tabClosingICs, self.tabSanctionedICs, self.tabClosedICs,
        ]

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs, self.btnArchivedPTWs],
                self._icTabs,
            ],
            {
                'PTWs': [
                    self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs, self.btnArchivedPTWs,
                ],
                'ICs': self._icTabs,
                'View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon('fa6s.print', color='white'))
        self.btnFAB.setToolTip(t("Print current widget PTWs [Ctrl+P]"))

        shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        shortcut.activated.connect(self.btnFABHandler)

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
        """Print the PTWs listed in the currently active tab, if the FAB is visible."""
        if self.btnFAB.isVisible(): 
            self.printPTWs()
