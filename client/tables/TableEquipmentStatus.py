"""Equipment (tag) status table: aggregates every unique tag across all ICs'
isolation items into one row showing its description, current isolation
status, and every IC that has ever referenced it. Read-only overview for
Issuing/Coordinator/Manager - see MainWindow.refreshICsGUI/_applyICEvent for
how it's kept in sync with the IC cache. Tags aren't a normalized entity
anywhere else in the system (see models.Isolation.IC.items), so this table is
the aggregation layer: it doesn't read from a tags table, it builds one in
memory from every IC's embedded items list."""

from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QAbstractItemView, QHeaderView, QFrame, QMenu)
from PyQt6.QtGui import QFont, QBrush, QAction
from typing import Iterable
from functools import partial
import qtawesome as qta

from models.Isolation import IC
from widgets.CheckableComboBox import CheckableComboBox
from helper.i18n import t

_TRANSLATABLE_FIELDS = {'status'}

# Lower sorts first: when the same tag appears on more than one IC (e.g. a closed
# historical IC and a newly requested one on the same equipment), the row shows
# whichever IC is most "live" - ties (same priority) broken by highest IC id, i.e.
# the most recently created one.
_STATUS_PRIORITY = {
    IC.Status.ACTIVE: 0,
    IC.Status.ISOLATE_CONFIRMING: 1,
    IC.Status.PENDING: 1,
    IC.Status.DEISOLATE_CONFIRMING: 1,
    IC.Status.CLOSING: 1,
    IC.Status.SANCTIONED: 1,
    IC.Status.APPROVED: 2,
    IC.Status.RETURNED: 2,
    IC.Status.REQUESTED: 2,
    IC.Status.CLOSED: 3,
}


class _EquipmentRow:
    """One aggregated tag: `candidates` holds every (IC, IsolationItem) pair
    that has ever referenced the tag, sorted most-live first (see
    _STATUS_PRIORITY) - `ic`/`item` expose that first, "current" pair for the
    table row's own display, while `candidates` is kept in full for
    DialogEquipmentStatus to list every linked IC."""

    def __init__(self, tag: str, candidates: list):
        self.tag = tag
        self.candidates = candidates  # list[(IC, IC.IsolationItem)], most-live first

    @property
    def ic(self) -> IC:
        return self.candidates[0][0]

    @property
    def item(self) -> 'IC.IsolationItem':
        return self.candidates[0][1]

    @property
    def allIcIds(self) -> list:
        return sorted({c[0].id for c in self.candidates}, key=lambda i: str(i))


