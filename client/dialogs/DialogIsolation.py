"""Dialog for creating a PTW's declarative required-isolation entry (type/tag/description)."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QFormLayout, QComboBox, QTextEdit, QDialogButtonBox, QMessageBox

from models.PTW import PTW
from models.Isolation import Isolation
from widgets.SearchableComboBox import SearchableComboBox
from helper.i18n import t


class DialogIsolation(QDialog):
    """Create a single declarative Isolation record (type, tag, description) to add
    to a PTW's list of expected isolations. Carries no runtime/linkage state -
    that lives on IC instead."""

    def __init__(self, parent=None):
        """Build the form: a type combo, a tag combo scoped to the chosen type, and a description field."""
        super().__init__(parent)
        self.setWindowTitle(t("New Isolation"))
        self.setModal(True)
        self.isolation = None

        lyt = QFormLayout()
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.typeCombo = QComboBox()
        self.boxTag = SearchableComboBox()
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 4 + 10)

        for typ in Isolation.Types:
            self.typeCombo.addItem(t(typ), typ.value)

        self._tagsForType = {typ.value: [] for typ in Isolation.Types}
        for iso in PTW.ALL_ISOLATIONS.values():
            self._tagsForType[iso.type.value].append(iso.tag)

        self.typeCombo.currentTextChanged.connect(self._on_type_changed)
        self.boxTag.itemSelected.connect(self._on_tag_selected)
        self._on_type_changed()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        lyt.addRow(t("Type:"), self.typeCombo)
        lyt.addRow(t("Tag:"), self.boxTag)
        lyt.addRow(t("Description:"), self.boxDescription)
        lyt.addWidget(btns)

    def _on_type_changed(self, _=None):
        """Restrict the tag combo's choices to tags belonging to the newly selected type.

        Triggered by the type combo's currentTextChanged signal (and once directly
        from __init__ to seed the initial tag list).
        """
        self.boxTag.setItems(self._tagsForType[self.typeCombo.currentData()])

    def _on_tag_selected(self, tag):
        """Autofill (or clear) the description to match the selected tag's library entry.

        Triggered by the tag combo box's itemSelected signal.
        """
        isolation = PTW.ALL_ISOLATIONS.get(tag)
        self.boxDescription.setText(isolation.description if isolation else '')

    def getIsolation(self):
        """Return the Isolation built on accept, or None if not yet accepted."""
        return self.isolation

    def accept(self):
        """Validate the form and build the resulting Isolation, then close the dialog.

        Triggered by the OK button. Requires a tag and description to be set.
        """
        type = self.typeCombo.currentData()
        tag = self.boxTag.currentText()
        description = self.boxDescription.toPlainText()

        if not tag:
            QMessageBox.warning(self, t("Invalid Input"), t("Please select a tag or enter a new one."))
            return
        if not description:
            QMessageBox.warning(self, t("Invalid Input"), t("Please enter a description."))
            return

        self.isolation = Isolation(type=type, tag=tag, description=description)
        super().accept()
