"""Main window for the unauthenticated Guest role - create and view PTWs only, no ICs."""

from PyQt6.QtGui import QKeySequence, QShortcut
import qtawesome as qta

from windows.MainWindow import MainWindow
from helper.i18n import t


class GuestMainWindow(MainWindow):
    """Guest role window: the only PTW tabs are Requested/Returned/Approved (each with
    a view/request/print/export option set), no IC tabs at all. The FAB (and Ctrl+N)
    opens the new-PTW dialog."""

    def __init__(self, loggedUser):
        """Build the Guest window: wire PTW tab options, sidebar/topbar, and the
        new-PTW FAB with its Ctrl+N shortcut."""
        super().__init__(loggedUser)
        self.setWindowTitle(t("PTW (Permit To Work) - Guest Window"))

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

        self.btnFAB.setToolTip(t("Request New PTW [Ctrl+N]"))
        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        """Show the FAB only on the Welcome and Requested PTWs tabs."""
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRequestedPTWs, self.tabWelcome])

    def btnFABHandler(self):
        """Open the new-PTW dialog when the FAB is clicked (or Ctrl+N is pressed)."""
        if self.btnFAB.isVisible():
            self.addPTWDialog()
    
    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload PTW/user data from the server and rebuild the PTW tabs.

        Args:
            refreshArchivedPTWs: Ignored - Guest has no archived-PTWs tab.
        """
        super().refreshPtwUserGUI()
