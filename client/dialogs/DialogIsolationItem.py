from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QComboBox, QLineEdit, QTextEdit, QDialogButtonBox, QMessageBox

from models.PTW import PTW
from models.Isolation import IC
from widgets.SearchableComboBox import SearchableComboBox


class DialogIsolationItem(QDialog):
    def __init__(self, parent=None, item: IC.IsolationItem = None, readonly: bool = False):
        super().__init__(parent)
        self.readonly = readonly
        self._originalItem = item  # only consulted for lock_num/lock_box_num, which the user never edits here
        self.setWindowTitle("View Isolation Item" if readonly else ("Edit Isolation Item" if item else "New Isolation Item"))
        self.setModal(True)
        self.item = None

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.boxTag = SearchableComboBox()
        self.boxTag.setItems(list(PTW.ALL_ISOLATIONS.keys()))
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 3 + 10)
        self.boxDescription.setTabChangesFocus(True)
        self.stateCombo = QComboBox()
        self.stateCombo.addItems([s.value for s in IC.IsolationItem.States])
        self.boxLockNum = QLineEdit()
        self.boxLockNum.setReadOnly(True)
        self.boxLockNum.setPlaceholderText("Set by isolator on confirmation")
        self.boxLockBoxNum = QLineEdit()
        self.boxLockBoxNum.setReadOnly(True)
        self.boxLockBoxNum.setPlaceholderText("Set by isolator on confirmation")

        if item:
            self.boxTag.setCurrentText(item.tag)
            self.boxDescription.setText(item.description)
            self.stateCombo.setCurrentText(item.state)
            self.boxLockNum.setText(item.lock_num)
            self.boxLockBoxNum.setText(item.lock_box_num)

        self.boxTag.itemSelected.connect(self._on_tag_selected)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        lyt.addRow("Tag:", self.boxTag)
        lyt.addRow("Description:", self.boxDescription)
        lyt.addRow("State:", self.stateCombo)
        lyt.addRow("Lock #:", self.boxLockNum)
        lyt.addRow("Lock Box #:", self.boxLockBoxNum)
        lyt.addWidget(btns)

        if readonly:
            self.boxTag.setEnabled(False)
            self.boxDescription.setReadOnly(True)
            self.stateCombo.setEnabled(False)
            btns.button(QDialogButtonBox.StandardButton.Cancel).hide()

    def _on_tag_selected(self, tag):
        if self.readonly:
            return
        # Only autofill from the library when the tag actually matches a known entry - a
        # custom/out-of-list tag (typed freely, or an existing item's own tag while editing)
        # must leave whatever description is already there alone, not blank it out.
        isolation = PTW.ALL_ISOLATIONS.get(tag)
        if isolation:
            self.boxDescription.setText(isolation.description)

    def getItem(self):
        return self.item

    def accept(self):
        if self.readonly:
            super().accept()
            return

        tag = self.boxTag.currentText()
        description = self.boxDescription.toPlainText()

        if not tag:
            QMessageBox.warning(self, "Invalid Input", "Please select a tag or enter a new one.")
            return
        if not description:
            QMessageBox.warning(self, "Invalid Input", "Please enter a description.")
            return

        self.item = IC.IsolationItem(tag=tag, description=description, state=self.stateCombo.currentText())
        lockNum = self._originalItem.lock_num if self._originalItem else self.boxLockNum.text()
        lockBoxNum = self._originalItem.lock_box_num if self._originalItem else self.boxLockBoxNum.text()
        self.item.setLockNum(lockNum).setLockBoxNum(lockBoxNum)
        super().accept()
