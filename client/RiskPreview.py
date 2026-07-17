import copy
import re
from datetime import datetime
from PyQt6.QtCore import Qt, QPoint, QDir
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QTextEdit, QLabel, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                              QAbstractItemView, QHeaderView, QPushButton, QDialog, QMessageBox,
                              QLineEdit, QFormLayout, QMenu, QDialogButtonBox, QFileDialog)
from PyQt6.QtGui import QAction
import qtawesome as qta

from GlobalData import globalData
from PTWData import RiskItem, RiskAssessment, riskItemKey
from utils import parseTabularFile
from i18n import t



class DialogRiskItem(QDialog):
    def __init__(self, parent, riskItem: RiskItem = None, readonly: bool = False):
        super().__init__(parent)

        self.setWindowTitle(t("View mode" if readonly else "Edit mode"))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.collectData)
        btns.rejected.connect(self.reject)

        self.readonly = readonly
        self.riskItem = riskItem

        lyt = QFormLayout(self)
        lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.setLayout(lyt)

        self.txtHazard = QTextEdit(self)
        self.txtEffect = QTextEdit(self)
        self.txtFreeAnalysis = QLineEdit(self)
        self.txtControl = QTextEdit(self)
        self.txtControlledAnalysis = QLineEdit(self)
        self.txtEval = QLineEdit(self)

        lyt.addRow("Hazard:", self.txtHazard)
        lyt.addRow("Effect:", self.txtEffect)
        lyt.addRow("Free Analysis:", self.txtFreeAnalysis)
        lyt.addRow("Control:", self.txtControl)
        lyt.addRow("Controlled Analysis:", self.txtControlledAnalysis)
        lyt.addRow("Evaluation:", self.txtEval)
        lyt.addWidget(btns)

        if riskItem:
            self.txtHazard.setText(riskItem.hazard)
            self.txtEffect.setText(riskItem.effect)
            self.txtControl.setText(riskItem.ctrl)
            self.txtFreeAnalysis.setText(riskItem.free_analysis)
            self.txtControlledAnalysis.setText(riskItem.ctrl_analysis)
            self.txtEval.setText(riskItem.eval)

        for field in [self.txtHazard, self.txtEffect, self.txtControl, self.txtFreeAnalysis, self.txtControlledAnalysis, self.txtEval]:
            field.setReadOnly(readonly)

        for field in [self.txtHazard, self.txtEffect, self.txtControl]:
            field.setTabChangesFocus(True)
            field.setMinimumHeight(field.fontMetrics().lineSpacing() * 4 + 10)
            field.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            field.setAcceptRichText(False)

        if parent:
            self.resize(int(parent.width() * 0.9), int(parent.height() * 0.9))
        
    def collectData(self):
        hazard = self.txtHazard.toPlainText()
        effect = self.txtEffect.toPlainText()
        ctrl = self.txtControl.toPlainText()
        free_analysis = self.txtFreeAnalysis.text().upper()
        ctrl_analysis = self.txtControlledAnalysis.text().upper()
        eval = self.txtEval.text()

        if any(not f for f in [hazard, effect, ctrl, free_analysis, ctrl_analysis, eval]):
            QMessageBox.warning(self, "Missing Information", "Please fill in all required fields.")
            return
        if any(not re.fullmatch(r'\d[A-Z]', analysis) for analysis in [free_analysis, ctrl_analysis]):
            QMessageBox.warning(self, "Invalid Analysis", "Both analysis (Free/Controlled) must be a single digit followed by single character")
            return
        
        self.riskItem.hazard = hazard
        self.riskItem.effect = effect
        self.riskItem.ctrl = ctrl
        self.riskItem.free_analysis = free_analysis
        self.riskItem.ctrl_analysis = ctrl_analysis
        self.riskItem.eval = eval

        self.accept()

