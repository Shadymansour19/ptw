"""PTW-specific risk assessment editor: the flat risk-item table shown on a PTW's Risks tab.

Provides the single-item editor (`DialogRiskItem`), the flat risk-items table
used across a PTW's new/edit/view modes (`RiskItemsTable`, with add/delete/
import/generic-pick and dedup logic), the generic-library picker
(`DialogSelectGenericRisks`), and the `RiskAssessmentPreview()` factory that
wraps a `RiskItemsTable` as either a popup dialog or an embeddable widget.
"""

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
from models.PTW import RiskItem, RiskAssessment, riskItemKey
from helper.utils import parseTabularFile
from helper.i18n import t



class DialogRiskItem(QDialog):
    """Form dialog for viewing or editing a single `RiskItem`'s six fields.

    Reused both to create a brand-new item and, via double-click on an
    existing row, to edit one in place; `readonly` switches between the two
    presentations without changing the field layout.
    """

    def __init__(self, parent, riskItem: RiskItem = None, readonly: bool = False):
        """Build the form, pre-filling it from `riskItem` if given and locking fields when `readonly`."""
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
        """Validate the form fields and, if valid, write them into `self.riskItem` and accept the dialog.

        Requires all six fields non-empty and both analysis fields to match a
        single digit followed by a single uppercase letter; shows a warning
        and leaves the dialog open otherwise.
        """
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
    """Flat, read-only-cell table of `RiskItem` rows backing a PTW's risk assessment.

    Used in all three PTW dialog modes (new/edit/view) as the sole risk-items
    UI — there is no separate preview state, the table's rows *are* the data.
    Rows can be populated by manual entry, picking from the generic library,
    or Excel/CSV import, and every addition/edit path is deduplicated via
    `riskItemKey()`: a new item that exactly matches (case/whitespace-insensitive,
    across all 6 fields) one already present is rejected, and an in-place edit
    that would collide with a *different* existing row is discarded and reverted.
    """

    COLUMN_LABELS = ['Hazard', 'Effect', 'Free Analysis', 'Control', 'Controlled Analysis', 'Evaluation']
    FIELDS        = ['hazard', 'effect', 'free_analysis', 'ctrl', 'ctrl_analysis', 'eval']
    TABLE_WIDTH_WEIGHTS = [30, 33, 20, 52, 20, 20]
    ROW_PADDING = 20

    def __init__(self, parent, items: list[RiskItem], readonly: bool = True):
        """Build the table widget and populate it with `items`.

        Args:
            items: the live list of RiskItem objects this table displays and
                mutates in place (rows added/removed here also update `items`).
        """
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
        """Reapply proportional column widths whenever the widget is resized."""
        self._applyColumnWidths()
        return super().resizeEvent(event)

    def showEvent(self, event):
        """Reapply proportional column widths whenever the widget becomes visible."""
        self._applyColumnWidths()
        return super().showEvent(event)

    def _applyColumnWidths(self):
        """Distribute the table's width across columns per `TABLE_WIDTH_WEIGHTS` and re-wrap row heights."""
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
        """Open `row` in `DialogRiskItem` for view/edit; on edit, revert the row if it would duplicate another.

        Edits apply directly to the shared `RiskItem` object, so a rejected
        edit restores the pre-edit copy taken before the dialog was opened.
        """
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
        """Append a new, non-editable table row rendering `item`'s fields."""
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
        """Overwrite an existing row's cell text to match `item`'s current field values."""
        for col, field in enumerate(self.FIELDS):
            cellItem = self.tbl.item(row, col)
            if not cellItem:
                cellItem = QTableWidgetItem()
                self.tbl.setItem(row, col, cellItem)
            cellItem.setText(str(getattr(item, field) or ''))
        self._resizeRowWithPadding(row)

    def _resizeRowWithPadding(self, row: int):
        """Size `row` to fit its wrapped content plus `ROW_PADDING` extra pixels."""
        self.tbl.resizeRowToContents(row)
        self.tbl.setRowHeight(row, self.tbl.rowHeight(row) + self.ROW_PADDING)

    def _isDuplicate(self, item: RiskItem, excludeRow: int = None) -> bool:
        """Return whether `item` exactly matches (via `riskItemKey`) any other row, optionally ignoring `excludeRow`."""
        key = riskItemKey(item)
        return any(riskItemKey(other) == key for i, other in enumerate(self.riskItems) if i != excludeRow)

    def addItem(self, item: RiskItem) -> bool:
        """Append `item` as a new row unless it duplicates an existing one.

        Returns:
            True if the item was added, False if it was rejected as a duplicate.
        """
        if self._isDuplicate(item):
            return False
        self.riskItems.append(item)
        self._addRow(item)
        return True

    def addRiskItemsDialog(self):
        """Prompt the user to add items manually, from the generic library, or by Excel/CSV import."""
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
        """Open a blank `DialogRiskItem` and add the resulting item, warning if it duplicates an existing row."""
        riskItem = RiskItem()
        dlg = DialogRiskItem(self, riskItem, readonly=False)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not self.addItem(riskItem):
            QMessageBox.information(self, "Duplicate Item", "An identical risk item already exists — not added again.")

    def importRiskItemsFromExcel(self):
        """Prompt for an Excel/CSV file, parse it, and add the resulting items, reporting skipped duplicates/errors."""
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
        """Open the generic-library picker and add the selected assessments' items, reporting skipped duplicates."""
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
        """Confirm with the user, then remove all checked/selected rows from the table and `riskItems`."""
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
        """Read the table's current cell contents back into a fresh list of `RiskItem` objects."""
        items = []
        for row in range(self.tbl.rowCount()):
            values = {}
            for col, field in enumerate(self.FIELDS):
                cell = self.tbl.item(row, col)
                values[field] = cell.text().strip() if cell else ''
            items.append(RiskItem(**values))
        return items

    def validate(self) -> str:
        """Check every row for required fields and valid analysis format.

        Returns:
            An error message for the first invalid row found, or None if all
            rows are valid.
        """
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
        """Parse an Excel/CSV file into `RiskItem` objects via `parseTabularFile`, validating each row.

        Blank rows are skipped silently; rows missing a required field or with
        a malformed analysis code are collected as error messages rather than
        raising, so a partially-bad file can still import its good rows.

        Returns:
            A tuple of (valid items, per-row error messages).
        """
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
        """Build the dialog around a selectable, read-only `TableRisks` over the generic library."""
        super().__init__(parent)
        self.setWindowTitle(t("Select Generic Risk Assessments"))

        # Local import: TableRisks.py imports from this module at load time too, so a
        # top-level import here would create a circular import.
        from tables.TableRisks import TableRisks
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
        """Return deep copies of every RiskItem from the checked generic assessments."""
        items = []
        for riskAssessment in self.tableRisks.getSelectedRiskAssessments():
            items.extend(copy.deepcopy(item) for item in riskAssessment.risks)
        return items


