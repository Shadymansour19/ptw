"""IC (Isolation Certificate) create/view dialog.

Tabbed like DialogPTW (Basic Info / Isolation Items / P&ID / Wiring / PSIC, plus History
and PTW Linkage in readonly mode only): lets a requestor build a new IC or, in readonly
mode, view an already-submitted one, including its approval/isolation history and any
PTWs linked to it.
"""

from datetime import datetime
from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout, QComboBox, QLineEdit,
                              QTextEdit, QCheckBox, QLabel, QMessageBox,
                              QWidget, QPushButton, QInputDialog)
import qtawesome as qta

from models.User import UserRoles, UserDepartments
from models.PTW import PTW
from models.Isolation import IC
from tables.TableIsolationItems import TableIsolationItems
from widgets.WidgetPidWiring import WidgetPidWiring
from widgets.UiUtils import Timeline
from GlobalData import globalData
from network.clientRequests import ClientRequests
from helper.i18n import t
from widgets.RefreshOverlay import RefreshOverlay
from dialogs.TabbedDialog import TabbedDialog


# PSIC ("Protective System IC") reason options - defined client-side only, not enforced
# by the server as a fixed enum; the server just stores whatever list of strings is sent.
PSIC_REASONS = ['ESD', 'Fire Protection', 'Fire Detection', 'Gas Detection', 'Protection System', 'Other']
PSIC_REASON_GRID_COLS = 3

# Sample per-tag isolation data for the "autofill from tag" convenience feature - stands in
# for a real per-tag data source, which doesn't exist yet.
PSIC_TAG_SAMPLES = {
    'XV-3615E': {
        'reasons': ['ESD'],
        'system_description': "UT-C Control Valve — part of the Unit UT-C emergency shutdown loop.",
        'isolation_method': "Close XV-3615E and secure in the closed position with a mechanical lock-out device.",
        'control_measures': "Verify zero-energy state with a local pressure/position check; apply lock-out tag; log in the isolation register before work starts.",
    },
    'SDV-6514': {
        'reasons': ['ESD', 'Fire Protection'],
        'system_description': "FL-A Breaker — feeds the flare header's shutdown valve actuator.",
        'isolation_method': "Open SDV-6514's supply breaker and rack it out.",
        'control_measures': "Verify de-energized with a voltage tester; apply electrical lock-out and danger tag; notify the Electrical shift lead.",
    },
    'EV-5333': {
        'reasons': ['Protection System'],
        'system_description': "IN-A Feeder Panel — supplies the instrument air system's protective shutdown solenoid.",
        'isolation_method': "Isolate EV-5333 at the feeder panel and remove the fuse.",
        'control_measures': "Confirm zero air pressure downstream; apply lock-out tag on the panel; retain the fuse with the permit holder.",
    },
}


