from datetime import datetime
import copy
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *

from PTWData import PTWData
from TablePTWs import TablePTWs
from WidgetPTW import DialogPTW
from DialogUser import DialogUser
from DialogSelectIsolations import DialogSelectIsolations
from TableUsers import TableUsers
from TableRisks import TableRisks
from TableActiveIsolations import TableActiveIsolations
from DialogSettings import DialogSettings
from clientRequests import ClientRequests
from GlobalData import globalData
from ReportGenerator import ReportGenerator
from SSEListener import SSEListener
from User import User, UserRoles
from functools import partial
import qtawesome as qta


class MainWindow(QMainWindow):
    def __init__(self, loggedUser: User):
        super().__init__()
        self.loggedUser = loggedUser
        self.setWindowTitle("PTW (Permit To Work)")
        self.setMinimumSize(1200, 900)

        frame = self.frameGeometry()
        frame.moveCenter(self.screen().availableGeometry().center())
        self.move(frame.topLeft())

        self.language = 'en'

        self.editOption = TablePTWs.MenuOption('Edit', self.editPTW, qta.icon('fa6s.pen'))
        self.viewOption = TablePTWs.MenuOption('View', self.viewPTW, qta.icon('fa6.eye'))
        self.requestPTWOption = TablePTWs.MenuOption('Re-Request PTW', self.requestPTW, qta.icon('fa6s.question'))
        self.dltOption  = TablePTWs.MenuOption('Delete', self.deletePTW, qta.icon('fa6s.trash-can'))
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
        self.tabAllUsers = TableUsers(self.stack, self.loggedUser, "All Users")
        self.tabRisks = TableRisks(self.stack, self.loggedUser, "All Risks", readonly=False, selectable=False)
        self.tabIsolations = TableActiveIsolations(self.stack, self.loggedUser, "Isolations")

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
        self.btnWelcomeName.setStyleSheet('QPushButton { background-color: transparent; border: none; color: green; } QPushButton:hover { color: lightgreen; } ')
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
        # self.btnActiveIsolations = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_MediaVolumeMuted), "")
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
        self.btnSettings = QPushButton(qta.icon('fa6s.gear'), "")
        self.btnRefresh = QPushButton(qta.icon('fa6s.rotate-right'), "")
        self.btnLogout = QPushButton(qta.icon('fa6s.arrow-right-from-bracket'), "")
        self.btnUsers = QPushButton(qta.icon('fa6s.users-gear'), "")
        # self.btnRisks = QPushButton(qta.icon('fa5s.exclamation-triangle'), "")
        self.btnRisks = QPushButton(qta.icon('mdi.shield-check-outline'), "")
        self.btnActiveIsolations = QPushButton(qta.icon('fa6s.unlock-keyhole'), "")
        self.btnLanguage = QPushButton(qta.icon('fa5s.language'), "")

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
        self.btnSettings.setToolTip("Settings")
        self.btnRefresh.setToolTip("Refresh [Ctrl+R]")
        self.btnLogout.setToolTip("Logout [Ctrl+X]")
        self.btnUsers.setToolTip("All Users")
        self.btnRisks.setToolTip("Risks")
        self.btnActiveIsolations.setToolTip("Isolations")
        self.btnLanguage.setToolTip("Switch Language")

        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self.btnWelcome.click)
        QShortcut(QKeySequence("Ctrl+X"), self).activated.connect(self.btnLogout.click)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.refreshGUI)

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
            self.btnUsers:                      self.tabAllUsers,
            self.btnRisks:                      self.tabRisks,
            self.btnActiveIsolations:           self.tabIsolations,
            self.btnRefresh:                    None, 
            self.btnSettings:                   None,
            self.btnLogout:                     None,
            self.btnLanguage:                   None,
        }

        SIDEBAR_BTN_STYLE = """
            QPushButton {
                background: transparent;
                border: none;
                padding: 6px;
                border-radius: 6px;
            }

            /* Hover */
            QPushButton:hover {
                background: rgba(255,255,255,30);
            }

            /* Pressed */
            QPushButton:pressed {
                background: rgba(255,255,255,60);
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
            btn.setStyleSheet(SIDEBAR_BTN_STYLE)
            if self._sideBarBtnMap[btn] is not None:
                btn.clicked.connect(partial(self.stack.setCurrentWidget, self._sideBarBtnMap[btn]))
        
        self.btnSettings.clicked.connect(self.dlgSettings)
        self.btnLanguage.clicked.connect(self.chgLanguage)
        self.btnRefresh.clicked.connect(self.refreshGUI)
        self.btnLogout.clicked.connect(self.logout)

        mainLayout = QHBoxLayout()
        sideBarWidget = QWidget()
        self.sideBarLayout = QVBoxLayout()
        sideBarWidget.setLayout(self.sideBarLayout)
        sideBarPalette = sideBarWidget.palette()
        sideBarColor = sideBarPalette.color(QPalette.ColorRole.Window).darker(130)
        sideBarBorderColor = sideBarPalette.color(QPalette.ColorRole.Window).darker(30)
        sideBarWidget.setStyleSheet(f"QWidget {{ background-color: {sideBarColor.name()}; border-right: 1px solid {sideBarBorderColor.name()}; }}")
        mainLayout.setContentsMargins(0, 0, 0, 0)

        mainLayout.addWidget(sideBarWidget, stretch=0)
        mainLayout.addWidget(self.stack, stretch=1)

        container = QWidget()
        container.setLayout(mainLayout)
        container.setAutoFillBackground(False)
        self.setCentralWidget(container)

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
        QTimer.singleShot(0, self._populateWelcomeBtns)

        sb = self.statusBar()
        sb.show()
        sb.setStyleSheet("QStatusBar { background: rgba(0,0,0,40); color: #ccc; padding: 0 8px; font-size: 14px; border-top: 1px solid rgba(255,255,255,20); }")

        self._trayIcon = QSystemTrayIcon(QIcon("sh-logo-bw.png"), self)
        self._trayIcon.show()

        self._sseListener = SSEListener(ClientRequests.SERVER_URL, loggedUser.getUsername(), loggedUser.getPassword())
        self._sseListener.eventReceived.connect(self._onSSEEvent)
        self._sseListener.start()


    def _makeSeparator(self):
        line = QFrame()
        line.setFixedHeight(2)
        # line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { background-color: rgba(255,255,255,40); border: none; margin: 2px 2px; }")
        return line

    def resizeEvent(self, event):
        self.btnFABUpdatePosition()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(0.02 if self.stack.currentWidget() == self.tabWelcome else 0.01)
        painter.drawPixmap(self.rect(), QPixmap('./sh-logo-bw.png'))
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

    def requestPTW(self, row: int, ptw: PTWData):
        newPTW = copy.deepcopy(ptw)
        newPTW.setId(None).clearApprovals()
        newPTWDialog = DialogPTW(self, self.loggedUser, newPTW, ptw, True, False, "Re-request PTW")
        if newPTWDialog.exec() == QDialog.DialogCode.Accepted:
            self.tabUnderReviewPTWs.addPTW(newPTW, newPTWDialog.attachsToBeUploaded)
            ClientRequests.copyPtwAttachments(self.loggedUser, ptw.id, newPTW.id)

    def deletePTW(self, row: int, ptw: PTWData):
        self.stack.currentWidget().deletePTW(row)
    
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
        ptw.performing = pa
        ptw.performing_timestamp = ts
        ptw.running_status = PTWData.RunningStatus.WAITING_RUN_CONFIRM
        self.refreshGUI()
    
    def runAcceptTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, True)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        ptw.issuing = ia
        ptw.issuing_timestamp = ts
        ptw.running_status = PTWData.RunningStatus.RUNNING
        self.refreshGUI()
    
    def runRejectTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.runResponsePTW(self.loggedUser, ptw.id, ia, ts, False)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return 
        ptw.issuing = ''
        ptw.issuing_timestamp = ''
        ptw.performing = ''
        ptw.performing_timestamp = ''
        ptw.running_status = PTWData.RunningStatus.NOT_RUNNING
        self.refreshGUI()

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
        ptw.close_performing = pa
        ptw.close_performing_timestamp = ts
        ptw.running_status = PTWData.RunningStatus.WAITING_CLS_CONFIRM
        self.refreshGUI()
    
    def clsAcceptPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, True)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        ptw.close_issuing = ia
        ptw.close_issuing_timestamp = ts
        ptw.running_status = PTWData.RunningStatus.CLOSED
        ptw.issuing = ''
        ptw.issuing_timestamp = ''
        ptw.performing = ''
        ptw.performing_timestamp = ''
        self.refreshGUI()
    
    def clsRejectPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.clsResponsePTW(self.loggedUser, ptw.id, ia, ts, False)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return 
        ptw.close_issuing = ''
        ptw.close_issuing_timestamp = ''
        ptw.close_performing = ''
        ptw.close_performing_timestamp = ''
        ptw.running_status = PTWData.RunningStatus.RUNNING
        self.refreshGUI()

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
        ptw.keep_isolations = keptTags
        ptw.hold_performing = pa
        ptw.hold_performing_timestamp = ts
        ptw.running_status = PTWData.RunningStatus.WAITING_HLD_CONFIRM
        self.refreshGUI()

    def hldAcceptPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, True)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        ptw.issuing = ''
        ptw.issuing_timestamp = ''
        ptw.performing = ''
        ptw.performing_timestamp = ''
        ptw.hold_issuing = ia
        ptw.hold_issuing_timestamp = ts
        ptw.keep_isolations = []
        ptw.running_status = PTWData.RunningStatus.NOT_RUNNING
        self.refreshGUI()

    def hldRejectPTW(self, row: int, ptw: PTWData):
        ia = self.loggedUser.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        err = ClientRequests.hldResponsePTW(self.loggedUser, ptw.id, ia, ts, False)
        if err:
            QMessageBox.warning(self, 'Fail', err)
            return
        ptw.keep_isolations = []
        ptw.hold_performing = ''
        ptw.hold_performing_timestamp = ''
        ptw.hold_issuing = ''
        ptw.hold_issuing_timestamp = ''
        ptw.running_status = PTWData.RunningStatus.RUNNING
        self.refreshGUI()

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
            
            lst.setStyleSheet("QListWidget::item { border-bottom: 1px solid #cccccc; }")

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
        dlg = DialogSettings(self, user)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        
        err = ClientRequests.updateUser(self.loggedUser, user)
        if err:
            QMessageBox.warning(self, "Fail", err)
            return
        
        self.loggedUser = user
        MainWindow.refreshWelcomePage(self)
        
    def btnFABUpdatePosition(self):
        margin = 40
        x = self.width() - self.btnFAB.width() - margin
        y = self.height() - self.btnFAB.height() - margin - self.statusBar().height()
        self.btnFAB.move(x, y)
    
    def _populateWelcomeBtns(self):
        col_count = 3
        for i in range(col_count):
            self.lytWelcomeBtns.setColumnStretch(i, 1)

        welcomeBtns = []
        for i in range(self.sideBarLayout.count()):
            widget = self.sideBarLayout.itemAt(i).widget()
            if isinstance(widget, QPushButton) and widget.toolTip() and widget.toolTip() != "Home [Ctrl+H]":
                btn = QToolButton()
                btn.setIcon(widget.icon())
                btn.setText(widget.toolTip())
                btn.setIconSize(QSize(48, 48))
                # btn.setFixedHeight(90)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                btn.clicked.connect(widget.click)
                btn.setStyleSheet("""
                    QToolButton {
                        background: rgba(255, 255, 255, 0.10);
                        border: 1px solid rgba(255, 255, 255, 0.30);
                        border-radius: 10px;
                        padding: 10px 6px;
                        color: white;
                    }
                    QToolButton:hover {
                        background: rgba(255, 255, 255, 0.15);
                        border: 1px solid rgba(255, 255, 255, 0.45);
                    }
                    QToolButton:pressed {
                        background: rgba(255, 255, 255, 0.20);
                    }
                """)
                welcomeBtns.append(btn)

        total = len(welcomeBtns)
        last_row_count = total % col_count or col_count
        last_row_start = total - last_row_count

        for i, btn in enumerate(welcomeBtns):
            row = i // col_count
            if i >= last_row_start:
                pos = i - last_row_start
                col = pos * col_count // last_row_count
                colspan = (pos + 1) * col_count // last_row_count - col
                self.lytWelcomeBtns.addWidget(btn, row, col, 1, colspan)
            else:
                self.lytWelcomeBtns.addWidget(btn, row, i % col_count)

            if i < 10:
                QShortcut('Alt+' + str(i), self).activated.connect(btn.click)

    def refreshGUI(self):
        pass

    def _onSSEEvent(self, event_type: str, data: dict):
        self.refreshGUI()
        msg = self._formatSSEMessage(event_type, data)
        QApplication.beep()
        self._trayIcon.showMessage("PTW Update", msg, QSystemTrayIcon.MessageIcon.Information, 5000)
        self.statusBar().showMessage(msg, 6000)

    def _formatSSEMessage(self, event_type: str, data: dict) -> str:
        ptw_id = data.get("ptw_id", "?")
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
        return f"Update: {event_type} for PTW #{ptw_id}"

    def refreshWelcomePage(self):
        globalData.refresh(self.loggedUser, self.loggedUser.getDepartment() if self.loggedUser.getRole() == UserRoles.USER else None, refreshUsers=True)
        self.btnWelcomeName.setText(self.loggedUser.getRole() + ' ' + self.loggedUser.getName().upper() + '!')

    def refreshPtwUserGUI(self):
        globalData.refresh(self.loggedUser, self.loggedUser.getDepartment() if self.loggedUser.getRole() == UserRoles.USER else None, refreshAll=True)
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

        self.tabIsolations.setIsolations(globalData.activeIsolations)

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

        self.tabRegisteredPTWs.addOptions([self.viewOption, self.editOption, self.requestPTWOption, self.viewRequestorOption, self.dltOption])
        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.dltOption, self.printOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.runRequestOption, self.printOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.dltOption, self.printOption])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.requestPTWOption, self.clsRequestOption, self.hldRequestOption, self.printOption])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.requestPTWOption, self.printOption])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.requestPTWOption, self.printOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.viewIsolationsOption, self.requestPTWOption, self.runRequestOption, self.printDeIsolationOption, self.printOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestPTWOption, self.printDeIsolationOption, self.printOption])


        self.sideBarLayout.addWidget(self.btnWelcome)
        self.sideBarLayout.addWidget(self._makeSeparator())
        # self.sideBarLayout.addWidget(self.btnRegisteredPTWs)
        self.sideBarLayout.addWidget(self.btnUnderReviewPTWs)
        self.sideBarLayout.addWidget(self.btnReturnedPTWs)
        self.sideBarLayout.addWidget(self.btnApprovedPTWs)
        self.sideBarLayout.addWidget(self.btnRejectedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnWaitingRunConfirmationPTWs)
        self.sideBarLayout.addWidget(self.btnRunningPTWs)
        self.sideBarLayout.addWidget(self.btnWaitingHldConfirmationPTWs)
        self.sideBarLayout.addWidget(self.btnHeldPTWs)
        self.sideBarLayout.addWidget(self.btnWaitingClsConfirmationPTWs)
        self.sideBarLayout.addWidget(self.btnClosedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnActiveIsolations)
        self.sideBarLayout.addStretch()
        self.sideBarLayout.addWidget(self.btnLanguage)
        self.sideBarLayout.addWidget(self.btnSettings)
        self.sideBarLayout.addWidget(self.btnRefresh)
        self.sideBarLayout.addWidget(self.btnLogout)

        self.btnFAB.setToolTip("New PTW [Ctrl+N]")
        self.btnFAB.setText("+")

        shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut.activated.connect(self.addNewPTWDialog)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab in [self.tabUnderReviewPTWs, self.tabRegisteredPTWs])

    def addNewPTWDialog(self):
        if not self.btnFAB.isVisible():
            return
        newPTW = PTWData()
        newPTWDialog = DialogPTW(self, self.loggedUser, newPTW, None, True, False, "New PTW")
        if newPTWDialog.exec() == QDialog.DialogCode.Accepted:
            self.stack.currentWidget().addPTW(newPTW, newPTWDialog.attachsToBeUploaded)

    def btnFABHandler(self):
        self.addNewPTWDialog()
    
    def refreshGUI(self):
        super().refreshPtwUserGUI()



class CoordinatorMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Coordinator Window")

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.requestEditsOption, self.acceptOption, self.printOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewApprovalsOption, self.viewRequestorOption, self.printOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.dltOption, self.printOption])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.printOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printDeIsolationOption, self.printOption])

        self.sideBarLayout.addWidget(self.btnWelcome)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnUnderReviewPTWs)
        self.sideBarLayout.addWidget(self.btnReturnedPTWs)
        self.sideBarLayout.addWidget(self.btnApprovedPTWs)
        self.sideBarLayout.addWidget(self.btnRejectedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnRunningPTWs)
        self.sideBarLayout.addWidget(self.btnHeldPTWs)
        self.sideBarLayout.addWidget(self.btnClosedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnActiveIsolations)
        self.sideBarLayout.addStretch()
        self.sideBarLayout.addWidget(self.btnSettings)
        self.sideBarLayout.addWidget(self.btnRefresh)
        self.sideBarLayout.addWidget(self.btnLogout)

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon("fa5.file-pdf"))
        self.btnFAB.setToolTip("Print current widget PTWs [Ctrl+P]")

        shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        shortcut.activated.connect(self.btnFABHandler)

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations)

    def refreshGUI(self):
        super().refreshPtwUserGUI()

    def btnFABHandler(self):
        if self.btnFAB.isVisible(): 
            self.printPTWs()




class IssuingMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Issuing Window")

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestEditsOption, self.acceptOption, self.rejectOption, self.printOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.dltOption, self.printOption])
        self.tabWaitingRunConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.runAcceptOption, self.runRejectOption, self.printOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])
        self.tabWaitingHldConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.viewIsolationsOption, self.hldTakeActionOption, self.printOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.printOption])
        self.tabWaitingClsConfirmationPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.clsAcceptOption, self.clsRejectOption, self.printOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printDeIsolationOption, self.printOption])

        self.sideBarLayout.addWidget(self.btnWelcome)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnUnderReviewPTWs)
        self.sideBarLayout.addWidget(self.btnReturnedPTWs)
        self.sideBarLayout.addWidget(self.btnApprovedPTWs)
        self.sideBarLayout.addWidget(self.btnRejectedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnWaitingRunConfirmationPTWs)
        self.sideBarLayout.addWidget(self.btnRunningPTWs)
        self.sideBarLayout.addWidget(self.btnWaitingHldConfirmationPTWs)
        self.sideBarLayout.addWidget(self.btnHeldPTWs)
        self.sideBarLayout.addWidget(self.btnWaitingClsConfirmationPTWs)
        self.sideBarLayout.addWidget(self.btnClosedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnActiveIsolations)
        self.sideBarLayout.addStretch()
        self.sideBarLayout.addWidget(self.btnSettings)
        self.sideBarLayout.addWidget(self.btnRefresh)
        self.sideBarLayout.addWidget(self.btnLogout)

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon("fa5.file-pdf"))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations)

    def refreshGUI(self):
        super().refreshPtwUserGUI()

    def btnFABHandler(self):
        self.printPTWs()




class SafetyMainWindow(MainWindow):
    def __init__(self, loggedUser):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Safety Window")

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestEditsOption, self.acceptOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])

        self.sideBarLayout.addWidget(self.btnWelcome)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnUnderReviewPTWs)
        self.sideBarLayout.addWidget(self.btnRunningPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnActiveIsolations)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnRisks)
        self.sideBarLayout.addStretch()
        self.sideBarLayout.addWidget(self.btnSettings)
        self.sideBarLayout.addWidget(self.btnRefresh)
        self.sideBarLayout.addWidget(self.btnLogout)

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

        self.tabUnderReviewPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.requestEditsOption, self.acceptOption, self.rejectOption, self.printOption])
        self.tabReturnedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption])
        self.tabApprovedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printOption])
        self.tabRejectedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.dltOption, self.printOption])
        self.tabRunningPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewPerformingOption, self.viewApprovalsOption, self.printOption])
        self.tabHeldPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.viewIsolationsOption, self.printDeIsolationOption, self.printOption])
        self.tabClosedPTWs.addOptions([self.viewOption, self.viewRequestorOption, self.viewApprovalsOption, self.printDeIsolationOption, self.printOption])

        self.sideBarLayout.addWidget(self.btnWelcome)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnUnderReviewPTWs)
        self.sideBarLayout.addWidget(self.btnReturnedPTWs)
        self.sideBarLayout.addWidget(self.btnApprovedPTWs)
        self.sideBarLayout.addWidget(self.btnRejectedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnRunningPTWs)
        self.sideBarLayout.addWidget(self.btnHeldPTWs)
        self.sideBarLayout.addWidget(self.btnClosedPTWs)
        self.sideBarLayout.addWidget(self._makeSeparator())
        self.sideBarLayout.addWidget(self.btnActiveIsolations)
        self.sideBarLayout.addStretch()
        self.sideBarLayout.addWidget(self.btnSettings)
        self.sideBarLayout.addWidget(self.btnRefresh)
        self.sideBarLayout.addWidget(self.btnLogout)

        # Create Floating Option Button
        self.btnFAB.setIcon(qta.icon("fa5.file-pdf"))
        self.btnFAB.setToolTip("Print current widget PTWs")

    def stackTabChanged(self):
        super().stackTabChanged()
        tab = self.stack.currentWidget()
        self.btnFAB.setVisible(tab != self.tabWelcome and tab != self.tabIsolations)

    def refreshGUI(self):
        super().refreshPtwUserGUI()

    def btnFABHandler(self):
        self.printPTWs()




class AdminMainWindow(MainWindow):
    def __init__(self, loggedUser: User):
        super().__init__(loggedUser)
        self.setWindowTitle("PTW (Permit To Work) - Admin Window")

        self.sideBarLayout.addWidget(self.btnWelcome)
        self.sideBarLayout.addWidget(self.btnUsers)
        self.sideBarLayout.addStretch()
        self.sideBarLayout.addWidget(self.btnSettings)
        self.sideBarLayout.addWidget(self.btnRefresh)
        self.sideBarLayout.addWidget(self.btnLogout)

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



