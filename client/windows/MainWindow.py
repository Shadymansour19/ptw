"""Base main-window chrome for the PTW desktop client.

Defines `MainWindow`, the `QMainWindow` subclass every role-specific window in
`client/windows/` (e.g. `AdminMainWindow`, `UserMainWindow`,
`IssuingMainWindow`) inherits from. Provides the shared sidebar/topbar/home-page
scaffolding, the PTW and IC action handlers (approvals, run/hold/close
requests, isolate/de-isolate cycle, linking), the SSE-driven real-time sync
path, the system tray/background-notification behavior, and the client-side
PTW run-cycle-shift and 14-shift-validity alarm polling.
"""
from datetime import datetime, timedelta
from collections import Counter
import copy
import re
from PyQt6.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, QTimer, QSettings, pyqtSignal
from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QPushButton, QToolButton,
                              QToolBar, QDialog, QMenu, QSizePolicy, QSystemTrayIcon, QCheckBox,
                              QMessageBox, QApplication, QGraphicsOpacityEffect, QInputDialog)
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QAction, QActionGroup, QShortcut, QCursor

from models.PTW import PTW, RiskAssessment
from tables.TablePTWs import TablePTWs
from dialogs.DialogPTW import DialogPTW
from dialogs.DialogUser import DialogUser
from dialogs.DialogSelectHeldICs import DialogSelectHeldICs
from dialogs.DialogPtwAlarms import DialogPtwAlarms
from tables.TableUsers import TableUsers
from tables.TableRisks import TableRisks
from tables.TableICs import TableICs
from dialogs.DialogIC import DialogIC
from dialogs.DialogCompleteIsolation import DialogCompleteIsolation
from models.Isolation import IC
from widgets.TabServerLogs import TabServerLogs
from tables.TableBackups import TableBackups
from dialogs.DialogSettings import DialogSettings
from widgets.RefreshOverlay import RefreshOverlay
from network.clientRequests import ClientRequests
from network.requestConfig import SERVER_URL
from GlobalData import globalData
from reports.ReportGenerator import ReportGenerator
from network.SSEListener import SSEListener
from models.SSE import SSEObject, SSEAction
from models.User import User, UserRoles
from widgets.DonutChart import DonutChart, DonutSegment, APPROVAL_CYCLE_COLORS, LOCATION_COLORS
from functools import partial
import qtawesome as qta
from helper.utils import resource_path
import helper.i18n as i18n
from helper.i18n import t

SETTINGS_CLOSE_BEHAVIOR_KEY = "app/closeBehavior"