class DialogIC(TabbedDialog):
    """IC create/view dialog: Basic Info, Isolation Items, P&ID / Wiring, and PSIC tabs
    always shown, plus History and PTW Linkage tabs added only in readonly mode (a
    brand-new IC has neither approval history nor any linked PTW yet). There is no
    editable-existing-IC mode - an IC can only be created new or viewed read-only."""

    def displayNameForUsername(username: str):
        """Return username's display name, or username itself if unknown/blank.

        Called on the class itself (DialogIC.displayNameForUsername(...)), not on an
        instance, so no self is passed despite the lack of a @staticmethod decorator.
        """
        if not username:
            return ''
        user = globalData.allUsers.get(username)
        return user.getName() if user else username

    def displayNameForApproval(approval) -> str:
        """Return "<role> <name> (<department>)" for a USER approver, "<role> <name>"
        otherwise, or a translated deleted-user placeholder if the acting account no
        longer exists - the Arabic-aware equivalent of IC.Approval's own English-only
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
        of IC.Approver's own English-only __str__."""
        if approver.role == UserRoles.USER and approver.department:
            return t(approver.department)
        return t(approver.role)

    def __init__(self, parent, loggedUser, ic: IC, new: bool, readOnly: bool, title: str):
        """Build every tab's widgets and wire up their signals, then populate them from
        ic and apply the readOnly state. History/PTW Linkage tabs are only added when
        readOnly is True."""
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.loggedUser = loggedUser
        self.ic = ic
        self.new = new
        self.readonly = readOnly
        self._requestorUsername = self.loggedUser.getUsername() if new else ic.requestor

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(0, 0, 0, 0)

        lyt.addWidget(self.tabsContainer)
        lyt.addWidget(self.stack, stretch=1)

        self.tabBasicInfo = QWidget(self.stack)
        self.tabItems = QWidget(self.stack)
        self.tabPidWiring = QWidget(self.stack)
        self.tabPsic = QWidget(self.stack)

        formBasicInfo = QFormLayout(self.tabBasicInfo)
        formBasicInfo.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lytItems = QVBoxLayout(self.tabItems)
        lytPidWiring = QVBoxLayout(self.tabPidWiring)
        lytPidWiring.setContentsMargins(0, 0, 0, 0)
        lytPsic = QVBoxLayout(self.tabPsic)

        self.btnBasicInfo = self.addTab(t("Basic Info"), "mdi6.file-document-outline", self.tabBasicInfo)
        self.btnItems = self.addTab(t("Isolation Items"), "fa6s.unlock-keyhole", self.tabItems)
        self.btnPidWiring = self.addTab(t("P&&ID / Wiring"), "mdi6.pipe", self.tabPidWiring)
        self.btnPsic = self.addTab(t("PSIC"), "mdi6.shield-check", self.tabPsic)

        # History and PTW Linkage are only meaningful once there's something to show,
        # so both are only offered in readonly mode (a brand-new IC has
        # neither approvals nor any linked PTW yet).
        lytLinkage = None
        if readOnly:
            self.tabHistory = QWidget(self.stack)
            lytHistoryPanes = QHBoxLayout(self.tabHistory)
            self.btnHistory = self.addTab(t("History"), "fa6s.clock-rotate-left", self.tabHistory)

            self.tabLinkage = QWidget(self.stack)
            lytLinkage = QVBoxLayout(self.tabLinkage)
            lytLinkage.addWidget(QLabel(f"<b>{t('Linked PTWs')}</b>", font=QFont("Helvetica", 14)))
            self.btnLinkage = self.addTab(t("PTW Linkage"), "mdi.link-variant", self.tabLinkage)

        self.boxId = QLineEdit()
        self.boxId.setReadOnly(True)
        self.typeCombo = QComboBox()
        for ty in IC.Types:
            self.typeCombo.addItem(t(ty), ty.value)
        self.boxRequestorDepartment = QLineEdit()
        self.boxRequestorDepartment.setReadOnly(True)
        self.boxExecutionDepartment = QComboBox()
        for dept in UserDepartments:
            self.boxExecutionDepartment.addItem(t(dept), dept.value)
        self.boxRequestor = QLineEdit()
        self.boxRequestor.setReadOnly(True)
        self.boxRequestTime = QLineEdit()
        self.boxRequestTime.setReadOnly(True)
        self.boxLocation = QComboBox()
        for location in PTW.Locations:
            self.boxLocation.addItem(t(location), location.value)
        self.boxEquipment = QLineEdit()
        self.boxReason = QTextEdit()
        self.boxReason.setFixedHeight(self.boxReason.fontMetrics().lineSpacing() * 4 + 10)

        self.typeCombo.currentTextChanged.connect(self._certTypeChanged)

        formBasicInfo.addRow(t("IC#:"), self.boxId)
        formBasicInfo.addRow(t("Type:"), self.typeCombo)
        formBasicInfo.addRow(t("Requestor Department:"), self.boxRequestorDepartment)
        formBasicInfo.addRow(t("Execution Department:"), self.boxExecutionDepartment)
        formBasicInfo.addRow(t("Requestor:"), self.boxRequestor)
        formBasicInfo.addRow(t("Request Time:"), self.boxRequestTime)
        formBasicInfo.addRow(t("Location:"), self.boxLocation)
        formBasicInfo.addRow(t("Equipment:"), self.boxEquipment)
        formBasicInfo.addRow(t("Reason:"), self.boxReason)

        self.boxIsolateAsap = QCheckBox(t("Isolate ASAP (once approved)"))
        formBasicInfo.addRow(self.boxIsolateAsap)

        self.boxLongTerm = QCheckBox(t("Long Term Isolation"))
        self.boxLongTermReason = QTextEdit()
        self.boxLongTermReason.setFixedHeight(self.boxLongTermReason.fontMetrics().lineSpacing() * 2 + 10)
        self.boxLongTermReason.setPlaceholderText(t("Reason for long term isolation"))
        self.boxLongTerm.toggled.connect(self.boxLongTermReason.setEnabled)
        formBasicInfo.addRow(self.boxLongTerm)
        formBasicInfo.addRow(t("Long Term Reason:"), self.boxLongTermReason)

        self.itemsTable = TableIsolationItems(self.tabItems, ic.items, readOnly)
        self.itemsTable.setMinimumHeight(300)
        lytItems.addWidget(self.itemsTable, stretch=1)

        self.pidWiringWidget = WidgetPidWiring(self.tabPidWiring, self.loggedUser, ic, readOnly)
        lytPidWiring.addWidget(self.pidWiringWidget, stretch=1)
        self.pidDocsToBeUploaded = self.pidWiringWidget.docsToBeUploaded
        self.itemsTable.itemsChanged.connect(self.pidWiringWidget.onItemsChanged)

        # PSIC (Protective System IC) - any IC, regardless of type, can be flagged as one.
        self.boxIsPsic = QCheckBox(t("Protective System IC (PSIC)"))
        self.boxIsPsic.setFont(QFont("Helvetica", 13, QFont.Weight.Bold))
        lytIsPsicRow = QHBoxLayout()
        lytIsPsicRow.addStretch()
        lytIsPsicRow.addWidget(self.boxIsPsic)
        lytIsPsicRow.addStretch()
        lytPsic.addLayout(lytIsPsicRow)

        formPsicOther = QFormLayout()
        formPsicOther.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.boxPsicMocNumber = QLineEdit()
        self.boxPsicMocNumber.setPlaceholderText(t("MOC # (if applicable)"))
        self.psicTagCombo = QComboBox()
        self.btnPsicAutofill = QPushButton(qta.icon("mdi6.auto-fix"), t("Autofill from Tag"))
        self.btnPsicAutofill.clicked.connect(self._autofillPsicFromTag)
        lytPsicAutofill = QHBoxLayout()
        lytPsicAutofill.addWidget(self.psicTagCombo, stretch=1)
        lytPsicAutofill.addWidget(self.btnPsicAutofill)
        formPsicOther.addRow(t("MOC Number:"), self.boxPsicMocNumber)
        formPsicOther.addRow(t("Autofill from Tag:"), lytPsicAutofill)
        lytPsic.addLayout(formPsicOther)

        lytPsic.addWidget(QLabel(f"<b>{t('PSIC Reason(s)')}</b>"))
        gridPsicReasons = QGridLayout()
        self.psicReasonCheckboxes: dict[str, QCheckBox] = {}
        for i, reason in enumerate(PSIC_REASONS):
            btn = QCheckBox(t(reason))
            self.psicReasonCheckboxes[reason] = btn
            gridPsicReasons.addWidget(btn, i // PSIC_REASON_GRID_COLS, i % PSIC_REASON_GRID_COLS)
        lytPsic.addLayout(gridPsicReasons)

        lytPsicFields = QHBoxLayout()

        def addPsicFieldColumn(labelText: str) -> QTextEdit:
            col = QVBoxLayout()
            col.addWidget(QLabel(t(labelText)), 0, Qt.AlignmentFlag.AlignTop)
            box = QTextEdit()
            box.setMinimumHeight(box.fontMetrics().lineSpacing() * 6 + 10)
            box.setTabChangesFocus(True)
            col.addWidget(box, 1)
            lytPsicFields.addLayout(col)
            return box

        self.boxPsicSystemDescription = addPsicFieldColumn("System to be Isolated:")
        self.boxPsicIsolationMethod = addPsicFieldColumn("Method of Isolation:")
        self.boxPsicControlMeasures = addPsicFieldColumn("Control Measure / Mitigation:")
        lytPsic.addLayout(lytPsicFields, stretch=1)

        # Combo/button/checkbox controls have no "read-only" concept, so they're always
        # disabled outright in readonly mode (matching typeCombo/boxLocation) to prevent
        # interaction. Text fields instead rely on setReadOnly() for that (see
        # _applyReadOnly) and stay visually enabled whenever checked, so a PSIC's own data
        # reads normally in view mode (matching boxLongTermReason's convention).
        self._psicComboWidgets = [self.psicTagCombo, self.btnPsicAutofill] + list(self.psicReasonCheckboxes.values())
        self._psicTextWidgets = [
            self.boxPsicMocNumber, self.boxPsicSystemDescription, self.boxPsicIsolationMethod, self.boxPsicControlMeasures,
        ]
        self.boxIsPsic.toggled.connect(self._psicToggled)
        self.boxIsPsic.toggled.connect(self._certTypeChanged)

        self.itemsTable.itemsChanged.connect(self._refreshPsicTagChoices)
        self._refreshPsicTagChoices()

        if readOnly:
            lytHistoryPanes.addWidget(self._buildApprovalTimelinePane(), stretch=1)
            lytHistoryPanes.addWidget(self._buildIsolationTimelinePane(), stretch=1)

            self._addPTWLinkRows(lytLinkage, ic.linked_ptws)
            self.btnLinkNewPTW = QPushButton(qta.icon("mdi.link-variant"), t("Link to PTW"))
            self.btnLinkNewPTW.clicked.connect(self._linkNewPTW)
            self.btnLinkNewPTW.setVisible(not self.ic.isWindingDown() and self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR))
            lytLinkage.addWidget(self.btnLinkNewPTW)
            lytLinkage.addStretch(1)

        self._refreshOverlay = RefreshOverlay(self)
        self._populate()
        self._applyReadOnly()

        lyt.addLayout(self.bottomButtonsLayout())

        self.stack.currentChanged.connect(self.stackTabChanged)
        self.stackTabChanged()
        self._certTypeChanged()

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.6))
        self.setMinimumHeight(650)

    def _makeReadOnlyField(self, text: str) -> QLineEdit:
        """Build a read-only QLineEdit showing text, scrolled to its start."""
        box = QLineEdit(text)
        box.setReadOnly(True)
        box.setCursorPosition(0)
        return box

    def _viewLinkedPTW(self, ptwId):
        """Handle a linked-PTW row's View button click: look up ptwId (active or
        archived) and open it in a read-only DialogPTW, or warn if it can't be found."""
        ptw = globalData.allPTWs.get(int(ptwId)) or globalData.archivedPTWs.get(int(ptwId))
        if ptw is None:
            QMessageBox.warning(self, t("PTW Not Found"), t("PTW #{0} could not be found (it may be archived).").format(ptwId))
            return
        from dialogs.DialogPTW import DialogPTW
        self._refreshOverlay.showBusy()
        dlg = DialogPTW(self, self.loggedUser, ptw, None, False, True, f"View Mode - PTW# {ptw.id}")
        self._refreshOverlay.hideBusy()
        dlg.exec()

    def _unlinkPTW(self, ptwId):
        """Handle a linked-PTW row's Unlink button click: after confirmation, request the
        server unlink ptwId from this IC, then close this dialog so the caller can reopen
        it with the updated linkage."""
        reply = QMessageBox.question(
            self, t("Unlink PTW"), t("Unlink PTW #{0} from this IC?").format(ptwId),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Unlink Failed"), err)
                return
            QMessageBox.information(self, t("Unlinked"), t("PTW #{0} has been unlinked. Reopen this IC to see the updated linkage.").format(ptwId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.unlinkPTWFromIC(self.loggedUser, self.ic.id, ptwId, callback=on_done)

    def _linkNewPTW(self):
        """Handle the Link to PTW button click: prompt for a PTW id, reject it if already
        linked, otherwise request the server link it to this IC and close this dialog so
        the caller can reopen it with the updated linkage."""
        ptwId, ok = QInputDialog.getText(self, t('Link PTW to IC #{0}').format(self.ic.id), t('PTW #:'))
        if not ok or not ptwId.strip():
            return
        ptwId = ptwId.strip()
        if ptwId in self.ic.linked_ptws:
            QMessageBox.warning(self, t("Already Linked"), t("PTW #{0} is already linked to this IC.").format(ptwId))
            return

        def on_done(err, _):
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Link Failed"), err)
                return
            QMessageBox.information(self, t("Linked"), t("PTW #{0} has been linked. Reopen this IC to see the updated linkage.").format(ptwId))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.linkPTWToIC(self.loggedUser, self.ic.id, ptwId, callback=on_done)

    def _ptwLinkRow(self, ptwId) -> QWidget:
        """Build one PTW Linkage tab row: a read-only label (PTW id plus running status,
        if the PTW is found) with a View button, and an Unlink button for
        User/Issuing/Coordinator roles."""
        ptw = globalData.allPTWs.get(int(ptwId)) or globalData.archivedPTWs.get(int(ptwId))
        label = f"PTW #{ptwId} — {ptw.running_status}" if ptw else f"PTW #{ptwId}"

        row = QWidget()
        lyt = QHBoxLayout(row)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(self._makeReadOnlyField(label), stretch=1)
        btnView = QPushButton(qta.icon("fa6.eye"), t("View"))
        btnView.clicked.connect(partial(self._viewLinkedPTW, ptwId))
        lyt.addWidget(btnView)
        if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR):
            btnUnlink = QPushButton(qta.icon("mdi.link-variant-off"), t("Unlink"))
            btnUnlink.clicked.connect(partial(self._unlinkPTW, ptwId))
            lyt.addWidget(btnUnlink)
        return row

    def _addPTWLinkRows(self, container: QVBoxLayout, ptwIds: list):
        """Populate container with a row per linked PTW id in ptwIds, or a placeholder
        label if there are none."""
        ids = [p for p in ptwIds if p]
        if not ids:
            container.addWidget(QLabel(t("No linked PTWs.")))
            return
        for ptwId in ids:
            container.addWidget(self._ptwLinkRow(ptwId))

    def _timelinePane(self, title: str, timeline: Timeline) -> QWidget:
        """Wrap timeline in a labeled pane, titled title, for the History tab."""
        pane = QWidget()
        lyt = QVBoxLayout(pane)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(QLabel(f"<b>{title}</b>", font=QFont("Helvetica", 14)))
        lyt.addWidget(timeline, stretch=1)
        return pane

    def _buildApprovalTimelinePane(self) -> QWidget:
        """Build the History tab's Approval Timeline pane: the initial request entry
        (green), one entry per recorded Approval (green if Approved, orange if Returned,
        including any comment), then one gray "Pending" entry per still-pending
        approver."""
        entries = []
        if self.ic.requestor:
            color = QColor('green')
            text = f"<b>{t('Requested')}</b> {t('by')} {DialogIC.displayNameForUsername(self.ic.requestor)} {t('at')} {self.ic.requestor_timestamp}"
            content = QLabel(text)
            content.setWordWrap(True)
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        for approval in self.ic.approvals:
            color = QColor('green') if approval.action == IC.ApprovalActions.APPROVED else QColor('orange')
            text = f"<b>{t(approval.action)}</b> {t('by')} {DialogIC.displayNameForApproval(approval)} {t('at')} {approval.timestamp}"
            if approval.comment:
                text += f"<br><b>{t('Comment')}:</b> {approval.comment}"
            content = QLabel(text)
            content.setWordWrap(True)
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        for approver in self.ic.pendingApprovers():
            color = QColor('gray')
            content = QLabel(f"<b>{t('Pending')}</b> {DialogIC.displayNameForApprover(approver)}")
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        timeline = Timeline(entries, t("There's no approval history at the moment"))
        return self._timelinePane(t("Approval Timeline"), timeline)

    def _isolationStageEntry(self, label: str, username: str, timestamp: str, doneColor: QColor = None):
        """Build one Isolation Timeline entry: label plus who/when in doneColor (default
        green) if username is set, else a gray "Pending" placeholder."""
        if username:
            text = f"<b>{label}</b> {t('by')} {DialogIC.displayNameForUsername(username)}"
            if timestamp:
                text += f" {t('at')} {timestamp}"
            color = doneColor or QColor('green')
        else:
            text = f"<b>{label}</b> — {t('Pending')}"
            color = QColor('gray')
        content = QLabel(text)
        content.setWordWrap(True)
        content.setFont(QFont("Helvetica", 13))
        content.setStyleSheet(f"color: {color.name()};")
        return (color, content)

    def _buildIsolationTimelinePane(self) -> QWidget:
        """Build the History tab's Isolation Timeline pane: fixed Isolate/De-isolate
        request-confirm-carried-out stage rows (shown gray/"Pending" until reached), plus
        Sanction-for-test and Re-isolate stage rows only once each has actually started
        (those two cycles are optional excursions that may never happen)."""
        ic = self.ic
        entries = []

        # Isolate and De-isolate always happen — shown as fixed stages, gray/"Pending"
        # until reached. Sanction-for-test and Re-isolate are optional excursions that
        # may not happen at all, so each of their rows only appears once it's set.
        issuingColor = QColor('orange') if ic.isolate_issuing_action == IC.ApprovalActions.RETURNED else QColor('green')
        issuingLabel = f"{t('Isolate')} {t(ic.isolate_issuing_action)}" if ic.isolate_issuing_action else f"{t('Isolate')} {t('Confirmed')}"
        entries.append(self._isolationStageEntry(f"{t('Isolate')} {t('Requested')}", ic.isolate_requestor, ic.isolate_requestor_timestamp))
        entries.append(self._isolationStageEntry(issuingLabel, ic.isolate_issuing, ic.isolate_issuing_timestamp, doneColor=issuingColor))
        entries.append(self._isolationStageEntry(f"{t('Isolate')} {t('Carried Out')}", ic.isolate_isolator, ic.isolate_isolator_timestamp))

        if ic.sanction_requestor:
            entries.append(self._isolationStageEntry(f"{t('Sanction')} {t('Requested')}", ic.sanction_requestor, ic.sanction_requestor_timestamp))
        if ic.sanction_issuing:
            entries.append(self._isolationStageEntry(f"{t('Sanction')} {t('Confirmed')}", ic.sanction_issuing, ic.sanction_issuing_timestamp))
        if ic.sanction_isolator:
            entries.append(self._isolationStageEntry(f"{t('Sanction')} {t('Carried Out')}", ic.sanction_isolator, ic.sanction_isolator_timestamp))

        if ic.reisolate_requestor:
            entries.append(self._isolationStageEntry(f"{t('Re-isolate')} {t('Requested')}", ic.reisolate_requestor, ic.reisolate_requestor_timestamp))
        if ic.reisolate_issuing:
            entries.append(self._isolationStageEntry(f"{t('Re-isolate')} {t('Confirmed')}", ic.reisolate_issuing, ic.reisolate_issuing_timestamp))
        if ic.reisolate_isolator:
            entries.append(self._isolationStageEntry(f"{t('Re-isolate')} {t('Carried Out')}", ic.reisolate_isolator, ic.reisolate_isolator_timestamp))

        entries.append(self._isolationStageEntry(f"{t('De-isolate')} {t('Requested')}", ic.deisolate_requestor, ic.deisolate_requestor_timestamp))
        entries.append(self._isolationStageEntry(f"{t('De-isolate')} {t('Confirmed')}", ic.deisolate_issuing, ic.deisolate_issuing_timestamp))
        entries.append(self._isolationStageEntry(f"{t('De-isolate')} {t('Carried Out')}", ic.deisolate_isolator, ic.deisolate_isolator_timestamp))

        timeline = Timeline(entries, t("No isolation activity yet"))
        return self._timelinePane(t("Isolation Timeline"), timeline)

    def _certTypeChanged(self, _=None):
        """Handle the type combo's currentTextChanged signal and the PSIC checkbox's
        toggled signal: recolor the tab bar for the current type/PSIC combination, and
        for a Self-type IC, force the execution department to match the requestor's own
        department and lock it (any other type leaves it editable, unless readonly)."""
        isPsic = self.boxIsPsic.isChecked()
        color = IC.backgroundColorForType(self.typeCombo.currentData(), isPsic)
        self.setTabBarColor(color)

        if self.typeCombo.currentData() == IC.Types.SELF:
            idx = self.boxExecutionDepartment.findData(self.boxRequestorDepartment.text())
            if idx >= 0:
                self.boxExecutionDepartment.setCurrentIndex(idx)
                self.boxExecutionDepartment.setEnabled(False)
        else:
            self.boxExecutionDepartment.setEnabled(not self.readonly)

    def _populate(self):
        """Fill every Basic Info and PSIC field from self.ic (defaulting the requestor
        and execution departments to the logged-in user's own department when new)."""
        self.boxId.setText(str(self.ic.id) if self.ic.id else '')
        if self.ic.type:
            self.typeCombo.setCurrentIndex(max(0, self.typeCombo.findData(self.ic.type)))
        self.boxRequestorDepartment.setText(self.ic.requestor_department or (self.loggedUser.getDepartment() if self.new else ''))
        executionDept = self.ic.execution_department or (self.loggedUser.getDepartment() if self.new else '')
        if executionDept:
            idx = self.boxExecutionDepartment.findData(executionDept)
            if idx >= 0:
                self.boxExecutionDepartment.setCurrentIndex(idx)
        self.boxRequestor.setText(DialogIC.displayNameForUsername(self._requestorUsername))
        self.boxRequestTime.setText(self.ic.requestor_timestamp or '')
        if self.ic.location:
            self.boxLocation.setCurrentIndex(max(0, self.boxLocation.findData(self.ic.location)))
        self.boxEquipment.setText(self.ic.equipment or '')
        self.boxReason.setText(self.ic.reason or '')
        self.boxIsolateAsap.setChecked(bool(self.ic.isolate_asap))
        self.boxLongTerm.setChecked(bool(self.ic.long_term))
        self.boxLongTermReason.setText(self.ic.long_term_reason or '')
        self.boxLongTermReason.setEnabled(self.boxLongTerm.isChecked())

        self.boxIsPsic.setChecked(bool(self.ic.is_psic))
        psicReasons = set(self.ic.psic_reasons or [])
        for reason, btn in self.psicReasonCheckboxes.items():
            btn.setChecked(reason in psicReasons)
        self.boxPsicMocNumber.setText(self.ic.psic_moc_number or '')
        self.boxPsicSystemDescription.setText(self.ic.psic_system_description or '')
        self.boxPsicIsolationMethod.setText(self.ic.psic_isolation_method or '')
        self.boxPsicControlMeasures.setText(self.ic.psic_control_measures or '')
        self._psicToggled(self.boxIsPsic.isChecked())

    def _applyReadOnly(self):
        """Lock down every Basic Info and PSIC field for viewing an existing IC (combos,
        buttons, and checkboxes disabled outright; text fields set read-only instead so
        their content still renders normally)."""
        self.typeCombo.setEnabled(not self.readonly)
        self.boxLocation.setEnabled(not self.readonly)
        self.boxEquipment.setReadOnly(self.readonly)
        self.boxReason.setReadOnly(self.readonly)
        self.boxIsolateAsap.setEnabled(not self.readonly)
        self.boxLongTerm.setEnabled(not self.readonly)
        self.boxLongTermReason.setReadOnly(self.readonly)
        if self.readonly:
            self.boxLongTermReason.setEnabled(self.boxLongTerm.isChecked())

        self.boxIsPsic.setEnabled(not self.readonly)
        self.boxPsicMocNumber.setReadOnly(self.readonly)
        self.boxPsicSystemDescription.setReadOnly(self.readonly)
        self.boxPsicIsolationMethod.setReadOnly(self.readonly)
        self.boxPsicControlMeasures.setReadOnly(self.readonly)
        if self.readonly:
            self._psicToggled(self.boxIsPsic.isChecked())

    def _psicToggled(self, checked: bool):
        """Handle the PSIC checkbox's toggled signal (and readonly re-application):
        enable/disable the PSIC reason checkboxes, tag combo, and Autofill button
        together with checked (never enabling them in readonly mode), while the PSIC text
        fields just follow checked so their content still reads normally when viewing."""
        for widget in self._psicComboWidgets:
            widget.setEnabled(checked and not self.readonly)
        for widget in self._psicTextWidgets:
            widget.setEnabled(checked)

    def _refreshPsicTagChoices(self):
        """Handle TableIsolationItems.itemsChanged: repopulate the PSIC tag combo from the
        current isolation items, keeping the previous selection if it still exists."""
        currentTag = self.psicTagCombo.currentText()
        self.psicTagCombo.clear()
        self.psicTagCombo.addItems([item.tag for item in self.itemsTable.getItems()])
        idx = self.psicTagCombo.findText(currentTag)
        if idx >= 0:
            self.psicTagCombo.setCurrentIndex(idx)

    def _autofillPsicFromTag(self):
        """Handle the Autofill from Tag button click: look up the selected tag in the
        client-side PSIC_TAG_SAMPLES placeholder data and, if found, check/uncheck the
        PSIC reason checkboxes to match and fill the three PSIC description fields from
        it (overwriting any text already there). Shows a message instead if no tag is
        selected or no sample data exists for it."""
        tag = self.psicTagCombo.currentText()
        if not tag:
            QMessageBox.information(self, t("No Tag Selected"), t("Add an isolation item first, then pick its tag to autofill from."))
            return
        sample = PSIC_TAG_SAMPLES.get(tag)
        if not sample:
            QMessageBox.information(self, t("No Sample Data"), t("No sample isolation data is defined yet for tag '{0}'. Please fill in the fields manually.").format(tag))
            return
        sampleReasons = set(sample.get('reasons', []))
        for reason, btn in self.psicReasonCheckboxes.items():
            btn.setChecked(reason in sampleReasons)
        self.boxPsicSystemDescription.setText(sample['system_description'])
        self.boxPsicIsolationMethod.setText(sample['isolation_method'])
        self.boxPsicControlMeasures.setText(sample['control_measures'])

    def getIC(self):
        """Return the IC model this dialog is editing/viewing."""
        return self.ic

    def accept(self):
        """Handle Finish/Ok being pressed: in readonly mode just close the dialog;
        otherwise validate required fields (equipment, reason, long-term reason if
        checked, at least one isolation item, and - if PSIC is checked - at least one
        PSIC reason plus all three PSIC description fields), write the form's values back
        onto self.ic, stamp requestor/department fields when creating a new IC, and
        close."""
        if self.readonly:
            super().accept()
            return

        equipment = self.boxEquipment.text().strip()
        reason = self.boxReason.toPlainText().strip()
        long_term_reason = self.boxLongTermReason.toPlainText().strip()
        if not equipment:
            QMessageBox.warning(self, "Invalid Input", "Please enter the equipment.")
            return
        if not reason:
            QMessageBox.warning(self, "Invalid Input", "Please enter a reason for the isolation.")
            return
        if self.boxLongTerm.isChecked() and not long_term_reason:
            QMessageBox.warning(self, "Invalid Input", "Please enter a reason to isolate for long term")
            return
        if not self.itemsTable.getItems():
            QMessageBox.warning(self, "Invalid Input", "Please add at least one isolation item.")
            return

        psic_system_description = self.boxPsicSystemDescription.toPlainText().strip()
        psic_isolation_method = self.boxPsicIsolationMethod.toPlainText().strip()
        psic_control_measures = self.boxPsicControlMeasures.toPlainText().strip()
        if self.boxIsPsic.isChecked():
            if not any(btn.isChecked() for btn in self.psicReasonCheckboxes.values()):
                QMessageBox.warning(self, "Invalid Input", "Please select at least one PSIC reason.")
                return
            if not psic_system_description or not psic_isolation_method or not psic_control_measures:
                QMessageBox.warning(self, "Invalid Input", "Please fill in the system to be isolated, method of isolation, and control measure/mitigation for this PSIC.")
                return

        executionDept = self.boxExecutionDepartment.currentData()
        if not executionDept:
            QMessageBox.warning(self, "Invalid Input", "Please select an execution department.")
            return
        if self.typeCombo.currentData() == IC.Types.SELF and executionDept != self.loggedUser.getDepartment():
            QMessageBox.warning(self, "Invalid Input", "Self-isolation must be executed by your own department.")
            return

        self.ic.type = self.typeCombo.currentData()
        self.ic.location = self.boxLocation.currentData()
        self.ic.equipment = equipment
        self.ic.reason = reason
        self.ic.isolate_asap = self.boxIsolateAsap.isChecked()
        self.ic.long_term = self.boxLongTerm.isChecked()
        self.ic.long_term_reason = long_term_reason

        self.ic.is_psic = self.boxIsPsic.isChecked()
        self.ic.psic_reasons = [reason for reason, btn in self.psicReasonCheckboxes.items() if btn.isChecked()]
        self.ic.psic_moc_number = self.boxPsicMocNumber.text().strip()
        self.ic.psic_system_description = psic_system_description
        self.ic.psic_isolation_method = psic_isolation_method
        self.ic.psic_control_measures = psic_control_measures

        if self.new:
            self.ic.requestor_department = self.loggedUser.getDepartment()
            self.ic.execution_department = executionDept
            self.ic.requestor = self.loggedUser.getUsername()
            self.ic.requestor_timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        super().accept()
