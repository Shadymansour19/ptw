from PyQt6.QtCore import Qt, QEvent, QEventLoop, QRect, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPixmap, QPainter
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QApplication

from utils import resource_path

_FRAME_W = 140
_FRAME_H = 200
_FRAME_COUNT = 90   # see dev-scripts/generate_refresh_overlay_frames.py


class _BouncingLogo(QWidget):
    """Steps through a precomputed sprite sheet: the logo shrinks into a ball, drops,
    bounces twice, then expands back into the logo - looping. Physics and frames are
    baked in offline (see the generator script) - this just blits the current frame."""

    def __init__(self, parent=None):
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
        return self._progress

    def _setProgress(self, value):
        self._progress = value
        self.update()

    progress = pyqtProperty(float, _getProgress, _setProgress)

    def start(self):
        self._anim.start()

    def stop(self):
        self._anim.stop()

    def paintEvent(self, event):
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
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 115);")
        self.setCursor(Qt.CursorShape.WaitCursor)
        self._count = 0

        self._logo = _BouncingLogo(self)

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
        if obj is self.parent() and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.setGeometry(self.parent().rect())
        return super().eventFilter(obj, event)

    def showBusy(self):
        self._count += 1
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        # Force the dimmed overlay to actually paint before returning - several callers
        # invoke showBusy() right before a synchronous, blocking call (no callback=), which
        # would otherwise never give the event loop a chance to render the pending show().
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def hideBusy(self):
        self._count = max(0, self._count - 1)
        if self._count == 0:
            self.hide()

    def showEvent(self, event):
        self._logo.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self._logo.stop()
        super().hideEvent(event)
