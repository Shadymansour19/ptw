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
            validityLyt.addWidget(self.btnCloseAll)
            for ptw in validityExpired:
                validityLyt.addWidget(self._validityRow(ptw))
        else:
            validityLyt.addWidget(QLabel("None."))
        contentLyt.addWidget(self._collapsibleSection(f"Exceeded 14-shift validity — needs closing ({len(validityExpired)})", validitySection))

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

    def _collapsibleSection(self, title: str, content: QWidget) -> QWidget:
        """A header button toggling `content`'s visibility. Starts expanded — this dialog's
        whole job is surfacing what needs attention, so nothing should start hidden."""
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
            content.setVisible(expanded)
            btnToggle.setIcon(qta.icon('fa6s.chevron-down' if expanded else 'fa6s.chevron-right'))
        btnToggle.toggled.connect(onToggled)

        lyt.addWidget(btnToggle)
        lyt.addWidget(content)
        return section

    def _rowLabel(self, ptw: PTW) -> QLineEdit:
        box = QLineEdit(f"PTW #{ptw.id} — {ptw.description}")
        box.setReadOnly(True)
        box.setCursorPosition(0)
        return box

    def _view(self, ptw: PTW):
        from dialogs.DialogPTW import DialogPTW
        self._refreshOverlay.showBusy()
        dlg = DialogPTW(self, self._mainWindow.loggedUser, ptw, None, False, True, f'View Mode - PTW# {ptw.id}')
        self._refreshOverlay.hideBusy()
        dlg.exec()

    def _validityRow(self, ptw: PTW) -> QWidget:
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
        def onDone(err, _):
            if err:
                QMessageBox.warning(self, 'Fail', err)
                return
            btnHold.setEnabled(False)
            btnClose.setEnabled(False)  # a stop request is now pending — no second one until IA responds
        self._mainWindow.requestToHldPTW(-1, ptw, callback=onDone)

    def _close(self, ptw: PTW, btnClose: QPushButton, btnHold: QPushButton = None):
        def onDone(err, _):
            if err:
                QMessageBox.warning(self, 'Fail', err)
                return
            btnClose.setEnabled(False)
            if btnHold:
                btnHold.setEnabled(False)
            self._refreshCloseAllState()
        self._mainWindow.requestToClsPTW(-1, ptw, callback=onDone)

    def _closeAll(self):
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
                if err:
                    QMessageBox.warning(self, 'Fail', f"PTW #{ptwId}: {err}")
                    return
                btnClose.setEnabled(False)
                self._refreshCloseAllState()
            ClientRequests.requestToClsPTW(user, ptwId, pa, ts, None, callback=onDone)

    def _refreshCloseAllState(self):
        if self.btnCloseAll and all(not btn.isEnabled() for btn in self._validityCloseButtons.values()):
            self.btnCloseAll.setEnabled(False)
