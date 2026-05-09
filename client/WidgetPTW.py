from datetime import date
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *

from PTWData import PTWData, Attachment
from TableRisks import TableRisks
from TableAttachments import TableAttachments
from GlobalData import globalData
from ReportGenerator import ReportGenerator
from clientRequests import ClientRequests
from TableIsolation import TableIsolation
from functools import partial
import qtawesome as qta

class DialogPTW(QDialog):
    GRID_LYT_COLS = 3
    def __init__(self, parent, loggedUser, ptw: PTWData, referencePTW: PTWData, new: bool, readOnly: bool, lbl: str):
        super().__init__(parent)

        self.setWindowTitle(lbl)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)
        self.ptw = ptw
        self.referencePTW = referencePTW
        self.new = new
        self.loggedUser = loggedUser
        self.readonly = readOnly
        self.requiredAttachs = self.ptw.requiredAttachs()

        attachs = []

        if not new:
            err, attachNames = ClientRequests.getPtwAttachmentNames(loggedUser, self.ptw.id)
            if err:
                QMessageBox.warning(parent, "Error", f"Failed to fetch attachments: {err}")
            else:
                attachs = [Attachment(remoteName=name, uploaded=True) for name in attachNames]

        if referencePTW is not None:
            err, refAttachNames = ClientRequests.getPtwAttachmentNames(loggedUser, referencePTW.id)
            if err:
                QMessageBox.warning(parent, "Error", f"Failed to fetch reference PTW attachments: {err}")
            else:
                attachs.extend([Attachment(remoteName=name, uploaded=True) for name in refAttachNames])

        lyt = QVBoxLayout()
        lytTabs = QHBoxLayout()
        lytBtns = QHBoxLayout()
        self.stack = QStackedWidget()
        self.btnBack = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), 'Back')
        self.btnNext = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward), 'Next')
        self.btnFinish = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton), 'Finish')
        self.btnCancel = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), 'Cancel')
        
        self.setLayout(lyt)
        lyt.addLayout(lytTabs)
        lyt.addWidget(self.stack)
        lyt.addLayout(lytBtns)

        lytBtns.addStretch()
        lytBtns.addWidget(self.btnBack, stretch=0)
        lytBtns.addWidget(self.btnNext, stretch=0)
        lytBtns.addWidget(self.btnFinish, stretch=0)
        lytBtns.addWidget(self.btnCancel, stretch=0)

        self.tabBasicInfo = QWidget(self.stack)
        self.tabTools     = QWidget(self.stack)
        self.tabHazards   = QWidget(self.stack)
        self.tabControls  = QWidget(self.stack)
        self.tabRisks     = TableRisks(self.stack, self.loggedUser, readonly=True, selectable=not readOnly)
        self.tabIsolation = QWidget(self.stack)
        self.tabMiwiMos = QWidget(self.stack)
        self.tabAttachments = QWidget(self.stack)

        lytBasicInfo = QFormLayout()
        lytBasicInfo.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lytTools = QGridLayout()
        lytHazards = QGridLayout()
        lytControls = QGridLayout()
        lytIsolation = QVBoxLayout()
        lytMiwiMos = QFormLayout()
        lytMiwiMos.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lytAttachments = QVBoxLayout()

        self.tabBasicInfo.setLayout(lytBasicInfo)
        self.tabTools.setLayout(lytTools)
        self.tabHazards.setLayout(lytHazards)
        self.tabControls.setLayout(lytControls)
        self.tabIsolation.setLayout(lytIsolation)
        self.tabMiwiMos.setLayout(lytMiwiMos)
        self.tabAttachments.setLayout(lytAttachments)

        # self.btnBasicInfo = QPushButton(qta.icon("mdi6.file-document-outline"), 'Basic Info')
        # self.btnTools     = QPushButton(qta.icon("fa6s.wrench"), 'Tools')
        # self.btnHazards   = QPushButton(qta.icon("mdi.alert-octagon-outline"), 'Hazards')
        # self.btnControls  = QPushButton(qta.icon("fa6s.shield-halved"), 'Controls')
        # self.btnRisks     = QPushButton(qta.icon("fa5s.exclamation-triangle"), 'Risks')
        # self.btnIsolation = QPushButton(qta.icon("fa6s.unlock-keyhole"), 'Isolation')
        # self.btnMiwiMos   = QPushButton(qta.icon("fa6.rectangle-list"), 'MIWI/MOS')
        # self.btnAttachments = QPushButton(qta.icon("fa6s.paperclip"), 'Attachs')

        self.btnBasicInfo = QToolButton()
        self.btnBasicInfo.setText("Basic Info")
        self.btnBasicInfo.setIcon(qta.icon("mdi6.file-document-outline"))

        self.btnTools     = QToolButton()
        self.btnTools.setText("Tools")
        self.btnTools.setIcon(qta.icon("fa6s.wrench"))

        self.btnHazards   = QToolButton()
        self.btnHazards.setText("Hazards")
        self.btnHazards.setIcon(qta.icon("mdi.alert-octagon-outline"))

        self.btnControls  = QToolButton()
        self.btnControls.setText("Controls")
        self.btnControls.setIcon(qta.icon("fa6s.shield-halved"))

        self.btnRisks     = QToolButton()
        self.btnRisks.setText("Risks")
        self.btnRisks.setIcon(qta.icon("fa5s.exclamation-triangle"))

        self.btnIsolation = QToolButton()
        self.btnIsolation.setText("Isolation")
        self.btnIsolation.setIcon(qta.icon("fa6s.unlock-keyhole"))

        self.btnMiwiMos   = QToolButton()
        self.btnMiwiMos.setText("MIWI/MOS")
        self.btnMiwiMos.setIcon(qta.icon("fa6.rectangle-list"))

        self.btnAttachments = QToolButton()
        self.btnAttachments.setText("Attachments")
        self.btnAttachments.setIcon(qta.icon("fa6s.paperclip"))

        TAB_BTN_STYLE = """
            QToolButton {
                background: transparent;
                border: none;
                border-radius: 12px;
                padding: 10px 20px;
                color: #d0d0d0;
            }

            QToolButton:hover {
                background: rgba(255,255,255,0.08);
            }

            QToolButton[selected="true"] {
                background: rgba(76,175,80,0.18);
                color: #4CAF50;
                background: rgba(25,118,210,0.18);
                color: #42A5F5;
                font-weight: bold;
            }
            """
        self.tabsBtns: list[QPushButton] = [self.btnBasicInfo, self.btnTools, self.btnHazards, self.btnControls, self.btnRisks, self.btnIsolation, self.btnMiwiMos, self.btnAttachments]

        for btn in self.tabsBtns:
            btn.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
            btn.setStyleSheet(TAB_BTN_STYLE)
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(QSize(32, 32))


        self.btnBasicInfo.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabBasicInfo))
        self.btnTools.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabTools))
        self.btnHazards.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabHazards))
        self.btnControls.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabControls))
        self.btnRisks.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabRisks))
        self.btnIsolation.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabIsolation))
        self.btnMiwiMos.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabMiwiMos))
        self.btnAttachments.clicked.connect(lambda: self.stack.setCurrentWidget(self.tabAttachments))

        self.stack.addWidget(self.tabBasicInfo)
        self.stack.addWidget(self.tabTools)
        self.stack.addWidget(self.tabHazards)
        self.stack.addWidget(self.tabControls)
        self.stack.addWidget(self.tabRisks)
        self.stack.addWidget(self.tabIsolation)
        self.stack.addWidget(self.tabMiwiMos)
        self.stack.addWidget(self.tabAttachments)

        lytTabs.addWidget(self.btnBasicInfo)
        lytTabs.addWidget(self.btnTools)
        lytTabs.addWidget(self.btnHazards)
        lytTabs.addWidget(self.btnControls)
        lytTabs.addWidget(self.btnRisks)
        lytTabs.addWidget(self.btnIsolation)
        lytTabs.addWidget(self.btnMiwiMos)
        lytTabs.addWidget(self.btnAttachments)
        # lytTabs.setSpacing(20)

        self.boxPTWId = QLineEdit()
        self.boxPTWType = QComboBox(self.tabBasicInfo)
        for type in PTWData.Types:
            self.boxPTWType.addItem(type)
        self.boxDate = QLineEdit()
        self.boxDepartment = QLineEdit()
        self.boxRequestor = QLineEdit()
        self.boxPerforming = QLineEdit()
        self.boxLocation = QComboBox(self.tabBasicInfo)
        for location in PTWData.Locations:
            self.boxLocation.addItem(location)
        self.boxAreaClass = QComboBox(self.tabBasicInfo)
        for areaClass in PTWData.AreaClasses:
            self.boxAreaClass.addItem(areaClass)
        self.boxEquipment = QLineEdit()
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 5 + 10)
        self.boxDescription.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.boxDescription.setAcceptRichText(False)

        self.boxPTWId.setText(str(ptw.id) if ptw.id else '')
        self.boxPTWType.setCurrentText(str(ptw.type))
        self.boxDate.setText(date.today().strftime("%d/%m/%Y") if new else str(ptw.date))
        self.boxDepartment.setText(self.loggedUser.department if new else str(ptw.department) if self.loggedUser.department else '')
        self.boxRequestor.setText(self.loggedUser.getUsername() if new else str(ptw.requestor) if ptw.requestor else '')
        self.boxPerforming.setText(str(ptw.performing) if ptw.performing else '')
        self.boxLocation.setCurrentText(str(ptw.location) if ptw.location else '')
        self.boxAreaClass.setCurrentText(str(ptw.area_class) if ptw.area_class else '')
        self.boxEquipment.setText(str(ptw.equipment) if ptw.equipment else '')
        self.boxDescription.setText(str(ptw.description) if ptw.description else '')

        self.boxPTWId.setReadOnly(True)
        self.boxPTWType.setEnabled(not readOnly)
        self.boxDate.setReadOnly(True)
        self.boxDepartment.setReadOnly(True)
        self.boxRequestor.setReadOnly(True)
        self.boxPerforming.setReadOnly(True)
        self.boxLocation.setEnabled(not readOnly)
        self.boxAreaClass.setEnabled(not readOnly)
        self.boxEquipment.setReadOnly(readOnly)
        self.boxDescription.setReadOnly(readOnly)
        self.boxDescription.setTabChangesFocus(True)

        lytBasicInfo.addRow('PTW#:', self.boxPTWId)
        lytBasicInfo.addRow('Date:', self.boxDate)
        lytBasicInfo.addRow('Dept:', self.boxDepartment)
        lytBasicInfo.addRow('Requestor:', self.boxRequestor)
        lytBasicInfo.addRow('Performing:', self.boxPerforming)
        lytBasicInfo.addRow('Type:', self.boxPTWType)
        lytBasicInfo.addRow('Location:', self.boxLocation)
        lytBasicInfo.addRow('Area Class:', self.boxAreaClass)
        lytBasicInfo.addRow('Equipment:', self.boxEquipment)
        lytBasicInfo.addRow('Description:', self.boxDescription)

        self.btnsTools: list[QCheckBox] = []
        for i,tool in enumerate(PTWData.ALL_TOOLS):
            btn = QCheckBox(tool)
            btn.setChecked(btn.text() in ptw.tools)
            btn.setEnabled(not readOnly)
            btn.setStyleSheet('QCheckBox::indicator {width: 20px; height: 20px}')
            lytTools.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsTools.append(btn)
        
        self.btnsHazard: list[QCheckBox] = []
        for i,hazard in enumerate(PTWData.ALL_HAZARDS):
            btn = QCheckBox(hazard)
            btn.setChecked(btn.text() in ptw.hazards)
            btn.setEnabled(not readOnly)
            btn.setStyleSheet('QCheckBox::indicator {width: 20px; height: 20px}')
            lytHazards.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsHazard.append(btn)
        
        self.btnsControl: list[QCheckBox] = []
        for i,ctrl in enumerate(PTWData.ALL_CONTROLS):
            btn = QCheckBox(ctrl)
            btn.setChecked(btn.text() in ptw.controls)
            btn.setEnabled(not readOnly)
            btn.setStyleSheet('QCheckBox::indicator {width: 20px; height: 20px;}')
            lytControls.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsControl.append(btn)

        if self.readonly:
            self.tabRisks.setRiskAssessmentsInGUI({
                title: risk
                for title, risk in globalData.allRiskAssessments.items()
                if title in self.ptw.risks
            })
        else:
            self.tabRisks.setRiskAssessmentsInGUI(globalData.allRiskAssessments)
            for riskTitle in ptw.risks:
                self.tabRisks.checkRisk(riskTitle)
        

        self.tableIsolation = TableIsolation(self.tabIsolation, self.ptw.isolations, readOnly)
        lytIsolation.addWidget(self.tableIsolation, stretch=1)

        self.btnMiwi = QRadioButton("MIWI")
        self.btnMos  = QRadioButton("MOS")

        self.btnMiwi.setEnabled(not readOnly)
        self.btnMos.setEnabled(not readOnly)

        self.selectorMiwiMos = QButtonGroup(self)
        self.selectorMiwiMos.addButton(self.btnMiwi)
        self.selectorMiwiMos.addButton(self.btnMos)

        self.selectorMiwiMos.buttonClicked.connect(self.miwiMosSwitch)

        self.btnMiwi.setChecked(bool(self.ptw.miwi))
        self.btnMos.setChecked(bool(self.ptw.mos) or not bool(self.ptw.miwi))

        self.boxMOS = QTextEdit()
        self.boxMOS.setReadOnly(readOnly)
        self.boxMOS.setTabChangesFocus(True)
        self.boxMOS.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.boxMOS.setAcceptRichText(False)
        self.boxMOS.setText(str(ptw.mos) if ptw.mos else '')

        self.boxMiwi = QComboBox(self.tabMiwiMos)
        self.boxMiwi.addItems(sorted(globalData.allMIWIs, key=str.casefold))
        # self.boxMiwi.setEditable(True)
        self.boxMiwi.setMaxVisibleItems(10)

        self.btnViewMiwi = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), 'View MIWI')
        self.btnViewMiwi.clicked.connect(self.openMIWI)

        self.btnNewMiwi = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), 'New MIWI')
        self.btnNewMiwi.clicked.connect(self.newMIWI)

        miwiLyt = QHBoxLayout()
        miwiLyt.addWidget(self.boxMiwi, stretch=1)
        miwiLyt.addWidget(self.btnViewMiwi, stretch=0)
        miwiLyt.addWidget(self.btnNewMiwi, stretch=0)

        lytMiwiMos.addRow(self.btnMos, self.boxMOS)
        lytMiwiMos.addRow(self.btnMiwi, miwiLyt)

        self.tableAttachments = TableAttachments(self.tabAttachments, loggedUser, self.ptw.id, referencePTW.id if referencePTW else None, attachs, readOnly)

        self.btnNewAttach = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogNewFolder), 'New Attachment')
        self.btnNewAttach.clicked.connect(self.newAttachment)

        lytAttachments.addWidget(self.tableAttachments, stretch=1)
        if not readOnly:
            lytAttachments.addWidget(self.btnNewAttach, stretch=0)
        
        for tabIdx in range(self.stack.count()):
            QShortcut(QKeySequence(f"Alt+{tabIdx + 1}"), self).activated.connect(partial(self.stack.setCurrentIndex, tabIdx))

        self.btnNext.clicked.connect(lambda: self.stack.setCurrentIndex(self.stack.currentIndex() + 1))
        self.btnBack.clicked.connect(lambda: self.stack.setCurrentIndex(self.stack.currentIndex() - 1))
        self.btnCancel.clicked.connect(self.reject)
        self.btnFinish.clicked.connect(self.accept)
        self.stack.currentChanged.connect(self.stackTabChanged)
        self.stackTabChanged()
        self.miwiMosSwitch()

    def miwiMosSwitch(self):
        if self.btnMiwi.isChecked():
            self.boxMiwi.setEnabled(not self.readonly)
            self.boxMOS.setEnabled(False)
            self.btnViewMiwi.setEnabled(True)
            self.btnNewMiwi.setEnabled(not self.readonly)
        elif self.btnMos.isChecked():
            self.boxMiwi.setEnabled(False)
            self.boxMOS.setEnabled(True)
            self.btnViewMiwi.setEnabled(False)
            self.btnNewMiwi.setEnabled(False)

    def openMIWI(self):
        miwiName = self.boxMiwi.currentText()
        if miwiName:
            err, filepath = ClientRequests.getMIWI(self.loggedUser, miwiName)
            if err:
                QMessageBox.warning(self, "Error", err)
            else:
                ReportGenerator.openPDF(filepath)

    class SaveAsDialog(QDialog):
        def __init__(self, parent, initName: str = '', invalidList: list[str] = [], title: str = "Save file as"):
            super().__init__(parent)
            self.setWindowTitle(title)
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowMaximizeButtonHint & ~Qt.WindowType.WindowMinimizeButtonHint)
            lyt = QFormLayout()
            lyt.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
            self.setLayout(lyt)
            self.invalidList = invalidList

            self.boxFileName = QLineEdit()
            self.boxFileName.setText(initName)
            self.boxFileName.setMinimumWidth(self.parent().width() // 3)
            self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            self.boxFileName.textChanged.connect(self.checkSaveName)
            self.boxFileName.setStyleSheet("QLineEdit[error='True'] {border: 1px solid red; border-radius: 2px;}")

            lyt.addRow("Save on Server as:", self.boxFileName)
            lyt.addRow(self.btns)

            self.btns.accepted.connect(self.collectData)
            self.btns.rejected.connect(self.reject)
            self.checkSaveName()

        def checkSaveName(self):
            name = self.boxFileName.text().strip()
            self.btns.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(name) and name not in self.invalidList)
            self.boxFileName.setProperty('error', str(not name or name in self.invalidList))
            self.boxFileName.style().unpolish(self.boxFileName)
            self.boxFileName.style().polish(self.boxFileName)

        def collectData(self):
            self.savename = self.boxFileName.text().strip()
            self.accept()


    def newMIWI(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select MIWI File", QDir.homePath(), "PDFs (*.pdf);;All Files (*)")
        if not filepath:
            return
        
        miwiName = QFileInfo(filepath).fileName()
        saveDialog = self.SaveAsDialog(self, initName=miwiName, title="Save MIWI as", invalidList=globalData.allMIWIs)
        resp = saveDialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            miwiName = saveDialog.savename
        elif resp == QDialog.DialogCode.Rejected:
            return
        
        err = ClientRequests.uploadMIWI(self.loggedUser, filepath, miwiName)
        if err:
            QMessageBox.warning(self, "Error", err)
            return
        globalData.allMIWIs.append(miwiName)
        self.boxMiwi.addItem(miwiName)
        self.boxMiwi.setCurrentText(miwiName)
    
    def newAttachment(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Select File", QDir.homePath(), "PDFs (*.pdf);;All Files (*)")
        if not filepath:
            return
        
        filename = QFileInfo(filepath).fileName()
        saveDialog = self.SaveAsDialog(self, initName=filename, title="Save Attachment as", invalidList=[a.remoteName for a in self.tableAttachments.getAttachments()])
        resp = saveDialog.exec()
        if resp == QDialog.DialogCode.Accepted:
            filename = saveDialog.savename
        elif resp == QDialog.DialogCode.Rejected:
            return

        self.tableAttachments.addAttachment(Attachment(filepath, filename, False))

    def stackTabChanged(self):
        tabIdx = self.stack.currentIndex()

        for i, btn in enumerate(self.tabsBtns):
            # btn.setStyleSheet('QPushButton { background-color: transparent; border: none; }')
            btn.setProperty("selected", i == tabIdx)

            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()
        # self.tabsBtns[tabIdx].setStyleSheet('QPushButton { background-color: transparent; border: none; color: green; }')

        self.btnNext.setEnabled(tabIdx < self.stack.count() - 1)
        self.btnBack.setEnabled(tabIdx > 0)

        self.collectData()
        self.requiredAttachs = self.ptw.requiredAttachs()
        self.tableAttachments.setRequiredAttachs(self.requiredAttachs)

    def collectData(self):
        if self.readonly:
            return
        
        self.ptw.setId(self.boxPTWId.text() if self.boxPTWId.text() else None)
        self.ptw.setType(self.boxPTWType.currentText())
        self.ptw.setDate(self.boxDate.text())
        self.ptw.setRequestor(self.boxRequestor.text())
        self.ptw.setDepartment(self.boxDepartment.text())
        self.ptw.setLocation(self.boxLocation.currentText())
        self.ptw.setAreaClass(self.boxAreaClass.currentText())
        self.ptw.setEquipment(self.boxEquipment.text())
        self.ptw.setDescription(self.boxDescription.toPlainText())
        if self.btnMiwi.isChecked():
            self.ptw.setMiwi(self.boxMiwi.currentText())
            self.ptw.setMos(None)
        elif self.btnMos.isChecked():
            self.ptw.setMos(self.boxMOS.toPlainText())
            self.ptw.setMiwi(None)
        
        self.ptw.tools = []
        for btn in self.btnsTools:
            if btn.isChecked():
                self.ptw.addTool(btn.text())
        
        self.ptw.hazards = []
        for btn in self.btnsHazard:
            if btn.isChecked():
                self.ptw.addHazard(btn.text())
        
        self.ptw.controls = []
        for btn in self.btnsControl:
            if btn.isChecked():
                self.ptw.addControl(btn.text())
        
        self.ptw.risks = []
        for riskAssessment in self.tabRisks.getSelectedRiskAssessments():
            self.ptw.risks.append(riskAssessment.title)

        self.ptw.isolations = []
        for isolation in self.tableIsolation.getIsolations():
            self.ptw.addIsolation(isolation)

        self.ptw.attachs = [a.remoteName for a in self.tableAttachments.getAttachments()]
        self.attachsToBeUploaded = [a for a in self.tableAttachments.getAttachments() if not a.uploaded]

    def accept(self):
        if self.readonly:
            return super().accept()
        
        self.collectData()
        err = self.ptw.validate()
        if err:
            QMessageBox.warning(self, "Invalid Data", err)
            return
        
        return super().accept()
