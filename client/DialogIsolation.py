from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QComboBox, QTextEdit, QDialogButtonBox, QMessageBox

from PTWData import Isolation, PTWData
from SearchableComboBox import SearchableComboBox


class DialogIsolation(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Isolation")
        self.setModal(True)
        self.isolation = None

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.typeCombo = QComboBox()
        self.boxTag = SearchableComboBox()
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 4 + 10)

        self.typeCombo.addItems([t.value for t in Isolation.Types])

        self._tagsForType = {t.value: [] for t in Isolation.Types}
        for iso in PTWData.ALL_ISOLATIONS.values():
            self._tagsForType[iso.type.value].append(iso.tag)

        self.typeCombo.currentTextChanged.connect(self._on_type_changed)
        self.boxTag.itemSelected.connect(self._on_tag_selected)
        self._on_type_changed()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        lyt.addRow("Type:", self.typeCombo)
        lyt.addRow("Tag:", self.boxTag)
        lyt.addRow("Description:", self.boxDescription)
        lyt.addWidget(btns)

    def _on_type_changed(self, _=None):
        self.boxTag.setItems(self._tagsForType[self.typeCombo.currentText()])

    def _on_tag_selected(self, tag):
        isolation = PTWData.ALL_ISOLATIONS.get(tag)
        self.boxDescription.setText(isolation.description if isolation else '')

    def getIsolation(self):
        return self.isolation

    def accept(self):
        type = self.typeCombo.currentText()
        tag = self.boxTag.currentText()
        description = self.boxDescription.toPlainText()

        if not tag:
            QMessageBox.warning(self, "Invalid Input", "Please select a tag or enter a new one.")
            return
        if not description:
            QMessageBox.warning(self, "Invalid Input", "Please enter a description.")
            return

        self.isolation = Isolation(type=type, tag=tag, description=description)
        super().accept()
