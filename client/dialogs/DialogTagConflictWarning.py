"""Duplicate-tag warning dialog, shown to Issuing before approving/confirming an IC
whose tag(s) are already isolated or in progress elsewhere (see
MainWindow._confirmNoTagConflicts/_findTagConflicts). One line per (tag, conflicting
IC) pair, each with its own right-aligned View button - a single dialog-wide "view"
action would be ambiguous whenever more than one different IC is named."""

from functools import partial

from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDialogButtonBox
import qtawesome as qta

from models.Isolation import IC
from helper.i18n import t


class DialogTagConflictWarning(QDialog):
    """Lists every (tag, conflicting IC) pair for `ic`, one line each with its own
    View button, plus Approve Anyway / Cancel to resolve the warning."""

    def __init__(self, parent, ic: IC, conflicts: dict, viewICFn):
        """Build the warning lines from `conflicts` ({tag: [otherIc, ...]}, as
        returned by MainWindow._findTagConflicts) and wire each line's View
        button to `viewICFn(row, otherIc)` (MainWindow.viewIC)."""
        super().__init__(parent)
        self.setWindowTitle(t('Possible Duplicate Isolation'))

        lyt = QVBoxLayout(self)
        lbl = QLabel(
            t('IC #{0} isolates tag(s) already isolated or in progress on another IC. '
              'Consider linking the existing IC to this PTW instead of approving a '
              'duplicate isolation:').format(ic.id)
        )
        lbl.setWordWrap(True)
        lyt.addWidget(lbl)

        rows = [(tag, otherIc) for tag, otherIcs in conflicts.items() for otherIc in otherIcs]
        self.viewButtons: list[QPushButton] = []
        for r, (tag, otherIc) in enumerate(rows):
            rowLyt = QHBoxLayout()
            rowLbl = QLabel(t('Tag "{0}" — already {1} on IC #{2}').format(tag, t(otherIc.getStatus().value), otherIc.id))
            rowLyt.addWidget(rowLbl)
            rowLyt.addStretch()
            btnView = QPushButton(qta.icon('fa6.eye'), t('View'))
            btnView.clicked.connect(partial(viewICFn, r, otherIc))
            rowLyt.addWidget(btnView)
            self.viewButtons.append(btnView)
            lyt.addLayout(rowLyt)

        btns = QDialogButtonBox()
        btnCancel = btns.addButton(t('Cancel'), QDialogButtonBox.ButtonRole.RejectRole)
        btns.addButton(t('Approve Anyway'), QDialogButtonBox.ButtonRole.AcceptRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btnCancel.setDefault(True)
        lyt.addWidget(btns)

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.5))
