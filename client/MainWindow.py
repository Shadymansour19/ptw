from datetime import datetime
from collections import Counter
import copy
import re
from PyQt6.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
                              QFormLayout, QLabel, QPushButton, QToolButton,
                              QToolBar, QDialog, QDialogButtonBox, QTextEdit, QListWidget,
                              QListWidgetItem, QMenu, QSizePolicy, QSystemTrayIcon,
                              QMessageBox, QApplication, QGraphicsOpacityEffect, QStyle, QInputDialog)
from PyQt6.QtGui import QFont, QIcon, QPalette, QKeySequence, QPainter, QPixmap, QAction, QActionGroup, QShortcut

from PTWData import PTWData, RiskAssessment
from TablePTWs import TablePTWs
from WidgetPTW import DialogPTW
from DialogUser import DialogUser
from DialogSelectIsolations import DialogSelectIsolations
from TableUsers import TableUsers
from TableRisks import TableRisks
from TableIsolations import TableIsolationsBrowser
from TableIsolationCertificates import TableIsolationCertificates
from DialogIsolationCertificate import DialogIsolationCertificate
from Isolation import IsolationCertificate
from TabServerLogs import TabServerLogs
from DialogSettings import DialogSettings
from clientRequests import ClientRequests
from GlobalData import globalData
from ReportGenerator import ReportGenerator
from SSEListener import SSEListener
from User import User, UserRoles
from DonutChart import DonutChart, DonutSegment, APPROVAL_CYCLE_COLORS, LOCATION_COLORS, DEPARTMENT_COLOR_CYCLE
from functools import partial
import qtawesome as qta
from utils import resource_path


