from datetime import datetime
import copy
import re
from PyQt6.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtWidgets import (QMainWindow, QWidget, QStackedWidget, QVBoxLayout, QGridLayout,
                              QFormLayout, QLabel, QPushButton, QToolButton,
                              QToolBar, QDialog, QDialogButtonBox, QTextEdit, QListWidget,
                              QListWidgetItem, QMenu, QSizePolicy, QSystemTrayIcon,
                              QMessageBox, QApplication, QGraphicsOpacityEffect)
from PyQt6.QtGui import QFont, QIcon, QPalette, QKeySequence, QPainter, QPixmap, QAction, QActionGroup, QShortcut

from PTWData import PTWData
from TablePTWs import TablePTWs
from WidgetPTW import DialogPTW
from DialogUser import DialogUser
from DialogSelectIsolations import DialogSelectIsolations
from TableUsers import TableUsers
from TableRisks import TableRisks
from TableIsolations import TableIsolationsBrowser
from DialogSettings import DialogSettings
from clientRequests import ClientRequests
from GlobalData import globalData
from ReportGenerator import ReportGenerator
from SSEListener import SSEListener
from User import User, UserRoles
from functools import partial
import qtawesome as qta
from utils import resource_path


class MainWindow(QMainWindow):
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

        self.editOption = TablePTWs.MenuOption('Edit', self.editPTW, qta.icon('fa6s.pen'))
        self.viewOption = TablePTWs.MenuOption('View', self.viewPTW, qta.icon('fa6.eye'))
        self.requestPTWOption = TablePTWs.MenuOption('Re-Request PTW', self.addPTWDialog, qta.icon('fa6s.question'))
        self.dltOption  = TablePTWs.MenuOption('Delete', self.deletePTW, qta.icon('fa6s.trash-can'))
        self.archiveOption  = TablePTWs.MenuOption('Archive', self.archivePTWs, qta.icon('fa6s.box-archive'), allAtOnce=True)
        self.runRequestOption  = TablePTWs.MenuOption('Run', self.requestToRunPTW, qta.icon('fa6s.play'))
        self.runAcceptOption  = TablePTWs.MenuOption('Run', self.runAcceptTW, qta.icon('fa6s.play'))
        self.runRejectOption  = TablePTWs.MenuOption('Reject', self.runRejectTW, qta.icon('fa5s.times'))
        self.clsRequestOption  = TablePTWs.MenuOption('Close', self.requestToClsPTW, qta.icon('fa6s.stop'))
        self.clsAcceptOption  = TablePTWs.MenuOption('Close', self.clsAcceptPTW, qta.icon('fa6s.stop'))
        self.clsRejectOption  = TablePTWs.MenuOption('Reject', self.clsRejectPTW, qta.icon('fa5s.times'))
        self.hldRequestOption  = TablePTWs.MenuOption('Hold', self.requestToHldPTW, qta.icon('fa6s.pause'))
        self.hldTakeActionOption = TablePTWs.MenuOption('Take Action', self.hldTakeAction, qta.icon('fa6s.pause'))
        self.tstRequestOption  = TablePTWs.MenuOption('Suction for Test', self.requestToSuctionTestPTW, qta.icon('fa6s.plug-circle-exclamation'))
        self.tstAcceptOption  = TablePTWs.MenuOption('Suction for Test', self.suctionTestAcceptPTW, qta.icon('fa6s.plug-circle-exclamation'))
        self.tstRejectOption  = TablePTWs.MenuOption('Reject', self.suctionTestRejectPTW, qta.icon('fa5s.times'))
        self.requestEditsOption = TablePTWs.MenuOption('Request Edits', self.requestEdits, qta.icon('fa5s.undo'))
        self.acceptOption = TablePTWs.MenuOption('Accept', self.acceptPTW, qta.icon('fa6s.check'))
        self.rejectOption = TablePTWs.MenuOption('Reject', self.rejectPTW, qta.icon('fa5s.times'))
        self.exportOption = TablePTWs.MenuOption('Export', self.exportPTWs, qta.icon('fa6s.file-excel'), allAtOnce=True)
        self.printOption = TablePTWs.MenuOption('Print', self.printPTW, qta.icon('fa6s.print'))
        self.printDeIsolationOption = TablePTWs.MenuOption('Print De-Isolation', self.printDeIsolation, qta.icon('fa6s.print'))
        self.viewIsolationsOption = TablePTWs.MenuOption('View Isolations', self.viewIsolations, qta.icon('fa6s.unlock-keyhole'))
        self.viewApprovalsOption = TablePTWs.MenuOption('View Approvals', self.viewApprovals, qta.icon('fa6s.check-double'))
        self.viewRequestorOption = TablePTWs.MenuOption('View Requestor', self.viewRequestor, qta.icon('fa6s.user'))
        self.viewPerformingOption = TablePTWs.MenuOption('View PA', self.viewPerforming, qta.icon('mdi6.account-hard-hat'))
        self.viewIssuingOption = TablePTWs.MenuOption('View IA', self.viewIssuing, qta.icon('fa6s.user-tie'))

        self.stack = QStackedWidget()
        self.stack.setAutoFillBackground(False)
        self.tabWelcome = QWidget()
        self.tabWelcome.setAutoFillBackground(False)
        self.tabRegisteredPTWs = TablePTWs(self.stack, self.loggedUser, "Template PTWs")
        self.tabUnderReviewPTWs = TablePTWs(self.stack, self.loggedUser, "Under Review PTWs")
        self.tabReturnedPTWs = TablePTWs(self.stack, self.loggedUser, "Returned PTWs")
        self.tabApprovedPTWs = TablePTWs(self.stack, self.loggedUser, "Approved PTWs")
        self.tabRejectedPTWs = TablePTWs(self.stack, self.loggedUser, "Rejected PTWs")
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

        lytWelcome = QVBoxLayout()
        self.lytWelcomeBtns = QGridLayout()
        self.tabWelcome.setLayout(lytWelcome)
        lytWelcome.addStretch()
        lytWelcome.addWidget(QLabel(
            "Welcome...", 
            font=QFont("Helvetica", 60, QFont.Weight.Bold, italic=True), 
            alignment=Qt.AlignmentFlag.AlignCenter, 
        ))
        self.btnWelcomeName = QPushButton(self.loggedUser.getRole() + ' ' + self.loggedUser.getName().upper() + '!')
        self.btnWelcomeName.setStyleSheet('''
            QPushButton { border: none; background: transparent; color: palette(link); }
            QPushButton:hover { text-decoration: underline;}
            QPushButton:pressed { color: palette(highlight); }
        ''')
        self.btnWelcomeName.setFont(QFont("Helvetica", 40, QFont.Weight.Bold, italic=True))
        self.btnWelcomeName.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btnWelcomeName.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.lytWelcomeBtns.setSpacing(10)
        lytWelcome.addWidget(self.btnWelcomeName)
        lytWelcome.setAlignment(self.btnWelcomeName, Qt.AlignmentFlag.AlignCenter)
        lytWelcome.addStretch()
        lytWelcome.addLayout(self.lytWelcomeBtns)
        lytWelcome.addStretch()
        self.btnWelcomeName.clicked.connect(self.dlgSettings)
        
        self.stack.addWidget(self.tabWelcome)
        self.stack.addWidget(self.tabRegisteredPTWs)
        self.stack.addWidget(self.tabUnderReviewPTWs)
        self.stack.addWidget(self.tabReturnedPTWs)
        self.stack.addWidget(self.tabApprovedPTWs)
        self.stack.addWidget(self.tabRejectedPTWs)
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

        self.stack.currentChanged.connect(self.stackTabChanged)

        # self.btnWelcome = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirHomeIcon), "")
        # self.btnUnderReviewPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion), "")
        # self.btnReturnedPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning), "")
        # self.btnApprovedPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton), "")
        # self.btnRejectedPTWs = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), "")
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
        self.btnUnderReviewPTWs = QPushButton(qta.icon('fa6s.magnifying-glass-chart'), "")
        self.btnReturnedPTWs = QPushButton(qta.icon('fa5s.undo'), "")
        self.btnApprovedPTWs = QPushButton(qta.icon('fa6s.check'), "")
        self.btnRejectedPTWs = QPushButton(qta.icon('fa5s.times'), "")
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
        self.btnLanguage = QPushButton(qta.icon('fa5s.language'), "")
        self.btnTheme = QPushButton(qta.icon('fa6s.circle-half-stroke'), "")

        self._btnIcons = {
            self.btnWelcome:                    'fa5s.home',
            self.btnUnderReviewPTWs:            'fa6s.magnifying-glass-chart',
            self.btnReturnedPTWs:               'fa5s.undo',
            self.btnApprovedPTWs:               'fa6s.check',
            self.btnRejectedPTWs:               'fa5s.times',
            self.btnWaitingRunConfirmationPTWs: 'fa6.clock',
            self.btnRunningPTWs:                'fa6s.play',
            self.btnWaitingHldConfirmationPTWs: 'fa5s.hourglass-half',
            self.btnHeldPTWs:                   'fa6s.pause',
            self.btnWaitingClsConfirmationPTWs: 'fa6s.clock',
            self.btnClosedPTWs:                 'fa6s.stop',
            self.btnArchivedPTWs:               'fa6s.box-archive',
            self.btnSettings:                   'fa6s.gear',
            self.btnRefresh:                    'fa6s.rotate-right',
            self.btnLogout:                     'fa6s.arrow-right-from-bracket',
            self.btnUsers:                      'fa6s.users-gear',
            self.btnRisks:                      'mdi.shield-check-outline',
            self.btnIsolations:                 'fa6s.unlock-keyhole',
            self.btnLanguage:                   'fa5s.language',
            self.btnTheme:                      'fa6s.circle-half-stroke',
        }

        self.btnWelcome.setToolTip("Home [Ctrl+H]")
        self.btnUnderReviewPTWs.setToolTip("Under Review PTWs")
        self.btnReturnedPTWs.setToolTip("Returned PTWs")
        self.btnApprovedPTWs.setToolTip("Approved PTWs")
        self.btnRejectedPTWs.setToolTip("Rejected PTWs")
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
        self.btnLanguage.setToolTip("Switch Language")
        self.btnTheme.setToolTip("Toggle Light/Dark Mode")

        self._sideBarBtnMap = {
            self.btnWelcome:                    self.tabWelcome,
            self.btnUnderReviewPTWs:            self.tabUnderReviewPTWs,
            self.btnReturnedPTWs:               self.tabReturnedPTWs,
            self.btnApprovedPTWs:               self.tabApprovedPTWs,
            self.btnRejectedPTWs:               self.tabRejectedPTWs,
            self.btnWaitingRunConfirmationPTWs: self.tabWaitingRunConfirmationPTWs,
            self.btnRunningPTWs:                self.tabRunningPTWs,
            self.btnWaitingHldConfirmationPTWs: self.tabWaitingHldConfirmationPTWs,
            self.btnHeldPTWs:                   self.tabHeldPTWs,
            self.btnWaitingClsConfirmationPTWs: self.tabWaitingClsConfirmationPTWs,
            self.btnClosedPTWs:                 self.tabClosedPTWs,
            self.btnArchivedPTWs:               self.tabArchivedPTWs,
            self.btnUsers:                      self.tabAllUsers,
            self.btnRisks:                      self.tabRisks,
            self.btnIsolations:           self.tabIsolations,
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
        self.btnFAB.setFont(QFont("Arial", 24, QFont.Weight.Bold))
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
        err = ClientRequests.updateTheme(self.loggedUser, new_theme)
        if err:
            QMessageBox.warning(self, "Error", f"Failed to save theme preference:\n{err}")
            return

        if msg.clickedButton() == btn_restart:
            self.logout()

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
                    self._expandSidebar()
                elif event.type() == QEvent.Type.Leave:
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
        import os
        import sys
        self._sseListener.stop()
        self._sseListener.wait(1000)
        self.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)
    
    def viewPTW(self, row: int, ptw: PTWData):
        viewPTWDialog = DialogPTW(self, self.loggedUser, ptw, None, False, True, f'View Mode - PTW# {ptw.id}')
        viewPTWDialog.exec()
    
    def editPTW(self, row: int, ptw: PTWData):
        toEditPtw = copy.deepcopy(ptw)
        editPTWDialog = DialogPTW(self, self.loggedUser, toEditPtw, None, False, False, 'Edit Mode - PTW# {ptw.id}')
        if editPTWDialog.exec() == QDialog.DialogCode.Accepted:
            ptw = toEditPtw
            self.stack.currentWidget().updatePTW(row, ptw)

    def addPTWDialog(self, row: int = None, ptw: PTWData = None):
        newPTW = copy.deepcopy(ptw) if ptw else PTWData()
        if ptw:
            newPTW.setId(None).clearApprovals()
        title = "Re-request PTW" if ptw else "New PTW"
        dlg = DialogPTW(self, self.loggedUser, newPTW, ptw, True, False, title)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        err, ptwId = ClientRequests.addPTW(self.loggedUser, newPTW)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return
        newPTW.setId(ptwId)
        if dlg.attachsToBeUploaded:
            err = ClientRequests.addPtwAttachments(self.loggedUser, newPTW.id, dlg.attachsToBeUploaded)
            if err:
                QMessageBox.warning(self, "Error", f"Failed to upload attachments: {err}")
                return
        if ptw:
            ClientRequests.copyPtwAttachments(self.loggedUser, ptw.id, newPTW.id)
        # self.refreshGUI()  # SSE event handles refresh

    def deletePTW(self, row: int, ptw: PTWData):
        self.stack.currentWidget().deletePTW(row)
    
    def archivePTWs(self, rows: list, ptws: list[PTWData]):
        err = ClientRequests.archivePTWs(self.loggedUser, [ptw.id for ptw in ptws])
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh
    
    def requestToRunPTW(self, row: int, ptw: PTWData):
        for p in globalData.allPTWs:
            if p.performing == self.loggedUser.getUsername():
                QMessageBox.warning(self, 'Not Allowed', f"You are already the PA for PTW# {p.id}.")
                return
        
        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.requestToRunPTW(self.loggedUser, ptw.id, pa, ts)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh
    
    def runAcceptTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, True)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh

    def runRejectTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, False)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return 
        # self.refreshGUI()  # SSE event handles refresh

    def requestToClsPTW(self, row: int, ptw: PTWData):
        # QMessageBox.aboutQt(self)
        reply = QMessageBox.question(self, 'Close PTW', f"Are you sure you want to close PTW# '{ptw.id}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes:
            return
    
        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.requestToClsPTW(self.loggedUser, ptw.id, pa, ts)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh
    
    def clsAcceptPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, True)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh
    
    def clsRejectPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, False)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return 
        # self.refreshGUI()  # SSE event handles refresh

    def requestToHldPTW(self, row: int, ptw: PTWData):
        dlg = DialogSelectIsolations(self, ptw.isolations, selectable=True, title=f"Hold PTW# {ptw.id} - Select Isolations to Keep")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        keptTags = dlg.getKeptTags()
        pa = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.requestToHldPTW(self.loggedUser, ptw.id, pa, ts, keptTags)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh

    def hldAcceptPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, True)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh

    def hldRejectPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, False)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        # self.refreshGUI()  # SSE event handles refresh

    def hldTakeAction(self, row: int, ptw: PTWData):
        if ptw.running_status != PTWData.RunningStatus.WAITING_HLD_CONFIRM:
            QMessageBox.warning(self, 'Not Allowed', f"PTW# {ptw.id} is not waiting for hold confirmation.")
            return
        dlg = DialogSelectIsolations(self, ptw.isolations, kept=ptw.keep_isolations, selectable=False, review_mode=True, title=f"Hold Action - PTW# {ptw.id}")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.action == 'accept':
            self.hldAcceptPTW(row, ptw)
        elif dlg.action == 'reject':
            self.hldRejectPTW(row, ptw)

    def viewIsolations(self, row: int, ptw: PTWData):
        dlg = DialogSelectIsolations(
            self, ptw.isolations, kept=ptw.keep_isolations,
            selectable=False, view_only=True,
            title=f"Isolations - PTW# {ptw.id}"
        )
        dlg.exec()

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
    

    def viewRequestor(self, row: int, ptw: PTWData):
        self.viewUser(ptw.requestor, 'Requestor')

    def viewPerforming(self, row: int, ptw: PTWData):
        self.viewUser(ptw.performing, 'PA')

    def viewIssuing(self, row: int, ptw: PTWData):
        self.viewUser(ptw.issuing, 'IA')
    
    def viewApprovals(self, row: int, ptw: PTWData):
        dlg = QDialog(self)
        dlg.setWindowTitle(f"PTW# {ptw.id} Approval Cycle")
        dlg.resize(int(0.7 * self.width()), int(0.75 * self.height()))
        dlg.setMaximumHeight(int(0.9 * self.screen().availableGeometry().height()))

        lyt = QVBoxLayout()
        lst = QListWidget()
        if len(ptw.approvals) == 0:
            item = QListWidgetItem()
            widget = QLabel(
                text="There's no approval history at the moment",
                font=QFont("Helvetica", 12), 
            )
            item.setSizeHint(widget.sizeHint())
            lst.addItem(item)
            lst.setItemWidget(item, widget)
        else:
            for approval in ptw.approvals:
                item = QListWidgetItem()
                approvalWidget = approval.toWidget()
                sizeHint = approvalWidget.sizeHint()
                sizeHint = QSize(int(sizeHint.width() * 1.2), int(sizeHint.height() * 1.2))
                item.setSizeHint(sizeHint)
                lst.addItem(item)
                lst.setItemWidget(item, approvalWidget)
            
            lst.setStyleSheet("QListWidget::item { border-bottom: 2px solid palette(mid); }")

        dlg.setLayout(lyt)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(dlg.close)
        lyt.addWidget(lst)
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
        user = copy.deepcopy(self.loggedUser)
        old_theme = self.loggedUser.getTheme()
        dlg = DialogSettings(self, user)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        err = ClientRequests.updateUser(self.loggedUser, user)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return

        self.loggedUser = user
        MainWindow.refreshWelcomePage(self)

        if dlg.new_theme != old_theme:
            self._applyThemeChange(dlg.new_theme)
        
    def btnFABUpdatePosition(self):
        margin = 40
        x = self.width() - self.btnFAB.width() - margin
        y = self.height() - self.btnFAB.height() - margin - self.statusBar().height()
        self.btnFAB.move(x, y)
    
    def setAvailableTabs(self, groups: list[list[QPushButton]]):
        FOOTER_BTNS: list[QPushButton] = [self.btnTheme, self.btnSettings, self.btnRefresh, self.btnLogout]

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

        # --- Collect nav buttons ---
        nav_btns = [btn for group in groups for btn in group] + FOOTER_BTNS

        # --- Welcome grid ---
        col_count = 3
        for i in range(col_count):
            self.lytWelcomeBtns.setColumnStretch(i, 1)
        while self.lytWelcomeBtns.count():
            item = self.lytWelcomeBtns.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        tiles = []
        for btn in nav_btns:
            tile = QToolButton()
            tile.setIcon(btn.icon())
            tile.setText(btn.toolTip())
            tile.setIconSize(QSize(48, 48))
            tile.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            tile.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            tile.clicked.connect(btn.click)
            tile.setStyleSheet("""
                QToolButton {
                    background: rgba(128, 128, 128, 0.15);
                    border: 1px solid rgba(128, 128, 128, 0.30);
                    border-radius: 10px;
                    padding: 10px 6px;
                    color: palette(window-text);
                }
                QToolButton:hover {
                    background: rgba(128, 128, 128, 0.25);
                    border: 1px solid rgba(128, 128, 128, 0.50);
                }
                QToolButton:pressed {
                    background: rgba(128, 128, 128, 0.38);
                }
            """)
            tiles.append(tile)

        total = len(tiles)
        last_row_count = total % col_count or col_count
        last_row_start = total - last_row_count
        for i, tile in enumerate(tiles):
            row = i // col_count
            if i >= last_row_start:
                pos = i - last_row_start
                col = pos * col_count // last_row_count
                colspan = (pos + 1) * col_count // last_row_count - col
                self.lytWelcomeBtns.addWidget(tile, row, col, 1, colspan)
            else:
                self.lytWelcomeBtns.addWidget(tile, row, i % col_count)
            if i < 10:
                QShortcut('Alt+' + str(i + 1), self).activated.connect(tile.click)

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

        # TOOLBAR_GROUPS = [
        #     ("&PTWs",        lambda tip: "PTW" in tip),
        #     ("&Risks",       lambda tip: "Risks" in tip),
        #     ("&Isolations",  lambda tip: "Isolation" in tip),
        #     ("&Users",       lambda tip: "User" in tip),
        # ]
        
        TOOLBAR_GROUPS = ["&PTWs", "&Risks", "&Isolations", "&Users", "&View", "&Help"]

        def getToolbarGroup(tip):
            if "Home" in tip or "Refresh" in tip or "Light/Dark" in tip:
                return "&View"
            for group in TOOLBAR_GROUPS:
                if group[1:] in tip:
                    return group
            return "&Help"

        
        # group_widgets: dict[str, list] = {name: [] for name, _ in TOOLBAR_GROUPS}
        # ungrouped: list = []
        # for group in groups:
        #     for g in group_widgets.values():
        #         if g and g[-1]:
        #             g.append(None)  # separator between groups
        #     for btn in group:
        #         tip = btn.toolTip()
        #         for name, predicate in TOOLBAR_GROUPS:
        #             if predicate(tip):
        #                 group_widgets[name].append(btn)
        #                 break
        #         else:
        #             ungrouped.append(btn)

        group_widgets: dict[str, list] = {name: [] for name in TOOLBAR_GROUPS}
        for group in groups + [FOOTER_BTNS]:
            for g in group_widgets.values():
                if g and g[-1]:
                    g.append(None)  # separator between groups
            for btn in group:
                tip = btn.toolTip()
                group_name = getToolbarGroup(tip)
                group_widgets[group_name].append(btn)

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

        group_widgets["&View"].insert(0, sidebarToggle)
        group_widgets["&View"].insert(1, None)
        for act in sidebarDockActions[::-1]:
            group_widgets["&View"].insert(1, act)

        aboutAction = QAction(qta.icon('fa6s.circle-info'), "About PTW", self)
        aboutAction.triggered.connect(self._showAboutPTW)
        aboutQtAction = QAction(qta.icon('fa6s.circle-question'), "About Qt", self)
        aboutQtAction.triggered.connect(lambda: QMessageBox.aboutQt(self, "About Qt"))
        group_widgets["&Help"].extend([None, aboutAction, aboutQtAction])

        self.toolbar.clear()
        for name in TOOLBAR_GROUPS:
            if btns := group_widgets[name]:
                self.toolbar.addWidget(make_menu_btn(name, [nav_action(w) if isinstance(w, QPushButton) else w for w in btns]))

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
                "Authorizing work to run, and you can request edits or reject permits that "
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
                "Use the <b>Users</b> tab to create, and edit user accounts. "
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
        return f"Update: {event_type} for PTW #{ptw_id}"

    def refreshWelcomePage(self):
        globalData.refresh(self.loggedUser, self.loggedUser.getDepartment() if self.loggedUser.getRole() == UserRoles.USER else None, refreshUsers=True)
        self.btnWelcomeName.setText(self.loggedUser.getRole() + ' ' + self.loggedUser.getName().upper() + '!')

    def refreshPtwUserGUI(self, refreshArchivedPTWs: bool = False):
        globalData.refresh(
            self.loggedUser, 
            self.loggedUser.getDepartment() if self.loggedUser.getRole() == UserRoles.USER else None, 
            refreshUsers=True, refreshPTWs=True, refreshRiskAssessments=True, 
            refreshMIWIs=True, refreshIsolations=True, 
        )

        tabs: list[TablePTWs] = [
            self.tabUnderReviewPTWs,
            self.tabApprovedPTWs,
            self.tabReturnedPTWs,
            self.tabRejectedPTWs,
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
            mySt = ptw.getApprovalStatus(role=self.loggedUser.getRole())
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
            elif st == PTWData.ApprovalStatus.REJECTED:
                self.tabRejectedPTWs.addPTWToGUI(ptw)
            elif st == PTWData.ApprovalStatus.RETURNED:
                self.tabReturnedPTWs.addPTWToGUI(ptw)
            elif st == PTWData.ApprovalStatus.UNDER_REVIEW and mySt == PTWData.ApprovalStatus.UNDER_REVIEW:
                self.tabUnderReviewPTWs.addPTWToGUI(ptw)

        for tab in tabs:
            tab.sort()

        self.tabIsolations.setIsolations(globalData.isolations)

        if refreshArchivedPTWs:
            self.refreshArchivedPTWs()
    
    def refreshArchivedPTWs(self):
        self.tabArchivedPTWs.clear()
        globalData.refresh(
            self.loggedUser, 
            self.loggedUser.getDepartment() if self.loggedUser.getRole() == UserRoles.USER else None, 
            refreshArchivedPTWs=True
        )
        for ptw in globalData.archivedPTWs:
            self.tabArchivedPTWs.addPTWToGUI(ptw)
        self.tabArchivedPTWs.sort()

    def acceptPTW(self, row: int, ptw: PTWData):
        approval = PTWData.Approval(PTWData.ApprovalActions.APPROVED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'))
        err = ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return
        self.refreshGUI()

    def getComment(self, title: str):
        comment = ''

        dlg = QDialog(self)
        dlg.setWindowTitle(title)

        lyt = QFormLayout(dlg)
        boxComment = QTextEdit(self)
        boxComment.setPlaceholderText("Comment to be sent for requestor")
        lyt.addRow("Comment:", boxComment)
        dlg.setLayout(lyt)

        btnsDlgComment = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal, self
        )

        def getComment():
            nonlocal comment
            comment = boxComment.toPlainText()
            dlg.accept()
        
        btnsDlgComment.accepted.connect(getComment)
        btnsDlgComment.rejected.connect(dlg.reject)
        lyt.addRow(btnsDlgComment)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            return comment
        return None

    def rejectPTW(self, row: int, ptw: PTWData):
        comment = self.getComment(f'Reject PTW# {ptw.id}')
        if not comment:
            return
        
        approval = PTWData.Approval(
            PTWData.ApprovalActions.REJECTED, 
            self.loggedUser.getUsername(), 
            datetime.now().strftime('%d/%m/%Y %H:%M:%S'), 
            comment
        )
        err = ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return
        self.refreshGUI()
    
    def requestEdits(self, row: int, ptw: PTWData):
        comment = self.getComment(f'Return PTW# {ptw.id} to be Edited')
        if not comment:
            return
        
        approval = PTWData.Approval(PTWData.ApprovalActions.RETURNED, self.loggedUser.getUsername(), datetime.now().strftime('%d/%m/%Y %H:%M:%S'), comment)
        err = ClientRequests.updateApprovalPTW(self.loggedUser, ptw.id, approval)
        if err is not None:
            QMessageBox.critical(self, "Error", err)
            return
        
        ptw.updateApprovals(approval)
        self.refreshGUI()

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



class UserMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - User Window")

        self.tabRegisteredPTWs.addOptions([self.viewOption, self.editOption, self.requestPTWOption, self.viewRequestorOption, self.dltOption, self.exportOption])
        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.dltOption, self.printOption, self.exportOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.runRequestOption, self.printOption, self.exportOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.dltOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.requestPTWOption, self.clsRequestOption, self.hldRequestOption, self.printOption, self.exportOption])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.requestPTWOption, self.printOption, self.exportOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.viewIsolationsOption, self.requestPTWOption, self.runRequestOption, self.printDeIsolationOption, self.printOption, self.exportOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printDeIsolationOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabArchivedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])


        self.setAvailableTabs([
            [self.btnWelcome],
            [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs, self.btnRejectedPTWs],
            [self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs, self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs, self.btnArchivedPTWs],
            [self.btnIsolations],
        ])

        self.btnFAB.setToolTip("New PTW [Ctrl+N]")
        self.btnFAB.setText("+")

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabUnderReviewPTWs, self.tabRegisteredPTWs])
        if tab == self.tabArchivedPTWs and not globalData.archivedPTWs:
            self.refreshArchivedPTWs()

    def btnFABHandler(self):
        if self.btnFAB.isVisible():
            self.addPTWDialog()
    
    def refreshGUI(self, refreshArchivedPTWs: bool = False):
        super().refreshPtwUserGUI(refreshArchivedPTWs=refreshArchivedPTWs)



class CoordinatorMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Coordinator Window")

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.requestEditsOption, self.acceptOption, self.printOption, self.exportOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewApprovalsOption, self.viewRequestorOption, self.printOption, self.exportOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.dltOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printOption, self.exportOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.printOption, self.exportOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printDeIsolationOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabArchivedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])

        self.setAvailableTabs([
            [self.btnWelcome],
            [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs, self.btnRejectedPTWs],
            [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs, self.btnArchivedPTWs],
            [self.btnIsolations],
        ])

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon("fa5.file-pdf"))
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

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestEditsOption, self.acceptOption, self.rejectOption, self.printOption, self.exportOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.dltOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.runAcceptOption, self.runRejectOption, self.printOption, self.exportOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.hldTakeActionOption, self.printOption, self.exportOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.printOption, self.exportOption])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.clsAcceptOption, self.clsRejectOption, self.printOption, self.exportOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printDeIsolationOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabArchivedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])

        self.setAvailableTabs([
            [self.btnWelcome],
            [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs, self.btnRejectedPTWs],
            [self.btnWaitingRunConfirmationPTWs, self.btnRunningPTWs, self.btnWaitingHldConfirmationPTWs, self.btnHeldPTWs, self.btnWaitingClsConfirmationPTWs, self.btnClosedPTWs, self.btnArchivedPTWs],
            [self.btnIsolations],
        ])

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon("fa5.file-pdf"))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations)
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

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestEditsOption, self.acceptOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])

        self.setAvailableTabs([
            [self.btnWelcome],
            [self.btnUnderReviewPTWs, self.btnRunningPTWs],
            [self.btnIsolations],
            [self.btnRisks],
        ])

        self.btnFAB.setText("+")
        self.btnFAB.setToolTip("New Risk [Ctrl+N]")

        QShortcut(QKeySequence("Ctrl+N"), self).activated.connect(self.addNewRiskDialog)
    
    def btnFABHandler(self):
        self.addNewRiskDialog()
    

    def addNewRiskDialog(self):
        from PTWData import RiskAssessment
        from DialogRisk import DialogRiskAssessment

        if not self.btnFAB.isVisible():
            return
        riskAssessment = RiskAssessment()
        newPTWDialog = DialogRiskAssessment(self, False, riskAssessment, "New Risk Assessment")
        if newPTWDialog.exec() == QDialog.DialogCode.Accepted:
            self.stack.currentWidget().addRiskAssessment(riskAssessment)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabRisks])
    
    def refreshGUI(self):
        super().refreshPtwUserGUI()
        self.tabRisks.setRiskAssessmentsInGUI(globalData.allRiskAssessments)




