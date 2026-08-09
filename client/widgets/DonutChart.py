"""Reusable clickable/hoverable donut-chart widget.

Provides `DonutChart` (ring + legend, optional title) and `DonutSegment`
(one slice's label/count/color/click-callback), used by the home-page
dashboards (e.g. PTW approval-cycle and running-by-location donuts, the
Admin users-by-department donut).
"""
import math
from dataclasses import dataclass
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, QSize
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                              QSizePolicy, QGraphicsOpacityEffect)


# Fixed categorical palette (theme-agnostic, like PTW's per-type colors) drawn from the
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
    """One donut slice: its label, count, color, and optional click callback."""

    label: str
    count: int
    color: QColor
    callback: Optional[Callable[[], None]] = None


class _Ring(QWidget):
    """The painted donut ring: draws segments and handles hover/click hit-testing."""

    def __init__(self, parent=None):
        """Initialize empty segment state, enable mouse tracking, and set size constraints."""
        super().__init__(parent)
        self._segments: list[DonutSegment] = []
        self._hoverIndex: int | None = None
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        """Return the ring's preferred size for layout purposes."""
        return QSize(280, 280)

    def setSegments(self, segments: list[DonutSegment]):
        """Replace the drawn segments, clear hover/tooltip/cursor state, and repaint."""
        self._segments = segments
        self._hoverIndex = None
        self.setToolTip("")
        self.unsetCursor()
        self.update()

    def _geometry(self):
        """Compute the ring's drawing rect and outer/inner radii.

        The rect is centered in, and capped at `RING_MAX_SIDE` within, the
        widget's own bounds; the inner radius is a fixed 0.55 fraction of the
        outer radius (the donut hole).
        """
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
        """Compute each segment's (startAngle, span, segment) in degrees, proportional to its share of the total count.

        Angles run clockwise from the top (0 degrees), matching both the
        painting convention in `_segmentPath` and the hit-testing convention
        in `_angleAt`. Segments with count <= 0 still get an entry with
        span 0. Returns `([], 0)` if the total count is 0.
        """
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
        """Build the donut-wedge QPainterPath for one segment's angle span.

        `phiStart`/`phiSpan` are degrees clockwise from the top (as produced
        by `_cumulativeAngles`); they're converted to Qt's arc-angle
        convention (counterclockwise from 3 o'clock) via
        `qtStart = 90 - phiStart`, `qtSpan = -phiSpan` before drawing the
        outer arc, the connecting inner arc, and closing the path.
        """
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
        """Paint the ring: a gray placeholder wedge when there's no data, else each segment.

        The hovered segment (if any) is drawn lightened. The total count (or
        "No\\nData") is drawn centered in the donut's hole.
        """
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
        """Convert a widget-local position to its angle on the ring, or None if outside the ring band.

        Returns degrees measured clockwise from the top (0-360), matching
        the convention used by `_cumulativeAngles`/`_segmentPath`. Positions
        whose distance from center falls outside `[innerR, outerR]` (i.e.
        not on the ring itself) return None.
        """
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
        """Return the `(index, DonutSegment)` at a position, or None if not on any segment."""
        theta = self._angleAt(pos)
        if theta is None:
            return None
        angles, _ = self._cumulativeAngles()
        for i, (start, span, seg) in enumerate(angles):
            if start <= theta < start + span:
                return i, seg
        return None

    def mouseMoveEvent(self, event):
        """Qt handler for mouse movement over the ring; update hover highlight, tooltip, and cursor.

        Triggered continuously as the pointer moves (mouse tracking is
        enabled). Repaints when the hovered segment changes; shows a
        "label: count (pct%)" tooltip and pointing-hand cursor while over a
        segment with a callback, clearing both otherwise.
        """
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
        """Qt handler triggered when the mouse leaves the ring; clear hover highlight and cursor."""
        if self._hoverIndex is not None:
            self._hoverIndex = None
            self.update()
        self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        """Qt handler triggered on a click inside the ring; invoke the clicked segment's callback, if any."""
        hit = self._segmentAt(event.position())
        if hit and hit[1].callback:
            hit[1].callback()
        super().mousePressEvent(event)


class _LegendRow(QPushButton):
    """One legend entry: a colored-dot icon plus "label — count (pct%)" text.

    Acts as a clickable button (wired to the segment's callback) when the
    segment has one; otherwise disabled and dimmed for zero-count segments.
    """

    def __init__(self, segment: DonutSegment, percent: float, parent=None):
        """Build the legend row: paint the colored-dot icon, set its text, and wire its click."""
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
    """Public donut-chart widget: an optional title, a clickable ring, and a legend column.

    Reused across the home-page dashboards (PTW approval-cycle/location
    donuts, Admin users-by-department donut); segments and their
    click-callbacks are supplied via `setSegments()`.
    """

    def __init__(self, title: str = "", parent=None):
        """Build the optional title label and the ring+legend body layout."""
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
        """Update the ring and rebuild the legend rows from the given segments."""
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
