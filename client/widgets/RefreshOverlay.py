"""Busy overlay shown while a GUI refresh is in flight: dims and blocks input, and
plays a live-vector-rendered logo-typing animation until every outstanding refresh
has finished.

Busy state is app-wide, coordinated by the module-level `_Manager` singleton: a
`showBusy()` on any window's overlay dims that window AND every other window currently
on screen - dialogs included, via dimmers created on demand for windows that never made
their own - so the busy state stays visible even when a dialog is stacked on top of the
refreshing window, and blocks both mouse (by covering the window) and keyboard (by
stealing focus and swallowing key/shortcut events) everywhere."""

from PyQt6.QtCore import Qt, QEvent, QEventLoop, pyqtSignal
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication

from helper.i18n import t
from widgets.PtwLogoLive import PtwLogoLive

_WIDGET_W = 220      # the overlay's typing-logo widget size, on-screen
_WIDGET_H = 160


class _Manager:
    """App-wide busy coordinator shared by every `RefreshOverlay`: one refcount for
    all in-flight refreshes (regardless of which window they started from) and a
    registry mapping each top-level window to its dimmer overlay."""

    def __init__(self):
        """Start idle, with no refreshes in flight and no windows registered."""
        self.count = 0
        self._overlays = {}   # top-level window -> its RefreshOverlay dimmer child

    def register(self, overlay):
        """Record `overlay` as the dimmer for its parent window, dropping the registry
        entry automatically when that window is destroyed (the overlay itself dies with
        the window, being its child)."""
        window = overlay.parent()
        self._overlays[window] = overlay
        window.destroyed.connect(lambda _=None, w=window: self._overlays.pop(w, None))

    def showBusy(self, requester):
        """Increment the app-wide busy refcount and dim the requester's window plus
        every other window currently on screen. Also pumps the event loop once
        (excluding user input) so the dimmed overlays actually paint before returning,
        since several callers invoke this right before a blocking synchronous call that
        would otherwise never let them render."""
        self.count += 1
        for overlay in self._targets(requester):
            overlay._showDim()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def hideBusy(self):
        """Decrement the app-wide busy refcount; once it reaches zero, queue every
        dimmer's hide (each applies it at its own typing-cycle boundary)."""
        self.count = max(0, self.count - 1)
        if self.count != 0:
            return
        for overlay in list(self._overlays.values()):
            overlay._queueHide()

    def _targets(self, requester):
        """Return the dimmers to show for a new refresh: the requester's own window
        (even if not visible yet - e.g. a dialog fetching during construction shows
        its dimmer as soon as it appears) plus every currently visible plain window or
        dialog, creating a dimmer on demand for any window that never made its own.
        Windows that pop up later (e.g. the PTW alarm dialog on its timer) are
        deliberately left undimmed."""
        windows = [requester.parent()]
        for w in QApplication.topLevelWidgets():
            wtype = w.windowFlags() & Qt.WindowType.WindowType_Mask
            if w.isVisible() and wtype in (Qt.WindowType.Window, Qt.WindowType.Dialog) and w not in windows:
                windows.append(w)
        return [self._overlays.get(w) or RefreshOverlay(w) for w in windows]


