"""The full Permit to Work (PTW) form dialog: create, view, and edit modes.

DialogPTW presents every part of a PTW as tabs (Basic Info, Tools, Hazards,
Controls, Risks, Isolation, MIWI/MOS, Attachments, and — readonly mode only —
History and IC Linkage), built on the shared TabbedDialog infrastructure. The
History tab renders the approval log and the running cycle as two side-by-side
Timeline panes; the IC Linkage tab lists ICs linked to this PTW with View/Unlink
actions.
"""

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
    """The full PTW create/view/edit form, tabbed via TabbedDialog.

    Tabs: Basic Info, Tools, Hazards, Controls, Risks, Isolation, MIWI/MOS,
    Attachments — always present — plus History and IC Linkage, offered only in
    readonly mode (a brand-new PTW has neither approvals nor a linked IC yet).
    History shows two side-by-side Timeline panes: the approval log
    (_buildApprovalTimelinePane) and the running-cycle log
    (_buildRunningTimelinePane). IC Linkage lists ICs linked via ptw.linked_ics,
    each with View and (role-permitting) Unlink/Request Isolate actions.

    Mode is driven by the `new`/`readOnly` constructor flags: `new` controls
    whether data is fetched fresh vs. taken from an existing PTW (and whether a
    reference PTW's attachments/risk assessment can be pulled in), while
    `readOnly` disables every editable field/checkbox and switches the dialog
    from an editable form into a plain viewer (also gating the History/IC
    Linkage tabs).
    """

    GRID_LYT_COLS = 3
    CHECK_BOX_MAX_LINE_CHARS = 36

    def checkboxDisplayName(text: str):
        """Wrap `text` onto two lines (breaking at the last space before the max
        line width) if it's longer than CHECK_BOX_MAX_LINE_CHARS, for a tools/
        hazards/controls checkbox label."""
        if len(text) <= DialogPTW.CHECK_BOX_MAX_LINE_CHARS:
            return text
        else:
            # Insert a newline at the last space before the max line chars, or at max line chars if no space found
            breakpoint = text.rfind(' ', 0, DialogPTW.CHECK_BOX_MAX_LINE_CHARS)
            if breakpoint == -1:
                breakpoint = DialogPTW.CHECK_BOX_MAX_LINE_CHARS
            return text[:breakpoint] + '\n' + text[breakpoint:].lstrip()
        
    def formatCheckBoxText(text: str):
        """Collapse a checkboxDisplayName-wrapped label back to a single line."""
        return text.replace('\n', ' ')

    def displayNameForUsername(username: str):
        """Look up username in globalData.allUsers and return their display name,
        falling back to the raw username if not found (or '' if username is falsy)."""
        if not username:
            return ''
        user = globalData.allUsers.get(username)
        return user.getName() if user else username

    def displayNameForApproval(approval) -> str:
        """Return "<role> <name> (<department>)" for a USER approver, "<role> <name>"
        otherwise, or a translated deleted-user placeholder if the acting account no
        longer exists - the Arabic-aware equivalent of PTW.Approval's own English-only
        __str__ (used only for Timeline rendering here, not shared with the PDF report
        path in ReportGenerator.py, so translating it doesn't affect reports)."""
        user = globalData.allUsers.get(approval.username)
        if user is None:
            return f"[{t('deleted user')}: {approval.username}]"
        if user.getRole() == UserRoles.USER:
            return f"{t(user.getRole())} {user.getName()} ({t(user.getDepartment())})"
        return f"{t(user.getRole())} {user.getName()}"

    def displayNameForApprover(approver) -> str:
        """Return the translated department name for a USER-role Approver with a
        department set, else the translated role name - the Arabic-aware equivalent
        of PTW.Approver's own English-only __str__."""
        if approver.role == UserRoles.USER and approver.department:
            return t(approver.department)
        return t(approver.role)

    def __init__(self, parent, loggedUser, ptw: PTW, referencePTW: PTW, new: bool, readOnly: bool, lbl: str):
        """Build every tab of the PTW form from `ptw` and wire up its fields' enabled state.

        Args:
            ptw: the PTW to display/edit (a freshly-constructed one when `new`).
            referencePTW: an existing PTW to copy attachments/risk assessment
                from when creating a new PTW "from" it, or None.
            new: whether this is a brand-new PTW being created (vs. an existing
                one being viewed/edited) — controls data-fetching and whether
                History/IC Linkage even apply.
            readOnly: whether every field/checkbox is disabled for plain viewing;
                also gates the History/IC Linkage tabs.
            lbl: window title.
        """
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
        for val in ('No', 'Yes'):
            self.boxFastTrack.addItem(t(val), val)
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
        self.boxFastTrack.setCurrentIndex(max(0, self.boxFastTrack.findData('Yes' if ptw.fast_track else 'No')))
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
        """Build a read-only QLineEdit showing `text`, cursor reset to the start."""
        box = QLineEdit(text)
        box.setReadOnly(True)
        box.setCursorPosition(0)
        return box

    def _viewLinkedIC(self, icId):
        """Open the linked IC identified by icId in a read-only DialogIC.

        Slot for an IC Linkage row's View button click. Looks icId up in
        globalData.ics; warns if it can't be found (e.g. stale cache).
        """
        icsById = {str(ic.id): ic for ic in globalData.ics.values()}
        ic = icsById.get(str(icId))
        if ic is None:
            QMessageBox.warning(self, t("IC Not Found"), t("IC #{0} could not be found.").format(icId))
            return
        from dialogs.DialogIC import DialogIC
        dlg = DialogIC(self, self.loggedUser, ic, False, True, f"IC — {ic.type}")
        dlg.exec()

    def _unlinkIC(self, icId):
        """Unlink the IC identified by icId from this PTW, after confirmation.

        Slot for an IC Linkage row's Unlink button click. On success, closes
        this dialog (the caller must reopen it to see the updated linkage).
        """
        reply = QMessageBox.question(
            self, t("Unlink IC"), t("Unlink IC #{0} from this PTW?").format(icId),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            """Handle the unlink-request result: warn on failure, else confirm and close."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Unlink Failed"), err)
                return
            QMessageBox.information(self, t("Unlinked"), t("IC #{0} has been unlinked. Reopen this PTW to see the updated linkage.").format(icId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.unlinkPTWFromIC(self.loggedUser, int(icId), self.ptw.id, callback=on_done)

    def _requestIsolateIC(self, icId):
        """Request isolation of the linked IC identified by icId, after confirmation.

        Slot for an IC Linkage row's Request Isolate button click (USER role
        only). On success, closes this dialog (the caller must reopen it to see
        the updated status).
        """
        reply = QMessageBox.question(
            self, t('Request Isolate #{0}').format(icId), t("Request isolation for IC #{0}? This will notify Issuing to confirm.").format(icId),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            """Handle the isolate-request result: warn on failure, else confirm and close."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Request Failed"), err)
                return
            QMessageBox.information(self, t("Requested"), t("Isolation requested for IC #{0}. Reopen this PTW to see the updated status.").format(icId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.requestIsolateIC(self.loggedUser, int(icId), callback=on_done)

    def _linkNewIC(self):
        """Prompt for an IC number and link it to this PTW.

        Slot for the "Link New IC" button click. Rejects duplicates already in
        ptw.linked_ics; on success, closes this dialog (the caller must reopen
        it to see the updated linkage).
        """
        icId, ok = QInputDialog.getText(self, t('Link IC to PTW #{0}').format(self.ptw.id), t('IC #:'))
        if not ok or not icId.strip():
            return
        icId = icId.strip()
        if icId in self.ptw.linked_ics:
            QMessageBox.warning(self, t("Already Linked"), t("IC #{0} is already linked to this PTW.").format(icId))
            return

        def on_done(err, _):
            """Handle the link-request result: warn on failure, else confirm and close."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Link Failed"), err)
                return
            QMessageBox.information(self, t("Linked"), t("IC #{0} has been linked. Reopen this PTW to see the updated linkage.").format(icId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.linkPTWToIC(self.loggedUser, icId, self.ptw.id, callback=on_done)

    def _icLinkRow(self, icId) -> QWidget:
        """Build one IC Linkage row: label plus View and (role-permitting)
        Request Isolate/Unlink buttons for the IC identified by icId."""
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
        """Populate container with one _icLinkRow per non-empty id in icIds, or a
        "No linked ICs." label if there are none."""
        ids = [i for i in icIds if i]
        if not ids:
            container.addWidget(QLabel(t("No linked ICs.")))
            return
        for icId in ids:
            container.addWidget(self._icLinkRow(icId))

    def _timelinePane(self, title: str, timeline: Timeline) -> QWidget:
        """Wrap timeline in a titled pane for side-by-side placement in the History tab."""
        pane = QWidget()
        lyt = QVBoxLayout(pane)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(QLabel(f"<b>{title}</b>", font=QFont("Helvetica", 14)))
        lyt.addWidget(timeline, stretch=1)
        return pane

    def _buildApprovalTimelinePane(self) -> QWidget:
        """Build the History tab's left Timeline pane from ptw.approvals.

        Emits, in order: a green "Requested" entry (if the PTW has a requestor),
        then one entry per recorded Approval — green for APPROVED, orange
        otherwise (RETURNED/REJECTED) — with its comment appended if present.
        Once any non-APPROVED action is seen, `skipPending` is set so no gray
        "Pending" entries are appended afterward for ptw.pendingApprovers():
        once the chain has been returned/rejected, the remaining stages are no
        longer meaningfully "awaiting" anyone, so they're left out rather than
        shown as if still in progress.
        """
        entries = []
        if self.ptw.requestor:
            color = QColor('green')
            text = f"<b>{t('Requested')}</b> {t('by')} {DialogPTW.displayNameForUsername(self.ptw.requestor)} {t('at')} {self.ptw.request_date}"
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
            text = f"<b>{t(approval.action)}</b> {t('by')} {DialogPTW.displayNameForApproval(approval)} {t('at')} {approval.timestamp}"
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
                content = QLabel(f"<b>{t('Pending')}</b> {DialogPTW.displayNameForApprover(approver)}")
                content.setFont(QFont("Helvetica", 13))
                content.setStyleSheet(f"color: {color.name()};")
                entries.append((color, content))

        timeline = Timeline(entries, t("There's no approval history at the moment"))
        return self._timelinePane(t("Approval Timeline"), timeline)

    def _runCycleRequestEntry(self, label: str, username: str, timestamp: str, comment: str = None) -> tuple:
        """Build one Timeline (color, QLabel) entry for a run-cycle request step
        (e.g. "Run Requested", "Hold Requested").

        Green with the requester/timestamp/comment if `username` is set; gray
        "Pending" otherwise — which only happens for a step the current,
        still-open cycle hasn't reached yet, since every earlier cycle's request
        fields are always already filled in.
        """
        if username:
            text = f"<b>{label}</b> {t('by')} {DialogPTW.displayNameForUsername(username)}"
            if timestamp:
                text += f" {t('at')} {timestamp}"
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
        """Build one Timeline (color, QLabel) entry for the IA's response to a
        run-cycle request step (e.g. "Run Approved/Rejected").

        Green for an Approved action, orange for Rejected, with the responder/
        timestamp/comment; gray "Pending" if `action` is unset — which, as with
        _runCycleRequestEntry, only happens for the current, still-open cycle's
        not-yet-answered step.
        """
        if action:
            color = QColor('orange') if action == PTW.RunCycle.Actions.REJECTED else QColor('green')
            text = f"<b>{verb} {t(action)}</b> {t('by')} {DialogPTW.displayNameForUsername(username)}"
            if timestamp:
                text += f" {t('at')} {timestamp}"
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
        """Build the History tab's right Timeline pane from ptw.run_cycles.

        Renders each RunCycle as a "Run Cycle #N" header followed by its Run
        Requested / Run Approved-or-Rejected rows, and — only if a stop
        (hold/close) has actually been requested on that cycle
        (`cycle.stop_pa_request` set) — its Hold/Close Requested and
        Hold/Close Approved-or-Rejected rows too. A cycle with no stop request
        yet (i.e. still plainly RUNNING) shows no stop rows at all, not even
        pending ones. Gray "Pending" rows only ever appear for whichever step
        the current, still-open cycle hasn't reached yet: every earlier,
        already-finished cycle has all of its relevant fields filled in, so it
        never renders a pending row.
        """
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
        """Recolor the tab bar for the newly-selected PTW type and refresh required fields.

        Slot for the Type combo box's currentIndexChanged (and called once at
        init to set the initial color). Recomputes tab-bar color from the type,
        keeps tab-button selection in sync, and — unless read-only — re-runs
        checkRequirement() since a type change can add/remove required tools/
        hazards/controls/attachments.
        """
        color = PTW.backgroundColorForType(self.boxPTWType.currentData())
        self.setTabBarColor(color)
        self.stackTabChanged()

        if not self.readonly:
            self.checkRequirement()

    def checkRequirement(self, state=None):
        """Recompute and re-render which tools/hazards/controls/attachments are required.

        Slot for any tools/hazards/controls checkbox click (state is the new
        checked state, unused beyond triggering the recompute) and called
        directly by ptwTypeChanged(). No-op in read-only mode. Collects the
        current form data onto self.ptw, asks it to recompute requirements for
        the current type, then refreshes the checkbox UI to match.
        """
        if not self.readonly:
            self.collectData()
            self.ptw.updateRequirements()
            self.refreshUI()

    def refreshUI(self):
        """Re-check/enable each tools/hazards/controls checkbox against the current PTW type.

        Called by checkRequirement() after requirements are recomputed: for
        each checkbox, forces it checked if required by ptwType, forces it
        unchecked and disabled if restricted, otherwise leaves it as the user
        set it; also refreshes the "Others" free-text boxes and the attachment
        table's required-attachments list. Signals are blocked around the whole
        pass so programmatic checked-state changes don't re-trigger
        checkRequirement().
        """
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
        """Toggle the MIWI/MOS tab's enabled fields to match the selected radio button.

        Slot for the MIWI/MOS radio-button group's buttonClicked (and called
        once at init). Enables the MIWI combo/View/New buttons and disables the
        MOS text box when MIWI is selected, or the reverse when MOS is selected
        (focusing the MOS box in that case).
        """
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
        """Fetch and open the selected MIWI PDF. Slot for the "View MIWI" button click."""
        def on_done(err, filepath):
            """Handle the MIWI fetch result: warn on failure, else open the downloaded PDF."""
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
        """Small prompt for a save-on-server filename, validated against a list of names
        already in use (e.g. existing MIWIs or attachments)."""

        def __init__(self, parent, initName: str = '', invalidList: list[str] = [], title: str = "Save file as"):
            """Build the filename field, pre-filled with initName, and Ok/Cancel buttons.

            Args:
                invalidList: names that are rejected (Ok stays disabled) as
                    already in use.
            """
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
            """Enable Ok only for a non-empty, not-already-used name; flag the field red otherwise.

            Slot for the filename field's textChanged.
            """
            name = self.boxFileName.text().strip()
            self.btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(name) and name not in self.invalidList)
            self.boxFileName.setProperty('error', str(not name or name in self.invalidList))
            self.boxFileName.style().unpolish(self.boxFileName)
            self.boxFileName.style().polish(self.boxFileName)

        def collectData(self):
            """Store the trimmed filename as self.savename and accept the dialog.

            Slot for the Ok button (connected to btns.accepted).
            """
            self.savename = self.boxFileName.text().strip()
            self.accept()


    def newMIWI(self):
        """Pick a local PDF, name it, and upload it as a new MIWI document.

        Slot for the "New MIWI" button click. Prompts for a file, then a
        server-side save name (via SaveAsDialog, defaulting to the file's own
        name, rejecting names already in globalData.allMIWIs); on successful
        upload, adds the new name to globalData.allMIWIs and selects it in the
        MIWI combo.
        """
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
            """Handle the MIWI upload result: warn on failure, else register and select it."""
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
        """Pick a local PDF, name it, and add it to the Attachments table.

        Slot for the "New Attachment" button click. Prompts for a file, then a
        server-side save name (via SaveAsDialog, rejecting names already used
        by this PTW's attachments); the file itself is only queued locally here
        (added to the table as not-yet-uploaded) — collectData()/accept()
        collects the not-yet-uploaded attachments into self.attachsToBeUploaded
        for the caller to actually upload once the dialog is accepted.
        """
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
        """Write every editable form field back onto self.ptw. No-op if read-only.

        Also rebuilds self.ptw.tools/hazards/controls/isolations from their
        respective widgets (checkboxes plus the delimiter-split "Others" free
        text), and sets self.attachsToBeUploaded to the attachments not yet
        uploaded, for the caller to upload once this dialog is accepted.
        """
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
        self.ptw.setFastTrack(self.boxFastTrack.currentData() == 'Yes')
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
        """Validate and accept the dialog. Overrides QDialog.accept()/the Finish button's slot.

        Read-only mode accepts unconditionally (nothing to validate). Otherwise
        collects form data via collectData() and blocks acceptance — showing
        the validation error instead — unless self.ptw.validate() passes.
        """
        if self.readonly:
            return super().accept()
        
        self.collectData()
        err = self.ptw.validate()
        if err:
            QMessageBox.warning(self, t("Invalid Data"), err)
            return
        
        return super().accept()
