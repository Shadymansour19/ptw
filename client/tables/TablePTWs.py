"""PTW list table widget: one instance per status tab, with per-column filters,
a right-click context menu of role-supplied actions (e.g. Excel export), and
double-click drill-down into a PTW."""

from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QAbstractItemView, QHeaderView, QFrame,
                              QMenu, QMessageBox)
from PyQt6.QtGui import QFont, QBrush, QAction
from typing import Iterable
from functools import partial
import qtawesome as qta

from network.clientRequests import ClientRequests
from models.PTW import PTW
from widgets.CheckableComboBox import CheckableComboBox
from GlobalData import globalData
from helper.i18n import t


# Fields whose stored value is a fixed, translatable vocabulary word (PTW type,
# department, location, the fast-track Yes/No) rather than free text a user typed
# (name, description, date, id) - these get a t()-translated display/filter-dropdown
# label while every comparison/filter/sort still happens on the real underlying
# value via UserRole, exactly like the existing _FastTrackItem/_cellFilterText split.
_TRANSLATABLE_FIELDS = {'fast_track', 'type', 'department', 'location'}


class _FastTrackItem(QTableWidgetItem):
    """F.T. column cell: display text is left empty (so no colored/highlighted
    text can ever leak through, selected or not - the bolt icon is drawn by a
    separate cell widget). Sorts by the real Yes/No value stashed in UserRole."""

    def __lt__(self, other):
        """Compare by the stashed real Yes/No value instead of the empty display text."""
        if isinstance(other, QTableWidgetItem):
            return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)
        return super().__lt__(other)


