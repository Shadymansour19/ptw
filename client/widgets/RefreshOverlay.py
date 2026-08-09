"""Busy overlay shown while a GUI refresh is in flight: dims and blocks input to its
parent widget, and plays an animated bouncing-logo sprite until every outstanding
refresh has finished."""

from PyQt6.QtCore import Qt, QEvent, QEventLoop, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication

from helper.utils import resource_path

_FRAME_W = 140
_FRAME_H = 200
_FRAME_COUNT = 90   # see dev-scripts/generate_refresh_overlay_frames.py


class _BouncingLogo(QWidget):
    """Steps through a precomputed sprite sheet: the logo shrinks into a ball, drops,
    bounces twice, then expands back into the logo - looping. Physics and frames are
    baked in offline (see the generator script) - this just blits the current frame."""

    def __init__(self, parent=None):
        """Load the sprite sheet and configure the looping `progress` animation that
        drives it from 0.0 to 1.0 over one ~2.5s bounce cycle."""
        super().__init__(parent)
        self._sheet = QPixmap(resource_path("assets/sh-logo-bounce-frames.png"))
        self._progress = 0.0
        self.setFixedSize(_FRAME_W, _FRAME_H)

        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(2500)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.setLoopCount(-1)

    def _getProgress(self):
        """Return the current animation progress, in the range [0.0, 1.0]."""
        return self._progress

    def _setProgress(self, value):
        """Set the current animation progress and schedule a repaint so the sprite
        frame matching `value` gets drawn."""
        self._progress = value
        self.update()

    progress = pyqtProperty(float, _getProgress, _setProgress)

    def start(self):
        """Start (or resume) the looping bounce animation."""
        self._anim.start()

    def stop(self):
        """Stop the bounce animation."""
        self._anim.stop()

    def paintEvent(self, event):
        """Triggered whenever Qt needs to redraw the widget (e.g. after `_setProgress`
        calls `update()`); blit the sprite-sheet frame corresponding to the current
        `progress` value."""
        frame = min(_FRAME_COUNT - 1, int(self._progress * _FRAME_COUNT))
        source = QRect(0, frame * _FRAME_H, _FRAME_W, _FRAME_H)
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self._sheet, source)


class RefreshOverlay(QWidget):
    """Dims its parent and swallows input while a GUI refresh is in flight - keeps the
    user from clicking into a table mid-rebuild and hitting stale rows.

    Drop-in for any QWidget/QDialog: `self._refreshOverlay = RefreshOverlay(self)`, then
    `showBusy()`/`hideBusy()` (refcounted, so overlapping refreshes don't hide it early)
    around whatever network call + GUI rebuild needs guarding. Tracks the parent's size
    on its own - no manual resizeEvent forwarding needed."""

    def __init__(self, parent):
        """Build the dimmed overlay covering `parent`: configure its appearance and
        wait cursor, lay out the bouncing logo and "Refreshing..." label, install an
        event filter on `parent` to keep the overlay sized to it, and start hidden."""
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 115);")
        self.setCursor(Qt.CursorShape.WaitCursor)
        self._count = 0
        self._pendingHide = False

        self._logo = _BouncingLogo(self)
        # Fires once per completed bounce loop (~2.5s) - lets a refresh that finishes
        # mid-bounce play out to the end of that loop instead of cutting it off.
        self._logo._anim.currentLoopChanged.connect(self._onCycleBoundary)

        text = QLabel("Refreshing...", self)
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

    def eventFilter(self, obj, event):
        """Watch the parent widget's events; whenever the parent is resized or shown,
        resize this overlay to match its current rect so it keeps covering the parent
        completely without needing a manual resizeEvent forward."""
        if obj is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)

    def showBusy(self):
        """Increment the busy refcount and ensure the overlay is shown, canceling any
        hide previously queued by `hideBusy()`. Also pumps the event loop once
        (excluding user input) so the dimmed overlay actually paints before returning,
        since several callers invoke this right before a blocking synchronous call that
        would otherwise never let it render."""
        self._count += 1
        self._pendingHide = False  # a fresh refresh cancels any hide the last one queued up
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        # Force the dimmed overlay to actually paint before returning - several callers
        # invoke showBusy() right before a synchronous, blocking call (no callback=), which
        # would otherwise never give the event loop a chance to render the pending show().
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def hideBusy(self):
        """Decrement the busy refcount. If it has reached zero and the overlay is
        visible, don't hide it immediately - queue the hide so the current bounce
        animation cycle can finish, applied later by `_onCycleBoundary`."""
        self._count = max(0, self._count - 1)
        if self._count != 0 or not self.isVisible():
            return
        # Don't yank the animation off mid-bounce: queue the hide and let
        # _onCycleBoundary() apply it at the next loop edge, so a refresh that
        # finishes inside one cycle still plays that cycle out to completion -
        # the overlay's total visible time is always a whole multiple of the
        # ~2.5s bounce cycle instead of an abrupt, flickery cutoff.
        self._pendingHide = True

    def _onCycleBoundary(self, _loop=None):
        """Slot for the logo animation's `currentLoopChanged` signal, fired once per
        completed ~2.5s bounce cycle; if a hide is still pending and the refcount is
        zero, hide the overlay now that the cycle has played out."""
        if self._pendingHide and self._count == 0:
            self._pendingHide = False
            self.hide()

    def showEvent(self, event):
        """Triggered when the overlay becomes visible; starts the bouncing-logo
        animation."""
        self._logo.start()
        super().showEvent(event)

    def hideEvent(self, event):
        """Triggered when the overlay is hidden; stops the bouncing-logo animation."""
        self._logo.stop()
        super().hideEvent(event)
