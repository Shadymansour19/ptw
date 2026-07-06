import copy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton,
                              QLabel, QListWidget, QListWidgetItem, QMessageBox, QDialog)
from PyQt6.QtGui import QFont
import qtawesome as qta

from clientRequests import ClientRequests
from DialogRisk import DialogRiskAssessment
from PTWData import RiskAssessment
from User import User

class TableRisks(QWidget):
    class RecordWidget(QWidget):
        MAX_DISPLAY_NAME_LENGTH = 50

        checkRiskChanged = pyqtSignal(str)
        viewRiskClicked = pyqtSignal(str)
        editRiskClicked = pyqtSignal(str)
        # deleteRiskClicked = pyqtSignal(str)

        def __init__(self, parent, riskTitle: str, readonly: bool = True, selectable: bool = True):
            super().__init__(parent)

            lyt = QHBoxLayout()
            self.setLayout(lyt)

            self.riskTitle = riskTitle
            self.btnCheck = QCheckBox()
            self.btnView = QPushButton(qta.icon('fa6s.eye'), 'View')
            self.btnEdit = QPushButton(qta.icon('fa6s.pen'), 'Edit')
            # self.btnDelete = QPushButton(qta.icon('fa6s.trash'), 'Delete')

            self.btnCheck.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px }')

            self.btnCheck.clicked.connect(lambda: self.checkRiskChanged.emit(riskTitle))
            self.btnView.clicked.connect(lambda: self.viewRiskClicked.emit(riskTitle))
            self.btnEdit.clicked.connect(lambda: self.editRiskClicked.emit(riskTitle))
            # self.btnDelete.clicked.connect(lambda: self.deleteRiskClicked.emit(riskTitle))

            displayName = riskTitle[:self.MAX_DISPLAY_NAME_LENGTH] + ("..." if len(riskTitle) > self.MAX_DISPLAY_NAME_LENGTH else "")
            if selectable:
                lyt.addWidget(self.btnCheck, stretch=0)
            lyt.addWidget(QLabel(displayName, font=QFont('Helvetica', 16), alignment=Qt.AlignmentFlag.AlignCenter), stretch=1)
            lyt.addWidget(self.btnView, stretch=0)
            if not readonly:
                lyt.addWidget(self.btnEdit, stretch=0)
                # lyt.addWidget(self.btnDelete, stretch=0)


    def __init__(self, parent, loggedUser: User, label: str = None, risks: dict[str, RiskAssessment] = {}, readonly: bool = True, selectable: bool = True):
        super().__init__(parent)
        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.setSpacing(4)
        self.loggedUser = loggedUser
        self.readonly = readonly
        self.selectable = selectable
        self.risks: dict[str, RiskAssessment] = risks or {}

        self.lstRisks = QListWidget()
        self.setLayout(lyt)
        self.setAutoFillBackground(False)

        self.label = label
        if label:
            lbl = QLabel(label)
            lbl.setFont(QFont("Helvetica", 16, QFont.Weight.Bold))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lyt.addWidget(lbl)

        lyt.addWidget(self.lstRisks)
        self.lstRisks.itemDoubleClicked.connect(self.itemDoubleClicked)
        self.lstRisks.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.lstRisks.itemSelectionChanged.connect(self.setCheckBoxes)
        self.lstRisks.setStyleSheet("QListWidget { background: transparent; }")
        self.lstRisks.viewport().setAutoFillBackground(False)
        for riskTitle in self.risks:
            self.addRiskToGUI(riskTitle)

    def getSelectedRiskAssessments(self) -> list[RiskAssessment]:
        selected: list[RiskAssessment] = []
        for item in self.lstRisks.selectedItems():
            riskRecord: TableRisks.RecordWidget = self.lstRisks.itemWidget(item)
            selected.append(self.risks[riskRecord.riskTitle])
        return selected
    
    def checkRisk(self, title):
        for i in range(self.lstRisks.count()):
            item: QListWidgetItem = self.lstRisks.item(i)
            riskRecord: TableRisks.RecordWidget = self.lstRisks.itemWidget(item)
            if riskRecord.riskTitle == title:
                item.setSelected(True)
                break

    def clear(self):
        self.risks.clear()
        self.lstRisks.clear()
    
    def addRiskToGUI(self, riskTitle: str):
        item = QListWidgetItem()
        record = TableRisks.RecordWidget(self, riskTitle, self.readonly, self.selectable)
        item.setSizeHint(record.sizeHint())
        if self.selectable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsSelectable)
        else:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.lstRisks.addItem(item)
        self.lstRisks.setItemWidget(item, record)
        record.checkRiskChanged.connect(lambda riskTitle: self.checkRiskStateUpdate(riskTitle))
        record.viewRiskClicked.connect(lambda riskTitle: self.viewRiskAssessment(riskTitle))
        record.editRiskClicked.connect(lambda riskTitle: self.editRiskAssessment(riskTitle))
        # record.deleteRiskClicked.connect(lambda riskTitle: self.deleteRiskAssessment(riskTitle))

    def setRiskAssessmentsInGUI(self, risks: dict[str, RiskAssessment]):
        self.lstRisks.clear()
        self.risks = risks
        for riskTitle in self.risks:
            self.addRiskToGUI(riskTitle)

    def refreshGUI(self):
        self.lstRisks.clear()
        for riskTitle in self.risks:
            self.addRiskToGUI(riskTitle)

    def addRiskAssessment(self, riskAssessment: RiskAssessment):
        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.risks[riskAssessment.title] = riskAssessment
            self.addRiskToGUI(riskAssessment.title)
        ClientRequests.addNewRiskAssessment(self.loggedUser, riskAssessment, callback=on_done)
    
    def itemDoubleClicked(self, item: QListWidgetItem):
        riskRecord: TableRisks.RecordWidget = self.lstRisks.itemWidget(item)
        self.viewRiskAssessment(riskRecord.riskTitle)

    def checkRiskStateUpdate(self, riskTitle: str):
        for i in range(self.lstRisks.count()):
            item: QListWidgetItem = self.lstRisks.item(i)
            riskRecord: TableRisks.RecordWidget = self.lstRisks.itemWidget(item)
            if riskRecord.riskTitle == riskTitle:
                item.setSelected(riskRecord.btnCheck.isChecked())
                break
    
    def setCheckBoxes(self):
        for i in range(self.lstRisks.count()):
            item: QListWidgetItem = self.lstRisks.item(i)
            riskRecord: TableRisks.RecordWidget = self.lstRisks.itemWidget(item)
            riskRecord.btnCheck.setChecked(item.isSelected())

    def viewRiskAssessment(self, riskTitle: str):
        dialog = DialogRiskAssessment(self, True, self.risks[riskTitle], f"View Mode - Risk Assessment {riskTitle}")
        dialog.exec()

    def editRiskAssessment(self, riskTitle: str):
        riskAssessment = copy.deepcopy(self.risks[riskTitle])
        dialog = DialogRiskAssessment(self, False, riskAssessment, f"Edit Mode - Risk Assessment {riskTitle}")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.risks[riskTitle] = riskAssessment
        ClientRequests.updateRiskAssessment(self.loggedUser, riskAssessment, callback=on_done)
    
    def deleteRiskAssessment(self, riskTitle: str):
        reply = QMessageBox.question(self, 'Delete Risk Assessment', f"Are you sure you want to delete Risk Assessment '{riskTitle}'?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return

        def on_done(err, _):
            if err:
                QMessageBox.warning(self, "Fail", err)
                return
            self.risks.pop(riskTitle)
            self.refreshGUI()
        ptw_id = self.risks[riskTitle].ptw_id if riskTitle in self.risks else None
        ClientRequests.deleteRiskAssessment(self.loggedUser, riskTitle, ptw_id, callback=on_done)
    
    def addNewRiskAssessmentDialog(self):
        newRiskAssessment = RiskAssessment()
        dialog = DialogRiskAssessment(self, True, newRiskAssessment, "New Risk Assessment")
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.addRiskAssessment(newRiskAssessment)