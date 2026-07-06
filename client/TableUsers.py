import copy
from PyQt6.QtCore import Qt, QPoint, QDir
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QTableWidget, QLabel, QAbstractItemView,
                              QHeaderView, QTableWidgetItem, QMenu, QDialog, QMessageBox, QFileDialog)
from PyQt6.QtGui import QFont, QAction
from typing import Iterable
import qtawesome as qta

from DialogUser import DialogUser
from clientRequests import ClientRequests
from ImportUsersExcel import ImportUsersExcel, DialogUsersPreview
from GlobalData import globalData

class TableUsers(QWidget):
    def __init__(self, parent, loggedUser, label: str):
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.tbl = QTableWidget()
        self.loggedUser = loggedUser
        self.users = []

        self.summeryLabels = ['Username', 'Name', 'Role', 'Department', 'Email', 'EXT']
        self.summeryFields = ['username', 'name', 'role', 'department', 'email', 'ext']

        self.label = label
        lbl = QLabel(label)
        lbl.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.setLayout(lyt)
        self.setAutoFillBackground(False)
        lyt.addWidget(lbl)
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
        
        for u in self.users:
            data = self.userToRecord(u)
            self.tbl.insertRow(self.tbl.rowCount())
            for i,d in enumerate(data):
                cell = QTableWidgetItem(d)
                self.tbl.setItem(self.tbl.rowCount()-1, i, cell)
    
    def clear(self):
        self.tbl.clearContents()
        self.users.clear()
        self.tbl.setRowCount(0)

    def userToRecord(self, user):
        record = []
        for field in self.summeryFields:
            record.append(str(getattr(user, field)))
        return record
    
    def addUserToGUI(self, newUser):
        self.users.append(newUser)
        data = self.userToRecord(newUser)
        self.tbl.insertRow(self.tbl.rowCount())
        for i,d in enumerate(data):
            cell = QTableWidgetItem(d)
            self.tbl.setItem(self.tbl.rowCount()-1, i, cell)

    def addUser(self, newUser):
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.addUserToGUI(newUser)
        ClientRequests.addNewUser(self.loggedUser, newUser, callback=on_done)
    
    def addUsers(self, users: Iterable):
        for user in users:
            self.addUser(user)
    
    def doubleClickHandler(self, row: int, column: int):
        self.updateUser(row)

    def showContextMenu(self, pos: QPoint):
        row = self.tbl.indexAt(pos)

        if not row.isValid():
            return
        
        row = row.row()
        menu = QMenu(self.tbl)
        
        actionView = QAction(qta.icon('fa6s.eye'), 'View', self.tbl)
        actionEdit = QAction(qta.icon('fa6s.pen'), 'Edit', self.tbl)
        # actionDelete = QAction(qta.icon('fa5s.trash'), 'Delete', self.tbl)
        
        actionView.triggered.connect(lambda: self.viewUser(row))
        actionEdit.triggered.connect(lambda: self.updateUser(row))
        # actionDelete.triggered.connect(lambda: self.deleteUser(row))

        menu.addAction(actionView)
        menu.addAction(actionEdit)
        # menu.addAction(actionDelete)

        menu.exec(self.tbl.mapToGlobal(pos))
    
    def viewUser(self, row: int):
        user = self.users[row]
        DialogUser(self, True, False, self.loggedUser, user, f"Edit User - User {user.getUsername()}").exec()
        
    def updateUser(self, row: int):
        user = copy.deepcopy(self.users[row])
        dialog = DialogUser(self, False, False, self.loggedUser, user, f"Edit Mode - User {user.getUsername()}")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.users[row] = user
            data = self.userToRecord(user)
            for i,d in enumerate(data):
                cell = QTableWidgetItem(d)
                self.tbl.setItem(row, i, cell)
        ClientRequests.updateUser(self.loggedUser, user, callback=on_done)

    def deleteUser(self, row: int):
        user = self.users[row]
        reply = QMessageBox.question(self, 'Delete User', f"Are you sure you want to delete user '{user.getUsername()}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return
        
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.users.pop(row)
            self.tbl.removeRow(row)

        ClientRequests.deleteUser(self.loggedUser, self.users[row].getUsername(), callback=on_done)
    
    def addNewUserDialog(self):
        from User import User
        newUser = User()
        dialog = DialogUser(self, False, True, self.loggedUser, newUser, "New User")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.addUser(newUser)

    def importUsersFromExcel(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Users File", QDir.homePath(), "Excel/CSV Files (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv);;All Files (*)")
        if not filepath:
            return

        try:
            rows = ImportUsersExcel.parseFile(filepath, set(globalData.allUsers.keys()))
        except Exception as e:
            QMessageBox.critical(self, "Import Failed", f"Could not read the selected file.\n{e}")
            return

        if not rows:
            QMessageBox.information(self, "Import", "The selected file has no data rows.")
            return

        headers = ImportUsersExcel.HEADERS + ['Password', 'Status']
        preview = DialogUsersPreview(self, "Preview Import", headers, [r.asRecord() for r in rows], mode='confirm')
        if preview.exec() != QDialog.DialogCode.Accepted:
            return

        toImport = [r for r in rows if r.user is not None]
        if not toImport:
            self.finishImport(rows)
            return

        remaining = len(toImport)

        def makeHandler(row):
            def on_done(err, _):
                nonlocal remaining
                if err:
                    row.status = f"Failed: {err}"
                else:
                    row.status = "Success"
                    self.addUserToGUI(row.user)
                remaining -= 1
                if remaining == 0:
                    self.finishImport(rows)
            return on_done

        for row in toImport:
            ClientRequests.addNewUser(self.loggedUser, row.user, callback=makeHandler(row))

    def finishImport(self, rows: list):
        succeededCount = sum(1 for r in rows if r.status == "Success")
        attemptedCount = sum(1 for r in rows if r.user is not None)
        summary = f"{succeededCount} of {attemptedCount} user(s) imported successfully."

        headers = ImportUsersExcel.HEADERS + ['Password', 'Status']

        def onExport():
            savePath, _ = QFileDialog.getSaveFileName(self, "Save Import Result", "import_result.xlsx", "Excel Files (*.xlsx)")
            if not savePath:
                return
            try:
                ImportUsersExcel.exportResult(savePath, rows)
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"Could not save the result file.\n{e}")

        DialogUsersPreview(self, "Import Result", headers, [r.asRecord() for r in rows], mode='result', summary=summary, onExport=onExport).exec()