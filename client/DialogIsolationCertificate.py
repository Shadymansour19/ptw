from datetime import datetime
from functools import partial

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QComboBox, QLineEdit,
                              QTextEdit, QCheckBox, QDialogButtonBox, QMessageBox,
                              QWidget, QStackedWidget)

from PTWData import PTWData
from Isolation import IsolationCertificate
from TableIsolationItems import TableIsolationItems
from WidgetPTW import TabButton, lightenColor
from GlobalData import globalData
from i18n import t


class DialogIsolationCertificate(QDialog):
    def displayNameForUsername(username: str):
        if not username:
            return ''
        user = globalData.allUsers.get(username)
        return user.getName() if user else username

    def __init__(self, parent, loggedUser, cert: IsolationCertificate, new: bool, readOnly: bool, title: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.loggedUser = loggedUser
        self.cert = cert
        self.new = new
        self.readonly = readOnly
        self._requestorUsername = self.loggedUser.getUsername() if new else cert.isolate_requestor

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
        # so both are only offered in readonly mode (a brand-new certificate has
        # neither approvals nor any linked PTW yet).
        formHistory = None
        formLinkage = None
        if readOnly:
            self.tabHistory = QWidget(self.stack)
            formHistory = QFormLayout(self.tabHistory)
            formHistory.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            self.btnHistory = TabButton(self.stack, t("History"), "fa6s.clock-rotate-left")
            self.tabsBtnsMap[self.btnHistory] = self.tabHistory

            self.tabLinkage = QWidget(self.stack)
            formLinkage = QFormLayout(self.tabLinkage)
            formLinkage.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            self.btnLinkage = TabButton(self.stack, t("PTW Linkage"), "mdi.link-variant")
            self.tabsBtnsMap[self.btnLinkage] = self.tabLinkage

        for btn, tab in self.tabsBtnsMap.items():
            btn.clicked.connect(partial(self.stack.setCurrentWidget, tab))
            self.stack.addWidget(tab)
            lytTabs.addWidget(btn)

        self.boxId = QLineEdit()
        self.boxId.setReadOnly(True)
        self.typeCombo = QComboBox()
        self.typeCombo.addItems([ty.value for ty in IsolationCertificate.Types])
        self.boxDepartment = QLineEdit()
        self.boxDepartment.setReadOnly(True)
        self.boxRequestor = QLineEdit()
        self.boxRequestor.setReadOnly(True)
        self.boxLocation = QComboBox()
        for location in PTWData.Locations:
            self.boxLocation.addItem(t(location), location.value)
        self.boxEquipment = QLineEdit()
        self.boxReason = QTextEdit()
        self.boxReason.setFixedHeight(self.boxReason.fontMetrics().lineSpacing() * 4 + 10)

        self.typeCombo.currentTextChanged.connect(self._certTypeChanged)

        formBasicInfo.addRow(t("IC#:"), self.boxId)
        formBasicInfo.addRow(t("Type:"), self.typeCombo)
        formBasicInfo.addRow(t("Department:"), self.boxDepartment)
        formBasicInfo.addRow(t("Requestor:"), self.boxRequestor)
        formBasicInfo.addRow(t("Location:"), self.boxLocation)
        formBasicInfo.addRow(t("Equipment:"), self.boxEquipment)
        formBasicInfo.addRow(t("Reason:"), self.boxReason)

        self.boxLongTerm = QCheckBox(t("Long Term Isolation"))
        self.boxLongTermReason = QTextEdit()
        self.boxLongTermReason.setFixedHeight(self.boxLongTermReason.fontMetrics().lineSpacing() * 2 + 10)
        self.boxLongTermReason.setPlaceholderText(t("Reason for long term isolation"))
        self.boxLongTerm.toggled.connect(self.boxLongTermReason.setEnabled)
        formBasicInfo.addRow(self.boxLongTerm)
        formBasicInfo.addRow(t("Long Term Reason:"), self.boxLongTermReason)

        self.itemsTable = TableIsolationItems(self.tabItems, cert.items, readOnly)
        self.itemsTable.setMinimumHeight(300)
        lytItems.addWidget(self.itemsTable, stretch=1)

        if readOnly:
            self._addHistoryRow(formHistory, t("Requestor"), cert.isolate_requestor, cert.isolate_requestor_timestamp)
            self._addHistoryRow(formHistory, t("Issuing"), cert.isolate_issuing, cert.isolate_issuing_timestamp, cert.isolate_issuing_action)
            self._addHistoryRow(formHistory, t("Isolator"), cert.isolate_isolator, cert.isolate_isolator_timestamp)
            self._addHistoryRow(formHistory, t("Sanction Requestor"), cert.sanction_requestor, cert.sanction_requestor_timestamp)
            self._addHistoryRow(formHistory, t("Sanction Issuing"), cert.sanction_issuing, cert.sanction_issuing_timestamp)
            self._addHistoryRow(formHistory, t("Sanction Isolator"), cert.sanction_isolator, cert.sanction_isolator_timestamp)
            self._addHistoryRow(formHistory, t("Re-isolate Requestor"), cert.reisolate_requestor, cert.reisolate_requestor_timestamp)
            self._addHistoryRow(formHistory, t("Re-isolate Issuing"), cert.reisolate_issuing, cert.reisolate_issuing_timestamp)
            self._addHistoryRow(formHistory, t("Re-isolate Isolator"), cert.reisolate_isolator, cert.reisolate_isolator_timestamp)
            self._addHistoryRow(formHistory, t("De-isolate Requestor"), cert.deisolate_requestor, cert.deisolate_requestor_timestamp)
            self._addHistoryRow(formHistory, t("De-isolate Issuing"), cert.deisolate_issuing, cert.deisolate_issuing_timestamp)
            self._addHistoryRow(formHistory, t("De-isolate Isolator"), cert.deisolate_isolator, cert.deisolate_isolator_timestamp)

            formLinkage.addRow(t("Primary PTW:"), self._makeReadOnlyField(cert.primary_ptw or '—'))
            formLinkage.addRow(t("Latest PTW:"), self._makeReadOnlyField(cert.latest_ptw or '—'))
            formLinkage.addRow(t("Linked PTWs:"), self._makeReadOnlyField(', '.join(str(p) for p in cert.linked_ptws) or '—'))
            formLinkage.addRow(t("Held By:"), self._makeReadOnlyField(', '.join(str(p) for p in cert.held_by) or '—'))
            formLinkage.addRow(t("Physically Isolated:"), self._makeReadOnlyField(t('Yes') if cert.is_physically_isolated else t('No')))

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

    def _addHistoryRow(self, form: QFormLayout, label: str, username: str, timestamp: str, action: str = None):
        if not username:
            return
        text = DialogIsolationCertificate.displayNameForUsername(username)
        if timestamp:
            text += f" — {timestamp}"
        if action:
            text += f" ({action})"
        form.addRow(f"<b>{label}:</b>", self._makeReadOnlyField(text))

    def _certTypeChanged(self, _=None):
        color = IsolationCertificate.backgroundColorForType(self.typeCombo.currentText())
        accentColor = lightenColor(color)
        textColor = IsolationCertificate.foregroundColorForType(self.typeCombo.currentText())
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

    def stackTabChanged(self):
        tabIdx = self.stack.currentIndex()
        for i, btn in enumerate(self.tabsBtnsMap.keys()):
            btn.setProperty("selected", i == tabIdx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setIcon(isSelected=(i == tabIdx))
            btn.update()

    def _populate(self):
        self.boxId.setText(str(self.cert.id) if self.cert.id else '')
        if self.cert.type:
            self.typeCombo.setCurrentText(self.cert.type)
        self.boxDepartment.setText(self.cert.department or (self.loggedUser.getDepartment() if self.new else ''))
        self.boxRequestor.setText(DialogIsolationCertificate.displayNameForUsername(self._requestorUsername))
        if self.cert.location:
            self.boxLocation.setCurrentIndex(max(0, self.boxLocation.findData(self.cert.location)))
        self.boxEquipment.setText(self.cert.equipment or '')
        self.boxReason.setText(self.cert.reason or '')
        self.boxLongTerm.setChecked(bool(self.cert.long_term))
        self.boxLongTermReason.setText(self.cert.long_term_reason or '')
        self.boxLongTermReason.setEnabled(self.boxLongTerm.isChecked())

    def _applyReadOnly(self):
        self.typeCombo.setEnabled(not self.readonly)
        self.boxLocation.setEnabled(not self.readonly)
        self.boxEquipment.setReadOnly(self.readonly)
        self.boxReason.setReadOnly(self.readonly)
        self.boxLongTerm.setEnabled(not self.readonly)
        self.boxLongTermReason.setReadOnly(self.readonly)
        if self.readonly:
            self.boxLongTermReason.setEnabled(self.boxLongTerm.isChecked())

    def getCertificate(self):
        return self.cert

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

        self.cert.type = self.typeCombo.currentText()
        self.cert.location = self.boxLocation.currentData()
        self.cert.equipment = equipment
        self.cert.reason = reason
        self.cert.long_term = self.boxLongTerm.isChecked()
        self.cert.long_term_reason = long_term_reason

        if self.new:
            self.cert.department = self.loggedUser.getDepartment()
            self.cert.isolate_requestor = self.loggedUser.getUsername()
            self.cert.isolate_requestor_timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        super().accept()
