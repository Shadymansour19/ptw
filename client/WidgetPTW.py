import copy
from datetime import datetime
from PyQt6.QtCore import Qt, QSize, QDir, QFileInfo
from PyQt6.QtWidgets import (QToolButton, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                              QGridLayout, QStackedWidget, QWidget, QLineEdit, QComboBox,
                              QTextEdit, QPushButton, QCheckBox, QRadioButton, QButtonGroup,
                              QDialogButtonBox, QMessageBox, QApplication, QStyle,
                              QFileDialog, QSizePolicy, QFrame)
from PyQt6.QtGui import QFont, QKeySequence, QIcon, QPalette, QShortcut, QColor
import re

from PTWData import PTWData, Attachment, RiskAssessment
from TableRisks import TableRisks
from TableAttachments import TableAttachments
from GlobalData import globalData
from ReportGenerator import ReportGenerator
from clientRequests import ClientRequests
from TableIsolations import TablePTWIsolations
from RiskPreview import RiskAssessmentPreview
from functools import partial
import qtawesome as qta
from i18n import t

def lightenColor(color: QColor, amount: float = 0.4) -> QColor:
    return QColor(
        int(color.red()   + (255 - color.red())   * amount),
        int(color.green() + (255 - color.green()) * amount),
        int(color.blue()  + (255 - color.blue())  * amount),
    )

class TabButton(QToolButton):
    TAB_BTN_STYLE = """
        QToolButton {
            background: transparent;
            border: none;
            border-radius: 12px;
            padding: 10px 20px;
            color: palette(window-text);
        }

        QToolButton:hover {
            background: rgba(128, 128, 128, 0.15);
        }

        QToolButton:pressed {
            background: rgba(128, 128, 128, 0.30);
        }

        QToolButton[selected="true"] {
            background: palette(highlight);
            color: palette(highlighted-text);
            font-weight: bold;
        }
    """

    def __init__(self, parent = None, text = '', icon = ''):
        super().__init__(parent)
        self.setText(text)
        self.setFont(QFont("Helvetica", 12, QFont.Weight.Bold))
        self.iconName = icon
        highlighted_text = QApplication.palette().color(QPalette.ColorRole.HighlightedText).name()
        self.icon = qta.icon(icon) if icon else None
        self.selection_icon = qta.icon(icon, color=highlighted_text) if icon else None
        self.setStyleSheet(TabButton.TAB_BTN_STYLE)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(32, 32))

    def setIcon(self, isSelected):
        super().setIcon(self.selection_icon if isSelected and self.selection_icon else self.icon if self.icon else QIcon())

    def setHighlightColor(self, bgColor: QColor, textColor: QColor):
        self.selection_icon = qta.icon(self.iconName, color=textColor.name()) if self.iconName else None
        self.setStyleSheet(f"""
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 12px;
                padding: 10px 20px;
                color: palette(window-text);
            }}

            QToolButton:hover {{
                background: rgba(128, 128, 128, 0.15);
            }}

            QToolButton:pressed {{
                background: rgba(128, 128, 128, 0.30);
            }}

            QToolButton[selected="true"] {{
                background: {bgColor.name()};
                color: {textColor.name()};
                font-weight: bold;
            }}
        """)

