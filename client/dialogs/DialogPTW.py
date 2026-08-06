import copy
from datetime import datetime
from PyQt6.QtCore import Qt, QDir, QFileInfo
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QGridLayout, QWidget, QLineEdit, QComboBox,
                              QTextEdit, QPushButton, QCheckBox, QRadioButton, QButtonGroup,
                              QDialogButtonBox, QMessageBox,
                              QFileDialog, QSizePolicy, QFrame, QLabel, QInputDialog)
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QColor
import re

from models.User import UserRoles
from models.PTW import PTW, Attachment, RiskAssessment
from models.Isolation import IC
from tables.TableRisks import TableRisks
from tables.TableAttachments import TableAttachments
from GlobalData import globalData
from reports.ReportGenerator import ReportGenerator
from network.clientRequests import ClientRequests
from tables.TableIsolations import TablePTWIsolations
from widgets.RiskPreview import RiskAssessmentPreview
from widgets.UiUtils import Timeline
from widgets.RefreshOverlay import RefreshOverlay
from dialogs.TabbedDialog import TabbedDialog
from functools import partial
import qtawesome as qta
from helper.i18n import t

class DialogPTW(TabbedDialog):
    GRID_LYT_COLS = 3
    CHECK_BOX_MAX_LINE_CHARS = 36

    def checkboxDisplayName(text: str):
        if len(text) <= DialogPTW.CHECK_BOX_MAX_LINE_CHARS:
            return text
        else:
            # Insert a newline at the last space before the max line chars, or at max line chars if no space found
            breakpoint = text.rfind(' ', 0, DialogPTW.CHECK_BOX_MAX_LINE_CHARS)
            if breakpoint == -1:
                breakpoint = DialogPTW.CHECK_BOX_MAX_LINE_CHARS
            return text[:breakpoint] + '\n' + text[breakpoint:].lstrip()
        
    def formatCheckBoxText(text: str):
        return text.replace('\n', ' ')

    def displayNameForUsername(username: str):
        if not username:
            return ''
        user = globalData.allUsers.get(username)
        return user.getName() if user else username

    def __init__(self, parent, loggedUser, ptw: PTW, referencePTW: PTW, new: bool, readOnly: bool, lbl: str):
        super().__init__(parent)

        self.setWindowTitle(lbl)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)
        self.ptw = ptw
        self.referencePTW = referencePTW
        self.new = new
        self.loggedUser = loggedUser
        self.readonly = readOnly
        self.requiredAttachs = self.ptw.requiredAttachs()

        attachs = []

        if not new:
            err, attachNames = ClientRequests.getPtwAttachmentNames(loggedUser, self.ptw.id)
            if err:
                QMessageBox.warning(parent, t("Error"), t("Failed to fetch attachments:") + f" {err}")
            else:
                attachs = [Attachment(remoteName=name, uploaded=True) for name in attachNames]

        if referencePTW is not None:
            err, refAttachNames = ClientRequests.getPtwAttachmentNames(loggedUser, referencePTW.id)
            if err:
                QMessageBox.warning(parent, t("Error"), t("Failed to fetch reference PTW attachments:") + f" {err}")
            else:
                attachs.extend([Attachment(remoteName=name, uploaded=True) for name in refAttachNames])

        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)

        self.setLayout(lyt)
        lyt.addWidget(self.tabsContainer)
        lyt.addWidget(self.stack)
        lyt.addLayout(self.bottomButtonsLayout())

        self.tabBasicInfo = QWidget(self.stack)
        self.tabTools     = QWidget(self.stack)
        self.tabHazards   = QWidget(self.stack)
        self.tabControls  = QWidget(self.stack)
        self.tabRisks     = QWidget(self.stack)
        self.tabIsolation = QWidget(self.stack)
        self.tabMiwiMos   = QWidget(self.stack)
        self.tabAttachments = QWidget(self.stack)

        lytBasicInfo = QFormLayout()
        lytBasicInfo.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lytTools = QGridLayout()
        lytHazards = QGridLayout()
        lytControls = QGridLayout()
        lytRisks = QVBoxLayout()
        lytIsolation = QVBoxLayout()
        lytMiwiMos = QGridLayout()
        lytAttachments = QVBoxLayout()

        self.tabBasicInfo.setLayout(lytBasicInfo)
        self.tabTools.setLayout(lytTools)
        self.tabHazards.setLayout(lytHazards)
        self.tabControls.setLayout(lytControls)
        self.tabRisks.setLayout(lytRisks)
        self.tabIsolation.setLayout(lytIsolation)
        self.tabMiwiMos.setLayout(lytMiwiMos)
        self.tabAttachments.setLayout(lytAttachments)

        self.btnBasicInfo   = self.addTab(t("Basic Info"), "mdi6.file-document-outline", self.tabBasicInfo)
        self.btnTools       = self.addTab(t("Tools"), "fa6s.wrench", self.tabTools)
        self.btnHazards     = self.addTab(t("Hazards"), "mdi.alert-octagon-outline", self.tabHazards)
        self.btnControls    = self.addTab(t("Controls"), "fa6s.shield-halved", self.tabControls)
        self.btnRisks       = self.addTab(t("Risks"), "fa5s.exclamation-triangle", self.tabRisks)
        self.btnIsolation   = self.addTab(t("Isolation"), "fa6s.unlock-keyhole", self.tabIsolation)
        self.btnMiwiMos     = self.addTab(t("MIWI/MOS"), "fa6.rectangle-list", self.tabMiwiMos)
        self.btnAttachments = self.addTab(t("Attachments"), "fa6s.paperclip", self.tabAttachments)

        # History and IC Linkage are only meaningful once there's something to show,
        # so both are only offered in readonly mode (a brand-new PTW has neither
        # approvals nor any linked IC yet).
        lytHistoryPanes = None
        lytLinkage = None
        if readOnly:
            self.tabHistory = QWidget(self.stack)
            lytHistoryPanes = QHBoxLayout(self.tabHistory)
            self.btnHistory = self.addTab(t("History"), "fa6s.clock-rotate-left", self.tabHistory)

            self.tabLinkage = QWidget(self.stack)
            lytLinkage = QVBoxLayout(self.tabLinkage)
            lytLinkage.addWidget(QLabel(f"<b>{t('Linked ICs')}</b>", font=QFont("Helvetica", 14)))
            self.btnLinkage = self.addTab(t("IC Linkage"), "mdi.link-variant", self.tabLinkage)

        self.boxPTWId = QLineEdit()
        self.boxPTWType = QComboBox(self.tabBasicInfo)
        for type in PTW.Types:
            self.boxPTWType.addItem(t(type), type.value)
        self.boxDate = QLineEdit()
        self.boxDepartment = QLineEdit()
        self.boxRequestor = QLineEdit()
        self.boxPerforming = QLineEdit()
        self.boxLocation = QComboBox(self.tabBasicInfo)
        for location in PTW.Locations:
            self.boxLocation.addItem(t(location), location.value)
        self.boxAreaClass = QComboBox(self.tabBasicInfo)
        for areaClass in PTW.AreaClasses:
            self.boxAreaClass.addItem(t(areaClass), areaClass.value)
        self.boxEquipment = QLineEdit()
        self.boxFastTrack = QComboBox()
        self.boxFastTrack.addItems(['No', 'Yes'])
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 5 + 10)
        self.boxDescription.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.boxDescription.setAcceptRichText(False)

        self.boxPTWId.setText(str(ptw.id) if ptw.id else '')
        self.boxPTWType.setCurrentIndex(max(0, self.boxPTWType.findData(str(ptw.type))))
        self.boxDate.setText(datetime.now().strftime("%d/%m/%Y %H:%M:%S") if new else str(ptw.request_date))
        self.boxDepartment.setText(self.loggedUser.department if new else str(ptw.department) if self.loggedUser.department else '')
        self._requestorUsername = self.loggedUser.getUsername() if new else ptw.requestor
        self.boxRequestor.setText(DialogPTW.displayNameForUsername(self._requestorUsername))
        self.boxPerforming.setText(DialogPTW.displayNameForUsername(ptw.getPerforming()))
        self.boxLocation.setCurrentIndex(max(0, self.boxLocation.findData(str(ptw.location) if ptw.location else '')))
        self.boxAreaClass.setCurrentIndex(max(0, self.boxAreaClass.findData(str(ptw.area_class) if ptw.area_class else '')))
        self.boxEquipment.setText(str(ptw.equipment) if ptw.equipment else '')
        self.boxFastTrack.setCurrentText('Yes' if ptw.fast_track else 'No')
        self.boxDescription.setText(str(ptw.description) if ptw.description else '')

        self.boxPTWId.setReadOnly(True)
        self.boxPTWType.setEnabled(not readOnly)
        self.boxDate.setReadOnly(True)
        self.boxDepartment.setReadOnly(True)
        self.boxRequestor.setReadOnly(True)
        self.boxPerforming.setReadOnly(True)
        self.boxLocation.setEnabled(not readOnly)
        self.boxAreaClass.setEnabled(not readOnly)
        self.boxEquipment.setReadOnly(readOnly)
        self.boxFastTrack.setEnabled(not readOnly)
        self.boxDescription.setReadOnly(readOnly)
        self.boxDescription.setTabChangesFocus(True)

        lytBasicInfo.addRow(t('PTW#:'), self.boxPTWId)
        lytBasicInfo.addRow(t('Request Time:'), self.boxDate)
        lytBasicInfo.addRow(t('Dept:'), self.boxDepartment)
        lytBasicInfo.addRow(t('Requestor:'), self.boxRequestor)
        lytBasicInfo.addRow(t('Performing:'), self.boxPerforming)
        lytBasicInfo.addRow(t('Fast Track:'), self.boxFastTrack)
        lytBasicInfo.addRow(t('Type:'), self.boxPTWType)
        lytBasicInfo.addRow(t('Location:'), self.boxLocation)
        lytBasicInfo.addRow(t('Area Class:'), self.boxAreaClass)
        lytBasicInfo.addRow(t('Equipment:'), self.boxEquipment)
        lytBasicInfo.addRow(t('Description:'), self.boxDescription)

        self.btnsTools: dict[str, QCheckBox] = {}
        i = 0
        for tool in PTW.ALL_TOOLS:
            if tool is None:        # Add separator
                i = DialogPTW.GRID_LYT_COLS * ((i + DialogPTW.GRID_LYT_COLS - 1) // DialogPTW.GRID_LYT_COLS)
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                lytTools.addWidget(line, i // DialogPTW.GRID_LYT_COLS, 0, 1, DialogPTW.GRID_LYT_COLS)
                i += DialogPTW.GRID_LYT_COLS
                continue
            btn = QCheckBox(DialogPTW.checkboxDisplayName(t(tool)))
            btn.setObjectName(tool)
            btn.clicked.connect(self.checkRequirement)
            btn.setChecked(tool in ptw.tools)
            btn.setEnabled(not readOnly)
            # btn.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px; }')
            lytTools.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsTools[tool] = btn
            i += 1
        self.boxOtherTools = QLineEdit()
        self.boxOtherTools.setEnabled(not readOnly)
        self.boxOtherTools.setPlaceholderText(t("Others"))
        self.boxOtherTools.setToolTip(t("Other Tools"))
        self.boxOtherTools.setText(', '.join(tool for tool in ptw.tools if tool not in PTW.ALL_TOOLS))
        remaining_cols = DialogPTW.GRID_LYT_COLS - (i % DialogPTW.GRID_LYT_COLS)
        lytTools.addWidget(self.boxOtherTools, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS, 1, remaining_cols)
        
        self.btnsHazard: dict[str, QCheckBox] = {}
        i = 0
        for hazard in PTW.ALL_HAZARDS:
            if hazard is None:        # Add separator
                i = DialogPTW.GRID_LYT_COLS * ((i + DialogPTW.GRID_LYT_COLS - 1) // DialogPTW.GRID_LYT_COLS)
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                lytHazards.addWidget(line, i // DialogPTW.GRID_LYT_COLS, 0, 1, DialogPTW.GRID_LYT_COLS)
                i += DialogPTW.GRID_LYT_COLS
                continue
            btn = QCheckBox(DialogPTW.checkboxDisplayName(t(hazard)))
            btn.setObjectName(hazard)
            btn.clicked.connect(self.checkRequirement)
            btn.setChecked(hazard in ptw.hazards)
            btn.setEnabled(not readOnly)
            # btn.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px; }')
            lytHazards.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsHazard[hazard] = btn
            i += 1
        self.boxOtherHazards = QLineEdit()
        self.boxOtherHazards.setEnabled(not readOnly)
        self.boxOtherHazards.setPlaceholderText(t("Others"))
        self.boxOtherHazards.setToolTip(t("Other Hazards"))
        self.boxOtherHazards.setText(', '.join(hazard for hazard in ptw.hazards if hazard not in PTW.ALL_HAZARDS))
        remaining_cols = DialogPTW.GRID_LYT_COLS - (i % DialogPTW.GRID_LYT_COLS)
        lytHazards.addWidget(self.boxOtherHazards, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS, 1, remaining_cols)
        
        self.btnsControls: dict[str, QCheckBox] = {}
        i = 0
        for ctrl in PTW.ALL_CONTROLS:
            if ctrl is None:        # Add separator
                i = DialogPTW.GRID_LYT_COLS * ((i + DialogPTW.GRID_LYT_COLS - 1) // DialogPTW.GRID_LYT_COLS)
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                lytControls.addWidget(line, i // DialogPTW.GRID_LYT_COLS, 0, 1, DialogPTW.GRID_LYT_COLS)
                i += DialogPTW.GRID_LYT_COLS
                continue
            btn = QCheckBox(DialogPTW.checkboxDisplayName(t(ctrl)))
            btn.setObjectName(ctrl)
            btn.clicked.connect(self.checkRequirement)
            btn.setChecked(ctrl in ptw.controls)
            btn.setEnabled(not readOnly)
            # btn.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px; }')
            lytControls.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsControls[ctrl] = btn
            i += 1
        self.boxOtherControls = QLineEdit()
        self.boxOtherControls.setEnabled(not readOnly)
        self.boxOtherControls.setPlaceholderText(t("Others"))
        self.boxOtherControls.setToolTip(t("Other Controls"))
        self.boxOtherControls.setText(', '.join(ctrl for ctrl in ptw.controls if ctrl not in PTW.ALL_CONTROLS))
        remaining_cols = DialogPTW.GRID_LYT_COLS - (i % DialogPTW.GRID_LYT_COLS)
        lytControls.addWidget(self.boxOtherControls, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS, 1, remaining_cols)

        # Set equal column stretches to maintain consistent width across resize
        for col in range(DialogPTW.GRID_LYT_COLS):
            lytTools.setColumnStretch(col, 1)
            lytHazards.setColumnStretch(col, 1)
            lytControls.setColumnStretch(col, 1)

        riskTitle = t("PTW") + (f"#{self.ptw.id}" if self.ptw.id else "") + t(" - Specific Risk Assessment")
        self.riskAssessment: RiskAssessment = RiskAssessment(title=riskTitle)
        if new and referencePTW:
            err, risk = ClientRequests.getPTWSpecificRiskAssessment(self.loggedUser, referencePTW.id)
            if err:
                QMessageBox.warning(parent, t("Error"), t("Failed to fetch risk assessment for PTW") + f"# {referencePTW.id}. {err}")
            elif risk:
                self.riskAssessment = risk
        elif self.ptw.id:
            err, ptwSpecificRisk = ClientRequests.getPTWSpecificRiskAssessment(self.loggedUser, self.ptw.id)
            if err:
                QMessageBox.warning(self, t("Warning"), t("Failed to load PTW-specific risk assessment") + f"\n{err}")
            elif ptwSpecificRisk:
                self.riskAssessment = ptwSpecificRisk

        self.riskAssessmentPreviewTable = RiskAssessmentPreview(self.tabRisks, self.riskAssessment, readonly=readOnly)
        lytRisks.addWidget(self.riskAssessmentPreviewTable, stretch=1)
        # if not readOnly:
            # TableRisks(self.tabRisks, self.loggedUser, readonly=True, selectable=True)

            # self.tabRisks.setRiskAssessmentsInGUI(dict(globalData.allRiskAssessments))
            # for riskTitle in ptw.risks:
            #     self.tabRisks.checkRisk(riskTitle)


        self.tableIsolation = TablePTWIsolations(self.tabIsolation, self.ptw.isolations, readOnly)
        lytIsolation.addWidget(self.tableIsolation, stretch=1)

        self.btnMiwi = QRadioButton("MIWI")
        self.btnMos  = QRadioButton("MOS")

        self.btnMiwi.setEnabled(not readOnly)
        self.btnMos.setEnabled(not readOnly)

        self.selectorMiwiMos = QButtonGroup(self)
        self.selectorMiwiMos.addButton(self.btnMiwi)
        self.selectorMiwiMos.addButton(self.btnMos)

        self.selectorMiwiMos.buttonClicked.connect(self.miwiMosSwitch)

        self.btnMiwi.setChecked(bool(self.ptw.miwi))
        self.btnMos.setChecked(bool(self.ptw.mos) or not bool(self.ptw.miwi))

        self.boxMOS = QTextEdit()
        self.boxMOS.setReadOnly(readOnly)
        self.boxMOS.setTabChangesFocus(True)
        self.boxMOS.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.boxMOS.setAcceptRichText(False)
        self.boxMOS.setText(str(ptw.mos) if ptw.mos else '')

        self.boxMiwi = QComboBox(self.tabMiwiMos)
        self.boxMiwi.addItems(sorted(globalData.allMIWIs, key=str.casefold))
        # self.boxMiwi.setEditable(True)
        self.boxMiwi.setMaxVisibleItems(10)

        self.btnViewMiwi = QPushButton(qta.icon("fa6.eye"), t('View MIWI'))
        self.btnViewMiwi.clicked.connect(self.openMIWI)

        self.btnNewMiwi = QPushButton(qta.icon("fa6s.plus"), t('New MIWI'))
        self.btnNewMiwi.clicked.connect(self.newMIWI)

        miwiLyt = QHBoxLayout()
        miwiLyt.addWidget(self.boxMiwi, stretch=1)
        miwiLyt.addWidget(self.btnViewMiwi, stretch=0)
        miwiLyt.addWidget(self.btnNewMiwi, stretch=0)

        lytMiwiMos.setColumnStretch(1, 1)
        lytMiwiMos.setRowStretch(0, 1)
        lytMiwiMos.addWidget(self.btnMos, 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignCenter)
        lytMiwiMos.addWidget(self.boxMOS, 0, 1)
        lytMiwiMos.addWidget(self.btnMiwi, 1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lytMiwiMos.addLayout(miwiLyt, 1, 1)

        self.tableAttachments = TableAttachments(self.tabAttachments, loggedUser, self.ptw.id, referencePTW.id if referencePTW else None, attachs, readOnly)

        self.btnNewAttach = QPushButton(qta.icon("fa6s.plus"), t('New Attachment'))
        self.btnNewAttach.clicked.connect(self.newAttachment)

        lytAttachments.addWidget(self.tableAttachments, stretch=1)
        if not readOnly:
            lytAttachments.addWidget(self.btnNewAttach, stretch=0)

        if readOnly:
            lytHistoryPanes.addWidget(self._buildApprovalTimelinePane(), stretch=1)
            lytHistoryPanes.addWidget(self._buildRunningTimelinePane(), stretch=1)

            self._addICLinkRows(lytLinkage, self.ptw.linked_ics)
            self.btnLinkNewIC = QPushButton(qta.icon("mdi.link-variant"), t("Link New IC"))
            self.btnLinkNewIC.clicked.connect(self._linkNewIC)
            self.btnLinkNewIC.setVisible(self.ptw.canLinkIC() and self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR))
            lytLinkage.addWidget(self.btnLinkNewIC)
            lytLinkage.addStretch(1)

        for tabIdx in range(self.stack.count()):
            QShortcut(QKeySequence(f"Alt+{tabIdx + 1}"), self).activated.connect(partial(self.stack.setCurrentIndex, tabIdx))

        self.stack.currentChanged.connect(self.stackTabChanged)
        self.boxPTWType.currentIndexChanged.connect(self.ptwTypeChanged)
        self.stackTabChanged()
        self.miwiMosSwitch()
        self.ptwTypeChanged()

        self._refreshOverlay = RefreshOverlay(self)

    def _makeReadOnlyField(self, text: str) -> QLineEdit:
        box = QLineEdit(text)
        box.setReadOnly(True)
        box.setCursorPosition(0)
        return box

    def _viewLinkedIC(self, icId):
        icsById = {str(ic.id): ic for ic in globalData.ics.values()}
        ic = icsById.get(str(icId))
        if ic is None:
            QMessageBox.warning(self, t("IC Not Found"), t("IC #{0} could not be found.").format(icId))
            return
        from dialogs.DialogIC import DialogIC
        dlg = DialogIC(self, self.loggedUser, ic, False, True, f"IC — {ic.type}")
        dlg.exec()

    def _unlinkIC(self, icId):
        reply = QMessageBox.question(
            self, t("Unlink IC"), t("Unlink IC #{0} from this PTW?").format(icId),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Unlink Failed"), err)
                return
            QMessageBox.information(self, t("Unlinked"), t("IC #{0} has been unlinked. Reopen this PTW to see the updated linkage.").format(icId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.unlinkPTWFromIC(self.loggedUser, int(icId), self.ptw.id, callback=on_done)

    def _requestIsolateIC(self, icId):
        reply = QMessageBox.question(
            self, t('Request Isolate #{0}').format(icId), t("Request isolation for IC #{0}? This will notify Issuing to confirm.").format(icId),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Request Failed"), err)
                return
            QMessageBox.information(self, t("Requested"), t("Isolation requested for IC #{0}. Reopen this PTW to see the updated status.").format(icId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.requestIsolateIC(self.loggedUser, int(icId), callback=on_done)

    def _linkNewIC(self):
        icId, ok = QInputDialog.getText(self, t('Link IC to PTW #{0}').format(self.ptw.id), t('IC #:'))
        if not ok or not icId.strip():
            return
        icId = icId.strip()
        if icId in self.ptw.linked_ics:
            QMessageBox.warning(self, t("Already Linked"), t("IC #{0} is already linked to this PTW.").format(icId))
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Link Failed"), err)
                return
            QMessageBox.information(self, t("Linked"), t("IC #{0} has been linked. Reopen this PTW to see the updated linkage.").format(icId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.linkPTWToIC(self.loggedUser, icId, self.ptw.id, callback=on_done)

    def _icLinkRow(self, icId) -> QWidget:
        icsById = {str(ic.id): ic for ic in globalData.ics.values()}
        ic = icsById.get(str(icId))
        label = f"IC #{icId} — {ic.getStatus()}" if ic else f"IC #{icId}"

        row = QWidget()
        lyt = QHBoxLayout(row)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(self._makeReadOnlyField(label), stretch=1)
        btnView = QPushButton(qta.icon("fa6.eye"), t("View"))
        btnView.clicked.connect(partial(self._viewLinkedIC, icId))
        lyt.addWidget(btnView)
        if self.loggedUser.getRole() == UserRoles.USER:
            btnRequestIsolate = QPushButton(qta.icon("fa6s.unlock-keyhole"), t("Request Isolate"))
            btnRequestIsolate.setEnabled(bool(ic) and ic.getStatus() == IC.Status.APPROVED)
            btnRequestIsolate.clicked.connect(partial(self._requestIsolateIC, icId))
            lyt.addWidget(btnRequestIsolate)
        if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR):
            btnUnlink = QPushButton(qta.icon("mdi.link-variant-off"), t("Unlink"))
            btnUnlink.clicked.connect(partial(self._unlinkIC, icId))
            lyt.addWidget(btnUnlink)
        return row

    def _addICLinkRows(self, container: QVBoxLayout, icIds: list):
        ids = [i for i in icIds if i]
        if not ids:
            container.addWidget(QLabel(t("No linked ICs.")))
            return
        for icId in ids:
            container.addWidget(self._icLinkRow(icId))

    def _timelinePane(self, title: str, timeline: Timeline) -> QWidget:
        pane = QWidget()
        lyt = QVBoxLayout(pane)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(QLabel(f"<b>{title}</b>", font=QFont("Helvetica", 14)))
        lyt.addWidget(timeline, stretch=1)
        return pane

    def _buildApprovalTimelinePane(self) -> QWidget:
        entries = []
        if self.ptw.requestor:
            color = QColor('green')
            text = f"<b>Requested</b> by {DialogPTW.displayNameForUsername(self.ptw.requestor)} at {self.ptw.request_date}"
            content = QLabel(text)
            content.setWordWrap(True)
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        skipPending = False
        for approval in self.ptw.approvals:
            if approval.action == PTW.ApprovalActions.APPROVED:
                color = QColor('green') 
            else:
                color = QColor('orange')
                skipPending = True
            firstWord, _, rest = str(approval).partition(' ')
            text = f"<b>{firstWord}</b> {rest}"
            if approval.comment:
                text += f"<br><b>{t('Comment')}:</b> {approval.comment}"
            content = QLabel(text)
            content.setWordWrap(True)
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        if not skipPending:
            for approver in self.ptw.pendingApprovers():
                color = QColor('gray')
                content = QLabel('<b>Pending</b> ' + str(approver))
                content.setFont(QFont("Helvetica", 13))
                content.setStyleSheet(f"color: {color.name()};")
                entries.append((color, content))

        timeline = Timeline(entries, t("There's no approval history at the moment"))
        return self._timelinePane(t("Approval Timeline"), timeline)

    def _runCycleRequestEntry(self, label: str, username: str, timestamp: str, comment: str = None) -> tuple:
        if username:
            text = f"<b>{label}</b> by {DialogPTW.displayNameForUsername(username)}"
            if timestamp:
                text += f" at {timestamp}"
            if comment:
                text += f"<br><b>{t('Comment')}:</b> {comment}"
            color = QColor('green')
        else:
            text = f"<b>{label}</b> — {t('Pending')}"
            color = QColor('gray')
        content = QLabel(text)
        content.setWordWrap(True)
        content.setFont(QFont("Helvetica", 13))
        content.setStyleSheet(f"color: {color.name()};")
        return (color, content)

    def _runCycleResponseEntry(self, verb: str, username: str, action: str, timestamp: str, comment: str = None) -> tuple:
        if action:
            color = QColor('orange') if action == PTW.RunCycle.Actions.REJECTED else QColor('green')
            text = f"<b>{verb} {action}</b> by {DialogPTW.displayNameForUsername(username)}"
            if timestamp:
                text += f" at {timestamp}"
            if comment:
                text += f"<br><b>{t('Comment')}:</b> {comment}"
        else:
            color = QColor('gray')
            text = f"<b>{verb}</b> — {t('Pending')}"
        content = QLabel(text)
        content.setWordWrap(True)
        content.setFont(QFont("Helvetica", 13))
        content.setStyleSheet(f"color: {color.name()};")
        return (color, content)

    def _buildRunningTimelinePane(self) -> QWidget:
        entries = []
        for i, cycle in enumerate(self.ptw.run_cycles, start=1):
            header = QLabel(f"<b>{t('Run Cycle')} #{i}</b>")
            header.setFont(QFont("Helvetica", 13))
            header.setStyleSheet("color: #777777;")
            entries.append((QColor('#AAAAAA'), header))

            entries.append(self._runCycleRequestEntry(t('Run Requested'), cycle.run_pa, cycle.run_pa_timestamp))
            entries.append(self._runCycleResponseEntry(t('Run'), cycle.run_ia, cycle.run_ia_action, cycle.run_ia_timestamp, cycle.run_ia_comment))

            if cycle.stop_pa_request:
                stopLabel = t(cycle.stop_pa_request)
                entries.append(self._runCycleRequestEntry(f"{stopLabel} {t('Requested')}", cycle.stop_pa, cycle.stop_pa_timestamp, cycle.stop_pa_comment))
                entries.append(self._runCycleResponseEntry(stopLabel, cycle.stop_ia, cycle.stop_ia_action, cycle.stop_ia_timestamp, cycle.stop_ia_comment))

        timeline = Timeline(entries, t("There's no running history at the moment"))
        return self._timelinePane(t("Running Timeline"), timeline)

    def ptwTypeChanged(self):
        color = PTW.backgroundColorForType(self.boxPTWType.currentData())
        self.setTabBarColor(color)
        self.stackTabChanged()

        if not self.readonly:
            self.checkRequirement()

    def checkRequirement(self, state=None):
        if not self.readonly:
            self.collectData()
            self.ptw.updateRequirements()
            self.refreshUI()

    def refreshUI(self):
        ptwType = self.boxPTWType.currentData()

        all_check_btns: dict[str, QCheckBox] = {}
        for btns in [self.btnsTools, self.btnsHazard, self.btnsControls]:
            all_check_btns.update(btns)

        for btn in all_check_btns.values():
            btn.blockSignals(True)
            
        for title, btn in self.btnsTools.items():
            checkBox = PTW.ALL_TOOLS.get(title)
            required = checkBox.isRequired(ptwType)
            restricted = checkBox.isRestricted(ptwType)
            if required:
                btn.setChecked(True)
            elif restricted:
                btn.setChecked(False)
            else:
                btn.setChecked(title in self.ptw.tools)
            btn.setEnabled(not (required or restricted))
        self.boxOtherTools.setText(', '.join(tool for tool in self.ptw.tools if tool not in PTW.ALL_TOOLS))

        for title, btn in self.btnsHazard.items():
            checkBox = PTW.ALL_HAZARDS.get(title)
            required = checkBox.isRequired(ptwType)
            restricted = checkBox.isRestricted(ptwType)
            if required:
                btn.setChecked(True)
            elif restricted:
                btn.setChecked(False)
            else:
                btn.setChecked(title in self.ptw.hazards)
            btn.setEnabled(not (required or restricted))
        self.boxOtherHazards.setText(', '.join(tool for tool in self.ptw.hazards if tool not in PTW.ALL_HAZARDS))

        for title, btn in self.btnsControls.items():
            checkBox = PTW.ALL_CONTROLS.get(title)
            required = checkBox.isRequired(ptwType)
            restricted = checkBox.isRestricted(ptwType)
            if required:
                btn.setChecked(True)
            elif restricted:
                btn.setChecked(False)
            else:
                btn.setChecked(title in self.ptw.controls)
            btn.setEnabled(not (required or restricted))
        self.boxOtherControls.setText(', '.join(tool for tool in self.ptw.controls if tool not in PTW.ALL_CONTROLS))

        self.requiredAttachs = self.ptw.requiredAttachs()
        self.tableAttachments.setRequiredAttachs(self.requiredAttachs)

        for btn in all_check_btns.values():
            btn.blockSignals(False)

    def miwiMosSwitch(self):
        if self.btnMiwi.isChecked():
            self.boxMiwi.setEnabled(not self.readonly)
            self.boxMOS.setEnabled(False)
            self.btnViewMiwi.setEnabled(True)
            self.btnNewMiwi.setEnabled(not self.readonly)
        elif self.btnMos.isChecked():
            self.boxMiwi.setEnabled(False)
            self.boxMOS.setEnabled(True)
            self.btnViewMiwi.setEnabled(False)
            self.btnNewMiwi.setEnabled(False)
            self.boxMOS.setFocus()

    def openMIWI(self):
        def on_done(err, filepath):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), err)
            else:
                ReportGenerator.openPDF(filepath)
        miwiName = self.boxMiwi.currentText()
        if miwiName:
            department = self.ptw.department or self.loggedUser.department
            self._refreshOverlay.showBusy()
            ClientRequests.getMIWI(self.loggedUser, miwiName, department=department, callback=on_done)

    class SaveAsDialog(QDialog):
        def __init__(self, parent, initName: str = '', invalidList: list[str] = [], title: str = "Save file as"):
            super().__init__(parent)
            self.setWindowTitle(t(title))
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)
            lyt = QFormLayout()
            lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            self.setLayout(lyt)
            self.invalidList = invalidList

            self.boxFileName = QLineEdit()
            self.boxFileName.setText(initName)
            self.boxFileName.setMinimumWidth(self.parent().width() // 3)
            self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            self.boxFileName.textChanged.connect(self.checkSaveName)
            self.boxFileName.setStyleSheet("QLineEdit[error='True'] { border: 1px solid red; border-radius: 2px; }")

            lyt.addRow(t("Save on Server as:"), self.boxFileName)
            lyt.addRow(self.btns)

            self.btns.accepted.connect(self.collectData)
            self.btns.rejected.connect(self.reject)
            self.checkSaveName()

        def checkSaveName(self):
            name = self.boxFileName.text().strip()
            self.btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(name) and name not in self.invalidList)
            self.boxFileName.setProperty('error', str(not name or name in self.invalidList))
            self.boxFileName.style().unpolish(self.boxFileName)
            self.boxFileName.style().polish(self.boxFileName)

        def collectData(self):
            self.savename = self.boxFileName.text().strip()
            self.accept()


    def newMIWI(self):
        filepath, _ = QFileDialog.getOpenFileName(self, t("Select MIWI File"), QDir.homePath(), "PDFs (*.pdf);;All Files (*)")
        if not filepath:
            return

        miwiName = QFileInfo(filepath).fileName()
        saveDialog = self.SaveAsDialog(self, initName=miwiName, title="Save MIWI as", invalidList=globalData.allMIWIs)
        resp = saveDialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            miwiName = saveDialog.savename
        elif resp == QDialog.DialogCode.Rejected:
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Error"), err)
                return
            globalData.allMIWIs.append(miwiName)
            self.boxMiwi.addItem(miwiName)
            self.boxMiwi.setCurrentText(miwiName)

        self._refreshOverlay.showBusy()
        ClientRequests.uploadMIWI(self.loggedUser, filepath, miwiName, callback=on_done)
    
    def newAttachment(self):
        filepath, _ = QFileDialog.getOpenFileName(self, t("Select File"), QDir.homePath(), "PDFs (*.pdf);;All Files (*)")
        if not filepath:
            return

        filename = QFileInfo(filepath).fileName()
        saveDialog = self.SaveAsDialog(self, initName=filename, title="Save Attachment as", invalidList=[a.remoteName for a in self.tableAttachments.getAttachments()])
        resp = saveDialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            filename = saveDialog.savename
        elif resp == QDialog.DialogCode.Rejected:
            return

        self.tableAttachments.addAttachment(Attachment(filepath, filename, False))

    def collectData(self):
        if self.readonly:
            return
        
        self.ptw.setId(self.boxPTWId.text() if self.boxPTWId.text() else None)
        self.ptw.setType(self.boxPTWType.currentData())
        self.ptw.setDate(datetime.now().strftime("%d/%m/%Y %H:%M:%S") if self.new else self.boxDate.text())
        self.ptw.setRequestor(self._requestorUsername)
        self.ptw.setDepartment(self.boxDepartment.text())
        self.ptw.setLocation(self.boxLocation.currentData())
        self.ptw.setAreaClass(self.boxAreaClass.currentData())
        self.ptw.setEquipment(self.boxEquipment.text())
        self.ptw.setFastTrack(self.boxFastTrack.currentText() == 'Yes')
        self.ptw.setDescription(self.boxDescription.toPlainText())
        if self.btnMiwi.isChecked():
            self.ptw.setMiwi(self.boxMiwi.currentText())
            self.ptw.setMos(None)
        elif self.btnMos.isChecked():
            self.ptw.setMos(self.boxMOS.toPlainText())
            self.ptw.setMiwi(None)
        
        self.ptw.tools = []
        for title, btn in self.btnsTools.items():
            if btn.isChecked():
                self.ptw.addTool(title)
        if self.boxOtherTools.text():
            for tool in re.split(r'[,/\-+;|]', self.boxOtherTools.text()):
                tool = tool.strip()
                if tool:
                    self.ptw.addTool(tool)

        self.ptw.hazards = []
        for title, btn in self.btnsHazard.items():
            if btn.isChecked():
                self.ptw.addHazard(title)
        if self.boxOtherHazards.text():
            for hazard in re.split(r'[,/\-+;|]', self.boxOtherHazards.text()):
                hazard = hazard.strip()
                if hazard:
                    self.ptw.addHazard(hazard)
        
        self.ptw.controls = []
        for title, btn in self.btnsControls.items():
            if btn.isChecked():
                self.ptw.addControl(title)
        if self.boxOtherControls.text():
            for ctrl in re.split(r'[,/\-+;|]', self.boxOtherControls.text()):
                ctrl = ctrl.strip()
                if ctrl:
                    self.ptw.addControl(ctrl)


        self.ptw.isolations = []
        for isolation in self.tableIsolation.getIsolations():
            self.ptw.addIsolation(isolation)

        self.ptw.attachs = [a.remoteName for a in self.tableAttachments.getAttachments()]
        self.attachsToBeUploaded = [a for a in self.tableAttachments.getAttachments() if not a.uploaded]

    def accept(self):
        if self.readonly:
            return super().accept()
        
        self.collectData()
        err = self.ptw.validate()
        if err:
            QMessageBox.warning(self, t("Invalid Data"), err)
            return
        
        return super().accept()