class RefreshOverlay(QWidget):
    """Dims a top-level window and swallows its mouse and keyboard input while a GUI
    refresh is in flight - keeps the user from clicking into a table mid-rebuild and
    hitting stale rows, and from tabbing/shortcutting to controls underneath.

    Drop-in for any QWidget/QDialog window: `self._refreshOverlay = RefreshOverlay(self)`,
    then `showBusy()`/`hideBusy()` (refcounted app-wide, so overlapping refreshes from
    any window don't hide it early) around whatever network call + GUI rebuild needs
    guarding. Tracks the parent's size on its own - no manual resizeEvent forwarding
    needed. Windows without their own instance still get dimmed: `_Manager` creates
    one for them on demand."""

    # Fires whenever this overlay actually hides - whether immediately (never
    # became visible) or after waiting out a pending cycle-boundary hide (see
    # _queueHide/_onCycleBoundary). A caller that's about to hide/replace the
    # overlay's whole PARENT WINDOW (which would yank the animation off
    # mid-stroke regardless of this class's own cycle-boundary wait, since the
    # overlay is just a child widget of it) should wait for this signal first -
    # see main.py's _showMainWindow for the login-window example.
    hidden = pyqtSignal()

    def __init__(self, parent):
        """Build the dimmed overlay covering the `parent` window: configure its
        appearance, wait cursor, and focus stealing, lay out the typing logo and
        "Refreshing..." label, install an event filter on `parent` to keep the overlay
        sized to it, start hidden, and register with the app-wide `_Manager`."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 115);")
        self.setCursor(Qt.CursorShape.WaitCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pendingHide = False
        self._prevFocus = None

        self._logo = PtwLogoLive(self, _WIDGET_W, _WIDGET_H)
        # Fires once per completed typing loop (~2.5s) - lets a refresh that finishes
        # mid-cycle play out to the end of that loop instead of cutting it off.
        self._logo._anim.currentLoopChanged.connect(self._onCycleBoundary)

        text = QLabel(t("Refreshing..."), self)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: transparent;")

        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(self._logo, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(text, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.hide()
        _manager.register(self)

    def eventFilter(self, obj, event):
        """Watch the parent window's events; whenever the parent is resized or shown,
        resize this overlay to match its current rect so it keeps covering the parent
        completely without needing a manual resizeEvent forward."""
        if obj is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)

    def showBusy(self):
        """Report one more in-flight refresh to the app-wide `_Manager`, which dims
        this overlay's window plus every other window currently on screen and cancels
        any hides the last refresh queued up."""
        _manager.showBusy(self)

    def hideBusy(self):
        """Report one in-flight refresh finished to the app-wide `_Manager`, which -
        once no refresh remains anywhere - queues every dimmer's hide so the current
        typing animation cycle can finish, applied later by `_onCycleBoundary`."""
        _manager.hideBusy()

    def _showDim(self):
        """Show this dimmer over its window, canceling any hide previously queued."""
        self._pendingHide = False  # a fresh refresh cancels any hide the last one queued up
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()

    def _queueHide(self):
        """Queue this dimmer's hide for the next typing-cycle boundary. If it never
        actually became visible (its window was never shown while busy), just clear
        the pending show outright - there is no animation cycle to play out, and its
        `_onCycleBoundary` would otherwise never fire to apply the hide."""
        if not self.isVisible():
            self.hide()
            return
        # Don't yank the animation off mid-stroke: queue the hide and let
        # _onCycleBoundary() apply it at the next loop edge, so a refresh that
        # finishes inside one cycle still plays that cycle out to completion -
        # the overlay's total visible time is always a whole multiple of the
        # ~2.5s typing cycle instead of an abrupt, flickery cutoff.
        self._pendingHide = True

    def _onCycleBoundary(self, _loop=None):
        """Slot for the logo animation's `currentLoopChanged` signal, fired once per
        completed ~2.5s typing cycle; if a hide is still pending and the app-wide busy
        refcount is zero, hide the overlay now that the cycle has played out."""
        if self._pendingHide and _manager.count == 0:
            self._pendingHide = False
            self.hide()

    def event(self, event):
        """Swallow ShortcutOverride events while the overlay has focus, so window-level
        shortcuts (QAction/QShortcut) can't fire on the widgets underneath mid-refresh;
        everything else takes the normal QWidget path."""
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Swallow all key presses: the default implementation ignores them, which
        would let them bubble up to the window (and e.g. trigger a focused button's
        default action) underneath the overlay."""
        event.accept()

    def keyReleaseEvent(self, event):
        """Swallow all key releases, matching `keyPressEvent`."""
        event.accept()

    def focusNextPrevChild(self, next):
        """Refuse to move focus on Tab/Backtab while the overlay holds it, so keyboard
        focus can't walk to the widgets underneath; the Tab key press then falls
        through to `keyPressEvent`, which swallows it."""
        return False

    def _clearPrevFocus(self, _obj=None):
        """Slot for the remembered focus widget's `destroyed` signal: forget it so
        `_restoreFocus` doesn't touch a dead widget."""
        self._prevFocus = None

    def _restoreFocus(self):
        """Hand keyboard focus back to the widget that held it before the overlay
        stole it, if that widget still exists."""
        prev, self._prevFocus = self._prevFocus, None
        if prev is not None:
            prev.destroyed.disconnect(self._clearPrevFocus)
            prev.setFocus(Qt.FocusReason.OtherFocusReason)

    def showEvent(self, event):
        """Triggered when the overlay becomes visible; starts the logo-typing
        animation and steals the window's keyboard focus (remembering the previous
        focus widget) so key presses land on the overlay and get swallowed."""
        self._logo.start()
        prev = self.window().focusWidget()
        if prev is not None and prev is not self and self._prevFocus is None:
            self._prevFocus = prev
            prev.destroyed.connect(self._clearPrevFocus)
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        super().showEvent(event)

    def hideEvent(self, event):
        """Triggered when the overlay is hidden; stops the logo-typing animation, hands
        keyboard focus back to whichever widget held it before, and emits `hidden` -
        covers every path that hides this overlay (immediate or deferred to a cycle
        boundary), so callers that need to know when it's actually gone can just wait
        on the one signal instead of duplicating the immediate-vs-deferred logic."""
        self._logo.stop()
        self._restoreFocus()
        super().hideEvent(event)
        self.hidden.emit()


_manager = _Manager()
