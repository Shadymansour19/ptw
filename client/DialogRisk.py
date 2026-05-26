from datetime import datetime
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QWidget, QFormLayout, QVBoxLayout, QHBoxLayout,
                              QStackedWidget, QTextEdit, QLineEdit, QPushButton, QLabel,
                              QDialogButtonBox, QMessageBox, QApplication, QStyle)
from PyQt6.QtGui import QFont
import re

from PTWData import RiskAssessment, RiskItem
from GlobalData import globalData


class DialogRiskAssessment(QDialog):
    class RiskItemWidget(QWidget):
        def __init__(self, parent, risk: RiskItem, readonly: bool):
            super().__init__(parent)

            self.readonly = readonly
            self.risk = risk

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

            self.txtHazard.setText(risk.hazard)
            self.txtEffect.setText(risk.effect)
            self.txtControl.setText(risk.ctrl)
            self.txtFreeAnalysis.setText(risk.free_analysis)
            self.txtControlledAnalysis.setText(risk.ctrl_analysis)
            self.txtEval.setText(risk.eval)

            self.txtHazard.setReadOnly(readonly)
            self.txtEffect.setReadOnly(readonly)
            self.txtControl.setReadOnly(readonly)
            self.txtFreeAnalysis.setReadOnly(readonly)
            self.txtControlledAnalysis.setReadOnly(readonly)
            self.txtEval.setReadOnly(readonly)

            self.txtHazard.setTabChangesFocus(True)
            self.txtEffect.setTabChangesFocus(True)
            self.txtControl.setTabChangesFocus(True)

            self.txtHazard.setMinimumHeight(self.txtHazard.fontMetrics().lineSpacing() * 3 + 10)
            self.txtHazard.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.txtHazard.setAcceptRichText(False)
            
            self.txtEffect.setMinimumHeight(self.txtEffect.fontMetrics().lineSpacing() * 3 + 10)
            self.txtEffect.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.txtEffect.setAcceptRichText(False)

            self.txtControl.setMinimumHeight(self.txtEffect.fontMetrics().lineSpacing() * 5 + 10)
            self.txtControl.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
            self.txtControl.setAcceptRichText(False)

        def collectData(self):
            self.risk.hazard = self.txtHazard.toPlainText()
            self.risk.effect = self.txtEffect.toPlainText()
            self.risk.ctrl = self.txtControl.toPlainText()
            self.risk.free_analysis = self.txtFreeAnalysis.text().upper()
            self.risk.ctrl_analysis = self.txtControlledAnalysis.text().upper()
            self.risk.eval = self.txtEval.text()

            if any(not f for f in [self.risk.hazard, self.risk.effect, self.risk.ctrl, self.risk.free_analysis, self.risk.ctrl_analysis, self.risk.eval]):
                raise Exception('Please fill in all required fields')
            if any(not re.fullmatch(r'\d[A-Z]', analysis) for analysis in [self.risk.free_analysis, self.risk.ctrl_analysis]):
                raise Exception('Both analysis must be a single digit followed by single character')
        

    def __init__(self, parent, readonly: bool, riskAssessment: RiskAssessment, label: str=""):
        super().__init__(parent)
        self.setWindowTitle(label)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)

        self.riskAssessment = riskAssessment
        self.readonly = readonly

        lyt = QVBoxLayout()
        self.setLayout(lyt)

        self.btnPrev = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), 'Prev')
        self.btnNext = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward), 'Next')
        self.btnNew  = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), 'New')
        self.btnDelete = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), 'Delete')

        lytCtrl = QHBoxLayout()
        self.stack = QStackedWidget()
        self.txtTitle = QLineEdit()
        self.txtDate = QLineEdit()
        self.lblPageNum = QLabel(alignment=Qt.AlignmentFlag.AlignCenter, font=QFont('monospace', 12))

        lytCtrl.addStretch()
        if not readonly:
            lytCtrl.addWidget(self.btnDelete, stretch=0)
        lytCtrl.addWidget(self.btnPrev, stretch=0)
        lytCtrl.addWidget(self.lblPageNum, stretch=0)
        lytCtrl.addWidget(self.btnNext, stretch=0)
        if not readonly:
            lytCtrl.addWidget(self.btnNew, stretch=0)
        lytCtrl.addStretch()
        lytCtrl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.collectData)
        btns.rejected.connect(self.reject)

        lyt.addWidget(self.txtTitle)
        lyt.addWidget(self.txtDate)
        lyt.addWidget(self.stack)
        lyt.addLayout(lytCtrl)
        lyt.addWidget(btns)

        self.txtTitle.setPlaceholderText('Risk Assessment Title')
        self.txtTitle.setToolTip('Risk Assessment Title')
        self.txtTitle.setStyleSheet("QLineEdit[error='True'] {border: 1px solid red; border-radius: 2px;}")
        
        self.txtDate.setPlaceholderText('Last Update Date')
        self.txtDate.setToolTip('Last Update Date')

        self.lblPageNum.setFixedWidth(self.lblPageNum.fontMetrics().lineSpacing() * 5)

        self.txtTitle.setReadOnly(readonly)
        self.txtDate.setReadOnly(True)
        self.lblPageNum.setEnabled(False)

        if riskAssessment.title:
            self.txtTitle.setText(riskAssessment.title)
            self.txtTitle.setReadOnly(True)
            self.txtDate.setText(riskAssessment.date)
            self.isNew = False
        else:
            self.txtDate.setText(datetime.now().strftime('%d %b %Y'))
            self.isNew = True
        
        for riskItem in riskAssessment.risks:
            widget = DialogRiskAssessment.RiskItemWidget(self.stack, riskItem, readonly)
            self.stack.addWidget(widget)
        if not riskAssessment.risks:
            self.newRiskItem()

        self.btnNext.clicked.connect(lambda: self.stack.setCurrentIndex(self.stack.currentIndex() + 1))
        self.btnPrev.clicked.connect(lambda: self.stack.setCurrentIndex(self.stack.currentIndex() - 1))
        self.btnNew.clicked.connect(self.newRiskItem)
        self.btnDelete.clicked.connect(self.deleteRiskItem)
        self.stack.currentChanged.connect(self.stackTabChanged)
        self.txtTitle.textChanged.connect(self.checkRiskTitle)

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.7))

        self.stackTabChanged()


    def checkRiskTitle(self):
        title = self.txtTitle.text()
        self.txtTitle.setProperty('error', str(title != self.riskAssessment.title and title in globalData.allRiskAssessments))
        self.txtTitle.style().unpolish(self.txtTitle)
        self.txtTitle.style().polish(self.txtTitle)

    def stackTabChanged(self):
        tabIdx = self.stack.currentIndex()
        self.btnNext.setEnabled(tabIdx < self.stack.count() - 1)
        self.btnPrev.setEnabled(tabIdx > 0)
        self.lblPageNum.setText(f'{tabIdx + 1} / {self.stack.count()}')
        self.btnDelete.setEnabled(self.stack.count() > 1 and not self.readonly)

    def newRiskItem(self):
        newRisk = RiskItem()
        widget = DialogRiskAssessment.RiskItemWidget(self.stack, newRisk, False)
        self.stack.addWidget(widget)
        self.stack.setCurrentIndex(self.stack.count() - 1)

    def deleteRiskItem(self):
        reply = QMessageBox.question(self, 'Delete Risk', f"Are you sure you want to delete current risk item?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.No:
            return
        self.stack.removeWidget(self.stack.currentWidget())
    
    def collectData(self):
        if self.readonly:
            self.accept()
            return
        
        if not self.txtTitle.text():
            QMessageBox.critical(self, "Invalid Data", 'Please fill in Risk Assessment Title')
            return
        
        self.riskAssessment.title = self.txtTitle.text()
        if not self.readonly:
            self.riskAssessment.date = datetime.now().strftime('%d %b %Y')
        
        self.riskAssessment.risks.clear()
        for i in range(self.stack.count()):
            try:
                self.stack.widget(i).collectData()
                riskItem = self.stack.widget(i).risk
                self.riskAssessment.addRiskItem(riskItem)
            except Exception as e:
                self.stack.setCurrentIndex(i)
                QMessageBox.warning(self, "Invalid Data", str(e))
                return
        self.accept()
