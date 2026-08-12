"""Add/edit/view dialog for a single IC isolation item (tag, description, state)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QComboBox, QLineEdit, QTextEdit, QDialogButtonBox, QMessageBox

from models.PTW import PTW
from models.Isolation import IC
from widgets.SearchableComboBox import SearchableComboBox
from helper.i18n import t


class DialogIsolationItem(QDialog):
    """Create, edit, or view one IC.IsolationItem (tag/description/state).

    Lock #/Lock Box # are always shown read-only here regardless of mode -
    they are set later by the isolator when completing physical isolation
    (see DialogCompleteIsolation), never entered by the requestor.
    """

    def __init__(self, parent=None, item: IC.IsolationItem = None, readonly: bool = False):
        """Build the form, prefilling from `item` when editing/viewing an existing one.

        Args:
            parent: Parent widget.
            item: Existing IsolationItem to prefill for edit/view mode, or None to
                create a new item.
            readonly: If True, disable all fields and hide the Cancel button.
        """
        super().__init__(parent)
        self.readonly = readonly
        self._originalItem = item  # only consulted for lock_num/lock_box_num, which the user never edits here
        self.setWindowTitle(t("View Isolation Item") if readonly else (t("Edit Isolation Item") if item else t("New Isolation Item")))
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
        self.boxLockNum.setPlaceholderText(t("Set by isolator on confirmation"))
        self.boxLockBoxNum = QLineEdit()
        self.boxLockBoxNum.setReadOnly(True)
        self.boxLockBoxNum.setPlaceholderText(t("Set by isolator on confirmation"))

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

        lyt.addRow(t("Tag:"), self.boxTag)
        lyt.addRow(t("Description:"), self.boxDescription)
        lyt.addRow(t("State:"), self.stateCombo)
        lyt.addRow(t("Lock #:"), self.boxLockNum)
        lyt.addRow(t("Lock Box #:"), self.boxLockBoxNum)
        lyt.addWidget(btns)

        if readonly:
            self.boxTag.setEnabled(False)
            self.boxDescription.setReadOnly(True)
            self.stateCombo.setEnabled(False)
            btns.button(QDialogButtonBox.StandardButton.Cancel).hide()

    def _on_tag_selected(self, tag):
        """Autofill the description when a picked tag matches a known library entry.

        Triggered by the tag combo box's itemSelected signal. Does nothing in
        readonly mode.
        """
        if self.readonly:
            return
        # Only autofill from the library when the tag actually matches a known entry - a
        # custom/out-of-list tag (typed freely, or an existing item's own tag while editing)
        # must leave whatever description is already there alone, not blank it out.
        isolation = PTW.ALL_ISOLATIONS.get(tag)
        if isolation:
            self.boxDescription.setText(isolation.description)

    def getItem(self):
        """Return the IsolationItem built on accept, or None if not yet accepted."""
        return self.item

    def accept(self):
        """Validate the form and build the resulting IsolationItem, then close the dialog.

        Triggered by the OK button. In readonly mode just closes without validation.
        Otherwise requires a tag and description, then constructs `self.item`,
        carrying over the lock fields from the original item unchanged (or from
        the read-only lock boxes, which stay blank for a brand-new item).
        """
        if self.readonly:
            super().accept()
            return

        tag = self.boxTag.currentText()
        description = self.boxDescription.toPlainText()

        if not tag:
            QMessageBox.warning(self, t("Invalid Input"), t("Please select a tag or enter a new one."))
            return
        if not description:
            QMessageBox.warning(self, t("Invalid Input"), t("Please enter a description."))
            return

        self.item = IC.IsolationItem(tag=tag, description=description, state=self.stateCombo.currentText())
        lockNum = self._originalItem.lock_num if self._originalItem else self.boxLockNum.text()
        lockBoxNum = self._originalItem.lock_box_num if self._originalItem else self.boxLockBoxNum.text()
        self.item.setLockNum(lockNum).setLockBoxNum(lockBoxNum)
        super().accept()
