"""Read-only "equipment/tag" detail dialog: shows one tag's aggregated summary
plus every IC that has ever referenced it, each with its own View/Print action.

Opened from TableEquipmentStatus's row-level "View" option - a tag's aggregated
row alone doesn't say which of possibly several linked ICs (an active one and
older closed ones, say) a user meant when asking to view or print, so that
choice is made here instead, one row per linked IC.
"""

from functools import partial

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont, QBrush, QAction
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QFormLayout, QLabel, QTableWidget,
                              QTableWidgetItem, QHeaderView, QAbstractItemView,
                              QDialogButtonBox, QMenu)

from models.Isolation import IC
from GlobalData import globalData
from helper.i18n import t


class DialogEquipmentStatus(QDialog):
    """Shows one tag's current isolation summary (from whichever linked IC is
    currently "live" - see TableEquipmentStatus._aggregate) and a table of
    every IC that has ever referenced the tag, each row wired to the caller's
    own View/Print handlers (MainWindow.viewIC/printIC)."""

    def __init__(self, parent, row: 'TableEquipmentStatus._EquipmentRow', viewICFn, printICFn):
        """Build the summary header from `row` and the linked-ICs table, one
        row per (IC, IsolationItem) pair in `row.candidates` (most-live
        first), wiring `viewICFn`/`printICFn` as each row's View/Print action.
        """
        super().__init__(parent)
        self._viewICFn = viewICFn
        self._printICFn = printICFn
        self._candidates = row.candidates  # list[(IC, IC.IsolationItem)], most-live first

        self.setWindowTitle(t("Equipment — {0}").format(row.tag))
        lyt = QVBoxLayout(self)

        currentIc, currentItem = self._candidates[0]

        form = QFormLayout()
        form.addRow(t("Tag:"), QLabel(row.tag))
        form.addRow(t("Description:"), QLabel(currentItem.description or ''))
        lblStatus = QLabel(t(currentIc.getStatus().value))
        lblStatus.setFont(QFont("Helvetica", 10, QFont.Weight.Bold))
        form.addRow(t("Current Status:"), lblStatus)
        form.addRow(t("Location:"), QLabel(currentIc.location or ''))
        form.addRow(t("Execution Dept.:"), QLabel(currentIc.execution_department or ''))
        form.addRow(t("Lock #:"), QLabel(currentItem.lock_num or ''))
        form.addRow(t("Lock Box #:"), QLabel(currentItem.lock_box_num or ''))
        lyt.addLayout(form)

        lblLinked = QLabel(t("Linked ICs:"))
        lblLinked.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        lyt.addWidget(lblLinked)

        self.summeryLabels = [t('IC#'), t('Status'), t('Type'), t('Requestor'), t('Description'), t('Lock #'), t('Lock Box #')]
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.verticalHeader().hide()
        self.tbl.setAlternatingRowColors(True)
        # Not sortable - row order must stay in lockstep with self._candidates so a
        # double-click/context-menu row index resolves to the right IC (a handful of
        # linked ICs per tag doesn't need re-sorting anyway).
        self.tbl.setSortingEnabled(False)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._showContextMenu)
        self.tbl.cellDoubleClicked.connect(self._onDoubleClicked)
        lyt.addWidget(self.tbl)

        for ic, item in self._candidates:
            r = self.tbl.rowCount()
            self.tbl.insertRow(r)
            user = globalData.allUsers.get(ic.requestor)
            requestorName = user.getName() if user else (ic.requestor or '')
            values = [
                str(ic.id), t(ic.getStatus().value), str(ic.type or ''), requestorName,
                item.description or '', item.lock_num or '', item.lock_box_num or '',
            ]
            for c, v in enumerate(values):
                cell = QTableWidgetItem(v)
                cell.setBackground(QBrush(ic.backgroundColor()))
                cell.setForeground(QBrush(ic.foregroundColor()))
                self.tbl.setItem(r, c, cell)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.6))
            self.setMinimumHeight(int(parent.height() * 0.5))

    def _icAt(self, row: int) -> IC:
        """Return the IC backing table row `row`."""
        return self._candidates[row][0]

    def _onDoubleClicked(self, row: int, col: int):
        """Slot for cellDoubleClicked: open the double-clicked row's IC via
        the caller's View handler."""
        self._viewICFn(row, self._icAt(row))

    def _showContextMenu(self, pos: QPoint):
        """Slot for customContextMenuRequested: show a right-click menu with
        View/Print actions for the clicked row's IC."""
        rowIndex = self.tbl.indexAt(pos)
        if not rowIndex.isValid():
            return
        row = rowIndex.row()
        ic = self._icAt(row)
        menu = QMenu(self.tbl)
        actView = QAction(t('View'), self.tbl)
        actView.triggered.connect(partial(self._viewICFn, row, ic))
        menu.addAction(actView)
        actPrint = QAction(t('Print'), self.tbl)
        actPrint.triggered.connect(partial(self._printICFn, row, ic))
        menu.addAction(actPrint)
        menu.exec(self.tbl.mapToGlobal(pos))
