"""Coordinator's "Define PSIC Terms" dialog.

Shown as part of Coordinator *approving* a PSIC IC's own stage in its approval chain (see
MainWindow.acceptIC) - there is no separate "define terms" action outside the chain. Collects
the PSIC reasons, optional MOC number, and the three required description fields; the caller
(MainWindow.acceptIC) submits them together with the approval itself via
ClientRequests.updateApprovalIC(..., psic_terms=...).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGridLayout,
                              QComboBox, QLineEdit, QTextEdit, QCheckBox, QLabel,
                              QMessageBox, QPushButton, QDialogButtonBox)
import qtawesome as qta

from models.Isolation import IC, PSIC_REASONS, PSIC_REASON_GRID_COLS, PSIC_TAG_SAMPLES
from helper.i18n import t


class DialogDefinePsicTerms(QDialog):
    """Plain (non-tabbed) dialog collecting a PSIC's required terms: at least one reason,
    an optional MOC number, and the three description fields (system to be isolated, method
    of isolation, control measure/mitigation) - the same fields `DialogIC`'s PSIC tab used to
    let the requestor fill in at creation, now filled in by Coordinator instead, as part of
    their own approval."""

    def __init__(self, parent, ic: IC):
        """Build the form, pre-filled from any PSIC fields already on `ic` (normally blank -
        nothing sets them before this point any more), with the same tag-autofill convenience
        `DialogIC`'s PSIC tab has."""
        super().__init__(parent)
        self.ic = ic
        self.setWindowTitle(t("Define PSIC Terms") + f" — IC #{ic.id}")
        self.setModal(True)

        lyt = QVBoxLayout(self)
        lyt.addWidget(QLabel(t("Define the PSIC terms for IC #{0} - required before it can proceed to PDH/PGM/SOD/DFGM.").format(ic.id)))

        formOther = QFormLayout()
        formOther.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.boxMocNumber = QLineEdit(ic.psic_moc_number or '')
        self.boxMocNumber.setPlaceholderText(t("MOC # (if applicable)"))
        self.tagCombo = QComboBox()
        self.tagCombo.addItems([item.tag for item in ic.items])
        self.btnAutofill = QPushButton(qta.icon("mdi6.auto-fix"), t("Autofill from Tag"))
        self.btnAutofill.clicked.connect(self._autofillFromTag)
        lytAutofill = QHBoxLayout()
        lytAutofill.addWidget(self.tagCombo, stretch=1)
        lytAutofill.addWidget(self.btnAutofill)
        formOther.addRow(t("MOC Number:"), self.boxMocNumber)
        formOther.addRow(t("Autofill from Tag:"), lytAutofill)
        lyt.addLayout(formOther)

        lyt.addSpacing(20)

        lyt.addWidget(QLabel(f"<b>{t('PSIC Reason(s)')}</b>"))
        gridReasons = QGridLayout()
        psicReasons = set(ic.psic_reasons or [])
        self.reasonCheckboxes: dict[str, QCheckBox] = {}
        for i, reason in enumerate(PSIC_REASONS):
            btn = QCheckBox(t(reason))
            btn.setChecked(reason in psicReasons)
            self.reasonCheckboxes[reason] = btn
            gridReasons.addWidget(btn, i // PSIC_REASON_GRID_COLS, i % PSIC_REASON_GRID_COLS)
        lyt.addLayout(gridReasons)

        lyt.addSpacing(20)

        lytFields = QHBoxLayout()

        def addFieldColumn(labelText: str, initialText: str) -> QTextEdit:
            col = QVBoxLayout()
            col.addWidget(QLabel(t(labelText)), 0, Qt.AlignmentFlag.AlignTop)
            box = QTextEdit(initialText)
            box.setMinimumHeight(box.fontMetrics().lineSpacing() * 6 + 10)
            box.setTabChangesFocus(True)
            col.addWidget(box, 1)
            lytFields.addLayout(col)
            return box

        self.boxSystemDescription = addFieldColumn("System to be Isolated:", ic.psic_system_description or '')
        self.boxIsolationMethod = addFieldColumn("Method of Isolation:", ic.psic_isolation_method or '')
        self.boxControlMeasures = addFieldColumn("Control Measure / Mitigation:", ic.psic_control_measures or '')
        lyt.addLayout(lytFields, stretch=1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

        self.setMinimumSize(800, 500)

    def _autofillFromTag(self):
        """Handle the Autofill from Tag button click: look up the selected tag in the
        client-side PSIC_TAG_SAMPLES placeholder data and, if found, check/uncheck the
        reason checkboxes to match and fill the three description fields from it
        (overwriting any text already there) - same behavior as DialogIC's own version."""
        tag = self.tagCombo.currentText()
        if not tag:
            QMessageBox.information(self, t("No Tag Selected"), t("Add an isolation item first, then pick its tag to autofill from."))
            return
        sample = PSIC_TAG_SAMPLES.get(tag)
        if not sample:
            QMessageBox.information(self, t("No Sample Data"), t("No sample isolation data is defined yet for tag '{0}'. Please fill in the fields manually.").format(tag))
            return
        sampleReasons = set(sample.get('reasons', []))
        for reason, btn in self.reasonCheckboxes.items():
            btn.setChecked(reason in sampleReasons)
        self.boxSystemDescription.setText(sample['system_description'])
        self.boxIsolationMethod.setText(sample['isolation_method'])
        self.boxControlMeasures.setText(sample['control_measures'])

    def accept(self):
        """Validate at least one reason and all three description fields are filled in before
        closing - same requirement `DialogIC.accept()` used to enforce at creation time."""
        if not any(btn.isChecked() for btn in self.reasonCheckboxes.values()):
            QMessageBox.warning(self, "Invalid Input", "Please select at least one PSIC reason.")
            return
        if not self.boxSystemDescription.toPlainText().strip() or not self.boxIsolationMethod.toPlainText().strip() or not self.boxControlMeasures.toPlainText().strip():
            QMessageBox.warning(self, "Invalid Input", "Please fill in the system to be isolated, method of isolation, and control measure/mitigation for this PSIC.")
            return
        super().accept()

    def getTerms(self) -> dict:
        """Return the collected PSIC terms as a plain dict, ready to send as
        ClientRequests.updateApprovalIC's psic_terms argument."""
        return {
            'psic_reasons': [reason for reason, btn in self.reasonCheckboxes.items() if btn.isChecked()],
            'psic_moc_number': self.boxMocNumber.text().strip(),
            'psic_system_description': self.boxSystemDescription.toPlainText().strip(),
            'psic_isolation_method': self.boxIsolationMethod.toPlainText().strip(),
            'psic_control_measures': self.boxControlMeasures.toPlainText().strip(),
        }