class TableEquipmentStatus(QWidget):
    """Reusable read-only table listing every tag seen across all ICs, mirroring
    TableICs' filter bar and context-menu structure but with no CRUD actions of
    its own - registered options receive the row's full aggregated data (an
    _EquipmentRow, exposing every linked IC via `.candidates`), typically to open
    DialogEquipmentStatus rather than a single IC directly."""

    def __init__(self, parent, loggedUser, label: str):
        """Build the labeled table and filter bar for the aggregated tag list."""
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.rowsData: list[_EquipmentRow] = []
        self.loggedUser = loggedUser
        self.options = []

        self.summeryLabels = [t('Tag'), t('Description'), t('Status'), t('Location'), t('Execution Dept.'), t('Lock #'), t('Lock Box #'), t('Linked ICs')]
        self.summeryFields = ['tag', 'description', 'status', 'location', 'execution_department', 'lock_num', 'lock_box_num', 'linked_ics']

        lblLyt = QHBoxLayout()
        lblLyt.setContentsMargins(10, 0, 10, 0)
        self.label = label
        lbl = QLabel(label)
        lbl.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lblLyt.addStretch()
        lblLyt.addWidget(lbl)

        self._filterBtn = QPushButton(qta.icon('fa6s.filter'), "")
        self._filterBtn.setToolTip(t("Filter"))
        self._filterBtn.setIconSize(QSize(32, 32))
        self._filterBtn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filterBtn.setStyleSheet("""
            QPushButton { background: transparent; border: none; padding: 6px; border-radius: 6px; }
            QPushButton:hover { background: rgba(128, 128, 128, 0.15); }
            QPushButton:pressed { background: rgba(128, 128, 128, 0.30); }
            QPushButton:checked { background: palette(highlight); }
            QPushButton:checked:hover { background: palette(link); }
        """)
        self._filterBtn.setCheckable(True)
        self._filterBtn.toggled.connect(self._toggleFilters)
        lblLyt.addStretch()
        lblLyt.addWidget(self._filterBtn)

        self._filterBar = QWidget()
        filterBarLayout = QHBoxLayout(self._filterBar)
        filterBarLayout.setContentsMargins(0, 0, 0, 0)
        filterBarLayout.setSpacing(0)
        self._filterCombos = []
        for _ in self.summeryLabels:
            combo = CheckableComboBox()
            combo.filterChanged.connect(self._applyFilters)
            filterBarLayout.addWidget(combo)
            self._filterCombos.append(combo)
        self._filterBar.setVisible(False)

        self.setLayout(lyt)
        self.setAutoFillBackground(False)
        lyt.addLayout(lblLyt)
        lyt.addWidget(self._filterBar)
        lyt.addWidget(self.tbl)

        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.cellDoubleClicked.connect(self.doubleClickHandler)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self.showContextMenu)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setStyleSheet("QTableWidget { background: transparent; }")
        self.tbl.viewport().setAutoFillBackground(False)
        self.tbl.verticalHeader().hide()
        self.tbl.setFrameShape(QFrame.Shape.NoFrame)
        self.tbl.horizontalHeader().sectionResized.connect(self._syncFilterWidths)
        self.tbl.horizontalHeader().sortIndicatorChanged.connect(self._onSorted)

    def _toggleFilters(self, checked):
        """Slot for the filter button's toggled signal: show/hide the filter
        bar, (re)populating and applying filters when shown, or clearing all
        row hiding when hidden."""
        self._filterBar.setVisible(checked)
        if checked:
            self._populateFilters()
            self._syncFilterWidths()
            self._applyFilters()
        else:
            self._showAllRows()

    def _cellFilterText(self, col: int, item: QTableWidgetItem) -> str:
        """Return the value to filter/compare on for a cell: its stashed
        UserRole data if present (translatable columns), otherwise its
        display text."""
        userData = item.data(Qt.ItemDataRole.UserRole)
        return userData if userData is not None else item.text()

    def _populateFilters(self):
        """Rebuild each column's filter combo options from the table's current
        cell values, preserving any existing checked selections."""
        col_values = [set() for _ in self.summeryLabels]
        for row in range(self.tbl.rowCount()):
            for col in range(len(self.summeryLabels)):
                item = self.tbl.item(row, col)
                if item:
                    col_values[col].add(self._cellFilterText(col, item))
        for col, combo in enumerate(self._filterCombos):
            display = t if self.summeryFields[col] in _TRANSLATABLE_FIELDS else None
            combo.setItems(col_values[col], preserve_selection=True, display=display)

    def _syncFilterWidths(self):
        """Resize each filter combo to match its column's current header
        width, keeping the filter bar aligned with the table columns."""
        if not self._filterBar.isVisible():
            return
        header = self.tbl.horizontalHeader()
        for i, combo in enumerate(self._filterCombos[:-1]):
            combo.setFixedWidth(header.sectionSize(i))
        self._filterCombos[-1].setMinimumWidth(header.sectionSize(len(self._filterCombos) - 1))

    def _applyFilters(self):
        """Hide any row that doesn't match every currently-checked filter
        combo; called whenever a filter combo's selection changes."""
        active = [
            (col, combo.checkedItems())
            for col, combo in enumerate(self._filterCombos)
            if combo.isFiltering()
        ]
        for row in range(self.tbl.rowCount()):
            hide = any(
                (item := self.tbl.item(row, col)) is not None and self._cellFilterText(col, item) not in allowed
                for col, allowed in active
            )
            self.tbl.setRowHidden(row, hide)

    def _showAllRows(self):
        """Unhide every row in the table."""
        for row in range(self.tbl.rowCount()):
            self.tbl.setRowHidden(row, False)

    def _onSorted(self):
        """Slot for the header's sortIndicatorChanged signal: keep `rowsData`
        in row order after a sort (row indices are used to resolve a
        double-click/context-menu target) and reapply active filters."""
        self._syncRowsData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def _syncRowsData(self):
        """Reorder `rowsData` to match the table's current (possibly
        user-sorted) row order, keyed by the Tag column's text."""
        tagToRow = {r.tag: r for r in self.rowsData}
        self.rowsData = [tagToRow[self.tbl.item(r, 0).text()] for r in range(self.tbl.rowCount())]

    def _makeCell(self, col: int, value: str) -> QTableWidgetItem:
        """Build the QTableWidgetItem for one cell, translating fixed-vocabulary
        columns for display while keeping the real value in UserRole for
        filtering/sorting."""
        if self.summeryFields[col] in _TRANSLATABLE_FIELDS:
            cell = QTableWidgetItem(t(value))
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        return QTableWidgetItem(value)

    @staticmethod
    def _aggregate(ics: dict) -> list[_EquipmentRow]:
        """Flatten every IC's isolation items into one row per unique tag,
        picking whichever IC is currently most "live" for tags that appear on
        more than one IC (see _STATUS_PRIORITY)."""
        byTag: dict[str, list] = {}
        for ic in ics.values():
            for item in ic.items:
                if not item.tag:
                    continue
                byTag.setdefault(item.tag, []).append((ic, item))

        def sortKey(pair):
            ic, _ = pair
            priority = _STATUS_PRIORITY.get(ic.getStatus(), 2)
            try:
                icId = int(ic.id)
            except (TypeError, ValueError):
                icId = 0
            return (priority, -icId)

        rows = [_EquipmentRow(tag, sorted(candidates, key=sortKey)) for tag, candidates in byTag.items()]
        rows.sort(key=lambda r: r.tag.casefold())
        return rows

    def rowToRecord(self, row: _EquipmentRow) -> list:
        """Convert an aggregated row into its list of display strings."""
        values = {
            'tag': row.tag,
            'description': row.item.description,
            'status': row.ic.getStatus().value,
            'location': row.ic.location,
            'execution_department': row.ic.execution_department,
            'lock_num': row.item.lock_num,
            'lock_box_num': row.item.lock_box_num,
            'linked_ics': ', '.join(f"#{i}" for i in row.allIcIds),
        }
        return [str(values[f]) if values[f] is not None else '' for f in self.summeryFields]

    def refresh(self, ics: dict):
        """Rebuild the entire table from the given IC cache."""
        self.rowsData = self._aggregate(ics)
        self.tbl.setSortingEnabled(False)
        self.tbl.clearContents()
        self.tbl.setRowCount(0)
        for row in self.rowsData:
            self._addRowToGUI(row)
        self.tbl.setSortingEnabled(True)
        self._syncRowsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def _addRowToGUI(self, row: _EquipmentRow):
        """Append one table row for `row`, colored by its current IC's status."""
        data = self.rowToRecord(row)
        r = self.tbl.rowCount()
        self.tbl.insertRow(r)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            cell.setBackground(QBrush(row.ic.backgroundColor()))
            cell.setForeground(QBrush(row.ic.foregroundColor()))
            self.tbl.setItem(r, i, cell)

    def addOption(self, option):
        """Register a single context-menu option."""
        self.options.append(option)

    def addOptions(self, options: Iterable):
        """Register multiple context-menu options at once."""
        self.options.extend(options)

    def clear(self):
        """Remove all rows and cached data, and reset every filter combo back
        to its empty "Select All" state."""
        self.tbl.clearContents()
        self.rowsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def doubleClickHandler(self, row, col):
        """Slot for cellDoubleClicked: invoke the first registered menu
        option's handler on the double-clicked row's aggregated data."""
        if len(self.options) > 0:
            self.options[0].fun(row, self.rowsData[row])

    def showContextMenu(self, pos: QPoint):
        """Slot for customContextMenuRequested: build and show a right-click
        menu of the registered options that pass their `visibleFor` check for
        this row's aggregated data (if any)."""
        rowIndex = self.tbl.indexAt(pos)
        if not rowIndex.isValid():
            return
        row = rowIndex.row()
        rowData = self.rowsData[row]
        menu = QMenu(self.tbl)
        for option in self.options:
            if option.visibleFor is not None and not option.visibleFor(rowData):
                continue
            action = QAction(option.icn, option.lbl, self.tbl)
            menu.addAction(action)
            action.triggered.connect(partial(option.fun, row, rowData))
        menu.exec(self.tbl.mapToGlobal(pos))