class TablePTWs(QWidget):
    """PTW list table for a single status tab: filterable columns, a
    role-configurable right-click context menu, and double-click drill-down.
    `filterColumn(label, values)` is also called externally by the home
    dashboard's clickable donut segments to pre-filter this tab."""

    class MenuOption:
        """Describes one right-click context menu entry: label, handler, icon,
        whether it acts on all selected rows at once, and an optional
        visibility predicate."""

        def __init__(self, lbl, fun, icn, allAtOnce : bool = False, visibleFor = None):
            """Store the menu entry's label, handler, icon, batching mode, and
            visibility predicate for later use by showContextMenu()."""
            self.lbl = lbl
            self.fun = fun
            self.icn = icn
            self.allAtOnce = allAtOnce
            self.visibleFor = visibleFor

    def __init__(self, parent, loggedUser, label: str):
        """Build the labeled table, filter bar, and header/context-menu wiring
        for one PTW status tab."""
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.ptwsData = []
        self.loggedUser = loggedUser
        self.options = []

        self.summeryLabels = [t('PTW#'), t('F.T.'), t('Type'), t('Request Time'), t('Department'), t('Requestor'), t('Location'), t('Equipment'), t('Description')]
        self.summeryFields = ['id',       'fast_track', 'type', 'request_date',  'department',    'requestor',    'location',    'equipment',    'description']
        self._ftCol = self.summeryFields.index('fast_track')

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
        self._filterBtn.setObjectName("filterBtn")

        self._filterBtn.setCheckable(True)
        self._filterBtn.toggled.connect(self._toggleFilters)
        lblLyt.addStretch()
        lblLyt.addWidget(self._filterBtn)

        self._filterBar = QWidget()
        filterBarLayout = QHBoxLayout(self._filterBar)
        filterBarLayout.setContentsMargins(0, 0, 0, 0)
        filterBarLayout.setSpacing(0)
        self._filterCombos = []
        for i, _ in enumerate(self.summeryLabels):
            combo = CheckableComboBox()
            combo.filterChanged.connect(self._applyFilters)
            # if i < len(self.summeryLabels) - 1:
            #     combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            # else:
            #     combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
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

    def _populateFilters(self):
        """Rebuild each column's filter combo options from the table's current
        cell values, preserving any existing checked selections. Fixed-vocabulary
        columns (`_TRANSLATABLE_FIELDS`) get a translated dropdown label per value,
        same real value underneath - see `CheckableComboBox.setItems()`."""
        col_values = [set() for _ in self.summeryLabels]
        for row in range(self.tbl.rowCount()):
            for col in range(len(self.summeryLabels)):
                item = self.tbl.item(row, col)
                if item:
                    col_values[col].add(self._cellFilterText(item))
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
                (item := self.tbl.item(row, col)) is not None and self._cellFilterText(item) not in allowed
                for col, allowed in active
            )
            self.tbl.setRowHidden(row, hide)

    def _showAllRows(self):
        """Unhide every row in the table."""
        for row in range(self.tbl.rowCount()):
            self.tbl.setRowHidden(row, False)

    def filterColumn(self, field: str, values: set):
        """Programmatically filter one column down to a specific set of values.

        Used by the home dashboard's clickable donut segments to drill down
        into this tab: clicking a segment calls this to open the filter bar
        (if not already open) and check only the matching values in that
        column's combo, e.g. narrowing the PTW list to a single location.

        Args:
            field: column identifier as it appears in `summeryFields` (e.g.
                'location') - NOT the (translated, so language-dependent)
                display label in `summeryLabels`.
            values: the set of cell values to keep checked in that column.
        """
        if field not in self.summeryFields:
            return
        col = self.summeryFields.index(field)
        if not self._filterBtn.isChecked():
            self._filterBtn.setChecked(True)   # -> _toggleFilters(True): populates + applies
        else:
            self._populateFilters()
            self._syncFilterWidths()
        self._filterCombos[col].setCheckedOnly(values)

    def _onSorted(self):
        """Slot for the header's sortIndicatorChanged signal: keep
        `ptwsData` in row order after a sort and reapply active filters."""
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def ptwToRecord(self, ptw):
        """Convert a PTW model into the list of display strings for its row,
        resolving the requestor id to a display name and Yes/No-ing the
        fast-track flag."""
        record = []
        for field in self.summeryFields:
            value = getattr(ptw, field)
            if field == 'fast_track':
                value = 'Yes' if value else 'No'
            elif field == 'requestor' and value:
                user = globalData.allUsers.get(value)
                if user:
                    value = user.getName()
            record.append(str(value))
        return record

    def _makeCell(self, col: int, value: str) -> QTableWidgetItem:
        """Build the QTableWidgetItem for one cell, using `_FastTrackItem`
        (empty text, real value in UserRole) for the F.T. column, and translated
        display text (real value still in UserRole) for the other fixed-vocabulary
        columns in `_TRANSLATABLE_FIELDS` (type/department/location)."""
        if col == self._ftCol:
            cell = _FastTrackItem("")
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        if self.summeryFields[col] in _TRANSLATABLE_FIELDS:
            cell = QTableWidgetItem(t(value))
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        return QTableWidgetItem(value)

    @staticmethod
    def _cellFilterText(item: QTableWidgetItem) -> str:
        """Return the value to filter/compare on for a cell: its stashed
        UserRole data if present, otherwise its display text."""
        userData = item.data(Qt.ItemDataRole.UserRole)
        return userData if userData is not None else item.text()

    def _applyFastTrackStyle(self, cell: QTableWidgetItem, fastTrack: bool):
        """Bold and enlarge a cell's font when its row is fast-tracked."""
        if fastTrack:
            font = cell.font()
            font.setBold(True)
            if font.pointSize() > 0:
                font.setPointSize(font.pointSize() + 3)
            else:
                font.setPixelSize(font.pixelSize() + 4)
            cell.setFont(font)

    def _fastTrackIconWidget(self, fastTrack: bool) -> QWidget:
        """Build the F.T. column's cell widget: an empty container, or a
        bolt-icon badge when the row is fast-tracked."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if fastTrack:
            badge = QLabel()
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet("background: rgba(0, 0, 0, 140); border-radius: 14px;")
            badge.setPixmap(qta.icon('fa6s.bolt', color='orange').pixmap(20, 20))
            layout.addWidget(badge)
        return container
    
    def addPTWToGUI(self, ptw):
        """Append a new row for `ptw`, refresh cached data, and reapply
        filters if the filter bar is open."""
        self.ptwsData.append(ptw)
        data = self.ptwToRecord(ptw)
        self.tbl.setSortingEnabled(False)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            cell.setBackground(QBrush(ptw.backgroundColor()))
            cell.setForeground(QBrush(ptw.foregroundColor()))
            self._applyFastTrackStyle(cell, ptw.fast_track)
            self.tbl.setItem(row, i, cell)
            if i == self._ftCol:
                self.tbl.setCellWidget(row, i, self._fastTrackIconWidget(ptw.fast_track))
        self.tbl.setSortingEnabled(True)
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def addOption(self, options: MenuOption):
        """Register a single context-menu option."""
        self.options.append(options)

    def addOptions(self, options: Iterable[MenuOption]):
        """Register multiple context-menu options at once."""
        self.options.extend(options)

    def updatePTWInGUI(self, row: int, ptw):
        """Overwrite an existing row in place with `ptw`'s current data,
        refresh cached data, and reapply filters if the filter bar is open."""
        self.ptwsData[row] = ptw
        data = self.ptwToRecord(ptw)
        self.tbl.setSortingEnabled(False)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            cell.setBackground(QBrush(ptw.backgroundColor()))
            cell.setForeground(QBrush(ptw.foregroundColor()))
            self._applyFastTrackStyle(cell, ptw.fast_track)
            self.tbl.setItem(row, i, cell)
            if i == self._ftCol:
                self.tbl.setCellWidget(row, i, self._fastTrackIconWidget(ptw.fast_track))
        self.tbl.setSortingEnabled(True)
        self._syncPtwsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def updatePTW(self, row: int, ptw):
        """Send `ptw`'s updated data to the server, then update the row in
        the GUI on success (or show a warning on failure)."""
        def on_done(err, _):
            """Callback for updatePTW's request: update the GUI row on
            success, or show a warning on failure."""
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            self.updatePTWInGUI(row, ptw)
        ClientRequests.updatePTW(self.loggedUser, ptw, callback=on_done)

    def deletePTW(self, row: int):
        """Confirm with the user, then request deletion of the PTW at `row`
        and remove it from the table on success."""
        def on_done(err, _):
            """Callback for deletePTW's request: remove the row on success,
            or show a warning on failure."""
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            self.ptwsData.pop(row)
            self.tbl.removeRow(row)
            if self._filterBar.isVisible():
                self._populateFilters()

        ptw = self.ptwsData[row]
        reply = QMessageBox.question(self, t('Delete PTW'), t("Are you sure you want to delete PTW# '{0}'?").format(ptw.id), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            ClientRequests.deletePTW(self.loggedUser, ptw.id, callback=on_done)

    def removePTWById(self, ptwId) -> bool:
        """Remove the row for ptwId if this tab currently holds it. Used for SSE-driven
        targeted updates, where the caller doesn't know in advance which tab has the row."""
        for row, ptw in enumerate(self.ptwsData):
            if ptw.id == ptwId:
                self.ptwsData.pop(row)
                self.tbl.removeRow(row)
                if self._filterBar.isVisible():
                    self._populateFilters()
                return True
        return False

    def clear(self):
        """Remove all rows and cached PTWs, and reset every filter combo back
        to its empty "Select All" state."""
        self.tbl.clearContents()
        self.ptwsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def sort(self):
        """Sort rows by PTW# ascending then F.T. descending (fast-tracked
        rows first), and resync cached data to match."""
        self.tbl.sortItems(0, Qt.SortOrder.AscendingOrder)
        self.tbl.sortItems(1, Qt.SortOrder.DescendingOrder)
        self._syncPtwsData()

    def _syncPtwsData(self):
        """Reorder `ptwsData` to match the table's current (possibly
        user-sorted) row order, keyed by the PTW# column."""
        id_to_ptw = {str(p.id): p for p in self.ptwsData}
        self.ptwsData = [id_to_ptw[self.tbl.item(r, 0).text()] for r in range(self.tbl.rowCount())]

    def doubleClickHandler(self, row, col):
        """Slot for cellDoubleClicked: invoke the first registered menu
        option's handler on the double-clicked row's PTW."""
        if len(self.options) > 0:
            self.options[0].fun(row, self.ptwsData[row])

    def optionDoForAllSelected(self, fun, allAtOnce: bool):
        """Run a context-menu option's handler over the current selection:
        once with all selected rows/PTWs together if `allAtOnce`, otherwise
        once per row (in reverse order, so row indices stay valid as rows are
        removed)."""
        selectedRows = list(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()))
        if allAtOnce:
            fun(selectedRows, [self.ptwsData[row] for row in selectedRows])
        else:
            for row in selectedRows[::-1]:          # reverse to avoid messing up row numbers when deleting
                fun(row, self.ptwsData[row])

    def showContextMenu(self, pos: QPoint):
        """Slot for customContextMenuRequested: build and show a right-click
        menu of the registered options at `pos`, wired to run each option's
        handler over the selected rows on trigger."""
        row = self.tbl.indexAt(pos)

        if not row.isValid():
            return

        row = row.row()
        menu = QMenu(self.tbl)

        for option in self.options:
            action = QAction(option.icn, option.lbl, self.tbl)
            menu.addAction(action)
            action.triggered.connect(partial(self.optionDoForAllSelected, option.fun, option.allAtOnce))

        menu.exec(self.tbl.mapToGlobal(pos))
