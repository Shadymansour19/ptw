import math
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QSizePolicy, QGraphicsOpacityEffect)


# Fixed categorical palette (theme-agnostic, like PTWData's per-type colors) drawn from the
# dataviz skill's validated 8-hue categorical theme.
APPROVAL_CYCLE_COLORS = {
    'Requested':    QColor('#2a78d6'),
    'Under Review': QColor('#eda100'),
    'Returned':     QColor('#e34948'),
    'Approved':     QColor('#008300'),
}
LOCATION_COLORS = [QColor('#2a78d6'), QColor('#1baf7a'), QColor('#eda100'), QColor('#008300')]
DEPARTMENT_COLOR_CYCLE = [
    QColor(c) for c in
    ['#2a78d6', '#1baf7a', '#eda100', '#008300', '#4a3aa7', '#e34948', '#e87ba4', '#eb6834']
]

RING_MAX_SIDE = 420


@dataclass
class DonutSegment:
    label: str
    count: int
    color: QColor
    callback: Optional[Callable[[], None]] = None


class _Ring(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._segments: list[DonutSegment] = []
        self._hoverIndex: int | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(280, 280)

    def setSegments(self, segments: list[DonutSegment]):
        self._segments = segments
        self._hoverIndex = None
        self.setToolTip("")
        self.unsetCursor()
        self.update()

    def _geometry(self):
        # The widget fills its whole layout cell (so it never sits left-biased next to the
        # legend); the drawn ring itself is centered within that cell and capped so it doesn't
        # balloon on very large windows.
        side = max(min(min(self.width(), self.height()) - 4, RING_MAX_SIDE), 20)
        rect = QRectF(0, 0, side, side)
        rect.moveCenter(QPointF(self.width() / 2, self.height() / 2))
        outerR = side / 2
        innerR = outerR * 0.55
        return rect, outerR, innerR

    def _cumulativeAngles(self):
        total = sum(max(s.count, 0) for s in self._segments)
        result = []
        start = 0.0
        if total <= 0:
            return result, total
        for seg in self._segments:
            span = 360.0 * (max(seg.count, 0) / total)
            result.append((start, span, seg))
            start += span
        return result, total

    def _segmentPath(self, rect, outerR, innerR, phiStart, phiSpan):
        center = rect.center()
        outerRect = QRectF(center.x() - outerR, center.y() - outerR, outerR * 2, outerR * 2)
        innerRect = QRectF(center.x() - innerR, center.y() - innerR, innerR * 2, innerR * 2)
        qtStart = 90 - phiStart
        qtSpan = -phiSpan
        path = QPainterPath()
        path.arcMoveTo(outerRect, qtStart)
        path.arcTo(outerRect, qtStart, qtSpan)
        path.arcTo(innerRect, qtStart + qtSpan, -qtSpan)
        path.closeSubpath()
        return path

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect, outerR, innerR = self._geometry()
        angles, total = self._cumulativeAngles()

        if total <= 0:
            path = self._segmentPath(rect, outerR, innerR, 0, 359.99)
            painter.fillPath(path, QColor(128, 128, 128, 60))
        else:
            for i, (start, span, seg) in enumerate(angles):
                if span <= 0:
                    continue
                color = QColor(seg.color)
                if i == self._hoverIndex:
                    color = color.lighter(120)
                painter.fillPath(self._segmentPath(rect, outerR, innerR, start, span), color)

        painter.setPen(self.palette().windowText().color())
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSize(max(int(innerR * 0.35), 14))
        painter.setFont(font)
        centerRect = QRectF(rect.center().x() - innerR, rect.center().y() - innerR, innerR * 2, innerR * 2)
        painter.drawText(centerRect, Qt.AlignmentFlag.AlignCenter, str(total) if total > 0 else "No\nData")

    def _angleAt(self, pos):
        rect, outerR, innerR = self._geometry()
        center = rect.center()
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        r = math.hypot(dx, dy)
        if r < innerR or r > outerR:
            return None
        theta = math.degrees(math.atan2(dx, -dy))
        if theta < 0:
            theta += 360
        return theta

    def _segmentAt(self, pos):
        theta = self._angleAt(pos)
        if theta is None:
            return None
        angles, _ = self._cumulativeAngles()
        for i, (start, span, seg) in enumerate(angles):
            if start <= theta < start + span:
                return i, seg
        return None

    def mouseMoveEvent(self, event):
        hit = self._segmentAt(event.position())
        newIndex = hit[0] if hit else None
        if newIndex != self._hoverIndex:
            self._hoverIndex = newIndex
            self.update()
        if hit and hit[1].callback:
            seg = hit[1]
            total = sum(max(s.count, 0) for s in self._segments)
            pct = (seg.count / total * 100) if total else 0
            self.setToolTip(f"{seg.label}: {seg.count} ({pct:.0f}%)")
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setToolTip("")
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hoverIndex is not None:
            self._hoverIndex = None
            self.update()
        self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        hit = self._segmentAt(event.position())
        if hit and hit[1].callback:
            hit[1].callback()
        super().mousePressEvent(event)


class _LegendRow(QPushButton):
    def __init__(self, segment: DonutSegment, percent: float, parent=None):
        super().__init__(parent)
        pix = QPixmap(12, 12)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(segment.color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 12, 12)
        p.end()

        self.setIcon(QIcon(pix))
        self.setIconSize(QSize(12, 12))
        self.setText(f"  {segment.label} — {segment.count} ({percent:.0f}%)")
        self.setFlat(True)
        self.setEnabled(segment.callback is not None)
        if segment.callback:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.clicked.connect(segment.callback)
        self.setStyleSheet("""
            QPushButton { text-align: left; border: none; background: transparent; padding: 3px 6px; border-radius: 4px; }
            QPushButton:hover { background: rgba(128, 128, 128, 0.15); }
            QPushButton:pressed { background: rgba(128, 128, 128, 0.30); }
        """)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(1.0 if segment.count > 0 else 0.5)
        self.setGraphicsEffect(effect)


class DonutChart(QWidget):
    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._segments: list[DonutSegment] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        titleHeight = 0
        if title:
            titleLbl = QLabel(title)
            titleLbl.setFont(QFont("Helvetica", 14, QFont.Weight.Bold))
            titleLbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(titleLbl)
            titleHeight = titleLbl.sizeHint().height()

        # Cap the whole widget's height to what a maxed-out ring actually needs, so extra
        # vertical space collects outside the chart (pushed there by the caller's layout)
        # instead of as a gap between the title and the ring.
        self.setMaximumHeight(titleHeight + layout.spacing() + RING_MAX_SIDE + 10)

        body = QHBoxLayout()
        body.setSpacing(16)
        self._ring = _Ring()
        body.addWidget(self._ring, 2)

        self._legendContainer = QWidget()
        self._legendLayout = QVBoxLayout(self._legendContainer)
        self._legendLayout.setContentsMargins(0, 0, 0, 0)
        self._legendLayout.setSpacing(2)
        self._legendLayout.addStretch()
        self._legendLayout.addStretch()
        body.addWidget(self._legendContainer, 1)

        layout.addLayout(body, 1)

    def setSegments(self, segments: list[DonutSegment]):
        self._segments = segments
        self._ring.setSegments(segments)

        while self._legendLayout.count():
            item = self._legendLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._legendLayout.addStretch()
        total = sum(max(s.count, 0) for s in segments)
        for seg in segments:
            pct = (seg.count / total * 100) if total else 0
            self._legendLayout.addWidget(_LegendRow(seg, pct))
        self._legendLayout.addStretch()
