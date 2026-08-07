import qtawesome as qta

from GlobalData import globalData
from models.User import User
from windows.MainWindow import MainWindow


class ManagerMainWindow(MainWindow):
    def __init__(self, loggedUser: User, role: str):
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
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabUnderReviewICs)
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)

    def btnFABHandler(self):
        self.printPTWs()