class DialogPTW(QDialog):
    GRID_LYT_COLS = 3
    CHECK_BOX_MAX_LINE_CHARS = 36

    def checkboxDisplayName(text: str):
        if len(text) <= DialogPTW.CHECK_BOX_MAX_LINE_CHARS:
            return text
        else:
            # Insert a newline at the last space before the max line chars, or at max line chars if no space found
            breakpoint = text.rfind(' ', 0, DialogPTW.CHECK_BOX_MAX_LINE_CHARS)
            if breakpoint == -1:
                breakpoint = DialogPTW.CHECK_BOX_MAX_LINE_CHARS
            return text[:breakpoint] + '\n' + text[breakpoint:].lstrip()
        
    def formatCheckBoxText(text: str):
        return text.replace('\n', ' ')

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
                QMessageBox.warning(parent, t("Error"), t("Failed to fetch attachments:") + f" {err}")
            else:
                attachs = [Attachment(remoteName=name, uploaded=True) for name in attachNames]

        if referencePTW is not None:
            err, refAttachNames = ClientRequests.getPtwAttachmentNames(loggedUser, referencePTW.id)
            if err:
                QMessageBox.warning(parent, t("Error"), t("Failed to fetch reference PTW attachments:") + f" {err}")
            else:
                attachs.extend([Attachment(remoteName=name, uploaded=True) for name in refAttachNames])

        lyt = QVBoxLayout()
        lyt.setContentsMargins(0, 0, 0, 0)
        
        self.tabsContainer = QWidget()
        self.tabsContainer.setStyleSheet("""
            QWidget {
                background: palette(dark);
                border-bottom: 4px solid rgba(128, 128, 128, 0.5);
                border-right: 4px solid rgba(128, 128, 128, 0.5);
                border-bottom-right-radius: 20px;
            }
        """)
        lytTabs = QHBoxLayout(self.tabsContainer)
        lytTabs.setSpacing(2)
        lytTabs.setContentsMargins(8, 8, 8, 8)

        lytBtns = QHBoxLayout()
        lytBtns.setContentsMargins(8, 8, 8, 8)
        
        self.stack = QStackedWidget()
        self.btnBack = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), t('Back'))
        self.btnNext = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward), t('Next'))
        self.btnFinish = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton), t('Finish'))
        self.btnCancel = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton), t('Cancel'))

        self.setLayout(lyt)
        lyt.addWidget(self.tabsContainer)
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
        self.tabRisks     = QWidget(self.stack)
        self.tabIsolation = QWidget(self.stack)
        self.tabMiwiMos   = QWidget(self.stack)
        self.tabAttachments = QWidget(self.stack)

        lytBasicInfo = QFormLayout()
        lytBasicInfo.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        lytTools = QGridLayout()
        lytHazards = QGridLayout()
        lytControls = QGridLayout()
        lytRisks = QVBoxLayout()
        lytIsolation = QVBoxLayout()
        lytMiwiMos = QGridLayout()
        lytAttachments = QVBoxLayout()

        self.tabBasicInfo.setLayout(lytBasicInfo)
        self.tabTools.setLayout(lytTools)
        self.tabHazards.setLayout(lytHazards)
        self.tabControls.setLayout(lytControls)
        self.tabRisks.setLayout(lytRisks)
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

        self.btnBasicInfo = TabButton(self.stack, t("Basic Info"), "mdi6.file-document-outline")
        self.btnTools     = TabButton(self.stack, t("Tools"), "fa6s.wrench")
        self.btnHazards   = TabButton(self.stack, t("Hazards"), "mdi.alert-octagon-outline")
        self.btnControls  = TabButton(self.stack, t("Controls"), "fa6s.shield-halved")
        self.btnRisks     = TabButton(self.stack, t("Risks"), "fa5s.exclamation-triangle")
        self.btnIsolation = TabButton(self.stack, t("Isolation"), "fa6s.unlock-keyhole")
        self.btnMiwiMos   = TabButton(self.stack, t("MIWI/MOS"), "fa6.rectangle-list")
        self.btnAttachments = TabButton(self.stack, t("Attachments"), "fa6s.paperclip")

        self.tabsBtnsMap: dict[QPushButton, QWidget] = {
            self.btnBasicInfo:      self.tabBasicInfo,
            self.btnTools:          self.tabTools,
            self.btnHazards:        self.tabHazards,
            self.btnControls:       self.tabControls,
            self.btnRisks:          self.tabRisks,
            self.btnIsolation:      self.tabIsolation,
            self.btnMiwiMos:        self.tabMiwiMos,
            self.btnAttachments:    self.tabAttachments
        }

        for btn, tab in self.tabsBtnsMap.items():
            btn.clicked.connect(partial(self.stack.setCurrentWidget, tab))
            self.stack.addWidget(tab)
            lytTabs.addWidget(btn)
        
        # lytTabs.setSpacing(20)

        self.boxPTWId = QLineEdit()
        self.boxPTWType = QComboBox(self.tabBasicInfo)
        for type in PTWData.Types:
            self.boxPTWType.addItem(t(type), type.value)
        self.boxDate = QLineEdit()
        self.boxDepartment = QLineEdit()
        self.boxRequestor = QLineEdit()
        self.boxPerforming = QLineEdit()
        self.boxLocation = QComboBox(self.tabBasicInfo)
        for location in PTWData.Locations:
            self.boxLocation.addItem(t(location), location.value)
        self.boxAreaClass = QComboBox(self.tabBasicInfo)
        for areaClass in PTWData.AreaClasses:
            self.boxAreaClass.addItem(t(areaClass), areaClass.value)
        self.boxEquipment = QLineEdit()
        self.boxDescription = QTextEdit()
        self.boxDescription.setFixedHeight(self.boxDescription.fontMetrics().lineSpacing() * 5 + 10)
        self.boxDescription.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.boxDescription.setAcceptRichText(False)

        self.boxPTWId.setText(str(ptw.id) if ptw.id else '')
        self.boxPTWType.setCurrentIndex(max(0, self.boxPTWType.findData(str(ptw.type))))
        self.boxDate.setText(datetime.now().strftime("%d/%m/%Y %H:%M:%S") if new else str(ptw.request_date))
        self.boxDepartment.setText(self.loggedUser.department if new else str(ptw.department) if self.loggedUser.department else '')
        self.boxRequestor.setText(self.loggedUser.getUsername() if new else str(ptw.requestor) if ptw.requestor else '')
        self.boxPerforming.setText(str(ptw.performing) if ptw.performing else '')
        self.boxLocation.setCurrentIndex(max(0, self.boxLocation.findData(str(ptw.location) if ptw.location else '')))
        self.boxAreaClass.setCurrentIndex(max(0, self.boxAreaClass.findData(str(ptw.area_class) if ptw.area_class else '')))
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

        lytBasicInfo.addRow(t('PTW#:'), self.boxPTWId)
        lytBasicInfo.addRow(t('Request Time:'), self.boxDate)
        lytBasicInfo.addRow(t('Dept:'), self.boxDepartment)
        lytBasicInfo.addRow(t('Requestor:'), self.boxRequestor)
        lytBasicInfo.addRow(t('Performing:'), self.boxPerforming)
        lytBasicInfo.addRow(t('Type:'), self.boxPTWType)
        lytBasicInfo.addRow(t('Location:'), self.boxLocation)
        lytBasicInfo.addRow(t('Area Class:'), self.boxAreaClass)
        lytBasicInfo.addRow(t('Equipment:'), self.boxEquipment)
        lytBasicInfo.addRow(t('Description:'), self.boxDescription)

        self.btnsTools: dict[str, QCheckBox] = {}
        i = 0
        for tool in PTWData.ALL_TOOLS:
            if tool is None:        # Add separator
                i = DialogPTW.GRID_LYT_COLS * ((i + DialogPTW.GRID_LYT_COLS - 1) // DialogPTW.GRID_LYT_COLS)
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                lytTools.addWidget(line, i // DialogPTW.GRID_LYT_COLS, 0, 1, DialogPTW.GRID_LYT_COLS)
                i += DialogPTW.GRID_LYT_COLS
                continue
            btn = QCheckBox(DialogPTW.checkboxDisplayName(t(tool)))
            btn.setObjectName(tool)
            btn.clicked.connect(self.checkRequirement)
            btn.setChecked(tool in ptw.tools)
            btn.setEnabled(not readOnly)
            # btn.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px; }')
            lytTools.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsTools[tool] = btn
            i += 1
        self.boxOtherTools = QLineEdit()
        self.boxOtherTools.setEnabled(not readOnly)
        self.boxOtherTools.setPlaceholderText(t("Others"))
        self.boxOtherTools.setToolTip(t("Other Tools"))
        self.boxOtherTools.setText(', '.join(tool for tool in ptw.tools if tool not in PTWData.ALL_TOOLS))
        remaining_cols = DialogPTW.GRID_LYT_COLS - (i % DialogPTW.GRID_LYT_COLS)
        lytTools.addWidget(self.boxOtherTools, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS, 1, remaining_cols)
        
        self.btnsHazard: dict[str, QCheckBox] = {}
        i = 0
        for hazard in PTWData.ALL_HAZARDS:
            if hazard is None:        # Add separator
                i = DialogPTW.GRID_LYT_COLS * ((i + DialogPTW.GRID_LYT_COLS - 1) // DialogPTW.GRID_LYT_COLS)
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                lytHazards.addWidget(line, i // DialogPTW.GRID_LYT_COLS, 0, 1, DialogPTW.GRID_LYT_COLS)
                i += DialogPTW.GRID_LYT_COLS
                continue
            btn = QCheckBox(DialogPTW.checkboxDisplayName(t(hazard)))
            btn.setObjectName(hazard)
            btn.clicked.connect(self.checkRequirement)
            btn.setChecked(hazard in ptw.hazards)
            btn.setEnabled(not readOnly)
            # btn.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px; }')
            lytHazards.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsHazard[hazard] = btn
            i += 1
        self.boxOtherHazards = QLineEdit()
        self.boxOtherHazards.setEnabled(not readOnly)
        self.boxOtherHazards.setPlaceholderText(t("Others"))
        self.boxOtherHazards.setToolTip(t("Other Hazards"))
        self.boxOtherHazards.setText(', '.join(hazard for hazard in ptw.hazards if hazard not in PTWData.ALL_HAZARDS))
        remaining_cols = DialogPTW.GRID_LYT_COLS - (i % DialogPTW.GRID_LYT_COLS)
        lytHazards.addWidget(self.boxOtherHazards, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS, 1, remaining_cols)
        
        self.btnsControls: dict[str, QCheckBox] = {}
        i = 0
        for ctrl in PTWData.ALL_CONTROLS:
            if ctrl is None:        # Add separator
                i = DialogPTW.GRID_LYT_COLS * ((i + DialogPTW.GRID_LYT_COLS - 1) // DialogPTW.GRID_LYT_COLS)
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setFrameShadow(QFrame.Shadow.Sunken)
                lytControls.addWidget(line, i // DialogPTW.GRID_LYT_COLS, 0, 1, DialogPTW.GRID_LYT_COLS)
                i += DialogPTW.GRID_LYT_COLS
                continue
            btn = QCheckBox(DialogPTW.checkboxDisplayName(t(ctrl)))
            btn.setObjectName(ctrl)
            btn.clicked.connect(self.checkRequirement)
            btn.setChecked(ctrl in ptw.controls)
            btn.setEnabled(not readOnly)
            # btn.setStyleSheet('QCheckBox::indicator { width: 20px; height: 20px; }')
            lytControls.addWidget(btn, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS)
            self.btnsControls[ctrl] = btn
            i += 1
        self.boxOtherControls = QLineEdit()
        self.boxOtherControls.setEnabled(not readOnly)
        self.boxOtherControls.setPlaceholderText(t("Others"))
        self.boxOtherControls.setToolTip(t("Other Controls"))
        self.boxOtherControls.setText(', '.join(ctrl for ctrl in ptw.controls if ctrl not in PTWData.ALL_CONTROLS))
        remaining_cols = DialogPTW.GRID_LYT_COLS - (i % DialogPTW.GRID_LYT_COLS)
        lytControls.addWidget(self.boxOtherControls, i // DialogPTW.GRID_LYT_COLS, i % DialogPTW.GRID_LYT_COLS, 1, remaining_cols)

        # Set equal column stretches to maintain consistent width across resize
        for col in range(DialogPTW.GRID_LYT_COLS):
            lytTools.setColumnStretch(col, 1)
            lytHazards.setColumnStretch(col, 1)
            lytControls.setColumnStretch(col, 1)

        riskTitle = t("PTW") + (f"#{self.ptw.id}" if self.ptw.id else "") + t(" - Specific Risk Assessment")
        self.riskAssessment: RiskAssessment = RiskAssessment(title=riskTitle)
        if new and referencePTW:
            err, risk = ClientRequests.getPTWSpecificRiskAssessment(self.loggedUser, referencePTW.id)
            if err:
                QMessageBox.warning(parent, t("Error"), t("Failed to fetch risk assessment for PTW") + f"# {ptw.id}. {err}")
            else:
                self.riskAssessment = risk
        elif self.ptw.id:
            err, ptwSpecificRisk = ClientRequests.getPTWSpecificRiskAssessment(self.loggedUser, self.ptw.id)
            if err:
                QMessageBox.warning(self, t("Warning"), t("Failed to load PTW-specific risk assessment") + f"\n{err}")
            elif ptwSpecificRisk:
                self.riskAssessment = ptwSpecificRisk

        self.riskAssessmentPreviewTable = RiskAssessmentPreview(self.tabRisks, self.riskAssessment, readonly=readOnly)
        lytRisks.addWidget(self.riskAssessmentPreviewTable, stretch=1)
        # if not readOnly:
            # TableRisks(self.tabRisks, self.loggedUser, readonly=True, selectable=True)

            # self.tabRisks.setRiskAssessmentsInGUI(dict(globalData.allRiskAssessments))
            # for riskTitle in ptw.risks:
            #     self.tabRisks.checkRisk(riskTitle)


        self.tableIsolation = TablePTWIsolations(self.tabIsolation, self.ptw.isolations, readOnly)
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

        self.btnViewMiwi = QPushButton(qta.icon("fa6.eye"), t('View MIWI'))
        self.btnViewMiwi.clicked.connect(self.openMIWI)

        self.btnNewMiwi = QPushButton(qta.icon("fa6s.plus"), t('New MIWI'))
        self.btnNewMiwi.clicked.connect(self.newMIWI)

        miwiLyt = QHBoxLayout()
        miwiLyt.addWidget(self.boxMiwi, stretch=1)
        miwiLyt.addWidget(self.btnViewMiwi, stretch=0)
        miwiLyt.addWidget(self.btnNewMiwi, stretch=0)

        lytMiwiMos.setColumnStretch(1, 1)
        lytMiwiMos.setRowStretch(0, 1)
        lytMiwiMos.addWidget(self.btnMos, 0, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignCenter)
        lytMiwiMos.addWidget(self.boxMOS, 0, 1)
        lytMiwiMos.addWidget(self.btnMiwi, 1, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lytMiwiMos.addLayout(miwiLyt, 1, 1)

        self.tableAttachments = TableAttachments(self.tabAttachments, loggedUser, self.ptw.id, referencePTW.id if referencePTW else None, attachs, readOnly)

        self.btnNewAttach = QPushButton(qta.icon("fa6s.plus"), t('New Attachment'))
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
        self.boxPTWType.currentIndexChanged.connect(self.ptwTypeChanged)
        self.stackTabChanged()
        self.miwiMosSwitch()
        self.ptwTypeChanged()

    def ptwTypeChanged(self):
        color = PTWData.backgroundColorForType(self.boxPTWType.currentData())
        accentColor = lightenColor(color)
        textColor = PTWData.foregroundColorForType(self.boxPTWType.currentData())
        self.tabsContainer.setStyleSheet(f"""
            QWidget {{
                background: {color.name()};
                border-bottom: 4px solid {accentColor.name()};
                border-right: 4px solid {accentColor.name()};
                border-bottom-right-radius: 20px;
            }}
        """)
        for btn in self.tabsBtnsMap:
            btn.setHighlightColor(accentColor, textColor)
        self.stackTabChanged()

        if not self.readonly:
            self.checkRequirement()

    def checkRequirement(self, state=None):
        if not self.readonly:
            self.collectData()
            self.ptw.updateRequirements()
            self.refreshUI()

    def refreshUI(self):
        ptwType = self.boxPTWType.currentData()

        all_check_btns: dict[str, QCheckBox] = {}
        for btns in [self.btnsTools, self.btnsHazard, self.btnsControls]:
            all_check_btns.update(btns)

        for btn in all_check_btns.values():
            btn.blockSignals(True)
            
        for title, btn in self.btnsTools.items():
            checkBox = PTWData.ALL_TOOLS.get(title)
            required = checkBox.isRequired(ptwType)
            restricted = checkBox.isRestricted(ptwType)
            if required:
                btn.setChecked(True)
            elif restricted:
                btn.setChecked(False)
            else:
                btn.setChecked(title in self.ptw.tools)
            btn.setEnabled(not (required or restricted))
        self.boxOtherTools.setText(', '.join(tool for tool in self.ptw.tools if tool not in PTWData.ALL_TOOLS))

        for title, btn in self.btnsHazard.items():
            checkBox = PTWData.ALL_HAZARDS.get(title)
            required = checkBox.isRequired(ptwType)
            restricted = checkBox.isRestricted(ptwType)
            if required:
                btn.setChecked(True)
            elif restricted:
                btn.setChecked(False)
            else:
                btn.setChecked(title in self.ptw.hazards)
            btn.setEnabled(not (required or restricted))
        self.boxOtherHazards.setText(', '.join(tool for tool in self.ptw.hazards if tool not in PTWData.ALL_HAZARDS))

        for title, btn in self.btnsControls.items():
            checkBox = PTWData.ALL_CONTROLS.get(title)
            required = checkBox.isRequired(ptwType)
            restricted = checkBox.isRestricted(ptwType)
            if required:
                btn.setChecked(True)
            elif restricted:
                btn.setChecked(False)
            else:
                btn.setChecked(title in self.ptw.controls)
            btn.setEnabled(not (required or restricted))
        self.boxOtherControls.setText(', '.join(tool for tool in self.ptw.controls if tool not in PTWData.ALL_CONTROLS))

        self.requiredAttachs = self.ptw.requiredAttachs()
        self.tableAttachments.setRequiredAttachs(self.requiredAttachs)

        for btn in all_check_btns.values():
            btn.blockSignals(False)

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
            self.boxMOS.setFocus()

    def openMIWI(self):
        def on_done(err, filepath):
            if err:
                QMessageBox.warning(self, t("Error"), err)
            else:
                ReportGenerator.openPDF(filepath)
        miwiName = self.boxMiwi.currentText()
        if miwiName:
            department = self.ptw.department or self.loggedUser.department
            ClientRequests.getMIWI(self.loggedUser, miwiName, department=department, callback=on_done)

    class SaveAsDialog(QDialog):
        def __init__(self, parent, initName: str = '', invalidList: list[str] = [], title: str = "Save file as"):
            super().__init__(parent)
            self.setWindowTitle(t(title))
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
            self.boxFileName.setStyleSheet("QLineEdit[error='True'] { border: 1px solid red; border-radius: 2px; }")

            lyt.addRow(t("Save on Server as:"), self.boxFileName)
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
        filepath, _ = QFileDialog.getOpenFileName(self, t("Select MIWI File"), QDir.homePath(), "PDFs (*.pdf);;All Files (*)")
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
            QMessageBox.warning(self, t("Error"), err)
            return
        globalData.allMIWIs.append(miwiName)
        self.boxMiwi.addItem(miwiName)
        self.boxMiwi.setCurrentText(miwiName)
    
    def newAttachment(self):
        filepath, _ = QFileDialog.getOpenFileName(self, t("Select File"), QDir.homePath(), "PDFs (*.pdf);;All Files (*)")
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

        for i, btn in enumerate(self.tabsBtnsMap.keys()):
            # btn.setStyleSheet('QPushButton { background-color: transparent; border: none; }')
            btn.setProperty("selected", i == tabIdx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.setIcon(isSelected=(i == tabIdx))
            btn.update()
        # self.tabsBtns[tabIdx].setStyleSheet('QPushButton { background-color: transparent; border: none; color: green; }')

        self.btnNext.setEnabled(tabIdx < self.stack.count() - 1)
        self.btnBack.setEnabled(tabIdx > 0)
        # self.checkRequirement()

    def collectData(self):
        if self.readonly:
            return
        
        self.ptw.setId(self.boxPTWId.text() if self.boxPTWId.text() else None)
        self.ptw.setType(self.boxPTWType.currentData())
        self.ptw.setDate(datetime.now().strftime("%d/%m/%Y %H:%M:%S") if self.new else self.boxDate.text())
        self.ptw.setRequestor(self.boxRequestor.text())
        self.ptw.setDepartment(self.boxDepartment.text())
        self.ptw.setLocation(self.boxLocation.currentData())
        self.ptw.setAreaClass(self.boxAreaClass.currentData())
        self.ptw.setEquipment(self.boxEquipment.text())
        self.ptw.setDescription(self.boxDescription.toPlainText())
        if self.btnMiwi.isChecked():
            self.ptw.setMiwi(self.boxMiwi.currentText())
            self.ptw.setMos(None)
        elif self.btnMos.isChecked():
            self.ptw.setMos(self.boxMOS.toPlainText())
            self.ptw.setMiwi(None)
        
        self.ptw.tools = []
        for title, btn in self.btnsTools.items():
            if btn.isChecked():
                self.ptw.addTool(title)
        if self.boxOtherTools.text():
            for tool in re.split(r'[,/\-+;|]', self.boxOtherTools.text()):
                tool = tool.strip()
                if tool:
                    self.ptw.addTool(tool)

        self.ptw.hazards = []
        for title, btn in self.btnsHazard.items():
            if btn.isChecked():
                self.ptw.addHazard(title)
        if self.boxOtherHazards.text():
            for hazard in re.split(r'[,/\-+;|]', self.boxOtherHazards.text()):
                hazard = hazard.strip()
                if hazard:
                    self.ptw.addHazard(hazard)
        
        self.ptw.controls = []
        for title, btn in self.btnsControls.items():
            if btn.isChecked():
                self.ptw.addControl(title)
        if self.boxOtherControls.text():
            for ctrl in re.split(r'[,/\-+;|]', self.boxOtherControls.text()):
                ctrl = ctrl.strip()
                if ctrl:
                    self.ptw.addControl(ctrl)


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
            QMessageBox.warning(self, t("Invalid Data"), err)
            return
        
        return super().accept()