class MainWindow(QMainWindow):
    on_logout = pyqtSignal()
    
    def __init__(self, loggedUser: User):
        super().__init__()
        self.loggedUser = loggedUser
        self.setWindowTitle("PTW (Permit To Work)")
        self.setWindowIcon(QIcon(resource_path('assets/sh-logo-trans.png')))
        self.setMinimumSize(1200, 900)

        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

        self.language = 'en'

        self.optionEditPTW = TablePTWs.MenuOption('Edit', self.editPTW, qta.icon('fa6s.pen'))
        self.optionViewPTW = TablePTWs.MenuOption('View', self.viewPTW, qta.icon('fa6.eye'))
        self.optionRequestPTW = TablePTWs.MenuOption('Re-Request PTW', self.addPTWDialog, qta.icon('fa6s.paper-plane'))
        self.optionDltPTW  = TablePTWs.MenuOption('Delete', self.deletePTW, qta.icon('fa6s.trash-can'))
        self.optionArchivePTW  = TablePTWs.MenuOption('Archive', self.archivePTWs, qta.icon('fa6s.box-archive'), allAtOnce=True)
        self.optionRunRequestPTW  = TablePTWs.MenuOption('Run', self.requestToRunPTW, qta.icon('fa6s.play'))
        self.optionRunAcceptPTW  = TablePTWs.MenuOption('Run', self.runAcceptTW, qta.icon('fa6s.play'))
        self.optionRunRejectPTW  = TablePTWs.MenuOption('Reject', self.runRejectTW, qta.icon('fa5s.times'))
        self.optionClsRequestPTW  = TablePTWs.MenuOption('Close', self.requestToClsPTW, qta.icon('fa6s.stop'))
        self.optionClsAcceptPTW  = TablePTWs.MenuOption('Close', self.clsAcceptPTW, qta.icon('fa6s.stop'))
        self.optionClsRejectPTW  = TablePTWs.MenuOption('Reject', self.clsRejectPTW, qta.icon('fa5s.times'))
        self.optionHldRequestPTW  = TablePTWs.MenuOption('Hold', self.requestToHldPTW, qta.icon('fa6s.pause'))
        self.optionHldTakeActionPTW = TablePTWs.MenuOption('Take Action', self.hldTakeAction, qta.icon('fa6s.pause'))
        self.optionTstRequestPTW  = TablePTWs.MenuOption('Suction for Test', self.requestToSuctionTestPTW, qta.icon('fa6s.plug-circle-exclamation'))
        self.optionTstAcceptPTW  = TablePTWs.MenuOption('Approve Suction for Test', self.suctionTestAcceptPTW, qta.icon('fa6s.plug-circle-exclamation'))
        self.optionTstRejectPTW  = TablePTWs.MenuOption('Reject Suction for Test', self.suctionTestRejectPTW, qta.icon('fa5s.times'))
        self.optionRequestEditsPTW = TablePTWs.MenuOption('Request Edits', self.requestEditsPTW, qta.icon('fa5s.undo'))
        self.optionAcceptPTW = TablePTWs.MenuOption('Accept', self.acceptPTW, qta.icon('fa6s.check'))
        self.optionExportPTW = TablePTWs.MenuOption('Export', self.exportPTWs, qta.icon('fa6s.file-excel'), allAtOnce=True)
        self.optionPrintPTW = TablePTWs.MenuOption('Print', self.printPTW, qta.icon('fa6s.print'))
        self.printDeIsolationOption = TablePTWs.MenuOption('Print De-Isolation', self.printDeIsolation, qta.icon('fa6s.print'))
        self.viewIsolationsOption = TablePTWs.MenuOption('View Isolations', self.viewIsolations, qta.icon('fa6s.unlock-keyhole'))
        self.viewApprovalsOption = TablePTWs.MenuOption('View Approvals', self.viewApprovals, qta.icon('fa6s.check-double'))
        self.optionViewRequestorPTW = TablePTWs.MenuOption('View Requestor', self.viewRequestorPTW, qta.icon('fa6s.user'))
        self.optionViewPerformingPTW = TablePTWs.MenuOption('View PA', self.viewPerformingPTW, qta.icon('mdi6.account-hard-hat'))
        self.viewIssuingOption = TablePTWs.MenuOption('View IA', self.viewIssuing, qta.icon('fa6s.user-tie'))
        self.optionViewIC = TablePTWs.MenuOption('View', self.viewIC, qta.icon('fa6.eye'))
        self.optionAcceptIC = TablePTWs.MenuOption('Accept', self.acceptCertificate, qta.icon('fa6s.check'))
        self.optionRequestEditsIC = TablePTWs.MenuOption('Request Edits', self.requestEditsCertificate, qta.icon('fa5s.undo'))
        self.optionRequestIsolateIC = TablePTWs.MenuOption('Request Isolate', self.requestIsolateCertificate, qta.icon('fa6s.unlock-keyhole'))
        self.optionConfirmIsolateIC = TablePTWs.MenuOption(
            'Confirm Isolate', self.confirmIsolateCertificate, qta.icon('fa6s.check'),
            visibleFor=lambda cert: cert.getStatus() == IsolationCertificate.Status.ISOLATE_CONFIRMING,
        )
        self.optionReturnIsolateIC = TablePTWs.MenuOption(
            'Return Isolate Request', self.returnIsolateCertificate, qta.icon('fa5s.undo'),
            visibleFor=lambda cert: cert.getStatus() == IsolationCertificate.Status.ISOLATE_CONFIRMING,
        )
        self.optionExecuteIsolateIC = TablePTWs.MenuOption(
            'Complete Isolation', self.executeIsolateCertificate, qta.icon('fa6s.lock'),
            visibleFor=lambda cert: cert.getStatus() == IsolationCertificate.Status.PENDING,
        )

        self.stack = QStackedWidget()
        self.stack.setAutoFillBackground(False)
        self.tabWelcome = QWidget()
        self.tabWelcome.setAutoFillBackground(False)
        self.tabRegisteredPTWs = TablePTWs(self.stack, self.loggedUser, "Template PTWs")
        self.tabRequestedPTWs = TablePTWs(self.stack, self.loggedUser, "Requested PTWs")
        self.tabUnderReviewPTWs = TablePTWs(self.stack, self.loggedUser, "Under Review PTWs")
        self.tabReturnedPTWs = TablePTWs(self.stack, self.loggedUser, "Returned PTWs")
        self.tabApprovedPTWs = TablePTWs(self.stack, self.loggedUser, "Approved PTWs")
        self.tabWaitingRunConfirmationPTWs = TablePTWs(self.stack, self.loggedUser, "Waiting Run Confirmation PTWs")
        self.tabRunningPTWs = TablePTWs(self.stack, self.loggedUser, "Running PTWs")
        self.tabWaitingHldConfirmationPTWs = TablePTWs(self.stack, self.loggedUser, "Waiting Hold Confirmation PTWs")
        self.tabHeldPTWs = TablePTWs(self.stack, self.loggedUser, "Held PTWs")
        self.tabWaitingClsConfirmationPTWs = TablePTWs(self.stack, self.loggedUser, "Waiting Close Confirmation PTWs")
        self.tabClosedPTWs = TablePTWs(self.stack, self.loggedUser, "Closed PTWs")
        self.tabArchivedPTWs = TablePTWs(self.stack, self.loggedUser, "Archived PTWs")
        self.tabAllUsers = TableUsers(self.stack, self.loggedUser, "All Users")
        self.tabRisks = TableRisks(self.stack, self.loggedUser, "All Risks", readonly=False, selectable=False)
        self.tabIsolations = TableIsolationsBrowser(self.stack, self.loggedUser, "Isolations")
        self.tabRequestedICs = TableIsolationCertificates(self.stack, self.loggedUser, "Requested ICs")
        self.tabUnderReviewICs = TableIsolationCertificates(self.stack, self.loggedUser, "Under Review ICs")
        self.tabApprovedICs = TableIsolationCertificates(self.stack, self.loggedUser, "Approved ICs")
        self.tabIsolateConfirmingICs = TableIsolationCertificates(self.stack, self.loggedUser, "Isolate Confirming ICs")
        self.tabPendingICs = TableIsolationCertificates(self.stack, self.loggedUser, "Pending ICs")
        self.tabActiveICs = TableIsolationCertificates(self.stack, self.loggedUser, "Active ICs")
        self.tabSanctionedICs = TableIsolationCertificates(self.stack, self.loggedUser, "Sanctioned ICs")
        self.tabClosedICs = TableIsolationCertificates(self.stack, self.loggedUser, "Closed ICs")
        self.tabServerLogs = TabServerLogs(self.stack, self.loggedUser, "Server Logs")

        self._homeApprovalChart: DonutChart | None = None
        self._homeRunningChart: DonutChart | None = None
        self._availableNavButtons: set = set()
        self._availableTabs: set = set()

        lytWelcome = QVBoxLayout()
        self._homeContentLayout = QVBoxLayout()
        self.tabWelcome.setLayout(lytWelcome)

        welcomeHeaderLyt = QHBoxLayout()
        welcomeHeaderLyt.addStretch()
        lblWelcome = QLabel("Welcome,")
        lblWelcome.setFont(QFont("Helvetica", 30))
        welcomeHeaderLyt.addWidget(lblWelcome)
        self.btnWelcomeName = QPushButton(self.loggedUser.getRole() + ' ' + self.loggedUser.getName().upper() + '!')
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
        self.stack.addWidget(self.tabIsolations)
        self.stack.addWidget(self.tabRequestedICs)
        self.stack.addWidget(self.tabUnderReviewICs)
        self.stack.addWidget(self.tabApprovedICs)
        self.stack.addWidget(self.tabIsolateConfirmingICs)
        self.stack.addWidget(self.tabPendingICs)
        self.stack.addWidget(self.tabActiveICs)
        self.stack.addWidget(self.tabSanctionedICs)
        self.stack.addWidget(self.tabClosedICs)
        self.stack.addWidget(self.tabServerLogs)

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
        # self.btnIsolations = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolumeMuted), "")
        # self.btnLanguage = QPushButton("ع")

        self.btnWelcome = QPushButton(qta.icon('fa5s.home'), "")
        self.btnRequestedPTWs = QPushButton(qta.icon('fa6s.paper-plane'), "")
        self.btnUnderReviewPTWs = QPushButton(qta.icon('fa6s.magnifying-glass-chart'), "")
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
        self.btnIsolations = QPushButton(qta.icon('fa6s.unlock-keyhole'), "")
        self.btnCertRequested = QPushButton(qta.icon('fa6s.paper-plane'), "")
        self.btnCertUnderReview = QPushButton(qta.icon('fa6s.magnifying-glass-chart'), "")
        self.btnCertApproved = QPushButton(qta.icon('fa6s.check'), "")
        self.btnCertIsolateConfirming = QPushButton(qta.icon('fa6s.clipboard-check'), "")
        self.btnCertPending = QPushButton(qta.icon('fa6.hourglass'), "")
        self.btnCertActive = QPushButton(qta.icon('fa6s.lock'), "")
        self.btnCertSanctioned = QPushButton(qta.icon('fa6s.flask'), "")
        self.btnCertClosed = QPushButton(qta.icon('fa6s.lock-open'), "")
        self.btnLanguage = QPushButton(qta.icon('fa5s.language'), "")
        self.btnTheme = QPushButton(qta.icon('fa6s.circle-half-stroke'), "")
        self.btnServerLogs = QPushButton(qta.icon('fa6s.file-lines'), "")

        self.btnWelcome.setToolTip("Home [Ctrl+H]")
        self.btnRequestedPTWs.setToolTip("Requested PTWs")
        self.btnUnderReviewPTWs.setToolTip("Under Review PTWs")
        self.btnReturnedPTWs.setToolTip("Returned PTWs")
        self.btnApprovedPTWs.setToolTip("Approved PTWs")
        self.btnWaitingRunConfirmationPTWs.setToolTip("Waiting Run Confirmation PTWs")
        self.btnRunningPTWs.setToolTip("Running PTWs")
        self.btnWaitingHldConfirmationPTWs.setToolTip("Waiting Hold Confirmation PTWs")
        self.btnHeldPTWs.setToolTip("Held PTWs")
        self.btnWaitingClsConfirmationPTWs.setToolTip("Waiting Close Confirmation PTWs")
        self.btnClosedPTWs.setToolTip("Closed PTWs")
        self.btnArchivedPTWs.setToolTip("Archived PTWs")
        self.btnSettings.setToolTip("Settings")
        self.btnRefresh.setToolTip("Refresh [Ctrl+R]")
        self.btnLogout.setToolTip("Logout [Ctrl+X]")
        self.btnUsers.setToolTip("All Users")
        self.btnRisks.setToolTip("Risks")
        self.btnIsolations.setToolTip("Isolations")
        self.btnCertRequested.setToolTip("Requested ICs")
        self.btnCertUnderReview.setToolTip("Under Review ICs")
        self.btnCertApproved.setToolTip("Approved ICs")
        self.btnCertIsolateConfirming.setToolTip("Isolate Confirming ICs")
        self.btnCertPending.setToolTip("Pending ICs")
        self.btnCertActive.setToolTip("Active ICs")
        self.btnCertSanctioned.setToolTip("Sanctioned ICs")
        self.btnCertClosed.setToolTip("Closed ICs")
        self.btnLanguage.setToolTip("Switch Language")
        self.btnTheme.setToolTip("Toggle Light/Dark Mode")
        self.btnServerLogs.setToolTip("Server Logs")

        self._sideBarBtnMap = {
            self.btnWelcome:                    self.tabWelcome,
            self.btnRequestedPTWs:              self.tabRequestedPTWs,
            self.btnUnderReviewPTWs:            self.tabUnderReviewPTWs,
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
            self.btnIsolations:                 self.tabIsolations,
            self.btnCertRequested:              self.tabRequestedICs,
            self.btnCertUnderReview:            self.tabUnderReviewICs,
            self.btnCertApproved:                self.tabApprovedICs,
            self.btnCertIsolateConfirming:      self.tabIsolateConfirmingICs,
            self.btnCertPending:                self.tabPendingICs,
            self.btnCertActive:                 self.tabActiveICs,
            self.btnCertSanctioned:             self.tabSanctionedICs,
            self.btnCertClosed:                 self.tabClosedICs,
            self.btnServerLogs:                 self.tabServerLogs,
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
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, self.sideBarLayout)
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

        self._trayIcon = QSystemTrayIcon(QIcon(resource_path("assets/sh-logo-trans.png")), self)
        self._trayIcon.show()

        self._sseListener = SSEListener(ClientRequests.SERVER_URL, loggedUser.getUsername(), loggedUser.getPassword())
        self._sseListener.eventReceived.connect(self._onSSEEvent)
        self._sseListener.start()

    def _on_request_done_generic(self, err, _):
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh

    def toggleTheme(self):
        hints = QApplication.styleHints()
        is_dark = hints.colorScheme() == Qt.ColorScheme.Dark
        new_theme = 'light' if is_dark else 'dark'
        self._applyThemeChange(new_theme)

    def _applyThemeChange(self, new_theme: str | None):
        import os, sys
        label = new_theme.capitalize() if new_theme else "Default (System)"
        msg = QMessageBox(self)
        msg.setWindowTitle("Switch Theme")
        msg.setText(f"Switching to {label} mode requires a full-application restart.")
        btn_restart = msg.addButton("Restart Now", QMessageBox.ButtonRole.AcceptRole)
        btn_later   = msg.addButton("Later",        QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel  = msg.addButton("Cancel Change", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_restart)
        msg.exec()

        if msg.clickedButton() == btn_cancel:
            return

        self.loggedUser.setTheme(new_theme)

        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Error", f"Failed to save theme preference:\n{err}")
                return

        if msg.clickedButton() == btn_restart:
            err = ClientRequests.updateTheme(self.loggedUser, new_theme)
            on_done(err, None)
            self.logout()
        else:
            ClientRequests.updateTheme(self.loggedUser, new_theme, callback=on_done)


    def _sideBarStretch(self):
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.sideBarLayout.addWidget(spacer)

    def resizeEvent(self, event):
        self.btnFABUpdatePosition()
        super().resizeEvent(event)

    def _moveSidebar(self, area: Qt.ToolBarArea):
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
        current = self.toolBarArea(self.sideBarLayout)
        for area, act in self._sidebarDockActions.items():
            act.setChecked(area == current)

    def _sideBarMoveMenu(self, pos):
        current = self.toolBarArea(self.sideBarLayout)
        menu = QMenu(self)
        for area, label in [
            (Qt.ToolBarArea.LeftToolBarArea,   "Move to Left"),
            (Qt.ToolBarArea.RightToolBarArea,  "Move to Right"),
            (Qt.ToolBarArea.BottomToolBarArea, "Move to Bottom"),
        ]:
            act = menu.addAction(label)
            act.setEnabled(area != current)
            act.triggered.connect(lambda _, a=area: self._moveSidebar(a))
        menu.exec(self.sideBarLayout.mapToGlobal(pos))

    def _initSidebarHover(self):
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
        if not self._sidebarExpanded:
            for btn in self._sideBarBtnMap:
                btn.setText("")
                btn.setStyleSheet(self._sidebarBtnStyle)
                btn.setLayoutDirection(Qt.LayoutDirection.LeftToRight)

    def createPopupMenu(self):
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(0.2 if self.stack.currentWidget() == self.tabWelcome else 0.1)
        painter.drawPixmap(self.rect(), QPixmap(resource_path('assets/sh-logo-trans.png')))
        painter.setOpacity(1.0)
        super().paintEvent(event)

    def stackTabChanged(self):
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
        return
    
    def logout(self):
        self._sseListener.stop()
        self._sseListener.wait(1000)
        self.on_logout.emit()
        self.close()
    
    def viewPTW(self, row: int, ptw: PTWData):
        viewPTWDialog = DialogPTW(self, self.loggedUser, ptw, None, False, True, f'View Mode - PTW# {ptw.id}')
        viewPTWDialog.exec()

    def _savePTWRiskAssessment(self, ptwId: int, risk: RiskAssessment, callback=None):
        if risk:
            ClientRequests.updateRiskAssessment(self.loggedUser, risk, callback=callback)
        else:
            ClientRequests.deleteRiskAssessment(self.loggedUser, str(ptwId), ptwId, callback=callback)

    def editPTW(self, row: int, ptw: PTWData):
        toEditPtw = copy.deepcopy(ptw)
        wasReturned = toEditPtw.approval_status == PTWData.ApprovalStatus.RETURNED
        editPTWDialog = DialogPTW(self, self.loggedUser, toEditPtw, None, False, False, f'Edit Mode - PTW# {ptw.id}')
        if editPTWDialog.exec() == QDialog.DialogCode.Accepted:
            if wasReturned:
                toEditPtw.clearApprovals()
            ptw = toEditPtw

            def on_risk_saved(err, _):
                if err:
                    QMessageBox.warning(self, "Warning", f"PTW saved but failed to save risk assessment: {err}")
            risk = RiskAssessment(title=ptw.description, date=datetime.now().strftime('%d %b %Y'), risks=editPTWDialog.riskAssessmentPreviewTable.getRiskItems(), ptw_id=ptw.id)
            self._savePTWRiskAssessment(ptw.id, risk, callback=on_risk_saved)

            self.stack.currentWidget().updatePTW(row, ptw)

    def addPTWDialog(self, row: int = None, ptw: PTWData = None):
        newPTW = copy.deepcopy(ptw) if ptw else PTWData()
        if ptw:
            newPTW.setId(None).clearApprovals()
        title = "Re-request PTW" if ptw else "New PTW"
        dlg = DialogPTW(self, self.loggedUser, newPTW, ptw, True, False, title)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        def on_addPTW_done(err, ptwId=None):
            def on_copy_attachments_done(err, _):
                if err:
                    QMessageBox.warning(self, "Error", f"Failed to copy attachments: {err}")
                    return

            def on_attachments_uploaded(err, _):
                if err:
                    QMessageBox.warning(self, "Error", f"Failed to upload attachments: {err}")
                    return
                if ptw:
                    ClientRequests.copyPtwAttachments(self.loggedUser, ptw.id, newPTW.id, callback=on_copy_attachments_done)
                # self.refreshGUI()  # SSE event handles refresh

            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            newPTW.setId(ptwId)

            def on_risk_saved(err, _):
                if err:
                    QMessageBox.warning(self, "Warning", f"PTW saved but failed to save risk assessment: {err}")
            risk = RiskAssessment(title=newPTW.description, date=datetime.now().strftime('%d %b %Y'), risks=dlg.riskAssessmentPreviewTable.getRiskItems(), ptw_id=ptwId)
            self._savePTWRiskAssessment(ptwId, risk, callback=on_risk_saved)
            # On re-request, the server also copies the original PTW's own risk rows onto
            # this new ptw_id (server/app.py copyPtwAttachments), additively — so any custom
            # rows from the original that weren't re-selected/re-added here still carry over.

            if dlg.attachsToBeUploaded:
                ClientRequests.addPtwAttachments(self.loggedUser, newPTW.id, dlg.attachsToBeUploaded, callback=on_attachments_uploaded)

        ClientRequests.addPTW(self.loggedUser, newPTW, callback=on_addPTW_done)


    def deletePTW(self, row: int, ptw: PTWData):
        self.stack.currentWidget().deletePTW(row)
    
    def archivePTWs(self, rows: list, ptws: list[PTWData]):
        ClientRequests.archivePTWs(self.loggedUser, [ptw.id for ptw in ptws], callback=self._on_request_done_generic)
    
    def requestToRunPTW(self, row: int, ptw: PTWData):
        for p in globalData.allPTWs:
            if p.getPerforming() == self.loggedUser.getUsername():
                QMessageBox.warning(self, 'Not Allowed', f"You are already the PA for PTW# {p.id}.")
                return

        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.requestToRunPTW(self.loggedUser, ptw.id, pa, ts, callback=self._on_request_done_generic)

    def runAcceptTW(self, row: int, ptw: PTWData):
        proceed, comment = self.getOptionalComment(f'Accept PTW#{ptw.id} Run', f"Are you sure you want to accept run request for PTW#{ptw.id}?")
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, True, comment, callback=self._on_request_done_generic)

    def runRejectTW(self, row: int, ptw: PTWData):
        proceed, comment = self.getOptionalComment(f'Reject PTW#{ptw.id} Run', f"Are you sure you want to reject run request for PTW#{ptw.id}?")
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, False, comment, callback=self._on_request_done_generic)

    def requestToClsPTW(self, row: int, ptw: PTWData):
        proceed, comment = self.getOptionalComment('Close PTW', f"Are you sure you want to close PTW#{ptw.id}?")
        if not proceed:
            return

        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.requestToClsPTW(self.loggedUser, ptw.id, pa, ts, comment, callback=self._on_request_done_generic)

    def clsAcceptPTW(self, row: int, ptw: PTWData):
        proceed, comment = self.getOptionalComment(f'Accept PTW#{ptw.id} Close', f"Are you sure you want to accept close request for PTW#{ptw.id}? This is irreversible")
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, True, comment, callback=self._on_request_done_generic)

    def clsRejectPTW(self, row: int, ptw: PTWData):
        proceed, comment = self.getOptionalComment(f'Reject PTW#{ptw.id} Close', f"Are you sure you want to reject close request for PTW#{ptw.id}?")
        if not proceed:
            return

        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, False, comment, callback=self._on_request_done_generic)

    def requestToHldPTW(self, row: int, ptw: PTWData):
        dlg = DialogSelectIsolations(self, ptw.isolations, selectable=True, title=f"Hold PTW# {ptw.id} - Select Isolations to Keep")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        keptTags = dlg.getKeptTags()
        proceed, comment = self.getOptionalComment(f'Hold PTW# {ptw.id}', f"Are you sure you want to request hold for PTW#{ptw.id}?")
        if not proceed:
            return
        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.requestToHldPTW(self.loggedUser, ptw.id, pa, ts, comment, keptTags, callback=self._on_request_done_generic)

    def hldAcceptPTW(self, row: int, ptw: PTWData, comment: str = None):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, True, comment, callback=self._on_request_done_generic)

    def hldRejectPTW(self, row: int, ptw: PTWData, comment: str = None):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, False, comment, callback=self._on_request_done_generic)

    def hldTakeAction(self, row: int, ptw: PTWData):
        if ptw.running_status != PTWData.RunningStatus.WAITING_HLD_CONFIRM:
            QMessageBox.warning(self, 'Not Allowed', f"PTW# {ptw.id} is not waiting for hold confirmation.")
            return
        dlg = DialogSelectIsolations(self, ptw.isolations, kept=ptw.getKeepIsolations(), selectable=False, review_mode=True, title=f"Hold Action - PTW# {ptw.id}")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.action not in ('accept', 'reject'):
            return
        proceed, comment = self.getOptionalComment(f'Hold Action - PTW# {ptw.id}', f"Confirm {dlg.action} for the hold request on PTW#{ptw.id}?")
        if not proceed:
            return
        if dlg.action == 'accept':
            self.hldAcceptPTW(row, ptw, comment)
        elif dlg.action == 'reject':
            self.hldRejectPTW(row, ptw, comment)

    def viewIsolations(self, row: int, ptw: PTWData):
        dlg = DialogSelectIsolations(
            self, ptw.isolations, kept=ptw.getKeepIsolations(),
            selectable=False, view_only=True,
            title=f"Isolations - PTW# {ptw.id}"
        )
        dlg.exec()

    def viewIC(self, row: int, cert: IsolationCertificate):
        dlg = DialogIsolationCertificate(self, self.loggedUser, cert, False, True, f"Isolation Certificate — {cert.type}")
        dlg.exec()

    def acceptCertificate(self, row: int, cert: IsolationCertificate):
        reply = QMessageBox.question(
            self, f'Accept Certificate #{cert.id}', f"Are you sure you want to approve isolation certificate #{cert.id}? This is irreversible",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        approval = IsolationCertificate.Approval(IsolationCertificate.ApprovalActions.APPROVED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        ClientRequests.updateApprovalCertificate(self.loggedUser, cert.id, approval, callback=self._on_request_done_generic)

    def requestEditsCertificate(self, row: int, cert: IsolationCertificate):
        comment = self.getComment(f'Return Certificate #{cert.id} to be Edited')
        if not comment:
            return
        approval = IsolationCertificate.Approval(IsolationCertificate.ApprovalActions.RETURNED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'), comment)
        ClientRequests.updateApprovalCertificate(self.loggedUser, cert.id, approval, callback=self._on_request_done_generic)

    def requestIsolateCertificate(self, row: int, cert: IsolationCertificate):
        reply = QMessageBox.question(
            self, f'Request Isolate #{cert.id}', f"Request isolation for certificate #{cert.id}? This will notify Issuing to confirm.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.requestIsolateCertificate(self.loggedUser, cert.id, callback=self._on_request_done_generic)

    def confirmIsolateCertificate(self, row: int, cert: IsolationCertificate):
        reply = QMessageBox.question(
            self, f'Confirm Isolate #{cert.id}', f"Confirm isolation for certificate #{cert.id}? The isolator will then be notified to carry it out.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.confirmIsolateCertificate(self.loggedUser, cert.id, True, callback=self._on_request_done_generic)

    def returnIsolateCertificate(self, row: int, cert: IsolationCertificate):
        reply = QMessageBox.question(
            self, f'Return Isolate Request #{cert.id}', f"Return the isolate request for certificate #{cert.id}? The requestor will need to request isolation again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.confirmIsolateCertificate(self.loggedUser, cert.id, False, callback=self._on_request_done_generic)

    def executeIsolateCertificate(self, row: int, cert: IsolationCertificate):
        reply = QMessageBox.question(
            self, f'Complete Isolation #{cert.id}', f"Confirm that isolation for certificate #{cert.id} has been physically carried out?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        ClientRequests.executeIsolateCertificate(self.loggedUser, cert.id, callback=self._on_request_done_generic)

    def requestToSuctionTestPTW(self, row: int, ptw: PTWData):
        pass

    def suctionTestAcceptPTW(self, row: int, ptw: PTWData):
        pass

    def suctionTestRejectPTW(self, row: int, ptw: PTWData):
        pass


    def viewUser(self, username: str, role: str):
        if username is None or username.strip() == '':
            QMessageBox.warning(self, f'No {role} Assigned', f"No {role} assigned yet.")
            return
        elif username not in globalData.allUsers:
            QMessageBox.warning(self, 'User Not Found', f"username {username} was not found.")
            return
        DialogUser(self, True, False, self.loggedUser, globalData.allUsers[username], f"{role} - View Mode - User {username}").exec()
    
    def viewRequestorPTW(self, row: int, ptw: PTWData):
        self.viewUser(ptw.requestor, 'Requestor')

    def viewPerformingPTW(self, row: int, ptw: PTWData):
        self.viewUser(ptw.getPerforming(), 'PA')

    def viewIssuing(self, row: int, ptw: PTWData):
        self.viewUser(ptw.getIssuing(), 'IA')
    
    def viewApprovals(self, row: int, ptw: PTWData):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"PTW# {ptw.id} Approval Cycle")
        dlg.resize(int(0.7 * self.width()), int(0.75 * self.height()))
        dlg.setMaximumHeight(int(0.9 * self.screen().availableGeometry().height()))

        lyt = QVBoxLayout()
        dlg.setLayout(lyt)

        def addSection(title: str, lst: QListWidget):
            headerLyt = QHBoxLayout()
            expandBtn = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp), '')
            expandBtn.setStyleSheet('QPushButton { border: none; }')

            def toggle():
                if lst.isVisible():
                    lst.hide()
                    expandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
                else:
                    lst.show()
                    expandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))

            expandBtn.clicked.connect(toggle)
            lbl = QLabel(
                title, 
                font=QFont("Helvetica", 16, QFont.Weight.Bold), 
                alignment=Qt.AlignmentFlag.AlignCenter
            )
            headerLyt.addStretch()
            headerLyt.addWidget(lbl)
            headerLyt.addStretch()
            headerLyt.addWidget(expandBtn)
            lyt.addLayout(headerLyt)
            lyt.addWidget(lst)

        def addEmptyItem(lst: QListWidget, text: str):
            item = QListWidgetItem()
            widget = QLabel(text=text, font=QFont("Helvetica", 12))
            item.setSizeHint(widget.sizeHint())
            lst.addItem(item)
            lst.setItemWidget(item, widget)

        approvedLst = QListWidget()
        if len(ptw.approvals) == 0:
            addEmptyItem(approvedLst, "There's no approval history at the moment")
        else:
            for approval in ptw.approvals:
                item = QListWidgetItem()
                approvalWidget = approval.toWidget()
                sizeHint = approvalWidget.sizeHint()
                sizeHint = QSize(int(sizeHint.width() * 1.2), int(sizeHint.height() * 1.2))
                item.setSizeHint(sizeHint)
                approvedLst.addItem(item)
                approvedLst.setItemWidget(item, approvalWidget)
            approvedLst.setStyleSheet("QListWidget::item { border-bottom: 2px solid palette(mid); }")
        addSection('Approved By', approvedLst)

        pendingLst = QListWidget()
        pendingApprovers = ptw.pendingApprovers()
        if len(pendingApprovers) == 0:
            addEmptyItem(pendingLst, "There are no pending approvers")
        else:
            for approver in pendingApprovers:
                item = QListWidgetItem()
                widget = QLabel(text=str(approver), font=QFont("Helvetica", 14))
                item.setSizeHint(widget.sizeHint())
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                pendingLst.addItem(item)
                pendingLst.setItemWidget(item, widget)
            pendingLst.setStyleSheet("QListWidget::item { border-bottom: 2px solid palette(mid); }")
        addSection('Pending Approvers', pendingLst)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.close)
        lyt.addWidget(btns)

        dlg.exec()

    def chgLanguage(self):
        if self.language == 'en':
            self.language = 'ar'
            self.btnLanguage.setToolTip("Switch to English")
        else:
            self.language = 'en'
            self.btnLanguage.setToolTip("حول إلى العربية")
        # self.refreshGUI()

    def dlgSettings(self):
        if self.loggedUser.getRole() == UserRoles.GUEST:
            QMessageBox.warning(self, "Access Denied", "Guest users cannot access settings.")
            return
        user = copy.deepcopy(self.loggedUser)
        old_theme = self.loggedUser.getTheme()
        dlg = DialogSettings(self, user)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        def on_update_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.loggedUser = user
            MainWindow.refreshWelcomePage(self)
            if dlg.new_theme != old_theme:
                self._applyThemeChange(dlg.new_theme)

        ClientRequests.updateUser(self.loggedUser, user, callback=on_update_done)
        
    def btnFABUpdatePosition(self):
        margin = 40
        x = self.width() - self.btnFAB.width() - margin
        y = self.height() - self.btnFAB.height() - margin - self.statusBar().height()
        self.btnFAB.move(x, y)
    
    def _footerButtons(self) -> list[QPushButton]:
        footer: list[QPushButton] = []
        if self.loggedUser.getRole() != UserRoles.GUEST:
            footer.extend([self.btnTheme, self.btnSettings])
        footer.extend([self.btnRefresh, self.btnLogout])
        return footer

    def setAvailableTabs(self, sidebarGroups: list[list[QPushButton]], topbarGroups: dict[str, list[QPushButton | None]]):
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
        FOOTER_BTNS = self._footerButtons()

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

        # --- Quick-nav shortcuts (Alt+1..Alt+10) ---
        nav_btns = [btn for group in groups for btn in group]
        for i, btn in enumerate(nav_btns):
            if i < 10:
                QShortcut('Alt+' + str(i + 1), self).activated.connect(btn.click)

    def setTopbarButtons(self, groups: dict[str, list[QPushButton | None]]):
        """groups maps a topbar menu label (e.g. '&PTWs') to the buttons/actions shown in
        that menu, in order; a None entry inserts a separator within the menu. '&View' and
        '&Help' always exist and get the sidebar-visibility/about controls appended regardless
        of whether the caller supplies its own entries for them."""

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

        def make_menu_btn(text, actions):
            btn = QToolButton()
            btn.setText(text)
            m = re.search(r'&([A-Za-z])', text)
            if m:
                btn.setShortcut(QKeySequence(f"Alt+{m.group(1).upper()}"))
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

        sidebarToggle = QAction("Navigation Sidebar", self)
        sidebarToggle.setCheckable(True)
        sidebarToggle.setChecked(True)
        sidebarToggle.toggled.connect(self.sideBarLayout.setVisible)

        currentArea = self.toolBarArea(self.sideBarLayout)
        sidebarDockGroup = QActionGroup(self)
        sidebarDockGroup.setExclusive(True)
        self._sidebarDockActions.clear()
        sidebarDockActions = []
        for area, label in [
            (Qt.ToolBarArea.LeftToolBarArea,   "Navigation Sidebar: Left"),
            (Qt.ToolBarArea.RightToolBarArea,  "Navigation Sidebar: Right"),
            (Qt.ToolBarArea.BottomToolBarArea, "Navigation Sidebar: Bottom"),
        ]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(area == currentArea)
            act.triggered.connect(lambda _, a=area: self._moveSidebar(a))
            sidebarDockGroup.addAction(act)
            self._sidebarDockActions[area] = act
            sidebarDockActions.append(act)

        viewItems = group_widgets.pop("&View", [])
        group_widgets["&View"] = [sidebarToggle, *sidebarDockActions] + ([None] + viewItems if viewItems else [])

        aboutAction = QAction(qta.icon('fa6s.circle-info'), "About PTW", self)
        aboutAction.triggered.connect(self._showAboutPTW)
        aboutQtAction = QAction(qta.icon('fa6s.circle-question'), "About Qt", self)
        aboutQtAction.triggered.connect(lambda: QMessageBox.aboutQt(self, "About Qt"))

        helpItems = group_widgets.pop("&Help", [])
        group_widgets["&Help"] = (helpItems + [None] if helpItems else []) + [aboutAction, aboutQtAction]

        self.toolbar.clear()
        for name, btns in group_widgets.items():
            if btns:
                self.toolbar.addWidget(make_menu_btn(name, [nav_action(w) if isinstance(w, QPushButton) else w for w in btns]))

    def _approvalCycleTabs(self):
        return [
            ('Requested',    self.btnRequestedPTWs,   self.tabRequestedPTWs,   APPROVAL_CYCLE_COLORS['Requested']),
            ('Under Review', self.btnUnderReviewPTWs, self.tabUnderReviewPTWs, APPROVAL_CYCLE_COLORS['Under Review']),
            ('Returned',     self.btnReturnedPTWs,    self.tabReturnedPTWs,    APPROVAL_CYCLE_COLORS['Returned']),
            ('Approved',     self.btnApprovedPTWs,    self.tabApprovedPTWs,    APPROVAL_CYCLE_COLORS['Approved']),
        ]

    def buildHomePage(self):
        """Default home page: the shared PTW approval-cycle / running-by-location dashboard.
        Subclasses without PTW tabs (e.g. AdminMainWindow) override this instead."""
        charts = []
        if any(btn in self._availableNavButtons for _, btn, _, _ in self._approvalCycleTabs()):
            self._homeApprovalChart = DonutChart("PTWs in Approval Cycle")
            charts.append(self._homeApprovalChart)
        if self.btnRunningPTWs in self._availableNavButtons:
            self._homeRunningChart = DonutChart("Running PTWs")
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
                    loc.value, counts.get(loc.value, 0), LOCATION_COLORS[i % len(LOCATION_COLORS)],
                    partial(self._openRunningFilteredByLocation, loc.value)
                )
                for i, loc in enumerate(PTWData.Locations)
            ])

    def _openRunningFilteredByLocation(self, location: str):
        self.btnRunningPTWs.click()
        self.tabRunningPTWs.filterColumn('Location', {location})

    def _showAboutPTW(self):
        role = self.loggedUser.getRole()
        role_descriptions = {
            UserRoles.USER: (
                "As a <b>Requestor</b>, you initiate and submit work permit requests from the <b>Under Review</b> tab. "
                "You can track your PTWs through each stage of the approval workflow — "
                "from submission and review, through approval and active work, to formal closure. "
                "Use the PTWs menu to monitor the current status of your permits."
            ),
            UserRoles.COORDINATOR: (
                "As a <b>Coordinator</b>, you manage the PTW approval pipeline. "
                "You review submitted permits, either accepting or requesting changes to them, "
                "and review the overall workflow to ensure timely processing. "
                "Use the PTWs menu to act on permits awaiting your coordination in the <b>Under Review</b> Tab."
            ),
            UserRoles.ISSUING: (
                "As an <b>Issuing Authority</b>, you are responsible for formally approving "
                "and issuing work permits. You can oversee active isolations. "
                "Authorizing work to run, and you can request edits permits that "
                "do not meet requirements."
                "Use the <b>Under Review</b> tab to review permits waiting for your review."
                "Use the <b>Waiting Run/Hold/Close Confirmation</b> tabs to review permits waiting your coordination."
            ),
            UserRoles.SAFETY: (
                "As a <b>Safety Officer</b>, you review permits for safety compliance, "
                "manage associated risk assessments, and ensure that all necessary precautions are in place."
                "Use the <b>Risks</b> tab to manage risk assessment records."
                "Use the <b>Under Review</b> tab to review permits waiting for your review."
            ),
            UserRoles.ADMIN: (
                "As an <b>Administrator</b>, you manage system users and their access roles. "
                "Use the <b>Users</b> tab to create and edit user accounts. "
                "Use the <b>Server Logs</b> tab to monitor server activity and audit system events. "
                "You have full visibility over all registered users in the system."
            ),
        }
        role_text = role_descriptions.get(
            role,
            f"As a <b>{role}</b>, you participate in the PTW approval and oversight process. "
            "Use the PTWs menu to review and act on permits relevant to your role."
        )
        QMessageBox.about(
            self, "About PTW",
            "<b>PTW — Permit To Work</b><br><br>"
            "A digital system for managing work permits in industrial and hazardous environments. "
            "It provides end-to-end control over the permit lifecycle — from creation and multi-level "
            "approval to active monitoring, hold management, and formal closure.<br><br>"
            f"{role_text}<br><br>"
            "Key features:<br>"
            "&nbsp;&nbsp;• Structured permit workflows with role-based approvals<br>"
            "&nbsp;&nbsp;• Isolation and de-isolation tracking<br>"
            "&nbsp;&nbsp;• Risk assessment integration<br>"
            "&nbsp;&nbsp;• Real-time status updates and notifications<br>"
            "&nbsp;&nbsp;• Audit-ready reporting and PDF export<br><br>"
            f"<small>Logged in as: <b>{self.loggedUser.getName()}</b> &mdash; {role}</small>"
        )

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        pass

    def _onSSEEvent(self, event_type: str, data: dict):
        self.refreshGUI()
        msg = self._formatSSEMessage(event_type, data)
        QApplication.beep()
        self._trayIcon.showMessage("PTW Update", msg, QSystemTrayIcon.MessageIcon.Information, 5000)
        self.statusBar().showMessage(msg, 6000)

    def _formatSSEMessage(self, event_type: str, data: dict) -> str:
        ptw_id = data.get("ptw_id", "?")
        ptw_ids = data.get("ptw_ids", "?")
        by = data.get("by", "?")
        if event_type == "new_ptw":
            return f"New PTW #{ptw_id} created by {by} (type: {data.get('type', '?')})"
        if event_type == "ptw_deleted":
            return f"PTW #{ptw_id} deleted by {by}"
        if event_type == "ptw_approval":
            return f"PTW #{ptw_id}: {data.get('action', 'status update')} by {by}"
        if event_type == "ptw_updated":
            return f"PTW #{ptw_id}: edited and resubmitted by {by}"
        if event_type == "ptw_run_request":
            return f"PTW #{ptw_id}: run requested by {by}"
        if event_type == "ptw_run":
            verb = "now RUNNING" if data.get("accepted") else "run rejected"
            return f"PTW #{ptw_id}: {verb} (by {by})"
        if event_type == "ptw_hold_request":
            return f"PTW #{ptw_id}: hold requested by {by}"
        if event_type == "ptw_hold":
            verb = "now HELD" if data.get("accepted") else "hold rejected"
            return f"PTW #{ptw_id}: {verb} (by {by})"
        if event_type == "ptw_close_request":
            return f"PTW #{ptw_id}: close requested by {by}"
        if event_type == "ptw_close":
            verb = "CLOSED" if data.get("accepted") else "close rejected"
            return f"PTW #{ptw_id}: {verb} (by {by})"
        if event_type == "ptw_archived":
            return f"PTWs #{ptw_ids} archived by {by}"
        if event_type == "new_isolation_certificate":
            return f"New isolation certificate created by {by} (type: {data.get('type', '?')})"
        return f"Update: {event_type} for PTW #{ptw_id}"

    def refreshWelcomePage(self):
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Error", f"Failed to refresh data: {err}")
                return
            self.btnWelcomeName.setText(self.loggedUser.getRole() + ' ' + self.loggedUser.getName().upper() + '!')
        globalData.refresh(self.loggedUser, self.loggedUser.getDepartment() if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.GUEST, UserRoles.ISOLATOR) else None, refreshUsers=True, callback=on_done)

    def refreshPtwUserGUI(self, refreshArchivedPTWs: bool = False):
        def on_done(err, _):
            tabs: list[TablePTWs] = [
                self.tabRequestedPTWs,
                self.tabUnderReviewPTWs,
                self.tabApprovedPTWs,
                self.tabReturnedPTWs,
                self.tabWaitingRunConfirmationPTWs,
                self.tabRunningPTWs,
                self.tabWaitingHldConfirmationPTWs,
                self.tabHeldPTWs,
                self.tabWaitingClsConfirmationPTWs,
                self.tabClosedPTWs,
            ]

            for tab in tabs:
                tab.clear()

            for ptw in globalData.allPTWs:
                mySt = ptw.getApprovalStatus(role=self.loggedUser.getRole(), department=self.loggedUser.getDepartment())
                st = ptw.getApprovalStatus()
                runSt = ptw.running_status
                if runSt == PTWData.RunningStatus.WAITING_RUN_CONFIRM:
                    self.tabWaitingRunConfirmationPTWs.addPTWToGUI(ptw)
                elif runSt == PTWData.RunningStatus.WAITING_CLS_CONFIRM:
                    self.tabWaitingClsConfirmationPTWs.addPTWToGUI(ptw)
                elif runSt == PTWData.RunningStatus.WAITING_HLD_CONFIRM:
                    self.tabWaitingHldConfirmationPTWs.addPTWToGUI(ptw)
                elif runSt == PTWData.RunningStatus.RUNNING:
                    self.tabRunningPTWs.addPTWToGUI(ptw)
                elif runSt == PTWData.RunningStatus.HELD:
                    self.tabHeldPTWs.addPTWToGUI(ptw)
                elif runSt == PTWData.RunningStatus.CLOSED:
                    self.tabClosedPTWs.addPTWToGUI(ptw)
                elif st == PTWData.ApprovalStatus.APPROVED:
                    self.tabApprovedPTWs.addPTWToGUI(ptw)
                elif st == PTWData.ApprovalStatus.RETURNED:
                    self.tabReturnedPTWs.addPTWToGUI(ptw)
                elif st == PTWData.ApprovalStatus.UNDER_REVIEW:
                    if mySt == PTWData.ApprovalStatus.UNDER_REVIEW:
                        self.tabUnderReviewPTWs.addPTWToGUI(ptw)
                    else:
                        self.tabRequestedPTWs.addPTWToGUI(ptw)

            for tab in tabs:
                tab.sort()

            self.tabIsolations.setIsolations(globalData.isolations)
            self.tabRisks.setRiskAssessmentsInGUI(globalData.allRiskAssessments)
            self.refreshCertificatesGUI()

            if refreshArchivedPTWs:
                self.refreshArchivedPTWs()

            self.updateHomeDashboard()

            QApplication.beep()
            self.statusBar().showMessage("GUI refreshed successfully.", 2000)

        globalData.refresh(
            self.loggedUser,
            self.loggedUser.getDepartment() if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.GUEST) else None,
            refreshUsers=True, refreshPTWs=True, refreshRiskAssessments=True,
            refreshMIWIs=True, refreshIsolations=True, refreshIsolationCertificates=True,
            callback=on_done,
        )

    def refreshCertificatesGUI(self):
        tabs: list[TableIsolationCertificates] = [
            self.tabRequestedICs,
            self.tabUnderReviewICs,
            self.tabApprovedICs,
            self.tabIsolateConfirmingICs,
            self.tabPendingICs,
            self.tabActiveICs,
            self.tabSanctionedICs,
            self.tabClosedICs,
        ]
        for tab in tabs:
            tab.clear()

        for cert in globalData.isolationCertificates.values():
            status = cert.getStatus()
            myTurn = cert.getApprovalStatus(role=self.loggedUser.getRole(), department=self.loggedUser.getDepartment()) == IsolationCertificate.Status.REQUESTED
            if status == IsolationCertificate.Status.CLOSED:
                self.tabClosedICs.addCertificateToGUI(cert)
            elif status == IsolationCertificate.Status.SANCTIONED:
                self.tabSanctionedICs.addCertificateToGUI(cert)
            elif status == IsolationCertificate.Status.ACTIVE:
                self.tabActiveICs.addCertificateToGUI(cert)
            elif status == IsolationCertificate.Status.PENDING:
                self.tabPendingICs.addCertificateToGUI(cert)
            elif status == IsolationCertificate.Status.ISOLATE_CONFIRMING:
                self.tabIsolateConfirmingICs.addCertificateToGUI(cert)
            elif status == IsolationCertificate.Status.APPROVED:
                self.tabApprovedICs.addCertificateToGUI(cert)
            elif myTurn:
                self.tabUnderReviewICs.addCertificateToGUI(cert)
            else:
                self.tabRequestedICs.addCertificateToGUI(cert)

        for tab in tabs:
            tab.sort()

    def refreshArchivedPTWs(self):
        self.tabArchivedPTWs.clear()
        globalData.refresh(
            self.loggedUser, 
            self.loggedUser.getDepartment() if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.GUEST) else None, 
            refreshArchivedPTWs=True
        )
        for ptw in globalData.archivedPTWs:
            self.tabArchivedPTWs.addPTWToGUI(ptw)
        self.tabArchivedPTWs.sort()

    def acceptPTW(self, row: int, ptw: PTWData):
        reply = QMessageBox.question(
            self, f'Accept PTW#{ptw.id}', f"Are you sure you want to approve request for PTW#{ptw.id}? This is irreversible", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        approval = PTWData.Approval(PTWData.ApprovalActions.APPROVED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval, callback=self._on_request_done_generic)
        
    def getComment(self, title: str, emptyCommentErr: str = 'Empty comment not allowed'):
        while True:
            comment, ok = QInputDialog.getMultiLineText(self, title, "Comment:")
            if not ok:
                return None
            if comment:
                return comment
            QMessageBox.warning(self, 'Not Allowed', emptyCommentErr)

    def getOptionalComment(self, title: str, prompt: str) -> tuple[bool, str]:
        """Confirm an action with an optional comment. Returns (proceed, comment) — comment may be empty/None."""
        comment, ok = QInputDialog.getMultiLineText(self, title, prompt)
        return ok, (comment or None)
    
    def requestEditsPTW(self, row: int, ptw: PTWData):
        comment = self.getComment(f'Return PTW# {ptw.id} to be Edited')
        if not comment:
            return
        approval = PTWData.Approval(PTWData.ApprovalActions.RETURNED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'), comment)
        ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval, callback=self._on_request_done_generic)

    def exportPTWs(self, rows: list, ptws: list[PTWData]):
        if not ptws:
            QMessageBox.information(self, "No PTWs Selected", "Please select at least one PTW to export.")
            return
        err = ReportGenerator.exportPTWs(ptws)
        if err:
            QMessageBox.warning(self, "Export Failed", err)

    def printPTW(self, row: int, ptw: PTWData):
        ReportGenerator.ptwReport(self.loggedUser, ptw)

    def printDeIsolation(self, row: int, ptw: PTWData):
        ReportGenerator.deIsolationReport(self.loggedUser, ptw)

    def printPTWs(self):
        tab: TablePTWs = self.stack.currentWidget()
        for i,ptw in enumerate(tab.ptwsData):
            self.printPTW(i, ptw)



class GuestMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Guest Window")

        self.tabRequestedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

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

        self.btnFAB.setToolTip("Request New PTW [Ctrl+N]")
        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRequestedPTWs, self.tabWelcome])

    def btnFABHandler(self):
        if self.btnFAB.isVisible():
            self.addPTWDialog()
    
    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI()



class UserMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - User Window")

        self.tabRegisteredPTWs.addOptions([self.optionViewPTW, self.optionEditPTW, self.optionRequestPTW, self.optionViewRequestorPTW, self.optionDltPTW, self.optionExportPTW])
        self.tabRequestedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionEditPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionDltPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionRunRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionClsRequestPTW, self.optionHldRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.optionRequestPTW, self.optionRunRequestPTW, self.printDeIsolationOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.printDeIsolationOption, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        self.tabRequestedICs.addOptions([self.optionViewIC])
        self.tabApprovedICs.addOptions([self.optionViewIC, self.optionRequestIsolateIC])
        self.tabIsolateConfirmingICs.addOptions([self.optionViewIC])
        self.tabPendingICs.addOptions([self.optionViewIC])
        self.tabActiveICs.addOptions([self.optionViewIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC])
        self.tabClosedICs.addOptions([self.optionViewIC])

        self.setAvailableTabs(
            [   # sidebar: curated, most-used tabs for a requestor
                [self.btnWelcome],
                [self.btnRequestedPTWs, self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs],
                [self.btnIsolations],
                [self.btnCertRequested, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending, self.btnCertActive, self.btnCertSanctioned, self.btnCertClosed],
            ],
            {   # topbar: full set
                '&PTWs': [
                    self.btnRequestedPTWs, self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs,
                    self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs, self.btnArchivedPTWs,
                ],
                '&Isolations': [self.btnIsolations],
                '&ICs': [self.btnCertRequested, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending, self.btnCertActive, self.btnCertSanctioned, self.btnCertClosed],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setToolTip("Request New PTW [Ctrl+N]")
        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRequestedPTWs, self.tabWelcome, self.tabRequestedICs])
        self.btnFAB.setToolTip("New Isolation Certificate" if tab == self.tabRequestedICs else "Request New PTW [Ctrl+N]")
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def btnFABHandler(self):
        if not self.btnFAB.isVisible():
            return
        if self.stack.currentWidget() == self.tabRequestedICs:
            self.tabRequestedICs.addNewCertificateDialog()
        else:
            self.addPTWDialog()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)



class CoordinatorMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Coordinator Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.viewApprovalsOption, self.optionViewRequestorPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.printDeIsolationOption, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs, self.btnArchivedPTWs],
                [self.btnIsolations],
            ],
            {
                '&PTWs': [
                    self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs, self.btnArchivedPTWs,
                ],
                '&Isolations': [self.btnIsolations],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon('fa6s.print', color='white'))
        self.btnFAB.setToolTip("Print current widget PTWs [Ctrl+P]")

        shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations)
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)

    def btnFABHandler(self):
        if self.btnFAB.isVisible(): 
            self.printPTWs()




class IssuingMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Issuing Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionRunAcceptPTW, self.optionRunRejectPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.optionHldTakeActionPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionClsAcceptPTW, self.optionClsRejectPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.printDeIsolationOption, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        self.tabUnderReviewICs.addOptions([self.optionViewIC, self.optionAcceptIC, self.optionRequestEditsIC])
        self.tabApprovedICs.addOptions([self.optionViewIC])
        self.tabIsolateConfirmingICs.addOptions([self.optionViewIC, self.optionConfirmIsolateIC, self.optionReturnIsolateIC])
        self.tabPendingICs.addOptions([self.optionViewIC])
        self.tabActiveICs.addOptions([self.optionViewIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC])
        self.tabClosedICs.addOptions([self.optionViewIC])

        # no Requested button here: a single-stage (non-Protective) cert never routes to
        # tabCertRequested for the Issuing viewer once they've acted — it goes straight to
        # Pending. Only a rare Protective-type cert (needing PDH/PGM/SOD/DFGM after Issuing)
        # would land there for Issuing to track — accepted gap for now, not wired up.
        self._certTabs = [
            self.btnCertUnderReview, self.btnCertApproved, self.btnCertIsolateConfirming, self.btnCertPending,
            self.btnCertActive, self.btnCertSanctioned, self.btnCertClosed,
        ]
        self._certTabsWidgets = [
            self.tabUnderReviewICs, self.tabApprovedICs, self.tabIsolateConfirmingICs, self.tabPendingICs,
            self.tabActiveICs, self.tabSanctionedICs, self.tabClosedICs,
        ]

        self.setAvailableTabs(
            [   # sidebar: curated, run/hold/close confirmation is Issuing's core job
                [self.btnWelcome],
                [self.btnUnderReviewPTWs],
                [self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs, self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs],
                [self.btnIsolations],
                self._certTabs,
            ],
            {   # topbar: full set
                '&PTWs': [
                    self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs,
                    self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs, self.btnArchivedPTWs,
                ],
                '&Isolations': [self.btnIsolations],
                '&ICs': self._certTabs,
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon('fa6s.print', color='white'))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations and tab not in self._certTabsWidgets)
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)

    def btnFABHandler(self):
        self.printPTWs()




class SafetyMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Safety Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestEditsPTW, self.optionAcceptPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionPrintPTW])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnRunningPTWs],
                [self.btnIsolations],
                [self.btnRisks],
            ],
            {
                '&PTWs': [self.btnUnderReviewPTWs, self.btnRunningPTWs],
                '&Isolations': [self.btnIsolations],
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




class ManagerMainWindow(MainWindow):
    def __init__(self, loggedUser: User, role: str):
        super().__init__(loggedUser)
        self.setWindowTitle(f"PTW (Permit To Work) - {role} Window")

        self.tabUnderReviewPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestEditsPTW, self.optionAcceptPTW, self.optionPrintPTW, self.optionExportPTW])
        self.tabReturnedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabApprovedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabRunningPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.optionViewPerformingPTW, self.viewApprovalsOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabHeldPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.optionPrintPTW, self.optionExportPTW])
        self.tabClosedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.printDeIsolationOption, self.optionPrintPTW, self.optionArchivePTW, self.optionExportPTW])
        self.tabArchivedPTWs.addOptions([self.optionViewPTW, self.optionViewRequestorPTW, self.viewApprovalsOption, self.optionRequestPTW, self.optionPrintPTW, self.optionExportPTW])

        # Managers are only ever involved in a Protective-type certificate's approval
        # chain (after Issuing), so Under Review is the only certificate tab they need.
        self.tabUnderReviewICs.addOptions([self.optionViewIC, self.optionAcceptIC, self.optionRequestEditsIC])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs],
                [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs],
                [self.btnIsolations],
                [self.btnCertUnderReview],
            ],
            {
                '&PTWs': [
                    self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs,
                    None,
                    self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs,
                ],
                '&Isolations': [self.btnIsolations],
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
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations and tab != self.tabUnderReviewICs)
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)

    def btnFABHandler(self):
        self.printPTWs()




class AdminMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Admin Window")

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnUsers, self.btnServerLogs],
            ],
            {
                '&Users': [self.btnUsers, self.btnServerLogs],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setIcon(qta.icon('fa6s.plus', color='white'))
        self.btnFAB.setToolTip("Add New User [Ctrl+N]")

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.addNewUserDialog)
    
    def btnFABHandler(self):
        self.addNewUserDialog()
    
    def addNewUserDialog(self):
        if not self.btnFAB.isVisible():
            return

        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("Add Users")
        msgBox.setText("How would you like to add new user(s)?")
        btnManual = msgBox.addButton("&Type Manually", QMessageBox.ButtonRole.AcceptRole)
        btnImport = msgBox.addButton("Import from E&xcel", QMessageBox.ButtonRole.ActionRole)
        btnManual.setIcon(qta.icon('fa6s.keyboard'))
        btnImport.setIcon(qta.icon('fa6s.file-excel'))
        msgBox.addButton(QMessageBox.StandardButton.Cancel)
        msgBox.exec()
        clicked = msgBox.clickedButton()

        if clicked == btnManual:
            newUser = User()
            dlg = DialogUser(self, False, True, self.loggedUser, newUser, 'New User')
            if dlg.exec() == QDialog.DialogCode.Accepted:
                self.tabAllUsers.addUser(newUser)
        elif clicked == btnImport:
            self.tabAllUsers.importUsersFromExcel()

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabAllUsers])

    def buildHomePage(self):
        self._homeUsersChart = DonutChart("Users")
        row = QHBoxLayout()
        row.addWidget(self._homeUsersChart, 1)
        self._homeContentLayout.addLayout(row, 1)
        self.updateHomeDashboard()

    def updateHomeDashboard(self):
        counts = Counter(u.getDepartment() for u in globalData.allUsers.values() if u.getDepartment())
        self._homeUsersChart.setSegments([
            DonutSegment(dept, counts[dept], DEPARTMENT_COLOR_CYCLE[i % len(DEPARTMENT_COLOR_CYCLE)],
                         partial(self._openUsersFilteredByDept, dept))
            for i, dept in enumerate(sorted(counts))
        ])

    def _openUsersFilteredByDept(self, dept: str):
        self.btnUsers.click()
        self.tabAllUsers.filterColumn('Department', {dept})

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        def on_done(err, _):
            self.tabAllUsers.clear()
            for user in globalData.allUsers.values():
                self.tabAllUsers.addUserToGUI(user)

            self.updateHomeDashboard()

            QApplication.beep()
            self.statusBar().showMessage("GUI refreshed successfully.", 2000)

        globalData.refresh(self.loggedUser, None, refreshUsers=True, callback=on_done)
        self.tabServerLogs.refresh()


class IsolatorMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Isolator Window")

        self.tabPendingICs.addOptions([self.optionViewIC, self.optionExecuteIsolateIC])
        self.tabActiveICs.addOptions([self.optionViewIC])
        self.tabSanctionedICs.addOptions([self.optionViewIC])

        self.setAvailableTabs(
            [
                [self.btnWelcome],
                [self.btnCertPending, self.btnCertActive, self.btnCertSanctioned],
            ],
            {
                '&Certificates': [self.btnCertPending, self.btnCertActive, self.btnCertSanctioned],
                '&View': [self.btnWelcome, *self._footerButtons()],
            },
        )

        self.btnFAB.setVisible(False)

    def stackTabChanged(self):
        super().stackTabChanged()
        self.btnFAB.setVisible(False)

    def btnFABHandler(self):
        pass

    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Error", f"Failed to refresh data: {err}")
                return
            self.refreshCertificatesGUI()
            QApplication.beep()
            self.statusBar().showMessage("GUI refreshed successfully.", 2000)

        globalData.refresh(self.loggedUser, None, refreshUsers=True, refreshIsolationCertificates=True, callback=on_done)



