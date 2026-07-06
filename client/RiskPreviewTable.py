import re
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QPushButton, QDialog, QMessageBox,
                              QMenu, QDialogButtonBox)
from PyQt6.QtGui import QAction
import qtawesome as qta

from PTWData import RiskItem
from i18n import t


class RiskItemsTable(QWidget):
    """Flat table of risk items: Hazard / Effect / Free Analysis / Control / Controlled Analysis / Evaluation."""

    COLUMN_LABELS = ['Hazard', 'Effect', 'Free\nAnalysis', 'Control', 'Controlled\nAnalysis', 'Evaluation']
    FIELDS        = ['hazard', 'effect', 'free_analysis', 'ctrl', 'ctrl_analysis', 'eval']
    TABLE_WIDTH_WEIGHTS = [30, 33, 20, 52, 20, 20]

    def __init__(self, parent, items: list[RiskItem], readonly: bool):
        super().__init__(parent)
        self.readonly = readonly

        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lyt)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(len(self.COLUMN_LABELS))
        self.tbl.setHorizontalHeaderLabels([t(l) for l in self.COLUMN_LABELS])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.horizontalHeader().setMinimumHeight(44)
        self.tbl.verticalHeader().hide()
        self.tbl.setWordWrap(True)
        self.tbl.setAlternatingRowColors(True)
        lyt.addWidget(self.tbl)

        if readonly:
            self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        else:
            self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            self.tbl.customContextMenuRequested.connect(self._showContextMenu)

            btnLyt = QHBoxLayout()
            self.btnAddRow = QPushButton(qta.icon('fa6s.plus'), t('Add Row'))
            self.btnPrint  = QPushButton(qta.icon('fa6s.print'), t('Print Preview'))
            self.btnAddRow.clicked.connect(self.addBlankRow)
            self.btnPrint.clicked.connect(self.printPreview)
            btnLyt.addWidget(self.btnAddRow)
            btnLyt.addWidget(self.btnPrint)
            btnLyt.addStretch()
            lyt.addLayout(btnLyt)

        for item in items:
            self._addRow(item)
        self.tbl.resizeRowsToContents()
        self._applyColumnWidths()

    def resizeEvent(self, event):
        self._applyColumnWidths()
        return super().resizeEvent(event)

    def showEvent(self, event):
        # Inside a QStackedWidget tab, this widget may stay hidden (viewport width not yet
        # realized) until the tab is actually switched to — resizeEvent alone won't catch that.
        self._applyColumnWidths()
        return super().showEvent(event)

    def _applyColumnWidths(self):
        total = self.tbl.viewport().width()
        if total <= 0:
            return
        weightSum = sum(self.TABLE_WIDTH_WEIGHTS)
        # Last column is covered by setStretchLastSection(True), so it doesn't need an explicit width.
        for col, weight in enumerate(self.TABLE_WIDTH_WEIGHTS[:-1]):
            self.tbl.setColumnWidth(col, max(1, int(total * weight / weightSum)))

    def _addRow(self, item: RiskItem):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for col, field in enumerate(self.FIELDS):
            cellItem = QTableWidgetItem(str(getattr(item, field) or ''))
            if self.readonly:
                cellItem.setFlags(cellItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(row, col, cellItem)

    def addBlankRow(self):
        self._addRow(RiskItem())
        self.tbl.resizeRowsToContents()
        self.tbl.scrollToBottom()
        newItem = self.tbl.item(self.tbl.rowCount() - 1, 0)
        self.tbl.setCurrentItem(newItem)
        self.tbl.editItem(newItem)

    def printPreview(self):
        from ReportGenerator import ReportGenerator
        items = self.getRiskItems()
        # ReportGenerator.riskAssessmentReport(items, title=t('Risk Assessment Preview'))

    def _showContextMenu(self, pos: QPoint):
        if not self.tbl.indexAt(pos).isValid():
            return
        menu = QMenu(self.tbl)
        actionDelete = QAction(t('Delete Row'), self.tbl)
        actionDelete.triggered.connect(self.deleteSelectedRows)
        menu.addAction(actionDelete)
        menu.exec(self.tbl.mapToGlobal(pos))

    def deleteSelectedRows(self):
        rows = sorted(set(i.row() for i in self.tbl.selectedIndexes() if i.isValid()), reverse=True)
        for row in rows:
            self.tbl.removeRow(row)

    def getRiskItems(self) -> list[RiskItem]:
        items = []
        for row in range(self.tbl.rowCount()):
            values = {}
            for col, field in enumerate(self.FIELDS):
                cell = self.tbl.item(row, col)
                values[field] = cell.text().strip() if cell else ''
            items.append(RiskItem(**values))
        return items

    def validate(self) -> str:
        for row, item in enumerate(self.getRiskItems()):
            if any(not getattr(item, f) for f in self.FIELDS):
                return t('Row {row}: please fill in all fields').format(row=row + 1)
            if not re.fullmatch(r'\d[A-Z]', item.free_analysis):
                return t('Row {row}: Free Analysis must be a single digit followed by a single uppercase letter').format(row=row + 1)
            if not re.fullmatch(r'\d[A-Z]', item.ctrl_analysis):
                return t('Row {row}: Controlled Analysis must be a single digit followed by a single uppercase letter').format(row=row + 1)
        return None


class DialogRiskPreview(QDialog):
    def __init__(self, parent, items: list[RiskItem], label: str = "Risk Assessment Preview"):
        super().__init__(parent)
        self.setWindowTitle(t(label))

        lyt = QVBoxLayout()
        self.setLayout(lyt)

        self.table = RiskItemsTable(self, items, readonly=False)
        lyt.addWidget(self.table, stretch=1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        btns.addButton(t('Finish'), QDialogButtonBox.ButtonRole.AcceptRole)
        btns.accepted.connect(self._onFinish)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

        if parent:
            self.resize(int(parent.width() * 0.9), int(parent.height() * 0.7))

    def _onFinish(self):
        err = self.table.validate()
        if err:
            QMessageBox.warning(self, t("Invalid Data"), err)
            return
        self.accept()

    def getRiskItems(self) -> list[RiskItem]:
        return self.table.getRiskItems()
