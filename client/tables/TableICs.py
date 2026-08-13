"""IC (Isolation Certificate) list table widget: one instance per status tab,
mirroring TablePTWs' filter bar, context menu, and double-click drill-down
structure, plus the FAB dialog for creating a new IC."""

from PyQt6.QtCore import Qt, QSize, QPoint
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QLabel, QPushButton, QAbstractItemView, QHeaderView, QFrame,
                              QMenu, QMessageBox, QDialog)
from PyQt6.QtGui import QFont, QBrush, QAction
from typing import Iterable
from functools import partial
import qtawesome as qta

from network.clientRequests import ClientRequests
from models.Isolation import IC
from dialogs.DialogIC import DialogIC
from widgets.CheckableComboBox import CheckableComboBox
from GlobalData import globalData
from helper.i18n import t


# Fields whose stored value is a fixed, translatable vocabulary word rather
# than free text a user typed - these get a t()-translated display/filter-dropdown
# label while every comparison/filter/sort still happens on the real underlying
# value via UserRole, exactly like the existing _LongTermItem/_cellFilterText split.
_TRANSLATABLE_FIELDS = {'status', 'type', 'long_term', 'requestor_department', 'execution_department', 'location'}


class _LongTermItem(QTableWidgetItem):
    """Long Term column cell: display text is left empty (so no colored/highlighted
    text can ever leak through, selected or not - the icon is drawn by a separate
    cell widget). Sorts by the real Yes/No value stashed in UserRole."""

    def __lt__(self, other):
        """Compare by the stashed real Yes/No value instead of the empty display text."""
        if isinstance(other, QTableWidgetItem):
            return self.data(Qt.ItemDataRole.UserRole) < other.data(Qt.ItemDataRole.UserRole)
        return super().__lt__(other)


