"""Admin user management table.

Displays all registered users in a filterable, sortable table with a
right-click context menu for viewing/editing/activating users, and provides
the entry point for bulk user import from Excel/CSV files.
"""
import copy
from PyQt6.QtCore import Qt, QPoint, QDir, QSize
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QLabel, QAbstractItemView,
                              QHeaderView, QTableWidgetItem, QMenu, QDialog, QMessageBox, QFileDialog, QPushButton)
from PyQt6.QtGui import QFont, QAction
from typing import Iterable
import qtawesome as qta

from dialogs.DialogUser import DialogUser
from network.clientRequests import ClientRequests
from reports.ImportUsersExcel import ImportUsersExcel, DialogUsersPreview
from GlobalData import globalData
from widgets.CheckableComboBox import CheckableComboBox
from helper.i18n import t

class TableUsers(QWidget):
    """Table widget listing all users, for the Admin user-management tab.

    Supports per-column filtering, sorting, a right-click context menu
    (view/edit/activate-inactivate), and bulk user import from Excel/CSV.
    """

    def __init__(self, parent, loggedUser, label: str):
        """Build the table, header/filter bar, and per-column filter combos."""
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.loggedUser = loggedUser
        self.users = []

        self.summeryLabels = ['Username', 'Name', 'Role', 'Department', 'Email', 'EXT', 'Status']
        self.summeryFields = ['username', 'name', 'role', 'department', 'email', 'ext', 'is_active']

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
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setHorizontalHeaderLabels(self.summeryLabels)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.cellDoubleClicked.connect(self.doubleClickHandler)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self.showContextMenu)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        # self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.setStyleSheet("QTableWidget { background: transparent; }")
        self.tbl.viewport().setAutoFillBackground(False)
        self.tbl.verticalHeader().hide()
        self.tbl.horizontalHeader().sectionResized.connect(self._syncFilterWidths)
        self.tbl.horizontalHeader().sortIndicatorChanged.connect(self._onSorted)

        for u in self.users:
            data = self.userToRecord(u)
            self.tbl.insertRow(self.tbl.rowCount())
            for i,d in enumerate(data):
                cell = QTableWidgetItem(d)
                self.tbl.setItem(self.tbl.rowCount()-1, i, cell)

    def _toggleFilters(self, checked):
        """Slot for the filter button's toggled signal; show or hide the filter bar.

        When shown, (re)populates the filter combos and applies any active
        filters; when hidden, unhides all rows.
        """
        self._filterBar.setVisible(checked)
        if checked:
            self._populateFilters()
            self._syncFilterWidths()
            self._applyFilters()
        else:
            self._showAllRows()

    def _populateFilters(self):
        """Refresh each filter combo's choices from the values currently in its column."""
        col_values = [set() for _ in self.summeryLabels]
        for row in range(self.tbl.rowCount()):
            for col in range(len(self.summeryLabels)):
                item = self.tbl.item(row, col)
                if item:
                    col_values[col].add(item.text())
        for col, combo in enumerate(self._filterCombos):
            combo.setItems(col_values[col], preserve_selection=True)

    def _syncFilterWidths(self):
        """Slot for the header's sectionResized signal; keep filter combo widths aligned with their columns."""
        if not self._filterBar.isVisible():
            return
        header = self.tbl.horizontalHeader()
        for i, combo in enumerate(self._filterCombos[:-1]):
            combo.setFixedWidth(header.sectionSize(i))
        self._filterCombos[-1].setMinimumWidth(header.sectionSize(len(self._filterCombos) - 1))

    def _applyFilters(self):
        """Hide rows that don't match every active column filter's checked values."""
        active = [
            (col, combo.checkedItems())
            for col, combo in enumerate(self._filterCombos)
            if combo.isFiltering()
        ]
        for row in range(self.tbl.rowCount()):
            hide = any(
                (item := self.tbl.item(row, col)) is not None and item.text() not in allowed
                for col, allowed in active
            )
            self.tbl.setRowHidden(row, hide)

    def _showAllRows(self):
        """Unhide every row in the table."""
        for row in range(self.tbl.rowCount()):
            self.tbl.setRowHidden(row, False)

    def filterColumn(self, label: str, values: set):
        """Programmatically restrict a column's filter to the given values.

        Used by the Admin dashboard's department donut segments: clicking a
        segment (or its legend row) calls this to jump to and pre-filter this
        table by that department.
        """
        if label not in self.summeryLabels:
            return
        col = self.summeryLabels.index(label)
        if not self._filterBtn.isChecked():
            self._filterBtn.setChecked(True)   # -> _toggleFilters(True): populates + applies
        else:
            self._populateFilters()
            self._syncFilterWidths()
        self._filterCombos[col].setCheckedOnly(values)

    def _onSorted(self):
        """Slot for the header's sortIndicatorChanged signal; resync data order and filters after a sort."""
        self._syncUsersData()
        if self._filterBar.isVisible():
            self._applyFilters()

    def _syncUsersData(self):
        """Reorder self.users to match the table's current (possibly sorted) row order."""
        username_to_user = {u.username: u for u in self.users}
        self.users = [username_to_user[self.tbl.item(r, 0).text()] for r in range(self.tbl.rowCount())]

    def clear(self):
        """Remove all rows, users, and filter selections from the table."""
        self.tbl.clearContents()
        self.users.clear()
        self.tbl.setRowCount(0)
        for combo in self._filterCombos:
            combo._model.clear()
            combo._addSelectAllItem()
            combo._updateText()

    def userToRecord(self, user):
        """Convert a user object into the list of display strings for one table row."""
        record = []
        for field in self.summeryFields:
            value = getattr(user, field)
            if field == 'is_active':
                value = t('Active') if value else t('Inactive')
            record.append(str(value))
        return record
    
    def addUserToGUI(self, newUser):
        """Append a user to the local list and table, without a server round trip.

        Called once the server has already confirmed the user was created.
        """
        self.users.append(newUser)
        data = self.userToRecord(newUser)
        self.tbl.setSortingEnabled(False)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for i,d in enumerate(data):
            cell = QTableWidgetItem(d)
            self.tbl.setItem(row, i, cell)
        self.tbl.setSortingEnabled(True)
        self._syncUsersData()
        if self._filterBar.isVisible():
            self._populateFilters()
            self._applyFilters()

    def addUser(self, newUser):
        """Send a new user to the server and add it to the table on success."""
        def on_done(err, _):
            """Handle the addNewUser response; show an error or add the row to the GUI."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            self.addUserToGUI(newUser)
        self.window()._refreshOverlay.showBusy()
        ClientRequests.addNewUser(self.loggedUser, newUser, callback=on_done)
    
    def addUsers(self, users: Iterable):
        """Add multiple users, calling addUser() once per user."""
        for user in users:
            self.addUser(user)
    
    def doubleClickHandler(self, row: int, column: int):
        """Slot for the table's cellDoubleClicked signal; open the edit dialog for the row."""
        self.updateUser(row)

    def showContextMenu(self, pos: QPoint):
        """Slot for the table's customContextMenuRequested signal.

        Shows a View/Edit/Activate-Inactivate context menu for the
        right-clicked row.
        """
        row = self.tbl.indexAt(pos)

        if not row.isValid():
            return
        
        row = row.row()
        user = self.users[row]
        menu = QMenu(self.tbl)

        actionView = QAction(qta.icon('fa6s.eye'), t('View'), self.tbl)
        actionEdit = QAction(qta.icon('fa6s.pen'), t('Edit'), self.tbl)
        # actionDelete = QAction(qta.icon('fa5s.trash'), 'Delete', self.tbl)
        if user.getIsActive():
            actionToggleActive = QAction(qta.icon('fa6s.user-slash'), t('Inactivate'), self.tbl)
        else:
            actionToggleActive = QAction(qta.icon('fa6s.user-check'), t('Activate'), self.tbl)

        actionView.triggered.connect(lambda: self.viewUser(row))
        actionEdit.triggered.connect(lambda: self.updateUser(row))
        # actionDelete.triggered.connect(lambda: self.deleteUser(row))
        actionToggleActive.triggered.connect(lambda: self.toggleActive(row))

        menu.addAction(actionView)
        menu.addAction(actionEdit)
        # menu.addAction(actionDelete)
        menu.addAction(actionToggleActive)

        menu.exec(self.tbl.mapToGlobal(pos))
    
    def viewUser(self, row: int):
        """Open the read-only user dialog for the given row."""
        user = self.users[row]
        DialogUser(self, True, False, self.loggedUser, user, t("Edit User - User {0}").format(user.getUsername())).exec()
        
    def updateUser(self, row: int):
        """Open the edit dialog for a row and submit changes to the server if accepted."""
        user = copy.deepcopy(self.users[row])
        dialog = DialogUser(self, False, False, self.loggedUser, user, t("Edit Mode - User {0}").format(user.getUsername()))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def on_done(err, _):
            """Handle the updateUser response; show an error or refresh the row and filters."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            self.users[row] = user
            data = self.userToRecord(user)
            self.tbl.setSortingEnabled(False)
            for i,d in enumerate(data):
                cell = QTableWidgetItem(d)
                self.tbl.setItem(row, i, cell)
            self.tbl.setSortingEnabled(True)
            self._syncUsersData()
            if self._filterBar.isVisible():
                self._populateFilters()
                self._applyFilters()
        self.window()._refreshOverlay.showBusy()
        ClientRequests.updateUser(self.loggedUser, user, callback=on_done)

    def deleteUser(self, row: int):
        """Confirm with the user, then delete the user at the given row via the server."""
        user = self.users[row]
        reply = QMessageBox.question(self, t('Delete User'), t("Are you sure you want to delete user '{0}'?").format(user.getUsername()), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return
        
        def on_done(err, _):
            """Handle the deleteUser response; remove the row on success or show an error."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            self.users.pop(row)
            self.tbl.removeRow(row)
            if self._filterBar.isVisible():
                self._populateFilters()

        self.window()._refreshOverlay.showBusy()
        ClientRequests.deleteUser(self.loggedUser, self.users[row].getUsername(), callback=on_done)
    
    def toggleActive(self, row: int):
        """Confirm with the user, then activate or inactivate the user at the given row via the server."""
        user = self.users[row]
        activate = not user.getIsActive()
        title = t("Activate User") if activate else t("Inactivate User")
        message = (t("Are you sure you want to activate user '{0}'?") if activate else t("Are you sure you want to inactivate user '{0}'?")).format(user.getUsername())
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            """Handle the setUserActive response; update the row's status on success or show an error."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Fail"), err)
                return
            user.setIsActive(activate)
            data = self.userToRecord(user)
            self.tbl.setSortingEnabled(False)
            for i,d in enumerate(data):
                cell = QTableWidgetItem(d)
                self.tbl.setItem(row, i, cell)
            self.tbl.setSortingEnabled(True)
            self._syncUsersData()
            if self._filterBar.isVisible():
                self._populateFilters()
                self._applyFilters()
        self.window()._refreshOverlay.showBusy()
        ClientRequests.setUserActive(self.loggedUser, user.getUsername(), activate, callback=on_done)

    def addNewUserDialog(self):
        """Open the new-user dialog and, if accepted, submit the new user to the server."""
        from models.User import User
        newUser = User()
        dialog = DialogUser(self, False, True, self.loggedUser, newUser, t("New User"))
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.addUser(newUser)

    def importUsersFromExcel(self):
        """Bulk-import users from a user-selected Excel/CSV file.

        Entry point for the Admin dashboard's bulk import action: lets the
        user pick a file, parses it, shows a confirmation preview, then
        submits each parsed row to the server and shows a result dialog once
        every row has finished.
        """
        filepath, _ = QFileDialog.getOpenFileName(self, t("Select Users File"), QDir.homePath(), "Excel/CSV Files (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv);;All Files (*)")
        if not filepath:
            return

        try:
            rows = ImportUsersExcel.parseFile(filepath, set(globalData.allUsers.keys()))
        except Exception as e:
            QMessageBox.critical(self, t("Import Failed"), t("Could not read the selected file.\n{0}").format(e))
            return

        if not rows:
            QMessageBox.information(self, t("Import"), t("The selected file has no data rows."))
            return

        headers = ImportUsersExcel.HEADERS + ['Password', 'Status']
        preview = DialogUsersPreview(self, t("Preview Import"), headers, [r.asRecord() for r in rows], mode='confirm')
        if preview.exec() != QDialog.DialogCode.Accepted:
            return

        toImport = [r for r in rows if r.user is not None]
        if not toImport:
            self.finishImport(rows)
            return

        remaining = len(toImport)

        def makeHandler(row):
            """Build a per-row completion callback closing over that row's import result."""
            def on_done(err, _):
                """Record the row's import outcome and show the result dialog once all rows finish."""
                nonlocal remaining
                if err:
                    row.status = f"Failed: {err}"
                else:
                    row.status = "Success"
                    self.addUserToGUI(row.user)
                remaining -= 1
                if remaining == 0:
                    self.window()._refreshOverlay.hideBusy()
                    self.finishImport(rows)
            return on_done

        self.window()._refreshOverlay.showBusy()
        for row in toImport:
            ClientRequests.addNewUser(self.loggedUser, row.user, callback=makeHandler(row))

    def finishImport(self, rows: list):
        """Show the import-result dialog summarizing how many users were imported.

        Offers an option to export the per-row results to an Excel file.
        """
        succeededCount = sum(1 for r in rows if r.status == "Success")
        attemptedCount = sum(1 for r in rows if r.user is not None)
        summary = t("{0} of {1} user(s) imported successfully.").format(succeededCount, attemptedCount)

        headers = ImportUsersExcel.HEADERS + ['Password', 'Status']

        def onExport():
            """Slot for the result dialog's export action; save the import results to a chosen Excel file."""
            savePath, _ = QFileDialog.getSaveFileName(self, t("Save Import Result"), "import_result.xlsx", "Excel Files (*.xlsx)")
            if not savePath:
                return
            try:
                ImportUsersExcel.exportResult(savePath, rows)
            except Exception as e:
                QMessageBox.critical(self, t("Export Failed"), t("Could not save the result file.\n{0}").format(e))

        DialogUsersPreview(self, t("Import Result"), headers, [r.asRecord() for r in rows], mode='result', summary=summary, onExport=onExport).exec()