"""Grouped attention-required popup for PTWs past their shift/validity limits.

Shown by MainWindow._checkPtwAlarms() for a USER-role viewer: two individually
collapsible sections list 14-shift-validity-expired PTWs (View/Close/Close All)
and run-cycle-shift-ended PTWs (View/Hold/Close), each row acting straight through
MainWindow's existing hold/close request plumbing.
"""

from datetime import datetime
from functools import partial
import qtawesome as qta
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QToolButton,
                              QPushButton, QScrollArea, QWidget, QDialogButtonBox, QMessageBox)

from models.PTW import PTW
from network.clientRequests import ClientRequests
from widgets.RefreshOverlay import RefreshOverlay


class DialogPtwAlarms(QDialog):
    """Grouped reminder popup for MainWindow._checkPtwAlarms() — two independent, individually
    collapsible sections:

    - PTWs that exceeded their 14-shift validity (PTW.needsCloseAlarm()) — View + Close per
      row, plus a "Close All" bulk action.
    - PTWs whose current run cycle's shift has ended while still RUNNING
      (PTW.isRunCycleShiftExpired()) — View + Hold + Close per row.

    A PTW past both limits at once (rare, but possible) appears in both sections — they're
    independent conditions with independent actions. Every button calls straight into the
    same MainWindow.requestToHldPTW/requestToClsPTW used by the table context menus (no
    duplicated request logic here), and disables itself in place once its own action
    succeeds, so the dialog stays open and usable for whatever's left while the department
    works through the list — nothing here ever acts on a PTW without an explicit click.

    View opens its own DialogPTW directly (rather than delegating to MainWindow.viewPTW) so
    the busy overlay shown while it builds appears on *this* dialog — the one actually on
    screen — instead of flashing on the (possibly obscured) MainWindow underneath."""

    def __init__(self, mainWindow, validityExpired: list[PTW], shiftExpired: list[PTW]):
        """Build the two collapsible sections from the given already-computed alarm lists.

        Args:
            validityExpired: PTWs past their 14-shift validity (needsCloseAlarm()),
                rendered with View/Close per row and a "Close All" bulk button.
            shiftExpired: PTWs whose current run cycle's shift has ended while still
                RUNNING (isRunCycleShiftExpired()), rendered with View/Hold/Close.
        """
        super().__init__(mainWindow)
        self._mainWindow = mainWindow
        self.setWindowTitle("PTW Attention Required")

        outer = QVBoxLayout(self)
        repeatMinutes = getattr(mainWindow, '_PTW_ALARM_REPEAT_MINUTES', 5)
        intro = QLabel(f"This reminder repeats every {repeatMinutes} minutes for anything still unresolved below.")
        intro.setWordWrap(True)
        outer.addWidget(intro)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        contentLyt = QVBoxLayout(content)

        self._validityCloseButtons = {}
        validitySection = QWidget()
        validityLyt = QVBoxLayout(validitySection)
        validityLyt.setContentsMargins(0, 0, 0, 0)
        self.btnCloseAll = None
        if validityExpired:
            self.btnCloseAll = QPushButton(qta.icon('fa6s.stop'), "Close All")
            self.btnCloseAll.clicked.connect(self._closeAll)
            for ptw in validityExpired:
                validityLyt.addWidget(self._validityRow(ptw))
        else:
            validityLyt.addWidget(QLabel("None."))
        contentLyt.addWidget(self._collapsibleSection(
            f"Exceeded 14-shift validity — needs closing ({len(validityExpired)})", validitySection,
            headerExtra=self.btnCloseAll,
        ))

        contentLyt.addSpacing(16)

        shiftSection = QWidget()
        shiftLyt = QVBoxLayout(shiftSection)
        shiftLyt.setContentsMargins(0, 0, 0, 0)
        if shiftExpired:
            for ptw in shiftExpired:
                shiftLyt.addWidget(self._shiftRow(ptw))
        else:
            shiftLyt.addWidget(QLabel("None."))
        contentLyt.addWidget(self._collapsibleSection(f"Run cycle shift ended — needs hold/close ({len(shiftExpired)})", shiftSection))

        contentLyt.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        outer.addWidget(btns)

        # Parented to self, not mainWindow — see the class docstring: View's busy overlay must
        # show on this dialog, since it's the window actually in front of the user.
        self._refreshOverlay = RefreshOverlay(self)

        if mainWindow:
            self.setMinimumWidth(int(mainWindow.width() * 0.6))
        self.setMinimumHeight(500)

    def _collapsibleSection(self, title: str, content: QWidget, headerExtra: QWidget = None) -> QWidget:
        """A header row — toggle button, optionally with a trailing widget (e.g. "Close All")
        pinned to its right — that shows/hides `content` below it. `headerExtra` stays in the
        header row itself, so it's reachable even while `content` is collapsed. Starts
        expanded — this dialog's whole job is surfacing what needs attention, so nothing
        should start hidden."""
        section = QWidget()
        lyt = QVBoxLayout(section)
        lyt.setContentsMargins(0, 0, 0, 0)

        btnToggle = QToolButton()
        btnToggle.setCheckable(True)
        btnToggle.setChecked(True)
        btnToggle.setAutoRaise(True)
        btnToggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btnToggle.setIcon(qta.icon('fa6s.chevron-down'))
        btnToggle.setText(title)
        btnToggle.setFont(QFont("Helvetica", 13, QFont.Weight.Bold))
        btnToggle.setStyleSheet("QToolButton { border: none; }")

        def onToggled(expanded):
            """Show/hide content and flip the chevron icon. Slot for btnToggle.toggled."""
            content.setVisible(expanded)
            btnToggle.setIcon(qta.icon('fa6s.chevron-down' if expanded else 'fa6s.chevron-right'))
        btnToggle.toggled.connect(onToggled)

        headerRow = QHBoxLayout()
        headerRow.addWidget(btnToggle)
        headerRow.addStretch(1)
        if headerExtra:
            headerRow.addWidget(headerExtra)

        lyt.addLayout(headerRow)
        lyt.addWidget(content)
        return section

    def _rowLabel(self, ptw: PTW) -> QLineEdit:
        """Build the read-only "PTW #id — description" label used at the left of a row."""
        box = QLineEdit(f"PTW #{ptw.id} — {ptw.description}")
        box.setReadOnly(True)
        box.setCursorPosition(0)
        return box

    def _view(self, ptw: PTW):
        """Open ptw in a read-only DialogPTW. Slot for a row's View button click.

        Builds its own DialogPTW directly (rather than delegating to
        MainWindow.viewPTW) so the busy overlay shown while it builds appears on
        this dialog, since it's the window actually in front of the user.
        """
        from dialogs.DialogPTW import DialogPTW
        self._refreshOverlay.showBusy()
        dlg = DialogPTW(self, self._mainWindow.loggedUser, ptw, None, False, True, f'View Mode - PTW# {ptw.id}')
        self._refreshOverlay.hideBusy()
        dlg.exec()

    def _validityRow(self, ptw: PTW) -> QWidget:
        """Build one row of the validity-expired section: label plus View/Close buttons."""
        row = QWidget()
        lyt = QHBoxLayout(row)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(self._rowLabel(ptw), stretch=1)

        btnView = QPushButton(qta.icon('fa6.eye'), "View")
        btnView.clicked.connect(partial(self._view, ptw))
        lyt.addWidget(btnView)

        btnClose = QPushButton(qta.icon('fa6s.stop'), "Close")
        btnClose.clicked.connect(partial(self._close, ptw, btnClose, None))
        lyt.addWidget(btnClose)
        self._validityCloseButtons[ptw.id] = btnClose
        return row

    def _shiftRow(self, ptw: PTW) -> QWidget:
        """Build one row of the shift-ended section: label plus View/Hold/Close buttons."""
        row = QWidget()
        lyt = QHBoxLayout(row)
        lyt.setContentsMargins(0, 0, 0, 0)
        lyt.addWidget(self._rowLabel(ptw), stretch=1)

        btnView = QPushButton(qta.icon('fa6.eye'), "View")
        btnView.clicked.connect(partial(self._view, ptw))
        lyt.addWidget(btnView)

        btnHold = QPushButton(qta.icon('fa6s.pause'), "Hold")
        btnClose = QPushButton(qta.icon('fa6s.stop'), "Close")
        btnHold.clicked.connect(partial(self._hold, ptw, btnHold, btnClose))
        btnClose.clicked.connect(partial(self._close, ptw, btnClose, btnHold))
        lyt.addWidget(btnHold)
        lyt.addWidget(btnClose)
        return row

    def _hold(self, ptw: PTW, btnHold: QPushButton, btnClose: QPushButton):
        """Request a hold on ptw. Slot for a shift-ended row's Hold button click.

        Delegates to MainWindow.requestToHldPTW; on success disables both the
        Hold and Close buttons for that row, since a stop request is now pending
        and a second one shouldn't be sent until the IA responds.
        """
        def onDone(err, _):
            """Handle the hold-request result: warn on failure, else disable the row's buttons."""
            if err:
                QMessageBox.warning(self, 'Fail', err)
                return
            btnHold.setEnabled(False)
            btnClose.setEnabled(False)  # a stop request is now pending — no second one until IA responds
        self._mainWindow.requestToHldPTW(-1, ptw, callback=onDone)

    def _close(self, ptw: PTW, btnClose: QPushButton, btnHold: QPushButton = None):
        """Request a close on ptw. Slot for a row's Close button click.

        Delegates to MainWindow.requestToClsPTW; on success disables Close (and
        Hold, if present on this row) and refreshes the "Close All" button's
        enabled state.
        """
        def onDone(err, _):
            """Handle the close-request result: warn on failure, else disable the row's buttons."""
            if err:
                QMessageBox.warning(self, 'Fail', err)
                return
            btnClose.setEnabled(False)
            if btnHold:
                btnHold.setEnabled(False)
            self._refreshCloseAllState()
        self._mainWindow.requestToClsPTW(-1, ptw, callback=onDone)

    def _closeAll(self):
        """Request closing every not-yet-actioned validity-expired PTW, after one confirm.

        Slot for the validity section's "Close All" button click: collects rows
        whose Close button is still enabled, asks a single confirmation covering
        all of them, then fires one close request per PTW directly (bypassing the
        per-row confirmation), disabling each row's Close button as its own
        request succeeds.
        """
        pending = {ptwId: btn for ptwId, btn in self._validityCloseButtons.items() if btn.isEnabled()}
        if not pending:
            return
        reply = QMessageBox.question(
            self, 'Close All', f"Request closing all {len(pending)} PTW(s) listed above?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        user = self._mainWindow.loggedUser
        pa = user.getUsername()
        ts = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        for ptwId, btnClose in pending.items():
            def onDone(err, _, ptwId=ptwId, btnClose=btnClose):
                """Handle one PTW's close-request result: warn on failure, else disable its button."""
                if err:
                    QMessageBox.warning(self, 'Fail', f"PTW #{ptwId}: {err}")
                    return
                btnClose.setEnabled(False)
                self._refreshCloseAllState()
            ClientRequests.requestToClsPTW(user, ptwId, pa, ts, None, callback=onDone)

    def _refreshCloseAllState(self):
        """Disable "Close All" once every validity-section row it covers has been closed."""
        if self.btnCloseAll and all(not btn.isEnabled() for btn in self._validityCloseButtons.values()):
            self.btnCloseAll.setEnabled(False)
