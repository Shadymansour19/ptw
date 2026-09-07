"""Main window for the Gas Tester role - records per-shift initial gas test readings only."""

from windows.MainWindow import MainWindow
from helper.i18n import t


class GasTesterMainWindow(MainWindow):
    """Gas Tester role window: a single Gas Test tab listing every PTW that requires an
    initial gas test and doesn't yet have an acceptable one recorded for the current shift
    (see PTW.needsGasTestNow) - populated regardless of whether that PTW's PA has actually
    requested to run this shift. No other PTW/IC tabs. The FAB is permanently hidden since
    this role has no create/print quick-action."""

    def __init__(self, loggedUser):
        """Build the Gas Tester window: wire the Gas Test tab's options, sidebar/topbar,
        and hide the FAB."""
        super().__init__(loggedUser)
        self.setWindowTitle(t("PTW (Permit To Work) - Gas Tester Window"))

        self.tabGasTestPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRecordGasTestPTW])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnGasTestPTWs],
            ],
            {
                'PTWs': [self.btnGasTestPTWs],
                'View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setVisible(False)

    def stackTabChanged(self):
        """Keep the FAB hidden regardless of which tab becomes active."""
        super().stackTabChanged()
        self.btnFAB.setVisible(False)

    def btnFABHandler(self):
        """No-op - the FAB is never shown for this role."""
        pass

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Reload PTW/user data from the server and rebuild the Gas Test tab.

        Args:
            refreshArchivedPTWs: Ignored - Gas Tester has no archived-PTWs tab.
        """
        super().refreshPtwUserGUI()