class RiskItemsTable(QWidget):
    COLUMN_LABELS = ['Hazard', 'Effect', 'Free Analysis', 'Control', 'Controlled Analysis', 'Evaluation']
    FIELDS        = ['hazard', 'effect', 'free_analysis', 'ctrl', 'ctrl_analysis', 'eval']
    TABLE_WIDTH_WEIGHTS = [30, 33, 20, 52, 20, 20]
    ROW_PADDING = 20

    def __init__(self, parent, items: list[RiskItem], readonly: bool = True):
        super().__init__(parent)
        self.readonly = readonly
        self.riskItems = items

        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        self.setLayout(lyt)

        self.tbl = QTableWidget()
        self.tbl.setColumnCount(len(self.COLUMN_LABELS))
        self.tbl.setHorizontalHeaderLabels([t(l.replace(' ', '\n')) for l in self.COLUMN_LABELS])
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl.horizontalHeader().setStretchLastSection(True)
        self.tbl.cellDoubleClicked.connect(self.viewRiskItem)
        self.tbl.horizontalHeader().setMinimumHeight(44)
        self.tbl.setWordWrap(True)
        self.tbl.setAlternatingRowColors(True)
        lyt.addWidget(self.tbl)

        for item in items:
            self._addRow(item)
        self._applyColumnWidths()

    def resizeEvent(self, event):
        self._applyColumnWidths()
        return super().resizeEvent(event)

    def showEvent(self, event):
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
        # Row heights were computed against whatever column widths existed at the time each row
        # was added (often the default, narrower ones) — recompute now that widths are final,
        # otherwise wrapped text can be sized for far narrower columns than it actually gets.
        for row in range(self.tbl.rowCount()):
            self._resizeRowWithPadding(row)

    def viewRiskItem(self, row, col):
        riskItem = self.riskItems[row]
        original = copy.copy(riskItem)
        dlg = DialogRiskItem(self, riskItem, readonly=self.readonly)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.readonly and self._isDuplicate(riskItem, excludeRow=row):
            self.riskItems[row] = original
            QMessageBox.warning(self, "Duplicate Item", "This edit makes the item identical to another existing item — change discarded.")
            return
        self.riskItems[row] = riskItem
        self._updateRow(riskItem, row)

    def _addRow(self, item: RiskItem):
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        for col, field in enumerate(self.FIELDS):
            # data = str(getattr(item, field) or '').split('\n')
            # if len(data) > 1:
            #     data = '\n'.join('• ' + line for line in data)
            # else:
            #     data = data[0]
            data = str(getattr(item, field) or '')
            cellItem = QTableWidgetItem(data)
            cellItem.setFlags(cellItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tbl.setItem(row, col, cellItem)
        self._resizeRowWithPadding(row)

    def _updateRow(self, item: RiskItem, row: int):
        for col, field in enumerate(self.FIELDS):
            cellItem = self.tbl.item(row, col)
            if not cellItem:
                cellItem = QTableWidgetItem()
                self.tbl.setItem(row, col, cellItem)
            cellItem.setText(str(getattr(item, field) or ''))
        self._resizeRowWithPadding(row)

    def _resizeRowWithPadding(self, row: int):
        self.tbl.resizeRowToContents(row)
        self.tbl.setRowHeight(row, self.tbl.rowHeight(row) + self.ROW_PADDING)

    def _isDuplicate(self, item: RiskItem, excludeRow: int = None) -> bool:
        key = riskItemKey(item)
        return any(riskItemKey(other) == key for i, other in enumerate(self.riskItems) if i != excludeRow)

    def addItem(self, item: RiskItem) -> bool:
        if self._isDuplicate(item):
            return False
        self.riskItems.append(item)
        self._addRow(item)
        return True

    def addRiskItemsDialog(self):
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle("Add Risk Items")
        msgBox.setText("How would you like to add new risk items?")
        btnManual = msgBox.addButton("&Type Manually", QMessageBox.ButtonRole.AcceptRole)
        btnGeneric = msgBox.addButton("Use &Generic Risks", QMessageBox.ButtonRole.ActionRole)
        btnImport = msgBox.addButton("Import from E&xcel", QMessageBox.ButtonRole.ActionRole)
        btnManual.setIcon(qta.icon('fa6s.keyboard'))
        btnGeneric.setIcon(qta.icon('fa6s.bookmark'))
        btnImport.setIcon(qta.icon('fa6s.file-excel'))
        msgBox.addButton(QMessageBox.StandardButton.Cancel)
        msgBox.exec()
        clicked = msgBox.clickedButton()

        if clicked == btnManual:
            self.addRiskItemManual()
        elif clicked == btnGeneric:
            self.addRiskItemsFromGenericRisks()
        elif clicked == btnImport:
            self.importRiskItemsFromExcel()

    def addRiskItemManual(self):
        riskItem = RiskItem()
        dlg = DialogRiskItem(self, riskItem, readonly=False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.addItem(riskItem):
            QMessageBox.information(self, "Duplicate Item", "An identical risk item already exists — not added again.")

    def importRiskItemsFromExcel(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select Risk Items File", QDir.homePath(), "Excel/CSV Files (*.xlsx *.csv);;Excel Files (*.xlsx);;CSV Files (*.csv);;All Files (*)")
        if not filepath:
            return

        try:
            items, errors = self._parseRiskItemsFile(filepath)
        except ValueError as e:
            QMessageBox.warning(self, "Import Failed", str(e))
            return
        except Exception as e:
            QMessageBox.warning(self, "Import Failed", f"Could not read file: {e}")
            return

        if not items and not errors:
            QMessageBox.information(self, "Import", "The selected file has no data rows.")
            return

        added = sum(self.addItem(item) for item in items)
        duplicates = len(items) - added
        parts = [f"{added} item(s) imported."]
        if duplicates:
            parts.append(f"{duplicates} duplicate(s) skipped.")
        if errors:
            parts.append(f"{len(errors)} row(s) skipped due to errors:")
            parts.extend([f" • {err}" for err in errors])
        QMessageBox.information(self, "Import", '\n'.join(parts))

    def addRiskItemsFromGenericRisks(self):
        dlg = DialogSelectGenericRisks(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        newItems = dlg.getSelectedRiskItems()
        if not newItems:
            return
        added = sum(self.addItem(item) for item in newItems)
        duplicates = len(newItems) - added
        if duplicates:
            QMessageBox.information(self, "Add From Generic Risks", f"{added} item(s) added, {duplicates} duplicate(s) skipped.")

    def deleteSelectedRows(self):
        if QMessageBox.question(
            self, 
            "Delete Selected Items", 
            "Are you sure you want to delete the selected items?", 
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
            QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        rows = sorted(set(i.row() for i in self.tbl.selectedIndexes() if i.isValid()), reverse=True)
        for row in rows:
            self.tbl.removeRow(row)
            self.riskItems.pop(row)

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

    @staticmethod
    def _parseRiskItemsFile(filepath: str) -> tuple[list[RiskItem], list[str]]:
        dataRows = parseTabularFile(filepath, RiskItemsTable.COLUMN_LABELS)

        items = []
        errors = []
        for rowNum, record in enumerate(dataRows, start=2):
            if all(not v for v in record):
                continue

            values = dict(zip(RiskItemsTable.FIELDS, record))
            values['free_analysis'] = values['free_analysis'].upper()
            values['ctrl_analysis'] = values['ctrl_analysis'].upper()

            item = RiskItem(**values)
            if any(not getattr(item, f) for f in RiskItemsTable.FIELDS):
                errors.append(f"Row {rowNum}: missing required field(s)")
                continue
            if not re.fullmatch(r'\d[A-Z]', item.free_analysis) or not re.fullmatch(r'\d[A-Z]', item.ctrl_analysis):
                errors.append(f"Row {rowNum}: Free/Controlled Analysis must be a digit followed by an uppercase letter")
                continue
            items.append(item)

        return items, errors


class DialogSelectGenericRisks(QDialog):
    """Modal picker over the generic risk assessment library, reusing TableRisks' existing
    checkbox-list UI (same as the old embedded-in-PTW-widget selector) instead of a fresh one."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(t("Select Generic Risk Assessments"))

        # Local import: TableRisks.py imports from this module at load time too, so a
        # top-level import here would create a circular import.
        from TableRisks import TableRisks
        self.tableRisks = TableRisks(self, loggedUser=None, readonly=True, selectable=True)
        self.tableRisks.setRiskAssessmentsInGUI(dict(globalData.allRiskAssessments))

        lyt = QVBoxLayout()
        self.setLayout(lyt)
        lyt.addWidget(self.tableRisks, stretch=1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lyt.addWidget(btns)

        if parent:
            self.resize(int(parent.width() * 0.9), int(parent.height() * 0.9))

    def getSelectedRiskItems(self) -> list[RiskItem]:
        items = []
        for riskAssessment in self.tableRisks.getSelectedRiskAssessments():
            items.extend(copy.deepcopy(item) for item in riskAssessment.risks)
        return items


class _RiskPreviewDialog(QDialog):
    def __init__(self, parent, riskAssessment: RiskAssessment, readonly: bool):
        super().__init__(parent)

        self.riskAssessment = riskAssessment

        lyt = QVBoxLayout()
        self.setLayout(lyt)

        label = f'PTW#{riskAssessment.ptw_id} - Specific Risk Assessment' if riskAssessment.ptw_id else riskAssessment.title or t("Risk Assessment Preview")
        self.setWindowTitle(t("View mode" if readonly else "Edit mode") + " - " + t(label))
        lbl = QLabel(label)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table = RiskItemsTable(self, riskAssessment.risks, readonly=readonly)

        btnLyt = QHBoxLayout()
        
        self.btnAddItems = QPushButton(qta.icon('fa6s.plus'), '&' + t('Add Items'))
        self.btnDeleteItems = QPushButton(qta.icon('fa6s.trash-can'), '&' + t('Delete Selected Items'))
        self.btnPrint  = QPushButton(qta.icon('fa6s.print'), '&' + t('Print Preview'))
        
        self.btnAddItems.clicked.connect(lambda: self.table.addRiskItemsDialog())
        self.btnDeleteItems.clicked.connect(lambda: self.table.deleteSelectedRows())
        self.btnPrint.clicked.connect(self.printPreview)

        if not readonly:
            btnLyt.addWidget(self.btnAddItems)
            btnLyt.addWidget(self.btnDeleteItems)
        btnLyt.addWidget(self.btnPrint)
        btnLyt.addStretch()

        lyt.addWidget(lbl, stretch=0)
        lyt.addWidget(self.table, stretch=1)
        lyt.addLayout(btnLyt)

        if not readonly:
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
    
    def printPreview(self):
        from ReportGenerator import ReportGenerator
        ReportGenerator.riskAssessmentReport(riskAssessment=self.riskAssessment)


class _RiskPreviewWidget(QWidget):
    def __init__(self, parent, riskAssessment: RiskAssessment, readonly: bool):
        super().__init__(parent)

        self.riskAssessment = riskAssessment

        lyt = QVBoxLayout()
        self.setLayout(lyt)

        label = f'PTW#{riskAssessment.ptw_id} - Specific Risk Assessment' if riskAssessment.ptw_id else riskAssessment.title or t("Risk Assessment Preview")
        lbl = QLabel(t(label))
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table = RiskItemsTable(self, riskAssessment.risks, readonly=readonly)

        btnLyt = QHBoxLayout()
        
        self.btnAddItems = QPushButton(qta.icon('fa6s.plus'), '&' + t('Add Items'))
        self.btnDeleteItems = QPushButton(qta.icon('fa6s.trash-can'), '&' + t('Delete Selected Items'))
        self.btnPrint  = QPushButton(qta.icon('fa6s.print'), '&' + t('Print Preview'))
        
        self.btnAddItems.clicked.connect(lambda: self.table.addRiskItemsDialog())
        self.btnDeleteItems.clicked.connect(lambda: self.table.deleteSelectedRows())
        self.btnPrint.clicked.connect(self.printPreview)

        if not readonly:
            btnLyt.addWidget(self.btnAddItems)
            btnLyt.addWidget(self.btnDeleteItems)
        btnLyt.addWidget(self.btnPrint)
        btnLyt.addStretch()

        lyt.addWidget(lbl, stretch=0)
        lyt.addWidget(self.table, stretch=1)
        lyt.addLayout(btnLyt)

    def getRiskItems(self) -> list[RiskItem]:
        return self.table.getRiskItems()

    def printPreview(self):
        from ReportGenerator import ReportGenerator
        ReportGenerator.riskAssessmentReport(riskAssessment=self.riskAssessment)


def RiskAssessmentPreview(parent, riskAssessment: RiskAssessment, readonly: bool = False, popup: bool = False):
    """QDialog carries the Qt::Dialog window flag, so it always floats as a top-level
    window and can never be embedded inline via layout.addWidget() — hence the popup
    switch between a real QDialog and a plain QWidget sharing the same content."""
    cls = _RiskPreviewDialog if popup else _RiskPreviewWidget
    return cls(parent, riskAssessment, readonly=readonly)