class _RiskPreviewDialog(QDialog):
    """Popup-dialog presentation of a `RiskAssessment`'s `RiskItemsTable`, with Add/Delete/Print controls.

    Not instantiated directly — use `RiskAssessmentPreview(popup=True)`.
    """

    def __init__(self, parent, riskAssessment: RiskAssessment, readonly: bool):
        """Build the labeled table and action buttons, hiding Add/Delete when `readonly`."""
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
        """Validate the table and accept the dialog, or show a warning and keep it open if invalid."""
        err = self.table.validate()
        if err:
            QMessageBox.warning(self, t("Invalid Data"), err)
            return
        self.accept()

    def getRiskItems(self) -> list[RiskItem]:
        """Return the table's current risk items."""
        return self.table.getRiskItems()
    
    def printPreview(self):
        """Render this risk assessment via `ReportGenerator.riskAssessmentReport`."""
        from reports.ReportGenerator import ReportGenerator
        ReportGenerator.riskAssessmentReport(riskAssessment=self.riskAssessment)


class _RiskPreviewWidget(QWidget):
    """Embeddable-widget presentation of a `RiskAssessment`'s `RiskItemsTable`, with Add/Delete/Print controls.

    Same content as `_RiskPreviewDialog` but a plain `QWidget` so it can be
    laid out inline rather than always floating as a top-level window; use
    `RiskAssessmentPreview(popup=False)`.
    """

    def __init__(self, parent, riskAssessment: RiskAssessment, readonly: bool):
        """Build the labeled table and action buttons, hiding Add/Delete when `readonly`."""
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
        """Return the table's current risk items."""
        return self.table.getRiskItems()

    def printPreview(self):
        """Render this risk assessment via `ReportGenerator.riskAssessmentReport`."""
        from reports.ReportGenerator import ReportGenerator
        ReportGenerator.riskAssessmentReport(riskAssessment=self.riskAssessment)


def RiskAssessmentPreview(parent, riskAssessment: RiskAssessment, readonly: bool = False, popup: bool = False):
    """QDialog carries the Qt::Dialog window flag, so it always floats as a top-level
    window and can never be embedded inline via layout.addWidget() — hence the popup
    switch between a real QDialog and a plain QWidget sharing the same content."""
    cls = _RiskPreviewDialog if popup else _RiskPreviewWidget
    return cls(parent, riskAssessment, readonly=readonly)
