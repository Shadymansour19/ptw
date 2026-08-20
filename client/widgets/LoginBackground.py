"""Decorative backdrop widget for the login screen.

Paints a diagonal brand-colored gradient across the whole window, plus a soft radial
glow whose center sits exactly on the widget's bottom-right corner - since only the
widget's own rect is visible, that circle renders as a single quarter-circle occupying
the corner, fading the background there to something lighter/more transparent behind
the login fields card that sits on top of it.
"""

from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PyQt6.QtWidgets import QWidget


class LoginBackground(QWidget):
    """Custom-painted background for `LoginWindow`: brand gradient + a bottom-right glow."""

    def paintEvent(self, event):
        """Qt paint handler: fill with a diagonal gradient, then overlay a radial glow
        centered on the bottom-right corner (visible only as a quarter-circle)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()

        gradient = QLinearGradient(QPointF(rect.topLeft()), QPointF(rect.bottomRight()))
        gradient.setColorAt(0.0, QColor(14, 28, 20))
        gradient.setColorAt(1.0, QColor(21, 58, 36))
        painter.fillRect(rect, gradient)

        corner = QPointF(rect.right(), rect.bottom())
        radius = (rect.width() ** 2 + rect.height() ** 2) ** 0.5 * 0.55
        glow = QRadialGradient(corner, radius)
        glow.setColorAt(0.0, QColor(255, 255, 255, 100))
        glow.setColorAt(0.6, QColor(255, 255, 255, 35))
        glow.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(corner, radius, radius)

        super().paintEvent(event)