class MainWindow(QMainWindow):
    """Base main-window class that every role-specific window subclasses.

    Builds the shared chrome — sidebar navigation, topbar menus, floating
    action button, status bar, and template-method home-page dashboard — plus
    the full set of PTW and IC action handlers (approvals, run/hold/close
    requests and responses, isolate/de-isolate cycle, PTW-IC linking) common
    to all roles. Owns the SSE listener and patches incoming PTW/IC events
    into the cached data and the appropriate tab rather than doing a full
    refresh, manages the system tray icon and close-to-tray behavior, and
    polls for PTW run-cycle-shift-ended and 14-shift-validity-expired alarms.
    Subclasses call `setAvailableTabs()` to declare their role's sidebar/
    topbar buttons and may override `buildHomePage()`/`updateHomeDashboard()`/
    `refreshGUI()` to customize the home dashboard and data refresh.
    """

    on_logout = pyqtSignal()

    # See _checkPtwAlarms(): condition is polled this often, but a dismissed popup is only
    # re-shown after _PTW_ALARM_REPEAT_MINUTES — the two are independent.
    _PTW_ALARM_CHECK_INTERVAL_MS = 60 * 1000
    _PTW_ALARM_REPEAT_MINUTES = 5

    # See _updateFabProximity(): the FAB fades to _FAB_MIN_OPACITY once the cursor is
    # _FAB_FADE_RADIUS px or further from it, and eases back to fully solid as the
    # cursor comes within _FAB_SOLID_RADIUS.
    _FAB_PROXIMITY_CHECK_INTERVAL_MS = 60
    _FAB_SOLID_RADIUS = 40
    _FAB_FADE_RADIUS = 80
    _FAB_MIN_OPACITY = 0.3

    def __init__(self, loggedUser: User):
        """Build the base window for `loggedUser`: PTW/IC action menu options, the
        stacked tab widgets, sidebar/topbar button maps, the home page welcome
        banner, the floating action button, the status bar, the system tray icon,
        the SSE listener, and the PTW alarm-check timer."""
        super().__init__()
        self.loggedUser = loggedUser
        self.setWindowTitle(t("PTW (Permit To Work)"))
        self.setWindowIcon(QIcon(resource_path('assets/sh-logo-trans.png')))
        self.setMinimumSize(1200, 900)

        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

        self.language = self.loggedUser.getLanguage() or i18n.current_lang()

        self.optionEditPTW = TablePTWs.MenuOption(t('Edit'), self.editPTW, qta.icon('fa6s.pen'))
        self.optionViewPTW = TablePTWs.MenuOption(t('View'), self.viewPTW, qta.icon('fa6.eye'))
        self.optionRequestPTW = TablePTWs.MenuOption(t('Re-Request PTW'), self.addPTWDialog, qta.icon('fa6s.paper-plane'))
        self.optionDltPTW  = TablePTWs.MenuOption(t('Delete'), self.deletePTW, qta.icon('fa6s.trash-can'))
        self.optionArchivePTW  = TablePTWs.MenuOption(t('Archive'), self.archivePTWs, qta.icon('fa6s.box-archive'), allAtOnce=True)
        self.optionRunRequestPTW  = TablePTWs.MenuOption(t('Run'), self.requestToRunPTW, qta.icon('fa6s.play'))
        self.optionRunAcceptPTW  = TablePTWs.MenuOption(t('Run'), self.runAcceptTW, qta.icon('fa6s.play'))
        self.optionRunRejectPTW  = TablePTWs.MenuOption(t('Reject'), self.runRejectTW, qta.icon('fa5s.times'))
        self.optionClsRequestPTW  = TablePTWs.MenuOption(t('Close'), self.requestToClsPTW, qta.icon('fa6s.stop'))
        self.optionClsAcceptPTW  = TablePTWs.MenuOption(t('Close'), self.clsAcceptPTW, qta.icon('fa6s.stop'))
        self.optionClsRejectPTW  = TablePTWs.MenuOption(t('Reject'), self.clsRejectPTW, qta.icon('fa5s.times'))
        self.optionHldRequestPTW  = TablePTWs.MenuOption(t('Hold'), self.requestToHldPTW, qta.icon('fa6s.pause'))
        self.optionHldTakeActionPTW = TablePTWs.MenuOption(t('Take Action'), self.hldTakeAction, qta.icon('fa6s.pause'))
        self.optionTstRequestPTW  = TablePTWs.MenuOption(t('Suction for Test'), self.requestToSuctionTestPTW, qta.icon('fa6s.plug-circle-exclamation'))
        self.optionTstAcceptPTW  = TablePTWs.MenuOption(t('Approve Suction for Test'), self.suctionTestAcceptPTW, qta.icon('fa6s.plug-circle-exclamation'))
        self.optionTstRejectPTW  = TablePTWs.MenuOption(t('Reject Suction for Test'), self.suctionTestRejectPTW, qta.icon('fa5s.times'))
        self.optionRequestEditsPTW = TablePTWs.MenuOption(t('Request Edits'), self.requestEditsPTW, qta.icon('fa5s.undo'))
        self.optionAcceptPTW = TablePTWs.MenuOption(t('Accept'), self.acceptPTW, qta.icon('fa6s.check'))
        self.optionExportPTW = TablePTWs.MenuOption(t('Export'), self.exportPTWs, qta.icon('fa6s.file-excel'), allAtOnce=True)
        self.optionPrintPTW = TablePTWs.MenuOption(t('Print'), self.printPTW, qta.icon('fa6s.print'))
        self.viewHeldICsOption = TablePTWs.MenuOption(t('View Held ICs'), self.viewHeldICs, qta.icon('fa6s.unlock-keyhole'))
        self.optionViewRequestorPTW = TablePTWs.MenuOption(t('View Requestor'), self.viewRequestorPTW, qta.icon('fa6s.user'))
        self.optionViewPerformingPTW = TablePTWs.MenuOption(t('View PA'), self.viewPerformingPTW, qta.icon('mdi6.account-hard-hat'))
        self.viewIssuingOption = TablePTWs.MenuOption(t('View IA'), self.viewIssuing, qta.icon('fa6s.user-tie'))
        self.optionViewIC = TablePTWs.MenuOption(t('View'), self.viewIC, qta.icon('fa6.eye'))
        self.optionPrintIC = TablePTWs.MenuOption(t('Print'), self.printIC, qta.icon('fa6s.print'))
        self.optionAcceptIC = TablePTWs.MenuOption(t('Accept'), self.acceptIC, qta.icon('fa6s.check'))
        self.optionRequestEditsIC = TablePTWs.MenuOption(t('Request Edits'), self.requestEditsIC, qta.icon('fa5s.undo'))
        self.optionRequestIsolateIC = TablePTWs.MenuOption(t('Request Isolate'), self.requestIsolateIC, qta.icon('fa6s.unlock-keyhole'))
        self.optionConfirmIsolateIC = TablePTWs.MenuOption(
            t('Confirm Isolate'), self.confirmIsolateIC, qta.icon('fa6s.check'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.ISOLATE_CONFIRMING,
        )
        self.optionReturnIsolateIC = TablePTWs.MenuOption(
            t('Return Isolate Request'), self.returnIsolateIC, qta.icon('fa5s.undo'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.ISOLATE_CONFIRMING,
        )
        self.optionExecuteIsolateIC = TablePTWs.MenuOption(
            t('Complete Isolation'), self.executeIsolateIC, qta.icon('fa6s.lock'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.PENDING,
        )
        self.optionRequestDeisolateIC = TablePTWs.MenuOption(
            t('Request De-isolate'), self.requestDeisolateIC, qta.icon('fa6s.unlock'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.ACTIVE,
        )
        self.optionConfirmDeisolateIC = TablePTWs.MenuOption(
            t('Confirm De-isolate'), self.confirmDeisolateIC, qta.icon('fa6s.check'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.DEISOLATE_CONFIRMING,
        )
        self.optionReturnDeisolateIC = TablePTWs.MenuOption(
            t('Return De-isolate Request'), self.returnDeisolateIC, qta.icon('fa5s.undo'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.DEISOLATE_CONFIRMING,
        )
        self.optionExecuteDeisolateIC = TablePTWs.MenuOption(
            t('Complete De-isolation'), self.executeDeisolateIC, qta.icon('fa6s.lock-open'),
            visibleFor=lambda ic: ic.getStatus() == IC.Status.CLOSING,
        )
        self.optionLinkPTWToIC = TablePTWs.MenuOption(
            t('Link to PTW'), self.linkPTWToIC, qta.icon('mdi.link-variant'),
            visibleFor=lambda ic: not ic.isWindingDown(),
        )
        self.optionLinkICToPTW = TablePTWs.MenuOption(
            t('Link to IC'), self.linkICToPTW, qta.icon('mdi.link-variant'),
            visibleFor=lambda ptw: ptw.canLinkIC(),
        )

        self.stack = QStackedWidget()
        self.stack.setAutoFillBackground(False)
        self.tabWelcome = QWidget()
        self.tabWelcome.setAutoFillBackground(False)
        self.tabRegisteredPTWs = TablePTWs(self.stack, self.loggedUser, t("Template PTWs"))
        self.tabRequestedPTWs = TablePTWs(self.stack, self.loggedUser, t("Requested PTWs"))
        self.tabUnderReviewPTWs = TablePTWs(self.stack, self.loggedUser, t("Under Review PTWs"))
        self.tabMeetingPTWs = TablePTWs(self.stack, self.loggedUser, t("PTW in Meeting"))
        self.tabReturnedPTWs = TablePTWs(self.stack, self.loggedUser, t("Returned PTWs"))
        self.tabApprovedPTWs = TablePTWs(self.stack, self.loggedUser, t("Approved PTWs"))
        self.tabWaitingRunConfirmationPTWs = TablePTWs(self.stack, self.loggedUser, t("Waiting Run Confirmation PTWs"))
        self.tabRunningPTWs = TablePTWs(self.stack, self.loggedUser, t("Running PTWs"))
        self.tabWaitingHldConfirmationPTWs = TablePTWs(self.stack, self.loggedUser, t("Waiting Hold Confirmation PTWs"))
        self.tabHeldPTWs = TablePTWs(self.stack, self.loggedUser, t("Held PTWs"))
        self.tabWaitingClsConfirmationPTWs = TablePTWs(self.stack, self.loggedUser, t("Waiting Close Confirmation PTWs"))
        self.tabClosedPTWs = TablePTWs(self.stack, self.loggedUser, t("Closed PTWs"))
        self.tabArchivedPTWs = TablePTWs(self.stack, self.loggedUser, t("Archived PTWs"))
        self.tabAllUsers = TableUsers(self.stack, self.loggedUser, t("All Users"))
        self.tabRisks = TableRisks(self.stack, self.loggedUser, t("All Risks"), readonly=False, selectable=False)
        self.tabRequestedICs = TableICs(self.stack, self.loggedUser, t("Requested ICs"))
        self.tabUnderReviewICs = TableICs(self.stack, self.loggedUser, t("Under Review ICs"))
        self.tabApprovedICs = TableICs(self.stack, self.loggedUser, t("Approved ICs"))
        self.tabIsolateConfirmingICs = TableICs(self.stack, self.loggedUser, t("Isolate Confirming ICs"))
        self.tabPendingICs = TableICs(self.stack, self.loggedUser, t("Pending ICs"))
        self.tabActiveICs = TableICs(self.stack, self.loggedUser, t("Active ICs"))
        self.tabDeisolateConfirmingICs = TableICs(self.stack, self.loggedUser, t("Deisolate Confirming ICs"))
        self.tabClosingICs = TableICs(self.stack, self.loggedUser, t("Closing ICs"))
        self.tabSanctionedICs = TableICs(self.stack, self.loggedUser, t("Sanctioned ICs"))
        self.tabClosedICs = TableICs(self.stack, self.loggedUser, t("Closed ICs"))
        self.tabServerLogs = TabServerLogs(self.stack, self.loggedUser, t("Server Logs"))
        self.tabBackups = TableBackups(self.stack, self.loggedUser, t("Backups"))

        self._homeApprovalChart: DonutChart | None = None
        self._homeRunningChart: DonutChart | None = None
        self._availableNavButtons: set = set()
        self._availableTabs: set = set()

        lytWelcome = QVBoxLayout()
        self._homeContentLayout = QVBoxLayout()
        self.tabWelcome.setLayout(lytWelcome)

        welcomeHeaderLyt = QHBoxLayout()
        welcomeHeaderLyt.addStretch()
        lblWelcome = QLabel(t("Welcome,"))
        lblWelcome.setFont(QFont("Helvetica", 30))
        welcomeHeaderLyt.addWidget(lblWelcome)
        self.btnWelcomeName = QPushButton(t(self.loggedUser.getRole()) + ' ' + self.loggedUser.getName().upper() + '!')
        self.btnWelcomeName.setStyleSheet('''
            QPushButton { border: none; background: transparent; color: palette(link); }
            QPushButton:hover { text-decoration: underline;}
            QPushButton:pressed { color: palette(highlight); }
        ''')
        self.btnWelcomeName.setFont(QFont("Helvetica", 30, QFont.Weight.Bold, italic=True))
        self.btnWelcomeName.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnWelcomeName.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        welcomeHeaderLyt.addWidget(self.btnWelcomeName)
        welcomeHeaderLyt.addStretch()

        lytWelcome.addSpacing(10)
        lytWelcome.addLayout(welcomeHeaderLyt)
        lytWelcome.addLayout(self._homeContentLayout, 1)
        self.btnWelcomeName.clicked.connect(self.dlgSettings)
        
        self.stack.addWidget(self.tabWelcome)
        self.stack.addWidget(self.tabRegisteredPTWs)
        self.stack.addWidget(self.tabRequestedPTWs)
        self.stack.addWidget(self.tabUnderReviewPTWs)
        self.stack.addWidget(self.tabMeetingPTWs)
        self.stack.addWidget(self.tabReturnedPTWs)
        self.stack.addWidget(self.tabApprovedPTWs)
        self.stack.addWidget(self.tabWaitingRunConfirmationPTWs)
        self.stack.addWidget(self.tabRunningPTWs)
        self.stack.addWidget(self.tabWaitingHldConfirmationPTWs)
        self.stack.addWidget(self.tabHeldPTWs)
        self.stack.addWidget(self.tabWaitingClsConfirmationPTWs)
        self.stack.addWidget(self.tabClosedPTWs)
        self.stack.addWidget(self.tabArchivedPTWs)
        self.stack.addWidget(self.tabAllUsers)
        self.stack.addWidget(self.tabRisks)
        self.stack.addWidget(self.tabRequestedICs)
        self.stack.addWidget(self.tabUnderReviewICs)
        self.stack.addWidget(self.tabApprovedICs)
        self.stack.addWidget(self.tabIsolateConfirmingICs)
        self.stack.addWidget(self.tabPendingICs)
        self.stack.addWidget(self.tabActiveICs)
        self.stack.addWidget(self.tabDeisolateConfirmingICs)
        self.stack.addWidget(self.tabClosingICs)
        self.stack.addWidget(self.tabSanctionedICs)
        self.stack.addWidget(self.tabClosedICs)
        self.stack.addWidget(self.tabServerLogs)
        self.stack.addWidget(self.tabBackups)

        self.stack.currentChanged.connect(self.stackTabChanged)

        # self.btnWelcome = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), "")
        # self.btnUnderReviewPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion), "")
        # self.btnReturnedPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning), "")
        # self.btnApprovedPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton), "")
        # self.btnWaitingRunConfirmationPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion), "")
        # self.btnRunningPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "")
        # self.btnWaitingHldConfirmationPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning), "")
        # self.btnHeldPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause), "")
        # self.btnWaitingClsConfirmationPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning), "")
        # self.btnClosedPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop), "")
        # self.btnSettings = QPushButton(QIcon(QPixmap('./icon-settings-48.png')), "")
        # self.btnRefresh = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "")
        # self.btnLogout = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowLeft), "")
        # self.btnUsers = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), "")
        # self.btnRisks = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical), "")
        # self.btnLanguage = QPushButton("ع")

        self.btnWelcome = QPushButton(qta.icon('fa5s.home'), "")
        self.btnRequestedPTWs = QPushButton(qta.icon('fa6s.paper-plane'), "")
        self.btnUnderReviewPTWs = QPushButton(qta.icon('fa6s.magnifying-glass-chart'), "")
        self.btnMeetingPTWs = QPushButton(qta.icon('fa6s.people-group'), "")
        self.btnReturnedPTWs = QPushButton(qta.icon('fa5s.undo'), "")
        self.btnApprovedPTWs = QPushButton(qta.icon('fa6s.check'), "")
        self.btnWaitingRunConfirmationPTWs = QPushButton(qta.icon('fa6.clock'), "")
        self.btnRunningPTWs = QPushButton(qta.icon('fa6s.play'), "")
        self.btnWaitingHldConfirmationPTWs = QPushButton(qta.icon('fa5s.hourglass-half'), "")
        self.btnHeldPTWs = QPushButton(qta.icon('fa6s.pause'), "")
        self.btnWaitingClsConfirmationPTWs = QPushButton(qta.icon('fa6s.clock'), "")
        self.btnClosedPTWs = QPushButton(qta.icon('fa6s.stop'), "")
        self.btnArchivedPTWs = QPushButton(qta.icon('fa6s.box-archive'), "")
        self.btnSettings = QPushButton(qta.icon('fa6s.gear'), "")
        self.btnRefresh = QPushButton(qta.icon('fa6s.rotate-right'), "")
        self.btnLogout = QPushButton(qta.icon('fa6s.arrow-right-from-bracket'), "")
        self.btnUsers = QPushButton(qta.icon('fa6s.users-gear'), "")
        # self.btnRisks = QPushButton(qta.icon('fa5s.exclamation-triangle'), "")
        self.btnRisks = QPushButton(qta.icon('mdi.shield-check-outline'), "")
        self.btnCertRequested = QPushButton(qta.icon('fa6s.paper-plane'), "")
        self.btnCertUnderReview = QPushButton(qta.icon('fa6s.magnifying-glass-chart'), "")
        self.btnCertApproved = QPushButton(qta.icon('fa6s.check'), "")
        self.btnCertIsolateConfirming = QPushButton(qta.icon('fa6s.clipboard-check'), "")
        self.btnCertPending = QPushButton(qta.icon('fa6.hourglass'), "")
        self.btnCertActive = QPushButton(qta.icon('fa6s.lock'), "")
        self.btnCertDeisolateConfirming = QPushButton(qta.icon('fa6s.magnifying-glass'), "")
        self.btnCertClosing = QPushButton(qta.icon('mdi6.lock-open-variant-outline'), "")
        self.btnCertSanctioned = QPushButton(qta.icon('fa6s.flask'), "")
        self.btnCertClosed = QPushButton(qta.icon('fa6s.lock-open'), "")
        self.btnLanguage = QPushButton(qta.icon('fa5s.language'), "")
        self.btnTheme = QPushButton(qta.icon('fa6s.circle-half-stroke'), "")
        self.btnServerLogs = QPushButton(qta.icon('fa6s.file-lines'), "")
        self.btnBackups = QPushButton(qta.icon('fa6s.database'), "")

        self.btnWelcome.setToolTip(t("Home [Ctrl+H]"))
        self.btnRequestedPTWs.setToolTip(t("Requested PTWs"))
        self.btnUnderReviewPTWs.setToolTip(t("Under Review PTWs"))
        self.btnMeetingPTWs.setToolTip(t("PTW in Meeting"))
        self.btnReturnedPTWs.setToolTip(t("Returned PTWs"))
        self.btnApprovedPTWs.setToolTip(t("Approved PTWs"))
        self.btnWaitingRunConfirmationPTWs.setToolTip(t("Waiting Run Confirmation PTWs"))
        self.btnRunningPTWs.setToolTip(t("Running PTWs"))
        self.btnWaitingHldConfirmationPTWs.setToolTip(t("Waiting Hold Confirmation PTWs"))
        self.btnHeldPTWs.setToolTip(t("Held PTWs"))
        self.btnWaitingClsConfirmationPTWs.setToolTip(t("Waiting Close Confirmation PTWs"))
        self.btnClosedPTWs.setToolTip(t("Closed PTWs"))
        self.btnArchivedPTWs.setToolTip(t("Archived PTWs"))
        self.btnSettings.setToolTip(t("Settings"))
        self.btnRefresh.setToolTip(t("Refresh [Ctrl+R]"))
        self.btnLogout.setToolTip(t("Logout [Ctrl+X]"))
        self.btnUsers.setToolTip(t("All Users"))
        self.btnRisks.setToolTip(t("Risks"))
        self.btnCertRequested.setToolTip(t("Requested ICs"))
        self.btnCertUnderReview.setToolTip(t("Under Review ICs"))
        self.btnCertApproved.setToolTip(t("Approved ICs"))
        self.btnCertIsolateConfirming.setToolTip(t("Isolate Confirming ICs"))
        self.btnCertPending.setToolTip(t("Pending ICs"))
        self.btnCertActive.setToolTip(t("Active ICs"))
        self.btnCertDeisolateConfirming.setToolTip(t("Deisolate Confirming ICs"))
        self.btnCertClosing.setToolTip(t("Closing ICs"))
        self.btnCertSanctioned.setToolTip(t("Sanctioned ICs"))
        self.btnCertClosed.setToolTip(t("Closed ICs"))
        # Intentionally NOT run through t(): this label always names the *target* language in
        # that language's own script (Latin "English" / Arabic "حول إلى العربية"), regardless
        # of which language is currently active - wrapping it would translate it into the
        # active language instead of the switch target.
        self.btnLanguage.setToolTip("Switch to English" if self.language == 'ar' else "حول إلى العربية")
        self.btnTheme.setToolTip(t("Toggle Light/Dark Mode"))
        self.btnServerLogs.setToolTip(t("Server Logs"))
        self.btnBackups.setToolTip(t("Backups"))

        self._sideBarBtnMap = {
            self.btnWelcome:                    self.tabWelcome,
            self.btnRequestedPTWs:              self.tabRequestedPTWs,
            self.btnUnderReviewPTWs:            self.tabUnderReviewPTWs,
            self.btnMeetingPTWs:                self.tabMeetingPTWs,
            self.btnReturnedPTWs:               self.tabReturnedPTWs,
            self.btnApprovedPTWs:               self.tabApprovedPTWs,
            self.btnWaitingRunConfirmationPTWs: self.tabWaitingRunConfirmationPTWs,
            self.btnRunningPTWs:                self.tabRunningPTWs,
            self.btnWaitingHldConfirmationPTWs: self.tabWaitingHldConfirmationPTWs,
            self.btnHeldPTWs:                   self.tabHeldPTWs,
            self.btnWaitingClsConfirmationPTWs: self.tabWaitingClsConfirmationPTWs,
            self.btnClosedPTWs:                 self.tabClosedPTWs,
            self.btnArchivedPTWs:               self.tabArchivedPTWs,
            self.btnUsers:                      self.tabAllUsers,
            self.btnRisks:                      self.tabRisks,
            self.btnCertRequested:              self.tabRequestedICs,
            self.btnCertUnderReview:            self.tabUnderReviewICs,
            self.btnCertApproved:                self.tabApprovedICs,
            self.btnCertIsolateConfirming:      self.tabIsolateConfirmingICs,
            self.btnCertPending:                self.tabPendingICs,
            self.btnCertActive:                 self.tabActiveICs,
            self.btnCertDeisolateConfirming:    self.tabDeisolateConfirmingICs,
            self.btnCertClosing:                self.tabClosingICs,
            self.btnCertSanctioned:             self.tabSanctionedICs,
            self.btnCertClosed:                 self.tabClosedICs,
            self.btnServerLogs:                 self.tabServerLogs,
            self.btnBackups:                    self.tabBackups,
            self.btnRefresh:                    None,
            self.btnSettings:                   None,
            self.btnLogout:                     None,
            self.btnLanguage:                   None,
            self.btnTheme:                      None,
        }

        self._sidebarBtnStyle = """
            QPushButton {
                background: transparent;
                border: none;
                padding: 6px;
                border-radius: 6px;
            }

            /* Hover */
            QPushButton:hover {
                background: rgba(128, 128, 128, 0.15);
            }

            /* Pressed */
            QPushButton:pressed {
                background: rgba(128, 128, 128, 0.30);
            }

            /* Selected */
            QPushButton[selected="true"] {
                background: rgba(25,200,150,45);
                /* border-left: 4px solid #1a3a5c; */
            }

            /* Selected hover */
            QPushButton[selected="true"]:hover {
                background: rgba(25,200,150,65);
            }
            """

        for btn in self._sideBarBtnMap.keys():
            btn.setIconSize(QSize(32, 32))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._sidebarBtnStyle)
            if self._sideBarBtnMap[btn] is not None:
                btn.clicked.connect(partial(self.stack.setCurrentWidget, self._sideBarBtnMap[btn]))
        
        self.btnSettings.clicked.connect(self.dlgSettings)
        self.btnLanguage.clicked.connect(self.chgLanguage)
        self.btnRefresh.clicked.connect(lambda: self.refreshGUI(refreshArchivedPTWs=True))
        self.btnLogout.clicked.connect(self.logout)
        self.btnTheme.clicked.connect(self.toggleTheme)

        self.setCentralWidget(self.stack)

        self.sideBarLayout = QToolBar("SideBar Navigator")
        self.sideBarLayout.setMovable(False)
        # self.sideBarLayout.setAllowedAreas(Qt.ToolBarArea.LeftToolBarArea | Qt.ToolBarArea.RightToolBarArea | Qt.ToolBarArea.BottomToolBarArea)
        self.sideBarLayout.setFloatable(False)
        self.sideBarLayout.setIconSize(QSize(32, 32))
        self.sideBarLayout.setStyleSheet(f"""
            QToolBar {{
                background: palette(dark);
                spacing: 2px;
                padding: 4px 2px;
            }}
            QToolBar::separator:vertical {{
                background: palette(mid);
                height: 2px;
                margin: 2px 4px;
            }}
            QToolBar::separator:horizontal {{
                background: palette(mid);
                width: 2px;
                margin: 4px 2px;
            }}
        """)
        self.sideBarLayout.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sideBarLayout.customContextMenuRequested.connect(self._sideBarMoveMenu)
        self._sidebarDockActions: dict[Qt.ToolBarArea, QAction] = {}
        # Default dock side follows reading direction: left for English, right for Arabic -
        # still just a starting point, the sidebar's context menu (_sideBarMoveMenu) can move
        # it to either side or the bottom regardless of language.
        defaultSidebarArea = Qt.ToolBarArea.RightToolBarArea if i18n.is_rtl() else Qt.ToolBarArea.LeftToolBarArea
        self.addToolBar(defaultSidebarArea, self.sideBarLayout)
        self._initSidebarHover()

        self.toolbar = QToolBar("ToolBar")
        self.toolbar.setMovable(False)
        self.toolbar.setStyleSheet("""
            QToolBar {
                background: palette(dark);
                spacing: 4px;
                padding: 2px 4px;
            }
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
                color: palette(window-text);
                font-size: 13px;
            }
            QToolButton:hover {
                background: rgba(128, 128, 128, 0.20);
            }
            QToolButton:pressed {
                background: rgba(128, 128, 128, 0.38);
            }
        """)
        self.addToolBar(self.toolbar)

        # Create Floating Action Button
        self.btnFAB = QPushButton(self)
        self.btnFAB.setFixedSize(60, 60)
        # self.btnFAB.setIcon(QIcon.fromTheme("list-add"))
        self.btnFAB.setIconSize(QSize(32, 32))
        self.btnFAB.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: white;
                border-radius: 30px;
                border: none;
            }
            QPushButton:hover {
                background-color: #1565C0;
            }
            QPushButton:pressed {
                background-color: #0D47A1;
            }
        """)
        self.btnFAB.setToolTip("")
        self.btnFAB.clicked.connect(self.btnFABHandler)
        self.btnFABUpdatePosition()

        self._fabOpacityEffect = QGraphicsOpacityEffect(self.btnFAB)
        self.btnFAB.setGraphicsEffect(self._fabOpacityEffect)
        self._fabOpacityEffect.setOpacity(self._FAB_MIN_OPACITY)
        self._fabProximityTimer = QTimer(self)
        self._fabProximityTimer.setInterval(self._FAB_PROXIMITY_CHECK_INTERVAL_MS)
        self._fabProximityTimer.timeout.connect(self._updateFabProximity)
        self._fabProximityTimer.start()

        self._refreshOverlay = RefreshOverlay(self)

        self.stackTabChanged()
        self.refreshGUI()

        sb = self.statusBar()
        sb.show()
        sb.setStyleSheet("""
            QStatusBar { 
                background: palette(dark); 
                color: palette(window-text); 
                padding: 0 8px; 
                font-size: 14px; 
                border-top: 2px solid palette(mid); 
            }
        """)

        self._forceClose = False

        self._trayIcon = QSystemTrayIcon(QIcon(resource_path("assets/sh-logo-trans.png")), self)
        trayMenu = QMenu(self)
        trayMenu.addAction(t("Open PTW")).triggered.connect(self._restoreFromTray)
        trayMenu.addSeparator()
        trayMenu.addAction(t("Quit")).triggered.connect(self._quitApp)
        self._trayIcon.setContextMenu(trayMenu)
        self._trayIcon.activated.connect(self._onTrayActivated)
        self._trayIcon.show()

        self._sseListener = SSEListener(SERVER_URL, loggedUser.getUsername(), loggedUser.getPassword())
        self._sseListener.eventReceived.connect(self._onSSEEvent)
        self._sseListener.start()

        # PA-side reminder: a RUNNING PTW whose shift ended, or any open PTW past its
        # 14-shift validity, needs a human decision — see _checkPtwAlarms(). Nothing here
        # ever acts on a PTW automatically, it only nags until someone does.
        self._ptwAlarmSnoozeUntil = None
        self._ptwAlarmDialogOpen = False
        self._ptwAlarmTimer = QTimer(self)
        self._ptwAlarmTimer.setInterval(self._PTW_ALARM_CHECK_INTERVAL_MS)
        self._ptwAlarmTimer.timeout.connect(self._checkPtwAlarms)
        self._ptwAlarmTimer.start()

    def _on_request_done_generic(self, err, _):
        """Default callback for PTW/IC action requests: warn on error, otherwise do
        nothing since the resulting SSE event drives the GUI refresh."""
        if err:
            QMessageBox.warning(self, t('Fail'), err)
            return
        # self.refreshGUI()  # SSE event handles refresh

    def toggleTheme(self):
        """Handle a click of the theme button: flip between light and dark theme via
        `_applyThemeChange`."""
        hints = QApplication.styleHints()
        is_dark = hints.colorScheme() == Qt.ColorScheme.Dark
        new_theme = 'light' if is_dark else 'dark'
        self._applyThemeChange(new_theme)

    def _applyThemeChange(self, new_theme: str | None):
        """Apply a pending switch to `new_theme` (None for system default): ask the
        user via a modal to restart now, defer, or cancel the change; save the new
        theme preference to the server; and, if the user chose to restart now, log
        out immediately so the app can relaunch with the new theme."""
        import os, sys
        label = t(new_theme.capitalize()) if new_theme else t("Default (System)")
        msg = QMessageBox(self)
        msg.setWindowTitle(t("Switch Theme"))
        msg.setText(t("Switching to {0} mode requires a full-application restart.").format(label))
        btn_restart = msg.addButton(t("Restart Now"), QMessageBox.ButtonRole.AcceptRole)
        btn_later   = msg.addButton(t("Later"),        QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel  = msg.addButton(t("Cancel Change"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_restart)
        msg.exec()

        if msg.clickedButton() == btn_cancel:
            return

        self.loggedUser.setTheme(new_theme)

        def on_done(err, _):
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to save theme preference:") + f"\n{err}")
                return

        if msg.clickedButton() == btn_restart:
            err = ClientRequests.updateTheme(self.loggedUser, new_theme)
            on_done(err, None)
            self.logout()
        else:
            ClientRequests.updateTheme(self.loggedUser, new_theme, callback=on_done)


    def _sideBarStretch(self):
        """Add an expanding spacer widget to the sidebar so buttons added after it are
        pushed to the opposite end of the toolbar."""
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.sideBarLayout.addWidget(spacer)

    def resizeEvent(self, event):
        """Qt resize event override: reposition the floating action button whenever
        the window is resized."""
        self.btnFABUpdatePosition()
        super().resizeEvent(event)

    def _moveSidebar(self, area: Qt.ToolBarArea):
        """Dock the sidebar toolbar to `area` (left/right/bottom), first collapsing it
        out of its hover-expanded state if needed, and refresh the dock-position
        menu's checked state to match."""
        if self._sidebarExpanded:
            self._sidebarExpanded = False
            self._sidebarAnim.stop()
            for btn in self._sideBarBtnMap:
                btn.setText("")
                btn.setStyleSheet(self._sidebarBtnStyle)
                btn.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
                btn.setMinimumWidth(0)
        self.addToolBar(area, self.sideBarLayout)
        is_vertical = area in (Qt.ToolBarArea.LeftToolBarArea, Qt.ToolBarArea.RightToolBarArea)
        if is_vertical:
            self.sideBarLayout.setMaximumWidth(self._sidebarCollapsedW)
        else:
            self.sideBarLayout.setMaximumWidth(16777215)
        self._updateSidebarDockActions()

    def _updateSidebarDockActions(self):
        """Sync the checked state of the Left/Right/Bottom dock-position actions with
        the sidebar toolbar's actual current dock area."""
        current = self.toolBarArea(self.sideBarLayout)
        for area, act in self._sidebarDockActions.items():
            act.setChecked(area == current)

    def _sideBarMoveMenu(self, pos):
        """Show a context menu, triggered by a right-click on the sidebar, offering to
        move it to the left, right, or bottom dock area."""
        current = self.toolBarArea(self.sideBarLayout)
        menu = QMenu(self)
        for area, label in [
            (Qt.ToolBarArea.LeftToolBarArea,   t("Move to Left")),
            (Qt.ToolBarArea.RightToolBarArea,  t("Move to Right")),
            (Qt.ToolBarArea.BottomToolBarArea, t("Move to Bottom")),
        ]:
            act = menu.addAction(label)
            act.setEnabled(area != current)
            act.triggered.connect(lambda _, a=area: self._moveSidebar(a))
        menu.exec(self.sideBarLayout.mapToGlobal(pos))

    def _initSidebarHover(self):
        """Set up the sidebar's hover-to-expand behavior: initial collapsed/expanded
        widths, the width animation, the hover-delay timer, and the event filter used
        to detect mouse enter/leave on the sidebar and its buttons."""
        self._sidebarExpanded = False
        self._sidebarCollapsedW = 52
        self._sidebarExpandedW = 320
        self.sideBarLayout.setMaximumWidth(self._sidebarCollapsedW)
        self._sidebarAnim = QPropertyAnimation(self.sideBarLayout, b"maximumWidth")
        self._sidebarAnim.setDuration(300)
        self._sidebarAnim.setEasingCurve(QEasingCurve.Type.InOutQuart)
        self._sidebarAnim.finished.connect(self._onSidebarAnimFinished)
        self._sidebarHoverTimer = QTimer(self)
        self._sidebarHoverTimer.setSingleShot(True)
        self._sidebarHoverTimer.setInterval(600)
        self._sidebarHoverTimer.timeout.connect(self._expandSidebar)
        self.sideBarLayout.installEventFilter(self)
        for btn in self._sideBarBtnMap:
            btn.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Qt event filter: suppress the native tooltip popup on sidebar buttons
        (their label is shown via the hover-expanded sidebar instead) and start/stop
        the hover-expand timer, and trigger the collapse, as the mouse enters/leaves
        the sidebar toolbar."""
        if obj in self._sideBarBtnMap and event.type() == QEvent.Type.ToolTip:
            return True  # suppress tooltip popup while keeping toolTip() text intact
        if obj is self.sideBarLayout:
            area = self.toolBarArea(self.sideBarLayout)
            is_vertical = area in (Qt.ToolBarArea.LeftToolBarArea, Qt.ToolBarArea.RightToolBarArea)
            if is_vertical:
                if event.type() == QEvent.Type.Enter:
                    self._sidebarHoverTimer.start()
                elif event.type() == QEvent.Type.Leave:
                    self._sidebarHoverTimer.stop()
                    self._collapseSidebar()
        return super().eventFilter(obj, event)

    def _expandSidebar(self):
        """Expand the sidebar to show each button's label next to its icon, invoked
        once the hover-delay timer elapses; highlights the button for the currently
        selected tab at full opacity and dims the others."""
        if self._sidebarExpanded:
            return
        self._sidebarExpanded = True
        expanded_style = self._sidebarBtnStyle + "QPushButton { text-align: left; padding-left: 8px; }"
        current = self.stack.currentWidget()
        for btn, tab in self._sideBarBtnMap.items():
            is_selected = (tab is current)
            tip = btn.toolTip()
            if tip:
                btn.setText(tip.split(" [")[0])
            btn.setStyleSheet(expanded_style)
            effect = btn.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(btn)
                btn.setGraphicsEffect(effect)
            effect.setOpacity(1.0 if is_selected or tab is None else 0.5)
            btn.update()


        self._sidebarAnim.stop()
        self._sidebarAnim.setStartValue(self.sideBarLayout.maximumWidth())
        self._sidebarAnim.setEndValue(self._sidebarExpandedW)
        self._sidebarAnim.start()

    def _collapseSidebar(self):
        """Animate the sidebar back to its narrow, icon-only width, invoked when the
        mouse leaves it, restoring the selected/dimmed opacity of each button."""
        if not self._sidebarExpanded:
            return
        self._sidebarExpanded = False
        self._sidebarAnim.stop()
        self._sidebarAnim.setStartValue(self.sideBarLayout.maximumWidth())
        self._sidebarAnim.setEndValue(self._sidebarCollapsedW)
        self._sidebarAnim.start()
        current = self.stack.currentWidget()
        for btn, tab in self._sideBarBtnMap.items():
            is_selected = (tab is current)
            effect = btn.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(btn)
                btn.setGraphicsEffect(effect)
            effect.setOpacity(1.0 if is_selected or tab is None else 0.2)
            btn.update()


    def _onSidebarAnimFinished(self):
        """Slot for the sidebar width animation's `finished` signal: once a collapse
        animation ends, clear each button's text and style back to icon-only."""
        if not self._sidebarExpanded:
            for btn in self._sideBarBtnMap:
                btn.setText("")
                btn.setStyleSheet(self._sidebarBtnStyle)
                btn.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def createPopupMenu(self):
        """Qt override: disable QMainWindow's default toolbar/dock-widget right-click
        context menu by returning None."""
        return None

    def stackTabChanged(self):
        """Slot for the stacked widget's `currentChanged` signal (also invoked once at
        startup): update every sidebar button's selected/highlighted appearance to
        match whichever tab is now current."""
        self.update()
        current = self.stack.currentWidget()
        for btn, tab in self._sideBarBtnMap.items():
            is_selected = (tab is current)
            btn.setProperty("selected", is_selected)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            effect = btn.graphicsEffect()
            if not isinstance(effect, QGraphicsOpacityEffect):
                effect = QGraphicsOpacityEffect(btn)
                btn.setGraphicsEffect(effect)
            effect.setOpacity(1.0 if is_selected or tab is None else 0.2)
            btn.update()

    def btnFABHandler(self):
        """Handle a click of the floating action button; base implementation is a
        no-op, overridden by role-specific windows that need a FAB action (e.g.
        creating a new PTW or IC)."""
        return
    
    def logout(self):
        """Handle a logout request: stop the SSE listener, hide the tray icon, force
        a real close (bypassing the close-to-tray prompt), and emit `on_logout`."""
        self._sseListener.stop()
        self._sseListener.wait(1000)
        self._trayIcon.hide()
        self._forceClose = True
        self.on_logout.emit()
        self.close()

    def closeEvent(self, event):
        """Qt close event override triggered by the window's close (X) button: apply a
        remembered close-to-tray/exit preference immediately if one is set, otherwise
        ask the user (with an optional 'remember my choice' checkbox) whether to keep
        running in the tray or exit completely, and act on the answer — Cancel just
        re-ignores the event."""
        self._ptwAlarmTimer.stop()
        self._fabProximityTimer.stop()
        if self._forceClose:
            event.accept()
            return

        behavior = QSettings("PTW", "PTW").value(SETTINGS_CLOSE_BEHAVIOR_KEY, "", type=str)

        if behavior == "tray":
            event.ignore()
            self._minimizeToTray()
            return

        if behavior == "exit":
            self._quitApp()
            event.accept()
            return

        msgBox = QMessageBox(self)
        msgBox.setWindowTitle(t("Close PTW"))
        msgBox.setText(
            t("Do you want to keep receiving notifications in the background?\n\n"
              "Yes - PTW keeps running in the system tray and notifies you of updates.\n"
              "No - PTW closes completely and you stop receiving notifications.")
        )
        msgBox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel)
        msgBox.setDefaultButton(QMessageBox.StandardButton.Yes)
        chkRemember = QCheckBox(t("Remember my choice (change anytime in Settings)"))
        msgBox.setCheckBox(chkRemember)
        reply = msgBox.exec()

        if reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return

        if chkRemember.isChecked():
            QSettings("PTW", "PTW").setValue(
                SETTINGS_CLOSE_BEHAVIOR_KEY, "exit" if reply == QMessageBox.StandardButton.No else "tray"
            )

        if reply == QMessageBox.StandardButton.No:
            self._quitApp()
            event.accept()
            return

        event.ignore()
        self._minimizeToTray()

    def _minimizeToTray(self):
        """Hide the main window and show a tray notification that PTW is still
        running in the background."""
        self.hide()
        self._trayIcon.showMessage(
            t("PTW"), t("Still running in the background. Click the tray icon to reopen."),
            QSystemTrayIcon.MessageIcon.Information, 3000
        )

    def _onTrayActivated(self, reason):
        """Slot for the tray icon's `activated` signal: restore the main window on a
        single (Trigger) or double click."""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._restoreFromTray()

    def _restoreFromTray(self):
        """Show, raise, and activate the main window, restoring it from the system
        tray (used by both the tray icon's activation and its 'Open PTW' menu
        action)."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _quitApp(self):
        """Fully quit the application (from the tray menu's 'Quit' action or a
        close-behavior of 'exit'): stop the SSE listener, hide the tray icon, and
        call `QApplication.quit()`."""
        self._sseListener.stop()
        self._sseListener.wait(1000)
        self._trayIcon.hide()
        self._forceClose = True
        QApplication.quit()
    
    def viewPTW(self, row: int, ptw: PTW):
        """Open a read-only `DialogPTW` for `ptw`, e.g. from a table's View action."""
        self._refreshOverlay.showBusy()
        viewPTWDialog = DialogPTW(self, self.loggedUser, ptw, None, False, True, t('View Mode - PTW# {0}').format(ptw.id))
        self._refreshOverlay.hideBusy()
        viewPTWDialog.exec()

    def _savePTWRiskAssessment(self, ptwId: int, risk: RiskAssessment, callback=None):
        """Save `risk` as the PTW's risk assessment on the server, or delete the
        existing one for `ptwId` if `risk` is falsy."""
        if risk:
            ClientRequests.updateRiskAssessment(self.loggedUser, risk, callback=callback)
        else:
            ClientRequests.deleteRiskAssessment(self.loggedUser, str(ptwId), ptwId, callback=callback)

    def editPTW(self, row: int, ptw: PTW):
        """Open `ptw` in an editable `DialogPTW`; on acceptance, clear its approval
        history if it had been RETURNED, save its risk assessment, and update the
        row in the current table."""
        toEditPtw = copy.deepcopy(ptw)
        wasReturned = toEditPtw.approval_status == PTW.ApprovalStatus.RETURNED
        self._refreshOverlay.showBusy()
        editPTWDialog = DialogPTW(self, self.loggedUser, toEditPtw, None, False, False, t('Edit Mode - PTW# {0}').format(ptw.id))
        self._refreshOverlay.hideBusy()
        if editPTWDialog.exec() == QDialog.DialogCode.Accepted:
            if wasReturned:
                toEditPtw.clearApprovals()
            ptw = toEditPtw

            def on_risk_saved(err, _):
                if err:
                    QMessageBox.warning(self, t("Warning"), t("PTW saved but failed to save risk assessment:") + f" {err}")
            risk = RiskAssessment(title=ptw.description, date=datetime.now().strftime('%d %b %Y'), risks=editPTWDialog.riskAssessmentPreviewTable.getRiskItems(), ptw_id=ptw.id)
            self._savePTWRiskAssessment(ptw.id, risk, callback=on_risk_saved)

            self.stack.currentWidget().updatePTW(row, ptw)

    def addPTWDialog(self, row: int = None, ptw: PTW = None):
        """Open a new-PTW dialog, or a re-request dialog pre-filled from `ptw` (e.g.
        for a rejected/deleted permit) when `ptw` is given; on acceptance, submit the
        new PTW, save its risk assessment, and upload any pending attachments —
        additionally copying `ptw`'s own attachments (and, server-side, its risk rows)
        onto the new PTW when re-requesting."""
        newPTW = copy.deepcopy(ptw) if ptw else PTW()
        if ptw:
            newPTW.setId(None).clearApprovals()
        title = t("Re-request PTW") if ptw else t("New PTW")
        self._refreshOverlay.showBusy()
        dlg = DialogPTW(self, self.loggedUser, newPTW, ptw, True, False, title)
        self._refreshOverlay.hideBusy()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        def on_addPTW_done(err, ptwId=None):
            def on_copy_attachments_done(err, _):
                if err:
                    QMessageBox.warning(self, t("Error"), t("Failed to copy attachments:") + f" {err}")
                    return

            def on_attachments_uploaded(err, _):
                if err:
                    QMessageBox.warning(self, t("Error"), t("Failed to upload attachments:") + f" {err}")
                    return
                if ptw:
                    ClientRequests.copyPtwAttachments(self.loggedUser, ptw.id, newPTW.id, callback=on_copy_attachments_done)
                # self.refreshGUI()  # SSE event handles refresh

            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            newPTW.setId(ptwId)

            def on_risk_saved(err, _):
                if err:
                    QMessageBox.warning(self, t("Warning"), t("PTW saved but failed to save risk assessment:") + f" {err}")
            risk = RiskAssessment(title=newPTW.description, date=datetime.now().strftime('%d %b %Y'), risks=dlg.riskAssessmentPreviewTable.getRiskItems(), ptw_id=ptwId)
            self._savePTWRiskAssessment(ptwId, risk, callback=on_risk_saved)
            # On re-request, the server also copies the original PTW's own risk rows onto
            # this new ptw_id (server/app.py copyPtwAttachments), additively — so any custom
            # rows from the original that weren't re-selected/re-added here still carry over.

            if dlg.attachsToBeUploaded:
                ClientRequests.addPtwAttachments(self.loggedUser, newPTW.id, dlg.attachsToBeUploaded, callback=on_attachments_uploaded)

        ClientRequests.addPTW(self.loggedUser, newPTW, callback=on_addPTW_done)


    def deletePTW(self, row: int, ptw: PTW):
        """Delete `ptw` at `row` via the current table's own delete handling."""
        self.stack.currentWidget().deletePTW(row)
    
    def archivePTWs(self, rows: list, ptws: list[PTW]):
        """Archive the given PTWs in one bulk request, e.g. from a table's Archive
        action."""
        ClientRequests.archivePTWs(self.loggedUser, [ptw.id for ptw in ptws], callback=self._on_request_done_generic)
    
    def requestToRunPTW(self, row: int, ptw: PTW):
        """Send a run request for `ptw` as the current user acting as Performing
        Authority, refusing if the user is already the PA on another PTW."""
        for p in globalData.allPTWs.values():
            if p.getPerforming() == self.loggedUser.getUsername():
                QMessageBox.warning(self, t('Not Allowed'), t("You are already the PA for PTW# {0}.").format(p.id))
                return

        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.requestToRunPTW(self.loggedUser, ptw.id, pa, ts, callback=self._on_request_done_generic)

    def runAcceptTW(self, row: int, ptw: PTW):
        """Prompt for confirmation and an optional comment, then accept `ptw`'s
        pending run request as the Issuing Authority."""
        proceed, comment = self.getOptionalComment(t('Accept PTW#{0} Run').format(ptw.id), t("Are you sure you want to accept run request for PTW#{0}?").format(ptw.id))
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, True, comment, callback=self._on_request_done_generic)

    def runRejectTW(self, row: int, ptw: PTW):
        """Prompt for confirmation and an optional comment, then reject `ptw`'s
        pending run request as the Issuing Authority."""
        proceed, comment = self.getOptionalComment(t('Reject PTW#{0} Run').format(ptw.id), t("Are you sure you want to reject run request for PTW#{0}?").format(ptw.id))
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, False, comment, callback=self._on_request_done_generic)

    def requestToClsPTW(self, row: int, ptw: PTW, callback=None):
        """Prompt for confirmation and an optional comment, then send a close request
        for `ptw` as the Performing Authority."""
        proceed, comment = self.getOptionalComment(t('Close PTW'), t("Are you sure you want to close PTW#{0}?").format(ptw.id))
        if not proceed:
            return

        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.requestToClsPTW(self.loggedUser, ptw.id, pa, ts, comment, callback=callback or self._on_request_done_generic)

    def clsAcceptPTW(self, row: int, ptw: PTW):
        """Prompt for confirmation and an optional comment, then accept `ptw`'s
        pending close request as the Issuing Authority (irreversible)."""
        proceed, comment = self.getOptionalComment(t('Accept PTW#{0} Close').format(ptw.id), t("Are you sure you want to accept close request for PTW#{0}? This is irreversible").format(ptw.id))
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, True, comment, callback=self._on_request_done_generic)

    def clsRejectPTW(self, row: int, ptw: PTW):
        """Prompt for confirmation and an optional comment, then reject `ptw`'s
        pending close request as the Issuing Authority."""
        proceed, comment = self.getOptionalComment(t('Reject PTW#{0} Close').format(ptw.id), t("Are you sure you want to reject close request for PTW#{0}?").format(ptw.id))
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, False, comment, callback=self._on_request_done_generic)

    def _linkedICsFor(self, ptw: PTW) -> list[IC]:
        """Resolve `ptw.linked_ics` (a list of IC id strings) to the actual `IC`
        objects from the global cache."""
        icsById = {str(ic.id): ic for ic in globalData.ics.values()}
        return [icsById[icId] for icId in ptw.linked_ics if icId in icsById]

    def requestToHldPTW(self, row: int, ptw: PTW, callback=None):
        """If `ptw` has linked ICs, prompt the PA to pick which ones to keep held;
        then, after confirmation with an optional comment, send a hold request for
        `ptw` carrying the selected IC ids."""
        heldICs = []
        linkedICs = self._linkedICsFor(ptw)
        if linkedICs:
            dlg = DialogSelectHeldICs(self, linkedICs, selectable=True, title=t("Hold PTW# {0} - Select ICs to Keep Held").format(ptw.id))
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            heldICs = dlg.getHeldICIds()

        proceed, comment = self.getOptionalComment(t('Hold PTW# {0}').format(ptw.id), t("Are you sure you want to request hold for PTW#{0}?").format(ptw.id))
        if not proceed:
            return
        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.requestToHldPTW(self.loggedUser, ptw.id, pa, ts, comment, heldICs, callback=callback or self._on_request_done_generic)

    def hldAcceptPTW(self, row: int, ptw: PTW, comment: str = None):
        """Accept `ptw`'s pending hold request as the Issuing Authority."""
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, True, comment, callback=self._on_request_done_generic)

    def hldRejectPTW(self, row: int, ptw: PTW, comment: str = None):
        """Reject `ptw`'s pending hold request as the Issuing Authority."""
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, False, comment, callback=self._on_request_done_generic)

    def hldTakeAction(self, row: int, ptw: PTW):
        """Act on `ptw`'s pending hold request as Issuing Authority: refuse if it
        isn't actually waiting on a hold confirmation, otherwise show the linked-ICs
        review dialog to pick accept/reject, then confirm with an optional comment
        and dispatch to `hldAcceptPTW`/`hldRejectPTW`."""
        if ptw.running_status != PTW.RunningStatus.WAITING_HLD_CONFIRM:
            QMessageBox.warning(self, t('Not Allowed'), t("PTW# {0} is not waiting for hold confirmation.").format(ptw.id))
            return
        dlg = DialogSelectHeldICs(self, self._linkedICsFor(ptw), held=ptw.getHeldICs(), selectable=False, review_mode=True, title=t("Hold Action - PTW# {0}").format(ptw.id))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.action not in ('accept', 'reject'):
            return
        proceed, comment = self.getOptionalComment(t('Hold Action - PTW# {0}').format(ptw.id), t("Confirm {0} for the hold request on PTW#{1}?").format(dlg.action, ptw.id))
        if not proceed:
            return
        if dlg.action == 'accept':
            self.hldAcceptPTW(row, ptw, comment)
        elif dlg.action == 'reject':
            self.hldRejectPTW(row, ptw, comment)

    def viewHeldICs(self, row: int, ptw: PTW):
        """Open a read-only view of which linked ICs are currently kept held for
        `ptw`."""
        dlg = DialogSelectHeldICs(
            self, self._linkedICsFor(ptw), held=ptw.getHeldICs(),
            selectable=False, view_only=True,
            title=t("Held ICs - PTW# {0}").format(ptw.id)
        )
        dlg.exec()

    def viewIC(self, row: int, ic: IC):
        """Open a read-only `DialogIC` for `ic`."""
        dlg = DialogIC(self, self.loggedUser, ic, False, True, t("IC — {0}").format(ic.type))
        dlg.exec()

    def printIC(self, row: int, ic: IC):
        """Generate and open a printable report for `ic`, showing the busy overlay
        while it's produced."""
        self._refreshOverlay.showBusy()
        try:
            ReportGenerator.icReport(self.loggedUser, ic)
        finally:
            self._refreshOverlay.hideBusy()

    def acceptIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, record an irreversible approval for `ic` on its
        approval chain."""
        reply = QMessageBox.question(
            self, t('Accept IC #{0}').format(ic.id), t("Are you sure you want to approve IC #{0}? This is irreversible").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        approval = IC.Approval(IC.ApprovalActions.APPROVED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        ClientRequests.updateApprovalIC(self.loggedUser, ic.id, approval, callback=self._on_request_done_generic)

    def requestEditsIC(self, row: int, ic: IC):
        """Prompt for a mandatory comment and return `ic` to its requestor for edits,
        recording a RETURNED approval action."""
        comment = self.getComment(t('Return IC #{0} to be Edited').format(ic.id))
        if not comment:
            return
        approval = IC.Approval(IC.ApprovalActions.RETURNED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'), comment)
        ClientRequests.updateApprovalIC(self.loggedUser, ic.id, approval, callback=self._on_request_done_generic)

    def requestIsolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, request isolation for `ic`, notifying the
        Issuing Authority to confirm."""
        reply = QMessageBox.question(
            self, t('Request Isolate #{0}').format(ic.id), t("Request isolation for IC #{0}? This will notify Issuing to confirm.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.requestIsolateIC(self.loggedUser, ic.id, callback=self._on_request_done_generic)

    def confirmIsolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, confirm `ic`'s isolate request as Issuing
        Authority, notifying the isolator to carry it out."""
        reply = QMessageBox.question(
            self, t('Confirm Isolate #{0}').format(ic.id), t("Confirm isolation for IC #{0}? The isolator will then be notified to carry it out.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.confirmIsolateIC(self.loggedUser, ic.id, True, callback=self._on_request_done_generic)

    def returnIsolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, return `ic`'s isolate request, requiring the
        requestor to request isolation again."""
        reply = QMessageBox.question(
            self, t('Return Isolate Request #{0}').format(ic.id), t("Return the isolate request for IC #{0}? The requestor will need to request isolation again.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.confirmIsolateIC(self.loggedUser, ic.id, False, callback=self._on_request_done_generic)

    def executeIsolateIC(self, row: int, ic: IC):
        """Carry out `ic`'s isolation as the isolator: if `ic` has items, collect
        per-item lock details via `DialogCompleteIsolation`; otherwise just confirm
        physical completion; then submit the isolation as executed."""
        if ic.items:
            dlg = DialogCompleteIsolation(self, ic.items)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return
            items = dlg.getItems()
        else:
            reply = QMessageBox.question(
                self, t('Complete Isolation #{0}').format(ic.id), t("Confirm that isolation for IC #{0} has been physically carried out?").format(ic.id),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            items = []
        ClientRequests.executeIsolateIC(self.loggedUser, ic.id, items, callback=self._on_request_done_generic)

    def requestDeisolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, request de-isolation for `ic`, notifying the
        Issuing Authority to confirm."""
        reply = QMessageBox.question(
            self, t('Request De-isolate #{0}').format(ic.id), t("Request de-isolation for IC #{0}? This will notify Issuing to confirm.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.requestDeisolateIC(self.loggedUser, ic.id, callback=self._on_request_done_generic)

    def confirmDeisolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, confirm `ic`'s de-isolate request as Issuing
        Authority, notifying the isolator to carry it out."""
        reply = QMessageBox.question(
            self, t('Confirm De-isolate #{0}').format(ic.id), t("Confirm de-isolation for IC #{0}? The isolator will then be notified to carry it out.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.confirmDeisolateIC(self.loggedUser, ic.id, True, callback=self._on_request_done_generic)

    def returnDeisolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, return `ic`'s de-isolate request, requiring the
        requestor to request de-isolation again."""
        reply = QMessageBox.question(
            self, t('Return De-isolate Request #{0}').format(ic.id), t("Return the de-isolate request for IC #{0}? The requestor will need to request de-isolation again.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.confirmDeisolateIC(self.loggedUser, ic.id, False, callback=self._on_request_done_generic)

    def executeDeisolateIC(self, row: int, ic: IC):
        """Confirm and, if confirmed, carry out `ic`'s de-isolation as the
        isolator."""
        reply = QMessageBox.question(
            self, t('Complete De-isolation #{0}').format(ic.id), t("Confirm that de-isolation for IC #{0} has been physically carried out?").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.executeDeisolateIC(self.loggedUser, ic.id, callback=self._on_request_done_generic)

    def linkPTWToIC(self, row: int, ic: IC):
        """Prompt for a PTW number and link it to `ic`, refusing if that PTW is
        already linked."""
        ptwId, ok = QInputDialog.getText(self, t('Link IC #{0} to PTW').format(ic.id), t('PTW #:'))
        if not ok or not ptwId.strip():
            return
        ptwId = ptwId.strip()
        if ptwId in ic.linked_ptws:
            QMessageBox.warning(self, t("Already Linked"), t("PTW #{0} is already linked to this IC.").format(ptwId))
            return
        ClientRequests.linkPTWToIC(self.loggedUser, ic.id, ptwId, callback=self._on_request_done_generic)

    def linkICToPTW(self, row: int, ptw: PTW):
        """Prompt for an IC number and link `ptw` to it, validating the input is
        numeric and refusing if it's already linked."""
        certIdText, ok = QInputDialog.getText(self, t('Link PTW #{0} to IC').format(ptw.id), t('IC #:'))
        if not ok or not certIdText.strip():
            return
        try:
            icId = int(certIdText.strip())
        except ValueError:
            QMessageBox.warning(self, t("Invalid IC #"), t("IC # must be a number."))
            return
        if str(icId) in ptw.linked_ics:
            QMessageBox.warning(self, t("Already Linked"), t("IC #{0} is already linked to this PTW.").format(icId))
            return
        ClientRequests.linkPTWToIC(self.loggedUser, icId, ptw.id, callback=self._on_request_done_generic)

    def requestToSuctionTestPTW(self, row: int, ptw: PTW):
        """Placeholder for requesting a suction-for-test action on `ptw`; not yet
        implemented."""
        pass

    def suctionTestAcceptPTW(self, row: int, ptw: PTW):
        """Placeholder for approving a pending suction-for-test request on `ptw`; not
        yet implemented."""
        pass

    def suctionTestRejectPTW(self, row: int, ptw: PTW):
        """Placeholder for rejecting a pending suction-for-test request on `ptw`; not
        yet implemented."""
        pass


    def viewUser(self, username: str, role: str):
        """Open a read-only `DialogUser` for `username` (labeled with `role`, e.g.
        'PA'/'IA'/'Requestor'), warning instead if no username is assigned or the
        user can't be found."""
        if username is None or username.strip() == '':
            QMessageBox.warning(self, t('No {0} Assigned').format(t(role)), t("No {0} assigned yet.").format(t(role)))
            return
        elif username not in globalData.allUsers:
            QMessageBox.warning(self, t('User Not Found'), t("username {0} was not found.").format(username))
            return
        DialogUser(self, True, False, self.loggedUser, globalData.allUsers[username], t("{0} - View Mode - User {1}").format(t(role), username)).exec()
    
    def viewRequestorPTW(self, row: int, ptw: PTW):
        """View `ptw`'s requestor via `viewUser`."""
        self.viewUser(ptw.requestor, 'Requestor')

    def viewPerformingPTW(self, row: int, ptw: PTW):
        """View `ptw`'s current Performing Authority via `viewUser`."""
        self.viewUser(ptw.getPerforming(), 'PA')

    def viewIssuing(self, row: int, ptw: PTW):
        """View `ptw`'s current Issuing Authority via `viewUser`."""
        self.viewUser(ptw.getIssuing(), 'IA')
    
    def chgLanguage(self):
        """Handle a click of the language button: flip between English and Arabic via
        `_applyLanguageChange`."""
        new_language = 'en' if self.language == 'ar' else 'ar'
        self._applyLanguageChange(new_language)

    def _applyLanguageChange(self, new_language: str | None):
        """Apply a pending switch to `new_language` ('en'/'ar', or None for the OS-locale
        default): ask the user via a modal to restart now, defer, or cancel the change;
        save the new language preference to the server; and, if the user chose to restart
        now, log out immediately so the app can relaunch with the new language and text
        direction (translated strings are baked into widgets at construction time, so -
        exactly like a theme change - this can't be applied live to an already-built
        window)."""
        effective = new_language or i18n.current_lang()
        label = {"en": t("English"), "ar": t("Arabic"), None: t("Default (System)")}.get(new_language, new_language)
        msg = QMessageBox(self)
        msg.setWindowTitle(t("Switch Language"))
        msg.setText(t("Switching to {0} requires a full-application restart.").format(label))
        btn_restart = msg.addButton(t("Restart Now"), QMessageBox.ButtonRole.AcceptRole)
        btn_later   = msg.addButton(t("Later"),        QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel  = msg.addButton(t("Cancel Change"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_restart)
        msg.exec()

        if msg.clickedButton() == btn_cancel:
            return

        self.loggedUser.setLanguage(new_language)
        self.language = effective
        # Intentionally NOT run through t(): see the identical construct in __init__ above -
        # this always names the *target* language in that language's own script.
        self.btnLanguage.setToolTip("Switch to English" if effective == 'ar' else "حول إلى العربية")

        def on_done(err, _):
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to save language preference:") + f"\n{err}")
                return

        if msg.clickedButton() == btn_restart:
            err = ClientRequests.updateLanguage(self.loggedUser, new_language)
            on_done(err, None)
            self.logout()
        else:
            ClientRequests.updateLanguage(self.loggedUser, new_language, callback=on_done)

    def dlgSettings(self):
        """Open the Settings dialog, invoked from the settings button or the welcome
        banner's name link; blocks Guest users. On acceptance, save the updated user
        profile to the server, refresh the welcome banner's name/role text, and
        prompt to apply a theme and/or language change if either was changed."""
        if self.loggedUser.getRole() == UserRoles.GUEST:
            QMessageBox.warning(self, t("Access Denied"), t("Guest users cannot access settings."))
            return
        user = copy.deepcopy(self.loggedUser)
        old_theme = self.loggedUser.getTheme()
        old_language = self.loggedUser.getLanguage()
        dlg = DialogSettings(self, user)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        def on_update_done(err, _):
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            if not user.getPassword():
                user.setPassword(self.loggedUser.getPassword())
            self.loggedUser = user
            MainWindow.refreshWelcomePage(self)
            if dlg.new_theme != old_theme:
                self._applyThemeChange(dlg.new_theme)
            if dlg.new_language != old_language:
                self._applyLanguageChange(dlg.new_language)

        ClientRequests.updateUser(self.loggedUser, user, callback=on_update_done)
        
    def btnFABUpdatePosition(self):
        """Reposition the floating action button to the bottom corner of the window,
        above the status bar - the right corner for English, the left corner for
        Arabic (mirrors the sidebar's own language-based default side, though unlike
        the sidebar there's no menu to move the FAB back afterward)."""
        margin = 40
        x = margin if i18n.is_rtl() else self.width() - self.btnFAB.width() - margin
        y = self.height() - self.btnFAB.height() - margin - self.statusBar().height()
        self.btnFAB.move(x, y)

    def _updateFabProximity(self):
        """Polled by `_fabProximityTimer`: fade the floating action button toward
        `_FAB_MIN_OPACITY` as the cursor moves away from it, and back to fully solid
        as the cursor comes within `_FAB_SOLID_RADIUS` - proximity rather than just
        direct hover, since QSS `:hover` alone only reacts once the cursor is already
        over the button."""
        if not self.isVisible():
            return
        cursor = self.mapFromGlobal(QCursor.pos())
        rect = self.btnFAB.geometry()
        dx = max(rect.left() - cursor.x(), 0, cursor.x() - rect.right())
        dy = max(rect.top() - cursor.y(), 0, cursor.y() - rect.bottom())
        distance = (dx ** 2 + dy ** 2) ** 0.5
        if distance <= self._FAB_SOLID_RADIUS:
            opacity = 1.0
        elif distance >= self._FAB_FADE_RADIUS:
            opacity = self._FAB_MIN_OPACITY
        else:
            span = self._FAB_FADE_RADIUS - self._FAB_SOLID_RADIUS
            frac = (distance - self._FAB_SOLID_RADIUS) / span
            opacity = 1.0 - frac * (1.0 - self._FAB_MIN_OPACITY)
        self._fabOpacityEffect.setOpacity(opacity)

    def _footerButtons(self) -> list[QPushButton]:
        """Return the sidebar's footer button group (theme/language/settings, refresh,
        logout), omitting theme/language/settings for Guest users."""
        footer: list[QPushButton] = []
        if self.loggedUser.getRole() != UserRoles.GUEST:
            footer.extend([self.btnTheme, self.btnLanguage, self.btnSettings])
        footer.extend([self.btnRefresh, self.btnLogout])
        return footer

    def setAvailableTabs(self, sidebarGroups: list[list[QPushButton]], topbarGroups: dict[str, list[QPushButton | None]]):
        """Declare the role's full sidebar/topbar button layout in one call: record
        which nav buttons and tabs this role can reach, then build the sidebar, the
        topbar, and the home page from them. Called once by each role-specific
        window's `__init__`."""
        self._availableNavButtons = (
            {btn for group in sidebarGroups for btn in group} |
            {btn for group in topbarGroups.values() for btn in group if btn is not None}
        )
        self._availableTabs = {
            self._sideBarBtnMap[btn] for btn in self._availableNavButtons
            if self._sideBarBtnMap.get(btn) is not None
        }
        self.setSidebarButtons(sidebarGroups)
        self.setTopbarButtons(topbarGroups)
        self.buildHomePage()

    def setSidebarButtons(self, groups: list[list[QPushButton]]):
        """Populate the sidebar toolbar from `groups` (capped to 9 nav buttons total,
        separators between groups), append the shared footer buttons, and wire
        Alt+1..Alt+8 quick-nav shortcuts to the first 8 nav buttons."""
        FOOTER_BTNS = self._footerButtons()

        capped_groups = []
        remaining = 9
        for group in groups:
            if remaining <= 0:
                break
            capped_groups.append(group[:remaining])
            remaining -= len(group[:remaining])
        groups = capped_groups

        # --- Sidebar ---
        self.sideBarLayout.clear()
        for i, group in enumerate(groups):
            if i > 0:
                self.sideBarLayout.addSeparator()
            for btn in group:
                self.sideBarLayout.addWidget(btn)
        self._sideBarStretch()
        for btn in FOOTER_BTNS:
            self.sideBarLayout.addWidget(btn)

        # --- Quick-nav shortcuts (Alt+1..Alt+8) ---
        nav_btns = [btn for group in groups for btn in group]
        for i, btn in enumerate(nav_btns):
            if i < 8:
                QShortcut('Alt+' + str(i + 1), self).activated.connect(btn.click)
            else:
                break

    def setTopbarButtons(self, groups: dict[str, list[QPushButton | None]]):
        """groups maps a stable, language-independent topbar menu key (e.g. 'PTWs') to
        the buttons/actions shown in that menu, in order; a None entry inserts a
        separator within the menu. 'View' and 'Help' always exist and get the
        sidebar-visibility/about controls appended regardless of whether the caller
        supplies its own entries for them.

        The key itself is never displayed - `make_menu_btn` looks up its translated
        label via `t(key)` and its keyboard mnemonic letter via `_MENU_MNEMONICS`
        (below), so the key has to stay a plain English identifier (no leading '&')
        for `group_widgets.pop("View", [])`/`pop("Help", [])` to keep working
        regardless of the active language."""

        # --- Top toolbar (grouped) ---
        TOOLBAR_BTN_STYLE = """
            QToolButton {
                color: palette(window-text); background: transparent; border: none;
                border-radius: 4px; padding: 5px 14px;
                font-size: 13px; font-weight: 500;
            }
            QToolButton:hover { background: rgba(128, 128, 128, 0.15); }
            QToolButton:pressed { background: rgba(128, 128, 128, 0.30); }
            QToolButton::menu-indicator { image: none; width: 0px; }
        """

        # Not translated content (see ArabicText.py's "docstrings/comments" rule for why
        # a keyboard accelerator isn't UI copy) - just which character in each menu's
        # *translated* label becomes its Alt+<letter> shortcut. English mnemonics are
        # each key's original first letter, preserved so existing muscle memory doesn't
        # change; Arabic ones are hand-picked to avoid colliding with each other (an
        # Arabic label's first letter alone repeats too often - e.g. both "PTWs" and
        # "Risks" translate to a phrase starting with ت).
        MENU_MNEMONICS = {
            'en': {'PTWs': 'P', 'ICs': 'I', 'Users': 'U', 'Risks': 'R', 'View': 'V', 'Help': 'H'},
            'ar': {'PTWs': 'ت', 'ICs': 'ش', 'Users': 'م', 'Risks': 'ق', 'View': 'ع', 'Help': 'س'},
        }

        def make_menu_btn(key, actions):
            label = t(key)
            mnemonic = MENU_MNEMONICS.get(i18n.current_lang(), MENU_MNEMONICS['en']).get(key)
            text = label
            if mnemonic:
                idx = label.find(mnemonic)
                if idx == -1:
                    idx = label.lower().find(mnemonic.lower())
                if idx != -1:
                    text = label[:idx] + '&' + label[idx:]
            btn = QToolButton()
            btn.setText(text)
            # QKeySequence.mnemonic() is Qt's own '&'-marker parser (vs. hand-rolling
            # "Alt+<letter>" from a regex match) - it's exactly as Unicode-safe as this
            # needs, confirmed directly against Arabic mnemonic letters.
            mnemonicSeq = QKeySequence.mnemonic(text)
            if not mnemonicSeq.isEmpty():
                btn.setShortcut(mnemonicSeq)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            btn.setStyleSheet(TOOLBAR_BTN_STYLE)
            menu = QMenu(self)
            menu.setStyleSheet("QMenu::separator { height: 2px; background: rgba(255, 255, 255, 40); margin: 4px 4px; }")
            for a in actions:
                if a:
                    lbl = a.text()
                    a.setText('&' + lbl) if lbl else None
                    menu.addAction(a)
                else:
                    menu.addSeparator()
            btn.setMenu(menu)
            return btn

        def nav_action(w):
            tip = w.toolTip()
            m = re.search(r'\[(.+)\]$', tip.strip())
            label = tip[:m.start()].strip() if m else tip.replace('PTWs', '').replace('PTW', '').strip()
            a = QAction(w.icon(), label, self)
            if m:
                a.setShortcut(QKeySequence(m.group(1)))
            a.triggered.connect(w.click)
            return a

        group_widgets: dict[str, list] = {name: list(btns) for name, btns in groups.items()}

        sidebarToggle = QAction(t("Navigation Sidebar"), self)
        sidebarToggle.setCheckable(True)
        sidebarToggle.setChecked(True)
        sidebarToggle.toggled.connect(self.sideBarLayout.setVisible)

        currentArea = self.toolBarArea(self.sideBarLayout)
        sidebarDockGroup = QActionGroup(self)
        sidebarDockGroup.setExclusive(True)
        self._sidebarDockActions.clear()
        sidebarDockActions = []
        for area, label in [
            (Qt.ToolBarArea.LeftToolBarArea,   t("Navigation Sidebar: Left")),
            (Qt.ToolBarArea.RightToolBarArea,  t("Navigation Sidebar: Right")),
            (Qt.ToolBarArea.BottomToolBarArea, t("Navigation Sidebar: Bottom")),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(area == currentArea)
            act.triggered.connect(lambda _, a=area: self._moveSidebar(a))
            sidebarDockGroup.addAction(act)
            self._sidebarDockActions[area] = act
            sidebarDockActions.append(act)

        viewItems = group_widgets.pop("View", [])
        group_widgets["View"] = [sidebarToggle, *sidebarDockActions] + ([None] + viewItems if viewItems else [])

        aboutAction = QAction(qta.icon('fa6s.circle-info'), t("About PTW"), self)
        aboutAction.triggered.connect(self._showAboutPTW)
        aboutQtAction = QAction(qta.icon('fa6s.circle-question'), t("About Qt"), self)
        aboutQtAction.triggered.connect(lambda: QMessageBox.aboutQt(self, t("About Qt")))

        helpItems = group_widgets.pop("Help", [])
        group_widgets["Help"] = (helpItems + [None] if helpItems else []) + [aboutAction, aboutQtAction]

        self.toolbar.clear()
        for name, btns in group_widgets.items():
            if btns:
                self.toolbar.addWidget(make_menu_btn(name, [nav_action(w) if isinstance(w, QPushButton) else w for w in btns]))

    def _approvalCycleTabs(self):
        """Return the (label, sidebar button, tab, color) tuples for the four
        approval-cycle stages shown on the home-page dashboard."""
        return [
            (t('Requested'),    self.btnRequestedPTWs,   self.tabRequestedPTWs,   APPROVAL_CYCLE_COLORS['Requested']),
            (t('Under Review'), self.btnUnderReviewPTWs, self.tabUnderReviewPTWs, APPROVAL_CYCLE_COLORS['Under Review']),
            (t('Returned'),     self.btnReturnedPTWs,    self.tabReturnedPTWs,    APPROVAL_CYCLE_COLORS['Returned']),
            (t('Approved'),     self.btnApprovedPTWs,    self.tabApprovedPTWs,    APPROVAL_CYCLE_COLORS['Approved']),
        ]

    def buildHomePage(self):
        """Default home page: the shared PTW approval-cycle / running-by-location dashboard.
        Subclasses without PTW tabs (e.g. AdminMainWindow) override this instead."""
        charts = []
        if any(btn in self._availableNavButtons for _, btn, _, _ in self._approvalCycleTabs()):
            self._homeApprovalChart = DonutChart(t("PTWs in Approval Cycle"))
            charts.append(self._homeApprovalChart)
        if self.btnRunningPTWs in self._availableNavButtons:
            self._homeRunningChart = DonutChart(t("Running PTWs"))
            charts.append(self._homeRunningChart)

        if charts:
            row = QHBoxLayout()
            for i, chart in enumerate(charts):
                if i > 0:
                    row.addSpacing(40)
                row.addWidget(chart, 1)
            self._homeContentLayout.addLayout(row, 1)

        self.updateHomeDashboard()

    def updateHomeDashboard(self):
        """Refresh the chart(s) built by buildHomePage() with current data."""
        if self._homeApprovalChart:
            self._homeApprovalChart.setSegments([
                DonutSegment(label, len(tab.ptwsData), color, partial(btn.click))
                for label, btn, tab, color in self._approvalCycleTabs()
                if btn in self._availableNavButtons
            ])
        if self._homeRunningChart:
            counts = Counter(ptw.location for ptw in self.tabRunningPTWs.ptwsData)
            self._homeRunningChart.setSegments([
                DonutSegment(
                    t(loc.value), counts.get(loc.value, 0), LOCATION_COLORS[i % len(LOCATION_COLORS)],
                    partial(self._openRunningFilteredByLocation, loc.value)
                )
                for i, loc in enumerate(PTW.Locations)
            ])

    def _openRunningFilteredByLocation(self, location: str):
        """Navigate to the Running PTWs tab and filter it down to `location`,
        invoked when a running-PTWs-by-location donut segment is clicked. `location`
        stays the raw English value, matching `TablePTWs`'s UserRole-backed filter
        values - only the segment's own displayed label is translated, above."""
        self.btnRunningPTWs.click()
        self.tabRunningPTWs.filterColumn('location', {location})

    def _showAboutPTW(self):
        """Show the 'About PTW' dialog, with a usage summary tailored to the logged-in
        user's role."""
        role = self.loggedUser.getRole()
        role_descriptions = {
            UserRoles.USER: t(
                "As a <b>Requestor</b>, you initiate and submit work permit requests from the <b>Under Review</b> tab. "
                "You can track your PTWs through each stage of the approval workflow — "
                "from submission and review, through approval and active work, to formal closure. "
                "Use the PTWs menu to monitor the current status of your permits."
            ),
            UserRoles.COORDINATOR: t(
                "As a <b>Coordinator</b>, you manage the PTW approval pipeline. "
                "You review submitted permits, either accepting or requesting changes to them, "
                "and review the overall workflow to ensure timely processing. "
                "Use the PTWs menu to act on permits awaiting your coordination in the <b>Under Review</b> Tab."
            ),
            UserRoles.ISSUING: t(
                "As an <b>Issuing Authority</b>, you are responsible for formally approving "
                "and issuing work permits. You can oversee active isolations. "
                "Authorizing work to run, and you can request edits permits that "
                "do not meet requirements."
                "Use the <b>Under Review</b> tab to review permits waiting for your review."
                "Use the <b>Waiting Run/Hold/Close Confirmation</b> tabs to review permits waiting your coordination."
            ),
            UserRoles.SAFETY: t(
                "As a <b>Safety Officer</b>, you review permits for safety compliance, "
                "manage associated risk assessments, and ensure that all necessary precautions are in place."
                "Use the <b>Risks</b> tab to manage risk assessment records."
                "Use the <b>Under Review</b> tab to review permits waiting for your review."
            ),
            UserRoles.ADMIN: t(
                "As an <b>Administrator</b>, you manage system users and their access roles. "
                "Use the <b>Users</b> tab to create and edit user accounts. "
                "Use the <b>Server Logs</b> tab to monitor server activity and audit system events. "
                "You have full visibility over all registered users in the system.<br><br>"
                "<u>Server data location</u> — MIWI documents, logs, on-demand DB backups, and PTW/IC "
                "attachments are stored on the server under a dedicated data directory, separate from "
                "the application code:<br>"
                "&nbsp;&nbsp;• Linux default: <code>~/.local/share/ptw-server/</code><br>"
                "&nbsp;&nbsp;• Windows default: <code>%LOCALAPPDATA%\\PTW\\server\\</code><br>"
                "&nbsp;&nbsp;• Grouped as: <code>miwi/</code>, <code>logs/</code>, <code>backups/</code>, "
                "<code>ptws/</code>, <code>ics/</code><br>"
                "&nbsp;&nbsp;• Override on the server via the <code>PTW_DATA_DIR</code> environment variable."
            ),
        }
        role_text = role_descriptions.get(
            role,
            t("As a <b>{0}</b>, you participate in the PTW approval and oversight process. "
              "Use the PTWs menu to review and act on permits relevant to your role.").format(t(role))
        )
        QMessageBox.about(
            self, t("About PTW"),
            t("<b>PTW — Permit To Work</b><br><br>"
              "A digital system for managing work permits in industrial and hazardous environments. "
              "It provides end-to-end control over the permit lifecycle — from creation and multi-level "
              "approval to active monitoring, hold management, and formal closure.<br><br>"
              "{0}<br><br>"
              "Key features:<br>"
              "&nbsp;&nbsp;• Structured permit workflows with role-based approvals<br>"
              "&nbsp;&nbsp;• Isolation and de-isolation tracking<br>"
              "&nbsp;&nbsp;• Risk assessment integration<br>"
              "&nbsp;&nbsp;• Real-time status updates and notifications<br>"
              "&nbsp;&nbsp;• Audit-ready reporting and PDF export<br><br>"
              "<small>Logged in as: <b>{1}</b> &mdash; {2}</small>").format(role_text, self.loggedUser.getName(), t(role))
        )

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        """Template method for a full data-and-GUI refresh; base implementation is a
        no-op, overridden by role-specific windows (typically to call
        `refreshPtwUserGUI`)."""
        pass

    def _onSSEEvent(self, event_type: str, data: dict):
        """Slot for the SSE listener's `eventReceived` signal, fired on every incoming
        real-time PTW/IC change event: beep and show a tray/status-bar notification
        summarizing it, then patch the touched record into the cache and its tab via
        `_applyPTWEvent`/`_applyICEvent` instead of doing a full refresh."""
        obj = data.get("object")
        objectId = data.get("object_id")
        action = data.get("action")
        by = data.get("by", "?")
        msg = t("{0} #{1} {2} by {3}").format(obj, objectId, action, by) if obj and objectId is not None and action else t("Update: {0}").format(event_type)

        QApplication.beep()
        self._trayIcon.showMessage(t("PTW Update"), msg, QSystemTrayIcon.MessageIcon.Information, 5000)
        self.statusBar().showMessage(msg, 6000)

        if obj == SSEObject.PTW:
            self._applyPTWEvent(objectId, action)
        elif obj == SSEObject.IC:
            self._applyICEvent(objectId, action)

    def _checkPtwAlarms(self):
        """PA-side reminder, polled every _PTW_ALARM_CHECK_INTERVAL_MS: any RUNNING PTW whose
        current run cycle's shift has ended, or any open PTW past its 14-shift validity, needs
        a human to hold/close it — nothing here does that automatically (see PTW.needsCloseAlarm/
        isRunCycleShiftExpired). Only a USER-role viewer acts on run/hold/close, so only they
        get nagged, and only for their own department's PTWs. Grouped into one two-section
        dialog (DialogPtwAlarms); dismissing it just snoozes the *next* popup for
        _PTW_ALARM_REPEAT_MINUTES — it doesn't clear the underlying condition, so anything
        still unresolved comes right back."""
        if self.loggedUser.getRole() != UserRoles.USER or self._ptwAlarmDialogOpen:
            return
        now = datetime.now()
        if self._ptwAlarmSnoozeUntil is not None and now < self._ptwAlarmSnoozeUntil:
            return
        myDept = (self.loggedUser.getDepartment() or '').casefold()
        myPtws = [ptw for ptw in globalData.allPTWs.values() if (ptw.department or '').casefold() == myDept]
        validityExpired = [ptw for ptw in myPtws if ptw.needsCloseAlarm(now)]
        shiftExpired = [ptw for ptw in myPtws if ptw.isRunCycleShiftExpired(now)]
        if validityExpired or shiftExpired:
            self._showPtwAlarms(validityExpired, shiftExpired)

    def _showPtwAlarms(self, validityExpired: list[PTW], shiftExpired: list[PTW]):
        """Beep and show a tray notification with the total alarmed-PTW count, then
        open the grouped `DialogPtwAlarms` popup for `validityExpired`/`shiftExpired`
        and, once dismissed, snooze the next check for `_PTW_ALARM_REPEAT_MINUTES`."""
        total = len(validityExpired) + len(shiftExpired)
        QApplication.beep()
        self._trayIcon.showMessage(
            t("PTW Attention Required"), t("{0} PTW(s) need your attention.").format(total),
            QSystemTrayIcon.MessageIcon.Warning, 10000
        )

        self._ptwAlarmDialogOpen = True
        DialogPtwAlarms(self, validityExpired, shiftExpired).exec()
        self._ptwAlarmDialogOpen = False
        self._ptwAlarmSnoozeUntil = datetime.now() + timedelta(minutes=self._PTW_ALARM_REPEAT_MINUTES)

    def _allPTWTabs(self) -> list[TablePTWs]:
        """Return every PTW status tab (excluding Registered/Template and Archived)
        that a full refresh or an SSE patch needs to consider."""
        return [
            self.tabRequestedPTWs,
            self.tabUnderReviewPTWs,
            self.tabMeetingPTWs,
            self.tabApprovedPTWs,
            self.tabReturnedPTWs,
            self.tabWaitingRunConfirmationPTWs,
            self.tabRunningPTWs,
            self.tabWaitingHldConfirmationPTWs,
            self.tabHeldPTWs,
            self.tabWaitingClsConfirmationPTWs,
            self.tabClosedPTWs,
        ]

    def _ptwTargetTab(self, ptw: PTW) -> TablePTWs:
        """Which tab a PTW belongs in, given its current status. Shared by the full-refresh
        loop and the single-record SSE update path, so the categorization only lives once."""
        mySt = ptw.getApprovalStatus(role=self.loggedUser.getRole(), department=self.loggedUser.getDepartment())
        st = ptw.getApprovalStatus()
        runSt = ptw.running_status
        if runSt == PTW.RunningStatus.WAITING_RUN_CONFIRM:
            return self.tabWaitingRunConfirmationPTWs
        if runSt == PTW.RunningStatus.WAITING_CLS_CONFIRM:
            return self.tabWaitingClsConfirmationPTWs
        if runSt == PTW.RunningStatus.WAITING_HLD_CONFIRM:
            return self.tabWaitingHldConfirmationPTWs
        if runSt == PTW.RunningStatus.RUNNING:
            return self.tabRunningPTWs
        if runSt == PTW.RunningStatus.HELD:
            return self.tabHeldPTWs
        if runSt == PTW.RunningStatus.CLOSED:
            return self.tabClosedPTWs
        if st == PTW.ApprovalStatus.APPROVED:
            return self.tabApprovedPTWs
        if st == PTW.ApprovalStatus.RETURNED:
            return self.tabReturnedPTWs
        return self.tabUnderReviewPTWs if mySt == PTW.ApprovalStatus.UNDER_REVIEW else self.tabRequestedPTWs

    def _addPTWToGUI(self, ptw: PTW):
        """Route ptw into its (single, exclusive) status tab, then additionally drop it into
        the 'PTW in Meeting' overlay tab if it qualifies (see PTW.isInMeeting) — that tab isn't
        part of the exclusive routing above, a PTW sits in it *alongside* whichever tab
        _ptwTargetTab() picked."""
        self._ptwTargetTab(ptw).addPTWToGUI(ptw)
        if ptw.isInMeeting():
            self.tabMeetingPTWs.addPTWToGUI(ptw)

    def _removePTWFromTabs(self, ptwId):
        """Remove the PTW with id `ptwId` from every PTW tab it might currently be
        sitting in."""
        for tab in self._allPTWTabs():
            tab.removePTWById(ptwId)

    def _applyPTWEvent(self, ptwId, action: str):
        """Patch the single touched PTW into the cache/GUI instead of a full refresh."""
        if action in (SSEAction.DELETED, SSEAction.ARCHIVED):
            self._removePTWFromTabs(ptwId)
            globalData.removePTW(ptwId)
            self.updateHomeDashboard()
            return

        def on_done(err, ptw):
            if err:
                return   # transient network error — leave the cache as-is
            self._removePTWFromTabs(ptwId)
            if ptw is not None:
                globalData.upsertPTW(ptw)
                self._addPTWToGUI(ptw)
            else:
                globalData.removePTW(ptwId)   # no longer visible to us / gone
            self.updateHomeDashboard()

        ClientRequests.getPTWById(self.loggedUser, ptwId, callback=on_done)

    def _allICTabs(self) -> list[TableICs]:
        """Return every IC status tab that a full refresh or an SSE patch needs to
        consider."""
        return [
            self.tabRequestedICs,
            self.tabUnderReviewICs,
            self.tabApprovedICs,
            self.tabIsolateConfirmingICs,
            self.tabPendingICs,
            self.tabActiveICs,
            self.tabDeisolateConfirmingICs,
            self.tabClosingICs,
            self.tabSanctionedICs,
            self.tabClosedICs,
        ]

    def _icTargetTab(self, ic: IC) -> TableICs | None:
        """Which tab an IC belongs in, given its current status — or None if this viewer
        shouldn't see it at all (isolator outside the IC's execution department). Shared by
        the full-refresh loop and the single-record SSE update path."""
        status = ic.getStatus()
        isIsolator = self.loggedUser.getRole() == UserRoles.ISOLATOR
        myTurn = ic.getApprovalStatus(role=self.loggedUser.getRole(), department=self.loggedUser.getDepartment()) == IC.Status.REQUESTED
        # Physical isolate/de-isolate work is routed to isolators of the IC's own
        # execution department only — an isolator elsewhere doesn't see it queued at all.
        notMyExecutionDept = isIsolator and (ic.execution_department or '').casefold() != (self.loggedUser.getDepartment() or '').casefold()
        if status == IC.Status.CLOSED:
            return self.tabClosedICs
        if status == IC.Status.SANCTIONED:
            return self.tabSanctionedICs
        if status == IC.Status.CLOSING:
            return None if notMyExecutionDept else self.tabClosingICs
        if status == IC.Status.DEISOLATE_CONFIRMING:
            return self.tabDeisolateConfirmingICs
        if status == IC.Status.ACTIVE:
            return self.tabActiveICs
        if status == IC.Status.PENDING:
            return None if notMyExecutionDept else self.tabPendingICs
        if status == IC.Status.ISOLATE_CONFIRMING:
            return self.tabIsolateConfirmingICs
        if status == IC.Status.APPROVED:
            return self.tabApprovedICs
        return self.tabUnderReviewICs if myTurn else self.tabRequestedICs

    def _removeICFromTabs(self, icId):
        """Remove the IC with id `icId` from every IC tab it might currently be
        sitting in."""
        for tab in self._allICTabs():
            tab.removeICById(icId)

    def _applyICEvent(self, icId, action: str):
        """Patch the single touched IC into the cache/GUI instead of a full refresh."""
        def on_done(err, ic):
            if err:
                return   # transient network error — leave the cache as-is
            self._removeICFromTabs(icId)
            if ic is not None:
                globalData.upsertIC(ic)
                tab = self._icTargetTab(ic)
                if tab is not None:
                    tab.addICToGUI(ic)
            else:
                globalData.removeIC(icId)   # no longer visible to us / gone

        ClientRequests.getICById(self.loggedUser, icId, callback=on_done)

    def refreshWelcomePage(self):
        """Re-fetch the current user's own data (and users), then update the welcome
        banner's role/name text, showing the busy overlay meanwhile."""
        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to refresh data:") + f" {err}")
                return
            self.btnWelcomeName.setText(t(self.loggedUser.getRole()) + ' ' + self.loggedUser.getName().upper() + '!')
        self._refreshOverlay.showBusy()
        globalData.refresh(self.loggedUser, self.loggedUser.getDepartment() if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.GUEST, UserRoles.ISOLATOR) else None, refreshUsers=True, callback=on_done)

    def refreshPtwUserGUI(self, refreshArchivedPTWs: bool = False):
        """Do a full data refresh (users/PTWs/risk assessments/MIWIs/ICs) from the
        server, then clear and repopulate every PTW tab, the risks tab, and the IC
        tabs from the refreshed cache; optionally also refresh archived PTWs; and
        update the home dashboard."""
        def on_done(err, _):
            tabs = self._allPTWTabs()

            for tab in tabs:
                tab.clear()

            for ptw in globalData.allPTWs.values():
                self._addPTWToGUI(ptw)

            for tab in tabs:
                tab.sort()

            self.tabRisks.setRiskAssessmentsInGUI(globalData.allRiskAssessments)
            self.refreshICsGUI()

            if refreshArchivedPTWs:
                self.refreshArchivedPTWs()

            self.updateHomeDashboard()

            QApplication.beep()
            self.statusBar().showMessage(t("GUI refreshed successfully."), 2000)
            self._refreshOverlay.hideBusy()

        self._refreshOverlay.showBusy()
        globalData.refresh(
            self.loggedUser,
            self.loggedUser.getDepartment() if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.GUEST) else None,
            refreshUsers=True, refreshPTWs=True, refreshRiskAssessments=True,
            refreshMIWIs=True, refreshICs=True,
            callback=on_done,
        )

    def refreshICsGUI(self):
        """Clear and repopulate every IC tab from the currently cached IC data."""
        tabs = self._allICTabs()
        for tab in tabs:
            tab.clear()

        for ic in globalData.ics.values():
            tab = self._icTargetTab(ic)
            if tab is not None:
                tab.addICToGUI(ic)

        for tab in tabs:
            tab.sort()

    def refreshArchivedPTWs(self):
        """Fetch archived PTWs from the server (on demand) and repopulate the
        Archived PTWs tab from them."""
        self.tabArchivedPTWs.clear()

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), t("Failed to refresh archived PTWs:") + f" {err}")
                return
            for ptw in globalData.archivedPTWs.values():
                self.tabArchivedPTWs.addPTWToGUI(ptw)
            self.tabArchivedPTWs.sort()

        self._refreshOverlay.showBusy()
        globalData.refresh(
            self.loggedUser,
            self.loggedUser.getDepartment() if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.GUEST) else None,
            refreshArchivedPTWs=True,
            callback=on_done,
        )

    def acceptPTW(self, row: int, ptw: PTW):
        """Confirm and, if confirmed, record an irreversible approval for `ptw` on
        its approval chain."""
        reply = QMessageBox.question(
            self, t('Accept PTW#{0}').format(ptw.id), t("Are you sure you want to approve request for PTW#{0}? This is irreversible").format(ptw.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        approval = PTW.Approval(PTW.ApprovalActions.APPROVED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval, callback=self._on_request_done_generic)
        
    def getComment(self, title: str, emptyCommentErr: str = None):
        """Prompt for a mandatory multi-line comment, re-prompting with a warning
        until non-empty text is entered; returns None if the dialog is cancelled."""
        if emptyCommentErr is None:
            emptyCommentErr = t('Empty comment not allowed')
        while True:
            comment, ok = QInputDialog.getMultiLineText(self, title, t("Comment:"))
            if not ok:
                return None
            if comment:
                return comment
            QMessageBox.warning(self, t('Not Allowed'), emptyCommentErr)

    def getOptionalComment(self, title: str, prompt: str) -> tuple[bool, str]:
        """Confirm an action with an optional comment. Returns (proceed, comment) — comment may be empty/None."""
        comment, ok = QInputDialog.getMultiLineText(self, title, prompt)
        return ok, (comment or None)
    
    def requestEditsPTW(self, row: int, ptw: PTW):
        """Prompt for a mandatory comment and return `ptw` to its requestor for
        edits, recording a RETURNED approval action."""
        comment = self.getComment(t('Return PTW# {0} to be Edited').format(ptw.id))
        if not comment:
            return
        approval = PTW.Approval(PTW.ApprovalActions.RETURNED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'), comment)
        ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval, callback=self._on_request_done_generic)

    def exportPTWs(self, rows: list, ptws: list[PTW]):
        """Export the selected PTWs to an Excel report, warning if none are selected
        or if the export itself fails."""
        if not ptws:
            QMessageBox.information(self, t("No PTWs Selected"), t("Please select at least one PTW to export."))
            return
        err = ReportGenerator.exportPTWs(ptws)
        if err:
            QMessageBox.warning(self, t("Export Failed"), err)

    def printPTW(self, row: int, ptw: PTW):
        """Generate and open a printable report for `ptw`, showing the busy overlay
        while it's produced."""
        self._refreshOverlay.showBusy()
        try:
            ReportGenerator.ptwReport(self.loggedUser, ptw)
        finally:
            self._refreshOverlay.hideBusy()

    def printPTWs(self):
        """Print every PTW currently in the active tab, one report at a time."""
        tab: TablePTWs = self.stack.currentWidget()
        self._refreshOverlay.showBusy()
        try:
            for i,ptw in enumerate(tab.ptwsData):
                self.printPTW(i, ptw)
        finally:
            self._refreshOverlay.hideBusy()
