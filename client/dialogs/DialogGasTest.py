"""Gas Tester's "Record Gas Test" dialog.

Shown when a Gas Tester records an initial gas test reading for one or more PTWs at once
(see MainWindow.recordGasTestPTW) - one row per PTW.GAS_TEST_TYPES entry, each a required
percentage reading, plus an optional comment. Entered once regardless of how many PTWs are
selected - one reading recorded once is credited to every one of them, since they were
tested together. The caller submits the collected readings for the whole selection via
ClientRequests.recordGasTestPTW; username/timestamp are stamped server-side.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox, QTextEdit,
                              QLabel, QMessageBox, QDialogButtonBox)

from models.PTW import PTW
from helper.i18n import t


class DialogGasTest(QDialog):
    """Plain (non-tabbed) dialog collecting one gas-percentage reading per
    PTW.GAS_TEST_TYPES entry, plus an optional comment, for a whole selection of PTWs at
    once. accept() requires every reading to actually be entered (not left at its
    default) before closing."""

    def __init__(self, parent, ptws: list[PTW]):
        """Build the form: one required percentage spinbox per gas type, and an
        optional comment field, labeled with every selected PTW's id."""
        super().__init__(parent)
        self.ptws = ptws
        ids = ', '.join(f"#{ptw.id}" for ptw in ptws)
        self.setWindowTitle(t("Record Gas Test") + f" — PTW {ids}")
        self.setModal(True)

        lyt = QVBoxLayout(self)
        if len(ptws) == 1:
            lbl = QLabel(t("Record the initial gas test readings for PTW#{0}.").format(ptws[0].id))
        else:
            lbl = QLabel(t("Record the same initial gas test readings for PTWs {0}.").format(ids))
        lbl.setWordWrap(True)
        lyt.addWidget(lbl)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.gasBoxes: dict[str, QDoubleSpinBox] = {}
        for gas in PTW.GAS_TEST_TYPES:
            box = QDoubleSpinBox()
            # -1 is a sentinel "not entered yet" value, distinct from a real (and for
            # some gases, e.g. H2S, the desired) reading of 0.0 - only shown as such via
            # specialValueText while the box sits at its minimum.
            box.setRange(-1.0, 100.0)
            box.setDecimals(2)
            box.setSingleStep(0.1)
            box.setSuffix(" %")
            box.setSpecialValueText(t("Not entered"))
            box.setValue(-1.0)
            self.gasBoxes[gas] = box
            form.addRow(t(gas) + ":", box)
        lyt.addLayout(form)

        lyt.addWidget(QLabel(t("Comment (optional):")))
        self.boxComment = QTextEdit()
        self.boxComment.setTabChangesFocus(True)
        self.boxComment.setMinimumHeight(self.boxComment.fontMetrics().lineSpacing() * 3 + 10)
        lyt.addWidget(self.boxComment)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

        self.setMinimumWidth(400)

    def accept(self):
        """Require every gas reading to have actually been entered (left at its
        minimum -1 "Not entered" sentinel is treated as not filled in) before closing."""
        if any(box.value() < 0.0 for box in self.gasBoxes.values()):
            QMessageBox.warning(self, t("Invalid Input"), t("Please enter a reading for every gas."))
            return
        super().accept()

    def getReadings(self) -> list[dict]:
        """Return the collected readings as [{'gas': ..., 'percentage': ...}, ...],
        ready to send as ClientRequests.recordGasTestPTW's readings argument."""
        return [{'gas': gas, 'percentage': box.value()} for gas, box in self.gasBoxes.items()]

    def getComment(self) -> str:
        """Return the optional comment, or None if left blank."""
        return self.boxComment.toPlainText().strip() or None
