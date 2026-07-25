from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QComboBox, QLineEdit, QTextEdit, QDialogButtonBox, QMessageBox

from PTWData import PTWData
from Isolation import IC
from SearchableComboBox import SearchableComboBox


class DialogIsolationItem(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Isolation Item")
        self.setModal(True)
        self.item = None

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.boxTag = SearchableComboBox()
        self.boxTag.setItems(list(PTWData.ALL_ISOLATIONS.keys()))
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 3 + 10)
        self.stateCombo = QComboBox()
        self.stateCombo.addItems([s.value for s in IC.IsolationItem.States])
        self.boxLockNum = QLineEdit()
        self.boxLockNum.setReadOnly(True)
        self.boxLockNum.setPlaceholderText("Set by isolator on confirmation")
        self.boxLockBoxNum = QLineEdit()
        self.boxLockBoxNum.setReadOnly(True)
        self.boxLockBoxNum.setPlaceholderText("Set by isolator on confirmation")

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

    def _on_tag_selected(self, tag):
        isolation = PTWData.ALL_ISOLATIONS.get(tag)
        self.boxDescription.setText(isolation.description if isolation else '')

    def getItem(self):
        return self.item

    def accept(self):
        tag = self.boxTag.currentText()
        description = self.boxDescription.toPlainText()

        if not tag:
            QMessageBox.warning(self, "Invalid Input", "Please select a tag or enter a new one.")
            return
        if not description:
            QMessageBox.warning(self, "Invalid Input", "Please enter a description.")
            return

        self.item = IC.IsolationItem(tag=tag, description=description, state=self.stateCombo.currentText())
        self.item.setLockNum(self.boxLockNum.text()).setLockBoxNum(self.boxLockBoxNum.text())
        super().accept()
