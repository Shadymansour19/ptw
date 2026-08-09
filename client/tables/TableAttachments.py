"""File attachment management widget for a PTW: lists required (missing) and
already-attached documents, and supports uploading, viewing, and deleting
them. Can also fall back to a reference PTW's server copy of an attachment
when viewing one that hasn't been uploaded under the current PTW yet."""

from PyQt6.QtCore import Qt, pyqtSignal, QDir, QFileInfo
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
                              QListWidget, QListWidgetItem, QApplication, QStyle,
                              QFileDialog, QMessageBox)
from PyQt6.QtGui import QFont

from network.clientRequests import ClientRequests
from models.User import User
from models.PTW import Attachment


class TableAttachments(QWidget):
    """Two-list attachment manager for a PTW: a "Missing Required Docs" list
    (titles not yet satisfied by an upload) and an "Attached Docs" list of
    the PTW's current attachments, each collapsible via its header's toggle
    button."""

    class AttachmentRecordWidget(QWidget):
        """Row widget for one existing attachment: its display name plus a
        View button, and a Delete button when not readonly."""

        MAX_DISPLAY_NAME_LENGTH = 50

        viewRecordClicked = pyqtSignal(Attachment)
        deleteRecordClicked = pyqtSignal(Attachment)

        def __init__(self, parent, attachment: Attachment, readonly: bool = True):
            """Build the row for `attachment`, wiring its View/Delete buttons
            to emit `viewRecordClicked`/`deleteRecordClicked`."""
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
        """Row widget for one missing required attachment: its title plus an
        Upload button, shown only when not readonly."""

        MAX_DISPLAY_NAME_LENGTH = 50

        uploadRecordClicked = pyqtSignal(str)

        def __init__(self, parent, title: str, readonly: bool = True):
            """Build the row for the required attachment titled `title`,
            wiring its Upload button to emit `uploadRecordClicked`."""
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
        """Build the Missing/Attached lists for `ptwId` from `attachments`.

        Args:
            ptwId: the PTW this widget manages attachments for.
            refPtwId: an optional reference PTW to fall back to when viewing
                an attachment not yet uploaded under `ptwId` itself.
            readonly: hides Upload/Delete controls when True.
        """
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
        """Remove all attachments and clear the attached-docs list widget."""
        self.attachments.clear()
        self.optionalLst.clear()

    def toggleMissingDocs(self):
        """Slot for the Missing Docs header button: show/hide the missing
        docs list and flip the button's arrow icon to match."""
        if self.missingLst.isVisible():
            self.missingLst.hide()
            self.missingDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        else:
            self.missingLst.show()
            self.missingDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
    
    def toggleOptionalDocs(self):
        """Slot for the Attached Docs header button: show/hide the attached
        docs list and flip the button's arrow icon to match."""
        if self.optionalLst.isVisible():
            self.optionalLst.hide()
            self.optionalDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        else:
            self.optionalLst.show()
            self.optionalDocsExpandBtn.setIcon(QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
    
    def __addAttachmentToGUI(self, attachment: Attachment):
        """Append a row for `attachment` to the attached-docs list, wiring its
        View/Delete signals to this widget's handlers."""
        item = QListWidgetItem()
        record = TableAttachments.AttachmentRecordWidget(self, attachment, self.readonly)
        item.setSizeHint(record.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.optionalLst.addItem(item)
        self.optionalLst.setItemWidget(item, record)
        record.viewRecordClicked.connect(lambda attachment: self.viewAttachment(attachment))
        record.deleteRecordClicked.connect(lambda attachment: self.deleteAttachment(attachment.remoteName))
    
    def __addRequiredAttachmentToGUI(self, title: str):
        """Append a row for the missing required attachment `title` to the
        missing-docs list, wiring its Upload signal to this widget's handler."""
        item = QListWidgetItem()
        record = TableAttachments.RequiredAttachmentRecordWidget(self, title, self.readonly)
        item.setSizeHint(record.sizeHint())
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        self.missingLst.addItem(item)
        self.missingLst.setItemWidget(item, record)
        record.uploadRecordClicked.connect(lambda title: self.uploadRequiredAttachment(title))

    def addAttachment(self, attachment: Attachment):
        """Add `attachment` to the list and GUI, then refresh both lists."""
        self.__addAttachmentToGUI(attachment)
        self.attachments.append(attachment)
        self.refreshGUI()

    def refreshGUI(self):
        """Rebuild both list widgets from the current `attachments` and
        `requiredAttachs`, dropping any required title already satisfied by
        an upload."""
        self.optionalLst.clear()
        for attachment in self.attachments:
            self.__addAttachmentToGUI(attachment)
        self.missingLst.clear()
        for title in self.requiredAttachs:
            if title not in [attachment.remoteName[:attachment.remoteName.rfind('.')] for attachment in self.attachments]:
                self.__addRequiredAttachmentToGUI(title)

    def itemDoubleClicked(self, item: QListWidgetItem):
        """Slot for the attached-docs list's itemDoubleClicked: view the
        double-clicked attachment."""
        record: TableAttachments.AttachmentRecordWidget = self.optionalLst.itemWidget(item)
        self.viewAttachment(record.attachment)

    def viewAttachment(self, attachment: Attachment):
        """Open `attachment` as a PDF: fetch it from the server (trying this
        PTW first, then `refPtwId` as a fallback) if already uploaded,
        otherwise open the local unuploaded copy directly."""
        from reports.ReportGenerator import ReportGenerator

        def on_parent_fetch_attachs_done(err, filepath):
            """Callback for the reference-PTW fetch fallback: open the PDF on
            success, or show a warning if it also failed there."""
            self.window()._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, 'Error', err)
            else:
                ReportGenerator.openPDF(filepath)

        def on_ptw_fetch_attachs_done(err, filepath):
            """Callback for the primary PTW fetch: on failure, retry against
            `refPtwId`; on success, open the fetched PDF."""
            if err:
                ClientRequests.getPtwAttachment(self.loggedUser, self.refPtwId, attachment.remoteName, callback=on_parent_fetch_attachs_done)
            else:
                self.window()._refreshOverlay.hideBusy()
                ReportGenerator.openPDF(filepath)

        if attachment.uploaded:
            self.window()._refreshOverlay.showBusy()
            ClientRequests.getPtwAttachment(self.loggedUser, self.ptwId, attachment.remoteName, callback=on_ptw_fetch_attachs_done)
        else:
            ReportGenerator.openPDF(attachment.localPath)

    def deleteAttachment(self, savename: str):
        """Remove every attachment whose remote name matches `savename` from
        the list, then refresh the GUI."""
        i = 0
        while i < len(self.attachments):
            if self.attachments[i].remoteName == savename:
                self.attachments.pop(i)
            else:
                i += 1
        self.refreshGUI()

    def uploadRequiredAttachment(self, title: str):
        """Slot for a required-attachment row's Upload button: prompt for a
        local file and, if one is chosen, add it as a not-yet-uploaded
        attachment named after `title`."""
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
        """Return the current list of attachments."""
        return self.attachments
    
    def setRequiredAttachs(self, requiredAttachs: list[str]):
        """Set the list of required attachment titles (dropping any already
        satisfied by an existing attachment), then refresh the GUI."""
        self.requiredAttachs = [title for title in requiredAttachs if title not in [attachment.remoteName for attachment in self.attachments]]
        self.refreshGUI()