"""Embedded, editable list of an IC's isolation items (tag/description/state/
lock #/lock box #) shown inside DialogIC's Isolation Items tab. Emits
`itemsChanged` on any add/edit/bulk-delete so the P&ID/Wiring tab can prompt
to resync its highlights."""

from PyQt6.QtCore import Qt, QPoint, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QDialog, QMessageBox,
                              QMenu)
from PyQt6.QtGui import QAction

from models.Isolation import IC
from dialogs.DialogIsolationItem import DialogIsolationItem
from helper.i18n import t


class TableIsolationItems(QWidget):
    """Editable isolation-item list embedded inside an IC dialog."""

    itemsChanged = pyqtSignal()

    def __init__(self, parent, items, readonly):
        """Build the isolation-item table (Tag/Description/State/Lock #/Lock Box #)
        from `items`, plus, when not readonly, its right-click delete menu (the "New
        Isolation Item" action itself is exposed via DialogIC's floating action button
        and its shared Ctrl+N shortcut - see DialogIC.updateFabForTab and
        TabbedDialog's own Ctrl+N wiring). Double-clicking a row always opens it for
        editing/viewing."""
        super().__init__(parent)
        lyt = QVBoxLayout()
        self.tbl = QTableWidget()
        self.readonly = readonly
        self.items: list[IC.IsolationItem] = items

        self.summeryLabels = [t('Tag'), t('Description'), t('State'), t('Lock #'), t('Lock Box #')]
        self.summeryFields = ['tag', 'description', 'state', 'lock_num', 'lock_box_num']

        self.setLayout(lyt)
        lyt.addWidget(self.tbl)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setColumnCount(len(self.summeryLabels))
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.cellDoubleClicked.connect(self._onCellDoubleClicked)
        if not readonly:
            self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tbl.customContextMenuRequested.connect(self.showContextMenu)
        for item in self.items:
            self.__addItemToGUI(item)

    def clear(self):
        """Remove all rows and clear the underlying items list."""
        self.tbl.clearContents()
        self.items.clear()
        self.tbl.setRowCount(0)

    def __addItemToGUI(self, item: 'IC.IsolationItem'):
        """Append one new row displaying `item`'s fields (translating the
        state column's display text, a fixed vocabulary word), stashing the
        item object itself in the tag cell's UserRole so double-click can
        resolve it after re-sorting."""
        self.tbl.insertRow(self.tbl.rowCount())
        data = [str(getattr(item, f)) for f in self.summeryFields]
        for i, d in enumerate(data):
            cell = QTableWidgetItem(t(d) if self.summeryFields[i] == 'state' else d)
            if i == 0:
                # stashed so double-click can resolve the right item even after the
                # table has been re-sorted by a column header click
                cell.setData(Qt.ItemDataRole.UserRole, item)
            self.tbl.setItem(self.tbl.rowCount()-1, i, cell)

    def addItem(self, item: 'IC.IsolationItem'):
        """Add `item` to the list and GUI, refresh the table, and emit
        `itemsChanged`."""
        self.__addItemToGUI(item)
        self.items.append(item)
        self.refreshGUI()
        self.itemsChanged.emit()

    def newItemDialog(self):
        """Slot for the "New Isolation Item" button/shortcut: open
        `DialogIsolationItem` and, on acceptance, add the new item unless its
        tag duplicates an existing one (in which case a warning is shown
        instead)."""
        dialog = DialogIsolationItem(self)
        resp = dialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            item = dialog.getItem()
            if item.tag in [i.tag for i in self.items]:
                QMessageBox.warning(self, t("Error"), t("An isolation item with the same tag already exists."))
                return
            self.addItem(item)

    def _onCellDoubleClicked(self, row: int, col: int):
        """Slot for cellDoubleClicked: resolve the double-clicked row's item
        (stashed in the tag cell's UserRole) and open it for editing/viewing."""
        cell = self.tbl.item(row, 0)
        if cell is None:
            return
        item = cell.data(Qt.ItemDataRole.UserRole)
        if item is None:
            return
        self.editItemDialog(item)

    def editItemDialog(self, existingItem: 'IC.IsolationItem'):
        """Open `existingItem` in `DialogIsolationItem` (edit or view-only
        depending on `self.readonly`); on acceptance, replace it in the list
        unless the new tag duplicates another item's tag, then refresh the
        table and emit `itemsChanged`."""
        dialog = DialogIsolationItem(self, item=existingItem, readonly=self.readonly)
        resp = dialog.exec()
        if self.readonly or resp != QDialog.DialogCode.Accepted:
            return
        newItem = dialog.getItem()
        otherTags = [i.tag for i in self.items if i is not existingItem]
        if newItem.tag in otherTags:
            QMessageBox.warning(self, t("Error"), t("An isolation item with the same tag already exists."))
            return
        self.items[self.items.index(existingItem)] = newItem
        self.refreshGUI()
        self.itemsChanged.emit()

    def refreshGUI(self):
        """Rebuild the entire table from the current `items` list."""
        self.tbl.clearContents()
        self.tbl.setRowCount(0)
        for item in self.items:
            self.__addItemToGUI(item)

    def deleteItem(self, row: int):
        """Remove the item at `row` from both the list and the table."""
        self.items.pop(row)
        self.tbl.removeRow(row)

    def getItems(self):
        """Return the current list of isolation items."""
        return self.items

    def deleteSelectedRows(self):
        """Delete every currently-selected row (highest index first so
        earlier indices stay valid), then emit `itemsChanged` if anything
        was deleted."""
        selectedRows = sorted(set(row.row() for row in self.tbl.selectedIndexes() if row.isValid()), reverse=True)
        for row in selectedRows:
            self.deleteItem(row)
        if selectedRows:
            self.itemsChanged.emit()

    def showContextMenu(self, pos: QPoint):
        """Slot for customContextMenuRequested: show a right-click menu with
        a Delete action that removes the selected rows."""
        row = self.tbl.indexAt(pos)
        if not row.isValid():
            return
        menu = QMenu(self.tbl)
        actionDelete = QAction(t('Delete'), self.tbl)
        actionDelete.triggered.connect(self.deleteSelectedRows)
        menu.addAction(actionDelete)
        menu.exec(self.tbl.mapToGlobal(pos))