class TableICs(QWidget):
    """Reusable per-tab browsing widget for ICs, mirroring TablePTWs."""

    def __init__(self, parent, loggedUser, label: str):
        """Build the labeled table, filter bar, and header/context-menu wiring
        for one IC status tab."""
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.icsData: list[IC] = []
        self.loggedUser = loggedUser
        self.options = []

        self.summeryLabels = [t('IC#'), t('Status'), t('Type'), t('L.T.'), t('Requestor'), t('Request Time'), t('Requestor Dept.'), t('Execution Dept.'), t('Location'), t('Equipment'), t('Reason')]
        self.summeryFields = ['id',  'status', 'type', 'long_term', 'requestor', 'requestor_timestamp', 'requestor_department', 'execution_department', 'location', 'equipment', 'reason']
        self._ltCol = self.summeryFields.index('long_term')

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
        UserRole data if present (L.T. and other translatable columns),
        otherwise its display text."""
        userData = item.data(Qt.ItemDataRole.UserRole)
        return userData if userData is not None else item.text()

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

    def filterColumn(self, field: str, values: set):
        """Programmatically filter one column down to a specific set of values.

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
        `icsData` in row order after a sort and reapply active filters."""
        self._syncICsData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def icToRecord(self, ic: IC):
        """Convert an IC model into the list of display strings for its row,
        resolving computed status, the long-term flag, and the requestor id
        to a display name."""
        record = []
        for field in self.summeryFields:
            if field == 'status':
                value = ic.getStatus().value
            elif field == 'long_term':
                value = 'Yes' if ic.long_term else 'No'
            else:
                value = getattr(ic, field)
                if field == 'requestor' and value:
                    user = globalData.allUsers.get(value)
                    if user:
                        value = user.getName()
            record.append(str(value) if value is not None else '')
        return record

    def _makeCell(self, col: int, value: str) -> QTableWidgetItem:
        """Build the QTableWidgetItem for one cell, using `_LongTermItem`
        (empty text, real value in UserRole) for the L.T. column, and translated
        display text (real value still in UserRole) for the other fixed-vocabulary
        columns in `_TRANSLATABLE_FIELDS`."""
        if col == self._ltCol:
            cell = _LongTermItem("")
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        if self.summeryFields[col] in _TRANSLATABLE_FIELDS:
            cell = QTableWidgetItem(t(value))
            cell.setData(Qt.ItemDataRole.UserRole, value)
            return cell
        return QTableWidgetItem(value)

    
    def _longTermIconWidget(self, longTerm: bool) -> QWidget:
        """Build the L.T. column's cell widget: an empty container, or an
        infinity-icon badge when the IC is long-term."""
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if longTerm:
            badge = QLabel()
            badge.setFixedSize(28, 28)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet("background: rgba(0, 0, 0, 140); border-radius: 14px;")
            badge.setPixmap(qta.icon('ph.infinity-bold', color='cyan').pixmap(20, 20))
            layout.addWidget(badge)
        return container

    def addICToGUI(self, ic: IC):
        """Append a new row for `ic`, refresh cached data, and reapply
        filters if the filter bar is open."""
        self.icsData.append(ic)
        data = self.icToRecord(ic)
        self.tbl.setSortingEnabled(False)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            if i == 0:
                cell.setData(Qt.ItemDataRole.UserRole, ic.id)
            cell.setBackground(QBrush(ic.backgroundColor()))
            cell.setForeground(QBrush(ic.foregroundColor()))
            self.tbl.setItem(row, i, cell)
            if i == self._ltCol:
                self.tbl.setCellWidget(row, i, self._longTermIconWidget(ic.long_term))
        self.tbl.setSortingEnabled(True)
        self._syncICsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def updateICInGUI(self, row: int, ic: IC):
        """Overwrite an existing row in place with `ic`'s current data,
        refresh cached data, and reapply filters if the filter bar is open."""
        self.icsData[row] = ic
        data = self.icToRecord(ic)
        self.tbl.setSortingEnabled(False)
        for i, d in enumerate(data):
            cell = self._makeCell(i, d)
            if i == 0:
                cell.setData(Qt.ItemDataRole.UserRole, ic.id)
            cell.setBackground(QBrush(ic.backgroundColor()))
            cell.setForeground(QBrush(ic.foregroundColor()))
            self.tbl.setItem(row, i, cell)
            if i == self._ltCol:
                self.tbl.setCellWidget(row, i, self._longTermIconWidget(ic.long_term))
        self.tbl.setSortingEnabled(True)
        self._syncICsData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def removeICById(self, icId) -> bool:
        """Remove the row for icId if this tab currently holds it. Used for SSE-driven
        targeted updates, where the caller doesn't know in advance which tab has the row."""
        for row, ic in enumerate(self.icsData):
            if ic.id == icId:
                self.icsData.pop(row)
                self.tbl.removeRow(row)
                if self._filterBar.isVisible():
                    self._populateFilters()
                return True
        return False

    def addOption(self, option):
        """Register a single context-menu option."""
        self.options.append(option)

    def addOptions(self, options: Iterable):
        """Register multiple context-menu options at once."""
        self.options.extend(options)

    def clear(self):
        """Remove all rows and cached ICs, and reset every filter combo back
        to its empty "Select All" state."""
        self.tbl.clearContents()
        self.icsData.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def sort(self):
        """Sort rows by IC# ascending and resync cached data to match."""
        self.tbl.sortItems(0, Qt.SortOrder.AscendingOrder)
        self._syncICsData()

    def _syncICsData(self):
        """Reorder `icsData` to match the table's current (possibly
        user-sorted) row order, keyed by the IC# column's stashed id."""
        id_to_cert = {str(c.id): c for c in self.icsData}
        self.icsData = [
            id_to_cert[str(self.tbl.item(r, 0).data(Qt.ItemDataRole.UserRole))]
            for r in range(self.tbl.rowCount())
        ]

    def doubleClickHandler(self, row, col):
        """Slot for cellDoubleClicked: invoke the first registered menu
        option's handler on the double-clicked row's IC."""
        if len(self.options) > 0:
            self.options[0].fun(row, self.icsData[row])

    def optionDoForAllSelected(self, fun, allAtOnce: bool):
        """Run a context-menu option's handler over the current selection:
        once with all selected rows/ICs together if `allAtOnce`, otherwise
        once per row (in reverse order, so row indices stay valid as rows are
        removed)."""
        selectedRows = list(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()))
        if allAtOnce:
            fun(selectedRows, [self.icsData[row] for row in selectedRows])
        else:
            for row in selectedRows[::-1]:
                fun(row, self.icsData[row])

    def showContextMenu(self, pos: QPoint):
        """Slot for customContextMenuRequested: build and show a right-click
        menu of the registered options that pass their `visibleFor` check for
        this row's IC (if any), wired to run each option's handler over the
        selected rows on trigger."""
        row = self.tbl.indexAt(pos)
        if not row.isValid():
            return
        ic = self.icsData[row.row()]
        menu = QMenu(self.tbl)
        for option in self.options:
            if option.visibleFor is not None and not option.visibleFor(ic):
                continue
            action = QAction(option.icn, option.lbl, self.tbl)
            menu.addAction(action)
            action.triggered.connect(partial(self.optionDoForAllSelected, option.fun, option.allAtOnce))
        menu.exec(self.tbl.mapToGlobal(pos))

    def addNewICDialog(self):
        """Open a new-IC `DialogIC`; on acceptance, submit the IC to the
        server, add it to this table on success, and upload any pending
        P&ID/Wiring documents attached during the dialog."""
        ic = IC()
        dlg = DialogIC(self, self.loggedUser, ic, True, False, t("New IC"))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ic = dlg.getIC()

        def on_done(err, icId):
            """Callback for the addIC request: on success, stamp the new id,
            cache the IC, add its row to the table, and upload any pending
            P&ID/Wiring documents; on failure, show a warning."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            ic.id = icId
            globalData.ics[ic.id] = ic
            self.addICToGUI(ic)
            if dlg.pidDocsToBeUploaded:
                def on_pid_upload_done(err, _):
                    """Callback for the P&ID/Wiring upload request: warn if
                    the upload failed after the IC itself was already saved."""
                    if err:
                        QMessageBox.warning(self, t("Warning"), t("IC saved but failed to upload P&ID/Wiring documents:\n{0}").format(err))
                ClientRequests.addIcAttachments(self.loggedUser, ic.id, dlg.pidDocsToBeUploaded, callback=on_pid_upload_done)

        self.window()._refreshOverlay.showBusy()
        ClientRequests.addIC(self.loggedUser, ic, callback=on_done)
