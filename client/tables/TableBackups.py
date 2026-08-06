import os
from datetime import datetime

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QFont, QAction, QColor
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QLabel, QPushButton, QMenu,
                              QMessageBox, QFileDialog)
import qtawesome as qta

from network.clientRequests import ClientRequests

_WARN_AGE_HOURS = 36
_CRIT_AGE_HOURS = 72

_OK_COLOR = "#2e7d32"
_WARN_COLOR = "#f57c00"
_CRIT_COLOR = "#d32f2f"


def _formatBytes(n: int) -> str:
    if not n:
        return "0 B"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _formatAge(dt: datetime) -> str:
    seconds = (datetime.now() - dt).total_seconds()
    if seconds < 60:
        return "just now"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m ago"
    hours = minutes / 60
    if hours < 48:
        return f"{hours:.0f}h ago"
    return f"{hours / 24:.0f}d ago"


class TableBackups(QWidget):
    def __init__(self, parent, loggedUser, title: str = "Backups"):
        super().__init__(parent)
        self.loggedUser = loggedUser
        self.backups: list[dict] = []
        self.retentionDays = 14

        lyt = QVBoxLayout(self)
        lyt.setContentsMargins(16, 16, 16, 16)
        lyt.setSpacing(10)

        headerRow = QHBoxLayout()
        headerLabel = QLabel(title, font=QFont("Helvetica", 18, QFont.Weight.Bold))
        self._statusLabel = QLabel()

        self._btnBackupNow = QPushButton(qta.icon('fa6s.floppy-disk'), " Backup Now")
        self._btnBackupNow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btnBackupNow.clicked.connect(self._backupNow)

        btnRefresh = QPushButton(qta.icon('fa6s.rotate-right'), " Refresh")
        btnRefresh.setCursor(Qt.CursorShape.PointingHandCursor)
        btnRefresh.clicked.connect(self.refresh)

        headerRow.addWidget(headerLabel)
        headerRow.addWidget(self._statusLabel)
        headerRow.addStretch()
        headerRow.addWidget(self._btnBackupNow)
        headerRow.addWidget(btnRefresh)
        lyt.addLayout(headerRow)

        hintLabel = QLabel("Right-click a backup to download a local copy or delete it.")
        hintLabel.setStyleSheet("color: palette(placeholder-text);")
        lyt.addWidget(hintLabel)

        self.columns = ['Timestamp', 'Age', 'DB Size', 'Files Size', 'Total Size', 'Status', 'Auto-prune in']
        self.tbl = QTableWidget()
        self.tbl.setColumnCount(len(self.columns))
        self.tbl.setHorizontalHeaderLabels(self.columns)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._showContextMenu)
        header = self.tbl.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(len(self.columns) - 1, QHeaderView.ResizeMode.Stretch)
        self.tbl.setStyleSheet("QTableWidget { background: transparent; }")
        self.tbl.viewport().setAutoFillBackground(False)
        self.tbl.verticalHeader().hide()
        lyt.addWidget(self.tbl)

    def refresh(self):
        def on_done(err, summary):
            self.window()._refreshOverlay.hideBusy()
            if err:
                self._statusLabel.setText(err)
                self._statusLabel.setStyleSheet(f"color: {_CRIT_COLOR}; font-weight: bold;")
                QMessageBox.warning(self, "Backups", f"Failed to refresh backups: {err}")
                return
            self._populate(summary)

        self.window()._refreshOverlay.showBusy()
        ClientRequests.getBackups(self.loggedUser, callback=on_done)

    def _populate(self, summary: dict):
        self.backups = summary.get('backups', [])
        self.retentionDays = summary.get('retentionDays', 14)

        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(0)
        for data in self.backups:
            row = self.tbl.rowCount()
            self.tbl.insertRow(row)
            created = datetime.fromisoformat(data['created'])
            ageDays = (datetime.now() - created).total_seconds() / 86400
            pruneInDays = max(0, self.retentionDays - ageDays)
            complete = bool(data.get('complete'))

            values = [
                created.strftime('%Y-%m-%d %H:%M:%S'),
                _formatAge(created),
                _formatBytes(data.get('dumpSizeBytes')),
                _formatBytes(data.get('filesSizeBytes')),
                _formatBytes(data.get('totalSizeBytes')),
                'Complete' if complete else 'Incomplete',
                f"{pruneInDays:.0f}d",
            ]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, data['name'])
                if col == 5 and not complete:
                    cell.setForeground(QColor(_CRIT_COLOR))
                self.tbl.setItem(row, col, cell)
        self.tbl.setSortingEnabled(True)

        self._updateStatusLabel(summary)

    def _updateStatusLabel(self, summary: dict):
        freeBytes = summary.get('freeBytes')
        lastBackupAt = summary.get('lastBackupAt')
        totalSize = sum(b.get('totalSizeBytes', 0) for b in self.backups)

        if not lastBackupAt:
            self._statusLabel.setText("No backups yet")
            self._statusLabel.setStyleSheet(f"color: {_CRIT_COLOR}; font-weight: bold;")
            return

        ageHours = (datetime.now() - datetime.fromisoformat(lastBackupAt)).total_seconds() / 3600
        color = _OK_COLOR if ageHours < _WARN_AGE_HOURS else (_WARN_COLOR if ageHours < _CRIT_AGE_HOURS else _CRIT_COLOR)
        self._statusLabel.setText(
            f"Last backup: {_formatAge(datetime.fromisoformat(lastBackupAt))}  ·  "
            f"{len(self.backups)} backup(s)  ·  {_formatBytes(totalSize)} used  ·  "
            f"{_formatBytes(freeBytes)} free"
        )
        self._statusLabel.setStyleSheet(f"color: {color}; font-weight: bold;")

    def _backupNow(self):
        self._btnBackupNow.setEnabled(False)

        def on_done(err, _):
            self._btnBackupNow.setEnabled(True)
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, 'Backups', err)
                return
            QMessageBox.information(self, 'Backups', 'Backup created successfully.')
            self.refresh()

        self.window()._refreshOverlay.showBusy()
        ClientRequests.createBackup(self.loggedUser, callback=on_done)

    def _showContextMenu(self, pos: QPoint):
        index = self.tbl.indexAt(pos)
        if not index.isValid():
            return
        name = self.tbl.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self.tbl)
        actionDownload = QAction(qta.icon('fa6s.download'), 'Download…', self.tbl)
        actionDelete = QAction(qta.icon('fa5s.trash'), 'Delete', self.tbl)
        actionDownload.triggered.connect(lambda: self._downloadBackup(name))
        actionDelete.triggered.connect(lambda: self._deleteBackup(name))
        menu.addAction(actionDownload)
        menu.addAction(actionDelete)
        menu.exec(self.tbl.mapToGlobal(pos))

    def _downloadBackup(self, name: str):
        destRoot = QFileDialog.getExistingDirectory(self, 'Select destination folder')
        if not destRoot:
            return
        destDir = os.path.join(destRoot, name)
        os.makedirs(destDir, exist_ok=True)

        def on_files_done(err, result):
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, 'Backups', err)
                return
            with open(os.path.join(destDir, result['filename']), 'wb') as f:
                f.write(result['content'])
            QMessageBox.information(self, 'Backups', f"Backup '{name}' downloaded to:\n{destDir}")

        def on_dump_done(err, result):
            if err:
                self.window()._refreshOverlay.hideBusy()
                QMessageBox.warning(self, 'Backups', err)
                return
            with open(os.path.join(destDir, result['filename']), 'wb') as f:
                f.write(result['content'])
            ClientRequests.downloadBackupFile(self.loggedUser, name, 'files', callback=on_files_done)

        self.window()._refreshOverlay.showBusy()
        ClientRequests.downloadBackupFile(self.loggedUser, name, 'dump', callback=on_dump_done)

    def _deleteBackup(self, name: str):
        reply = QMessageBox.question(
            self, 'Delete Backup', f"Are you sure you want to delete backup '{name}'? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, 'Backups', err)
                return
            self.refresh()

        self.window()._refreshOverlay.showBusy()
        ClientRequests.deleteBackup(self.loggedUser, name, callback=on_done)
