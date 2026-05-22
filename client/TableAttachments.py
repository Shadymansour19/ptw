import copy
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *

from clientRequests import ClientRequests
from User import User
from PTWData import Attachment


class TableAttachments(QWidget):
    class AttachmentRecordWidget(QWidget):
        MAX_DISPLAY_NAME_LENGTH = 50

        viewRecordClicked = pyqtSignal(Attachment)
        deleteRecordClicked = pyqtSignal(Attachment)

        def __init__(self, parent, attachment: Attachment, readonly: bool = True):
            super().__init__(parent)

            lyt = QHBoxLayout()
            self.setLayout(lyt)

            self.attachment = attachment
            self.btnView = QPushButton('View')
            self.btnDelete = QPushButton('Delete')

            self.btnView.clicked.connect(lambda: self.viewRecordClicked.emit(attachment))
            self.btnDelete.clicked.connect(lambda: self.deleteRecordClicked.emit(attachment))
    
            displayName = attachment.remoteName[:self.MAX_DISPLAY_NAME_LENGTH] + ("..." if len(attachment.remoteName) > self.MAX_DISPLAY_NAME_LENGTH else "")
            lyt.addWidget(QLabel(displayName, font=QFont('Helvetica', 14), alignment=Qt.AlignmentFlag.AlignCenter), stretch=1)
            lyt.addWidget(self.btnView, stretch=0)
            if not readonly:
                lyt.addWidget(self.btnDelete, stretch=0)

    class RequiredAttachmentRecordWidget(QWidget):
        MAX_DISPLAY_NAME_LENGTH = 50

        uploadRecordClicked = pyqtSignal(str)

        def __init__(self, parent, title: str, readonly: bool = True):
            super().__init__(parent)

            lyt = QHBoxLayout()
            self.setLayout(lyt)

            self.title = title
            self.btnUpload = QPushButton('Upload')

            self.btnUpload.clicked.connect(lambda: self.uploadRecordClicked.emit(self.title))
    
            displayName = self.title[:self.MAX_DISPLAY_NAME_LENGTH] + ("..." if len(self.title) > self.MAX_DISPLAY_NAME_LENGTH else "")
            lyt.addWidget(QLabel(displayName, font=QFont('Helvetica', 14), alignment=Qt.AlignmentFlag.AlignCenter), stretch=1)
            if not readonly:
                lyt.addWidget(self.btnUpload, stretch=0)


    def __init__(self, parent, loggedUser: User, ptwId: str = None, refPtwId: str = None, attachments: list[Attachment] = [], readonly: bool = True):
        super().__init__(parent)
        lyt = QVBoxLayout()
        self.loggedUser = loggedUser
        self.ptwId = ptwId
        self.refPtwId = refPtwId
        self.readonly = readonly
        self.attachments: list[Attachment] = attachments
        self.requiredAttachs: list[str] = []

        self.setLayout(lyt)

        self.missingLst = QListWidget()
        missingDocsLblLyt = QHBoxLayout()
        self.missingDocsExpandBtn = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp), '')
        self.missingDocsExpandBtn.setStyleSheet('QPushButton { border: none; }')
        self.missingDocsExpandBtn.clicked.connect(self.toggleMissingDocs)
        missingDocsLblLyt.addWidget(QLabel('Missing Required Docs'))
        missingDocsLblLyt.addStretch()
        missingDocsLblLyt.addWidget(self.missingDocsExpandBtn)
        lyt.addLayout(missingDocsLblLyt)
        lyt.addWidget(self.missingLst)
        self.missingLst.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for title in self.requiredAttachs:
            if title not in [attachment.remoteName for attachment in self.attachments]:
                self.__addRequiredAttachmentToGUI(title)

        self.optionalLst = QListWidget()
        optionalDocsLblLyt = QHBoxLayout()
        self.optionalDocsExpandBtn = QPushButton(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp), '')
        self.optionalDocsExpandBtn.setStyleSheet('QPushButton { border: none; }')
        self.optionalDocsExpandBtn.clicked.connect(self.toggleOptionalDocs)
        optionalDocsLblLyt.addWidget(QLabel('Attached Docs'))
        optionalDocsLblLyt.addStretch()
        optionalDocsLblLyt.addWidget(self.optionalDocsExpandBtn)
        lyt.addLayout(optionalDocsLblLyt)
        lyt.addWidget(self.optionalLst)
        self.optionalLst.itemDoubleClicked.connect(self.itemDoubleClicked)
        self.optionalLst.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        for attachment in self.attachments:
            self.__addAttachmentToGUI(attachment)

        # lyt.addStretch()

    def clear(self):
        self.attachments.clear()
        self.optionalLst.clear()

    def toggleMissingDocs(self):
        if self.missingLst.isVisible():
            self.missingLst.hide()
            self.missingDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        else:
            self.missingLst.show()
            self.missingDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
    
    def toggleOptionalDocs(self):
        if self.optionalLst.isVisible():
            self.optionalLst.hide()
            self.optionalDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        else:
            self.optionalLst.show()
            self.optionalDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
    
    def __addAttachmentToGUI(self, attachment: Attachment):
        item = QListWidgetItem()
        record = TableAttachments.AttachmentRecordWidget(self, attachment, self.readonly)
        item.setSizeHint(record.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.optionalLst.addItem(item)
        self.optionalLst.setItemWidget(item, record)
        record.viewRecordClicked.connect(lambda attachment: self.viewAttachment(attachment))
        record.deleteRecordClicked.connect(lambda attachment: self.deleteAttachment(attachment.remoteName))
    
    def __addRequiredAttachmentToGUI(self, title: str):
        item = QListWidgetItem()
        record = TableAttachments.RequiredAttachmentRecordWidget(self, title, self.readonly)
        item.setSizeHint(record.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.missingLst.addItem(item)
        self.missingLst.setItemWidget(item, record)
        record.uploadRecordClicked.connect(lambda title: self.uploadRequiredAttachment(title))

    def addAttachment(self, attachment: Attachment):
        self.__addAttachmentToGUI(attachment)
        self.attachments.append(attachment)
        self.refreshGUI()

    def refreshGUI(self):
        self.optionalLst.clear()
        for attachment in self.attachments:
            self.__addAttachmentToGUI(attachment)
        self.missingLst.clear()
        for title in self.requiredAttachs:
            if title not in [attachment.remoteName[:attachment.remoteName.rfind('.')] for attachment in self.attachments]:
                self.__addRequiredAttachmentToGUI(title)

    def itemDoubleClicked(self, item: QListWidgetItem):
        record: TableAttachments.AttachmentRecordWidget = self.optionalLst.itemWidget(item)
        self.viewAttachment(record.attachment)

    def viewAttachment(self, attachment: Attachment):
        from ReportGenerator import ReportGenerator
        if attachment.uploaded:
            err, filepath = ClientRequests.getPtwAttachment(self.loggedUser, self.ptwId, attachment.remoteName)
            if err:
                err, filepath = ClientRequests.getPtwAttachment(self.loggedUser, self.refPtwId, attachment.remoteName)
                if err:
                    QMessageBox.warning(self, 'Error', err)
                else:
                    ReportGenerator.openPDF(filepath)
                if err:
                    QMessageBox.warning(self, 'Error', err)
            else:
                ReportGenerator.openPDF(filepath)
        else:
            ReportGenerator.openPDF(attachment.localPath)

    def deleteAttachment(self, savename: str):
        i = 0
        while i < len(self.attachments):
            if self.attachments[i].remoteName == savename:
                self.attachments.pop(i)
            else:
                i += 1
        self.refreshGUI()

    def uploadRequiredAttachment(self, title: str):
        fileDialog = QFileDialog(self, f'Select {title} file to upload', QDir.homePath(), "PDFs (*.pdf);;Photos (*.jpg *.jpeg *.png);;All Files (*)")
        fileDialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        if fileDialog.exec():
            selectedFiles = fileDialog.selectedFiles()
            if selectedFiles:
                localPath = selectedFiles[0]
                newAttachment = Attachment(localPath=localPath, remoteName=title + '.' + QFileInfo(localPath).suffix(), uploaded=False)
                self.addAttachment(newAttachment)
                self.refreshGUI()
    
    def getAttachments(self):
        return self.attachments
    
    def setRequiredAttachs(self, requiredAttachs: list[str]):
        self.requiredAttachs = [title for title in requiredAttachs if title not in [attachment.remoteName for attachment in self.attachments]]
        self.refreshGUI()