"""Duplicate-tag warning dialog, shown to Issuing before approving/confirming an IC
whose tag(s) are already isolated or in progress elsewhere (see
MainWindow._confirmNoTagConflicts/_findTagConflicts). One row per (tag, conflicting
IC) pair, each with its own View button - a single dialog-wide "view" action would be
ambiguous whenever more than one different IC is named."""

from functools import partial

from PyQt6.QtGui import QBrush
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
                              QHeaderView, QAbstractItemView, QPushButton, QDialogButtonBox)

from models.Isolation import IC
from helper.i18n import t


class DialogTagConflictWarning(QDialog):
    """Lists every (tag, conflicting IC) pair for `ic`, each row wired to its own
    View button, plus Approve Anyway / Cancel to resolve the warning."""

    def __init__(self, parent, ic: IC, conflicts: dict, viewICFn):
        """Build the warning table from `conflicts` ({tag: [otherIc, ...]}, as
        returned by MainWindow._findTagConflicts) and wire each row's View
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

        self.tbl = QTableWidget()
        summeryLabels = [t('Tag'), t('Status'), t('IC#'), '']
        self.tbl.setColumnCount(len(summeryLabels))
        self.tbl.setHorizontalHeaderLabels(summeryLabels)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tbl.verticalHeader().hide()
        self.tbl.setAlternatingRowColors(True)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setRowCount(len(rows))
        for r, (tag, otherIc) in enumerate(rows):
            self.tbl.setItem(r, 0, QTableWidgetItem(tag))
            statusItem = QTableWidgetItem(t(otherIc.getStatus().value))
            statusItem.setBackground(QBrush(otherIc.backgroundColor()))
            statusItem.setForeground(QBrush(otherIc.foregroundColor()))
            self.tbl.setItem(r, 1, statusItem)
            self.tbl.setItem(r, 2, QTableWidgetItem(str(otherIc.id)))
            btnView = QPushButton(t('View'))
            btnView.clicked.connect(partial(viewICFn, r, otherIc))
            self.tbl.setCellWidget(r, 3, btnView)
        lyt.addWidget(self.tbl)

        btns = QDialogButtonBox()
        btnCancel = btns.addButton(t('Cancel'), QDialogButtonBox.ButtonRole.RejectRole)
        btns.addButton(t('Approve Anyway'), QDialogButtonBox.ButtonRole.AcceptRole)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btnCancel.setDefault(True)
        lyt.addWidget(btns)

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.5))
