from datetime import datetime
from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
                              QTextEdit, QCheckBox, QLabel, QDialogButtonBox, QMessageBox,
                              QWidget, QStackedWidget, QPushButton, QInputDialog)
import qtawesome as qta

from User import UserRoles, UserDepartments
from PTWData import PTWData
from Isolation import IC
from TableIsolationItems import TableIsolationItems
from UiUtils import TabButton, lightenColor, Timeline
from GlobalData import globalData
from clientRequests import ClientRequests
from i18n import t
from RefreshOverlay import RefreshOverlay


class DialogIC(QDialog):
    def displayNameForUsername(username: str):
        if not username:
            return ''
        user = globalData.allUsers.get(username)
        return user.getName() if user else username

    def __init__(self, parent, loggedUser, ic: IC, new: bool, readOnly: bool, title: str):
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

        self.tabsContainer = QWidget()
        lytTabs = QHBoxLayout(self.tabsContainer)
        lytTabs.setSpacing(2)
        lytTabs.setContentsMargins(8, 8, 8, 8)

        self.stack = QStackedWidget()

        lyt.addWidget(self.tabsContainer)
        lyt.addWidget(self.stack, stretch=1)

        self.tabBasicInfo = QWidget(self.stack)
        self.tabItems = QWidget(self.stack)

        formBasicInfo = QFormLayout(self.tabBasicInfo)
        formBasicInfo.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lytItems = QVBoxLayout(self.tabItems)

        self.btnBasicInfo = TabButton(self.stack, t("Basic Info"), "mdi6.file-document-outline")
        self.btnItems = TabButton(self.stack, t("Isolation Items"), "fa6s.unlock-keyhole")

        self.tabsBtnsMap: dict[TabButton, QWidget] = {
            self.btnBasicInfo: self.tabBasicInfo,
            self.btnItems: self.tabItems,
        }

        # History and PTW Linkage are only meaningful once there's something to show,
        # so both are only offered in readonly mode (a brand-new IC has
        # neither approvals nor any linked PTW yet).
        lytLinkage = None
        if readOnly:
            self.tabHistory = QWidget(self.stack)
            lytHistoryPanes = QHBoxLayout(self.tabHistory)
            self.btnHistory = TabButton(self.stack, t("History"), "fa6s.clock-rotate-left")
            self.tabsBtnsMap[self.btnHistory] = self.tabHistory

            self.tabLinkage = QWidget(self.stack)
            lytLinkage = QVBoxLayout(self.tabLinkage)
            lytLinkage.addWidget(QLabel(f"<b>{t('Linked PTWs')}</b>", font=QFont("Helvetica", 14)))
            self.btnLinkage = TabButton(self.stack, t("PTW Linkage"), "mdi.link-variant")
            self.tabsBtnsMap[self.btnLinkage] = self.tabLinkage

        for btn, tab in self.tabsBtnsMap.items():
            btn.clicked.connect(partial(self.stack.setCurrentWidget, tab))
            self.stack.addWidget(tab)
            lytTabs.addWidget(btn)

        self.boxId = QLineEdit()
        self.boxId.setReadOnly(True)
        self.typeCombo = QComboBox()
        self.typeCombo.addItems([ty.value for ty in IC.Types])
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
        for location in PTWData.Locations:
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

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lytBtns = QHBoxLayout()
        lytBtns.setContentsMargins(8, 8, 8, 8)
        lytBtns.addStretch()
        lytBtns.addWidget(btns)
        lyt.addLayout(lytBtns)

        self.stack.currentChanged.connect(self.stackTabChanged)
        self.stackTabChanged()
        self._certTypeChanged()

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.6))
        self.setMinimumHeight(650)

    def _makeReadOnlyField(self, text: str) -> QLineEdit:
        box = QLineEdit(text)
        box.setReadOnly(True)
        box.setCursorPosition(0)
        return box

    def _viewLinkedPTW(self, ptwId):
        ptw = next((p for p in globalData.allPTWs if str(p.id) == str(ptwId)), None) or \
              next((p for p in globalData.archivedPTWs if str(p.id) == str(ptwId)), None)
        if ptw is None:
            QMessageBox.warning(self, t("PTW Not Found"), t("PTW #{0} could not be found (it may be archived).").format(ptwId))
            return
        from WidgetPTW import DialogPTW
        self._refreshOverlay.showBusy()
        dlg = DialogPTW(self, self.loggedUser, ptw, None, False, True, f"View Mode - PTW# {ptw.id}")
        self._refreshOverlay.hideBusy()
        dlg.exec()

    def _unlinkPTW(self, ptwId):
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
        ptw = next((p for p in globalData.allPTWs if str(p.id) == str(ptwId)), None) or \
              next((p for p in globalData.archivedPTWs if str(p.id) == str(ptwId)), None)
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
        ids = [p for p in ptwIds if p]
        if not ids:
            container.addWidget(QLabel(t("No linked PTWs.")))
            return
        for ptwId in ids:
            container.addWidget(self._ptwLinkRow(ptwId))

    def _timelinePane(self, title: str, timeline: Timeline) -> QWidget:
        pane = QWidget()
        lyt = QVBoxLayout(pane)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(QLabel(f"<b>{title}</b>", font=QFont("Helvetica", 14)))
        lyt.addWidget(timeline, stretch=1)
        return pane

    def _buildApprovalTimelinePane(self) -> QWidget:
        entries = []
        if self.ic.requestor:
            color = QColor('green')
            text = f"<b>Requested</b> by {DialogIC.displayNameForUsername(self.ic.requestor)} at {self.ic.requestor_timestamp}"
            content = QLabel(text)
            content.setWordWrap(True)
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        for approval in self.ic.approvals:
            color = QColor('green') if approval.action == IC.ApprovalActions.APPROVED else QColor('orange')
            firstWord, _, rest = str(approval).partition(' ')
            text = f"<b>{firstWord}</b> {rest}"
            if approval.comment:
                text += f"<br><b>{t('Comment')}:</b> {approval.comment}"
            content = QLabel(text)
            content.setWordWrap(True)
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        for approver in self.ic.pendingApprovers():
            color = QColor('gray')
            content = QLabel('<b>Pending</b> ' + str(approver))
            content.setFont(QFont("Helvetica", 13))
            content.setStyleSheet(f"color: {color.name()};")
            entries.append((color, content))

        timeline = Timeline(entries, t("There's no approval history at the moment"))
        return self._timelinePane(t("Approval Timeline"), timeline)

    def _isolationStageEntry(self, label: str, username: str, timestamp: str, doneColor: QColor = None):
        if username:
            text = f"<b>{label}</b> by {DialogIC.displayNameForUsername(username)}"
            if timestamp:
                text += f" at {timestamp}"
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
        ic = self.ic
        entries = []

        # Isolate and De-isolate always happen — shown as fixed stages, gray/"Pending"
        # until reached. Sanction-for-test and Re-isolate are optional excursions that
        # may not happen at all, so each of their rows only appears once it's set.
        issuingColor = QColor('orange') if ic.isolate_issuing_action == IC.ApprovalActions.RETURNED else QColor('green')
        issuingLabel = f"Isolate {ic.isolate_issuing_action}" if ic.isolate_issuing_action else "Isolate Confirmed"
        entries.append(self._isolationStageEntry("Isolate Requested", ic.isolate_requestor, ic.isolate_requestor_timestamp))
        entries.append(self._isolationStageEntry(issuingLabel, ic.isolate_issuing, ic.isolate_issuing_timestamp, doneColor=issuingColor))
        entries.append(self._isolationStageEntry("Isolate Carried Out", ic.isolate_isolator, ic.isolate_isolator_timestamp))

        if ic.sanction_requestor:
            entries.append(self._isolationStageEntry("Sanction Requested", ic.sanction_requestor, ic.sanction_requestor_timestamp))
        if ic.sanction_issuing:
            entries.append(self._isolationStageEntry("Sanction Confirmed", ic.sanction_issuing, ic.sanction_issuing_timestamp))
        if ic.sanction_isolator:
            entries.append(self._isolationStageEntry("Sanction Carried Out", ic.sanction_isolator, ic.sanction_isolator_timestamp))

        if ic.reisolate_requestor:
            entries.append(self._isolationStageEntry("Re-isolate Requested", ic.reisolate_requestor, ic.reisolate_requestor_timestamp))
        if ic.reisolate_issuing:
            entries.append(self._isolationStageEntry("Re-isolate Confirmed", ic.reisolate_issuing, ic.reisolate_issuing_timestamp))
        if ic.reisolate_isolator:
            entries.append(self._isolationStageEntry("Re-isolate Carried Out", ic.reisolate_isolator, ic.reisolate_isolator_timestamp))

        entries.append(self._isolationStageEntry("De-isolate Requested", ic.deisolate_requestor, ic.deisolate_requestor_timestamp))
        entries.append(self._isolationStageEntry("De-isolate Confirmed", ic.deisolate_issuing, ic.deisolate_issuing_timestamp))
        entries.append(self._isolationStageEntry("De-isolate Carried Out", ic.deisolate_isolator, ic.deisolate_isolator_timestamp))

        timeline = Timeline(entries, t("No isolation activity yet"))
        return self._timelinePane(t("Isolation Timeline"), timeline)

    def _certTypeChanged(self, _=None):
        color = IC.backgroundColorForType(self.typeCombo.currentText())
        accentColor = lightenColor(color)
        textColor = IC.foregroundColorForType(self.typeCombo.currentText())
        self.tabsContainer.setStyleSheet(f"""
            QWidget {{
                background: {color.name()};
                border-bottom: 4px solid {accentColor.name()};
                border-right: 4px solid {accentColor.name()};
                border-bottom-right-radius: 20px;
            }}
        """)
        for btn in self.tabsBtnsMap:
            btn.setHighlightColor(accentColor, textColor)

        if self.typeCombo.currentText() == IC.Types.SELF:
            idx = self.boxExecutionDepartment.findData(self.boxRequestorDepartment.text())
            if idx >= 0:
                self.boxExecutionDepartment.setCurrentIndex(idx)
                self.boxExecutionDepartment.setEnabled(False)
        else:
            self.boxExecutionDepartment.setEnabled(not self.readonly)

    def stackTabChanged(self):
        tabIdx = self.stack.currentIndex()
        for i, btn in enumerate(self.tabsBtnsMap.keys()):
            btn.setProperty("selected", i == tabIdx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setIcon(isSelected=(i == tabIdx))
            btn.update()

    def _populate(self):
        self.boxId.setText(str(self.ic.id) if self.ic.id else '')
        if self.ic.type:
            self.typeCombo.setCurrentText(self.ic.type)
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

    def _applyReadOnly(self):
        self.typeCombo.setEnabled(not self.readonly)
        self.boxLocation.setEnabled(not self.readonly)
        self.boxEquipment.setReadOnly(self.readonly)
        self.boxReason.setReadOnly(self.readonly)
        self.boxIsolateAsap.setEnabled(not self.readonly)
        self.boxLongTerm.setEnabled(not self.readonly)
        self.boxLongTermReason.setReadOnly(self.readonly)
        if self.readonly:
            self.boxLongTermReason.setEnabled(self.boxLongTerm.isChecked())

    def getIC(self):
        return self.ic

    def accept(self):
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

        executionDept = self.boxExecutionDepartment.currentData()
        if not executionDept:
            QMessageBox.warning(self, "Invalid Input", "Please select an execution department.")
            return
        if self.typeCombo.currentText() == IC.Types.SELF and executionDept != self.loggedUser.getDepartment():
            QMessageBox.warning(self, "Invalid Input", "Self-isolation must be executed by your own department.")
            return

        self.ic.type = self.typeCombo.currentText()
        self.ic.location = self.boxLocation.currentData()
        self.ic.equipment = equipment
        self.ic.reason = reason
        self.ic.isolate_asap = self.boxIsolateAsap.isChecked()
        self.ic.long_term = self.boxLongTerm.isChecked()
        self.ic.long_term_reason = long_term_reason

        if self.new:
            self.ic.requestor_department = self.loggedUser.getDepartment()
            self.ic.execution_department = executionDept
            self.ic.requestor = self.loggedUser.getUsername()
            self.ic.requestor_timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        super().accept()
