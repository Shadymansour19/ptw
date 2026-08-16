"""Main window for the User role - creates PTWs and requests run/hold/close on its
own permits."""

from PyQt6.QtGui import QKeySequence, QShortcut
import qtawesome as qta

from GlobalData import globalData
from windows.MainWindow import MainWindow
from helper.i18n import t


class UserMainWindow(MainWindow):
    """User (requestor) role window: the widest PTW tab set of any role, including the
    draft-only Registered tab and the full run/hold/close request lifecycle, plus a
    Requested-PTWs (tracking-only) and an Under Review (actionable) tab. Has the full
    IC lifecycle tabs except Under Review, which never gets populated for this role.
    The FAB creates a new PTW everywhere except the Requested ICs tab, where it creates
    a new IC instead."""

    def __init__(self, loggedUser):
        """Build the User window: wire PTW/IC tab options, sidebar/topbar, and the
        new-PTW/new-IC FAB with its Ctrl+N shortcut."""
        super().__init__(loggedUser)
        self.setWindowTitle(t("PTW (Permit To Work) - User Window"))

        self.tabRegisteredPTWs.addOptions([self.optionViewPTW, self.optionEditPTW, self.optionRequestPTW, self.optionViewRequestorPTW, self.optionDltPTW, self.optionExportPTW])
        self.tabRequestedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabMeetingPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionEditPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionDltPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionRunRequestPTW, self.optionLinkICToPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionRequestPTW, self.optionClsRequestPTW, self.optionHldRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewHeldICsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewHeldICsOption, self.optionRequestPTW, self.optionRunRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        self.tabRequestedICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabApprovedICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionRequestIsolateIC, self.optionLinkPTWToIC])
        self.tabIsolateConfirmingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabPendingICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionLinkPTWToIC])
        self.tabActiveICs.addOptions([self.optionViewIC, self.optionPrintIC, self.optionRequestDeisolateIC, self.optionLinkPTWToIC])
        self.tabDeisolateConfirmingICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabClosingICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC, self.optionPrintIC])
        self.tabClosedICs.addOptions([self.optionViewIC, self.optionPrintIC])

        self.setAvailableTabs(
            [   # sidebar: curated, most-used tabs for a requestor
                [self.btnWelcome],
                [self.btnRequestedPTWs, self.btnMeetingPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs],
                [self.btnCertRequested, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending,
                 self.btnCertActive, self.btnCertDeisolateConfirming, self.btnCertClosing, self.btnCertSanctioned, self.btnCertClosed],
            ],
            {   # topbar: full set
                'PTWs': [
                    self.btnRequestedPTWs, self.btnUnderReviewPTWs, self.btnMeetingPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs,
                    self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs, 
                    None, 
                    self.btnArchivedPTWs,
                ],
                'ICs': [self.btnCertRequested, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending,
                         self.btnCertActive, self.btnCertDeisolateConfirming, self.btnCertClosing, self.btnCertSanctioned, self.btnCertClosed],
                'View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setToolTip(t("Request New PTW [Ctrl+N]"))
        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        """Show the FAB on Welcome, Requested PTWs, and Requested ICs (with its tooltip
        switched to "New IC" on the latter); lazily fetch archived PTWs the first time
        that tab is opened."""
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRequestedPTWs, self.tabWelcome, self.tabRequestedICs])
        self.btnFAB.setToolTip(t("New IC") if tab == self.tabRequestedICs else t("Request New PTW [Ctrl+N]"))
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def btnFABHandler(self):
        """Open the new-IC dialog on the Requested ICs tab, otherwise the new-PTW dialog."""
        if not self.btnFAB.isVisible():
            return
        if self.stack.currentWidget() == self.tabRequestedICs:
            self.tabRequestedICs.addNewICDialog()
        else:
            self.addPTWDialog()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload PTW/user/IC data from the server and rebuild the PTW and IC tabs."""
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)