class ManagerMainWindow(MainWindow):
    def __init__(self, loggedUser: User, role: str):
        super().__init__(loggedUser)
        self.setWindowTitle(f"PTW (Permit To Work) - {role} Window")

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestEditsOption, self.acceptOption, self.rejectOption, self.printOption, self.exportOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.dltOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption, self.exportOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.printOption, self.exportOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printDeIsolationOption, self.printOption, self.archiveOption, self.exportOption])
        self.tabArchivedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption, self.exportOption])

        self.setAvailableTabs([
            [self.btnWelcome],
            [self.btnUnderReviewPTWs, self.btnReturnedPTWs, self.btnApprovedPTWs, self.btnRejectedPTWs],
            [self.btnRunningPTWs, self.btnHeldPTWs, self.btnClosedPTWs],
            [self.btnIsolations],
        ])

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon("fa5.file-pdf"))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations)
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

        self.setAvailableTabs([
            [self.btnWelcome],
            [self.btnUsers],
        ])

        self.btnFAB.setText("+")
        self.btnFAB.setToolTip("Add New User [Ctrl+N]")

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.addNewUserDialog)
    
    def btnFABHandler(self):
        self.addNewUserDialog()
    
    def addNewUserDialog(self):
        if not self.btnFAB.isVisible():
            return
        newUser = User()
        dlg = DialogUser(self, False, True, self.loggedUser, newUser, 'New User')
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.tabAllUsers.addUser(newUser)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabAllUsers])
    
    def refreshGUI(self):
        super().refreshWelcomePage()
        self.tabAllUsers.clear()
        for user in globalData.allUsers.values():
            self.tabAllUsers.addUserToGUI(user)



