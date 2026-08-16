"""Confirmation dialog for a PTW's run request.

Shown before `MainWindow.requestToRunPTW` actually sends the request: lists the
PTW's linked ICs with View, (for a not-yet-isolated IC) Request Isolate, and
Unlink actions — the same trio DialogPTW's IC Linkage tab offers, under the
same rules — so the Performing Authority can catch and fix a missed isolation,
or drop an IC that turns out not to be needed, before confirming the run
request itself.
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
                              QLineEdit, QPushButton, QDialogButtonBox, QMessageBox)
from PyQt6.QtGui import QFont
from functools import partial
import qtawesome as qta

from models.User import UserRoles
from models.Isolation import IC
from network.clientRequests import ClientRequests
from widgets.RefreshOverlay import RefreshOverlay
from helper.i18n import t


class DialogConfirmRunRequest(QDialog):
    """Ok/Cancel confirmation for requesting a run, with a linked-ICs review list.

    Each row in `ics` gets a View button; a Request Isolate button, enabled
    only while that IC's status is APPROVED (approved but isolation not yet
    requested); and, for USER/ISSUING/COORDINATOR viewers, an Unlink button,
    enabled only while `ic.canUnlinkPTW(self.ptw)` allows it — the same
    role/eligibility rules DialogPTW's IC Linkage tab uses. Either action
    closes this dialog rather than leaving it open — the outcome isn't
    reflected client-side until the PTW/IC data is reloaded, so the PA must
    click Run again afterwards to re-confirm with up-to-date linkage/statuses.
    """

    def __init__(self, parent, loggedUser, ptw, ics: list[IC]):
        super().__init__(parent)
        self.loggedUser = loggedUser
        self.ptw = ptw
        self.setWindowTitle(t('Run PTW# {0}').format(ptw.id))
        self._refreshOverlay = RefreshOverlay(self)

        lyt = QVBoxLayout(self)

        msg = QLabel(t("Are you sure you want to request run for PTW#{0}?").format(ptw.id))
        msg.setWordWrap(True)
        lyt.addWidget(msg)

        lyt.addWidget(QLabel(f"<b>{t('Linked ICs')}</b>", font=QFont("Helvetica", 12)))
        if not ics:
            lyt.addWidget(QLabel(t("No linked ICs.")))
        else:
            for ic in ics:
                lyt.addWidget(self._icRow(ic))

        self.btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.btns.accepted.connect(self.accept)
        self.btns.rejected.connect(self.reject)
        lyt.addWidget(self.btns)

        if parent:
            self.setMinimumWidth(int(parent.width() * 0.5))

    def _icRow(self, ic: IC) -> QWidget:
        """Build one linked-IC row: read-only "IC #<id> — <status>" label, a View
        button, a Request Isolate button enabled only while `ic` is APPROVED
        (i.e. not yet isolated/pending), and — for USER/ISSUING/COORDINATOR
        viewers — an Unlink button enabled only while ic.canUnlinkPTW(self.ptw)
        allows it, mirroring DialogPTW's IC Linkage tab row exactly."""
        row = QWidget()
        rowLyt = QHBoxLayout(row)
        rowLyt.setContentsMargins(0, 0, 0, 0)

        box = QLineEdit(f"IC #{ic.id} — {ic.getStatus()}")
        box.setReadOnly(True)
        box.setCursorPosition(0)
        rowLyt.addWidget(box, stretch=1)

        btnView = QPushButton(qta.icon("fa6.eye"), t("View"))
        btnView.clicked.connect(partial(self._viewIC, ic))
        rowLyt.addWidget(btnView)

        btnRequestIsolate = QPushButton(qta.icon("fa6s.unlock-keyhole"), t("Request Isolate"))
        btnRequestIsolate.setEnabled(ic.getStatus() == IC.Status.APPROVED)
        btnRequestIsolate.clicked.connect(partial(self._requestIsolate, ic))
        rowLyt.addWidget(btnRequestIsolate)

        if self.loggedUser.getRole() in (UserRoles.USER, UserRoles.ISSUING, UserRoles.COORDINATOR):
            btnUnlink = QPushButton(qta.icon("mdi.link-variant-off"), t("Unlink"))
            btnUnlink.setEnabled(ic.canUnlinkPTW(self.ptw))
            btnUnlink.clicked.connect(partial(self._unlinkIC, ic))
            rowLyt.addWidget(btnUnlink)

        return row

    def _viewIC(self, ic: IC):
        """Open a read-only DialogIC for `ic`. Slot for a row's View button click."""
        from dialogs.DialogIC import DialogIC
        dlg = DialogIC(self, self.loggedUser, ic, False, True, t("IC — {0}").format(ic.type))
        dlg.exec()

    def _requestIsolate(self, ic: IC):
        """Request isolation of `ic`, after confirmation. Slot for a row's Request
        Isolate button click. On success, closes this whole confirmation dialog —
        the PA must click Run again to re-confirm once the IC's status has
        updated."""
        reply = QMessageBox.question(
            self, t('Request Isolate #{0}').format(ic.id), t("Request isolation for IC #{0}? This will notify Issuing to confirm.").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            """Handle the isolate-request result: warn on failure, else confirm and close."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Request Failed"), err)
                return
            QMessageBox.information(self, t("Requested"), t("Isolation requested for IC #{0}.").format(ic.id))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.requestIsolateIC(self.loggedUser, ic.id, callback=on_done)

    def _unlinkIC(self, ic: IC):
        """Unlink `ic` from this PTW, after confirmation. Slot for a row's Unlink
        button click. On success, closes this whole confirmation dialog — the PA
        must click Run again to re-confirm once the linkage has updated."""
        reply = QMessageBox.question(
            self, t("Unlink IC"), t("Unlink IC #{0} from this PTW?").format(ic.id),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        def on_done(err, _):
            """Handle the unlink-request result: warn on failure, else confirm and close."""
            self._refreshOverlay.hideBusy()
            if err:
                QMessageBox.warning(self, t("Unlink Failed"), err)
                return
            QMessageBox.information(self, t("Unlinked"), t("IC #{0} has been unlinked.").format(ic.id))
            self.reject()
        self._refreshOverlay.showBusy()
        ClientRequests.unlinkPTWFromIC(self.loggedUser, int(ic.id), self.ptw.id, callback=on_done)
