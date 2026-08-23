"""Live-vector-rendered PtW typing animation for RefreshOverlay, drawn fresh
every frame via QPainter instead of blitting a pre-rendered sprite sheet (the
sprite-sheet approach - and its generator, dev-scripts/generate_ptw_logo_
assets.py's old gen_frames() - was retired once this was confirmed better in
the UI; see git history for the sprite version if it's ever needed again).

Why this exists: every shape in the mark is already QPainterPath math (see
PtwLogoGeometry.py) - the sprite was only ever a raster CACHE of that math,
rendered once offline. Drawing directly here means the mark is rasterized
fresh at whatever the widget's real on-screen size and device-pixel-ratio
are, every time - no fixed-resolution sprite to run out of headroom on a
high-DPI display, no QImageReader allocation-limit risk, and one geometry
source of truth instead of a generator script whose output has to be kept in
sync with a shipped asset.

Per Shady: the pen moves at a FIXED SPEED for the whole animation here -
unlike the sprite version's hand-tuned per-segment pacing (TRAVEL_WEIGHT,
PERIOD_A_BOOST, CROSS_EXTRA, PERIOD_B_CUT - all needed there specifically to
compensate for the old discrete/quantized frame-count system, e.g. a short
segment getting rounded down to a single frame and popping instead of
sliding), each segment's screen time here is exactly proportional to its own
raw pixel length, no boosts of any kind. Continuous (non-frame-quantized)
evaluation doesn't suffer the same "too few frames to look smooth" problem a
fixed small frame count does, so the compensating tuning simply isn't needed.
"""

from PyQt6.QtCore import Qt, QPointF, QRectF, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import QWidget

from widgets.PtwLogoGeometry import build_geometry, build_timeline, full_white_path, partial

WHITE = QColor(255, 255, 255)
ACCENT = QColor(140, 220, 170)

# Same proportions as the sprite version's hold: the finished mark sits still
# for the last ~11% of each loop before restarting.
HOLD_FRACTION = 17 / 150


class PtwLogoLive(QWidget):
    """Draws the PtW typing animation live, at whatever `progress` (0..1,
    looping) the driving QPropertyAnimation is currently at."""

    def __init__(self, parent=None, width=220, height=160):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._progress = 0.0

        g = build_geometry()
        self._timeline, self._reveal_st, _, _ = build_timeline(g)
        self._total_length = sum(t["length"] for t in self._timeline)
        cum = [0.0]
        for t in self._timeline:
            cum.append(cum[-1] + t["length"])
        self._cum = cum

        # A segment's FINISHED shape never changes once it's done (the same
        # timeline plays out identically every loop) - cached the first time
        # each index is confirmed done instead of recomputing createStroke()
        # for it on every single subsequent frame for the rest of the cycle.
        self._done_cache = {}

        # Fit the mark's own bounding box (pure vector math - no raster
        # measurement needed) into the widget, the same way the sprite
        # generator does, so the two look comparable size-wise.
        bbox_path = QPainterPath()
        bbox_path.addPath(full_white_path(g))
        for d in g["sh_dashes"]:
            bbox_path.addPath(d)
        bbox_path.addPath(g["tail_green"])
        bbox = bbox_path.boundingRect()
        self._bx, self._by, self._bw, self._bh = bbox.x(), bbox.y(), bbox.width(), bbox.height()

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

    # ---------------------------------------------------------- resolving ----
    def _finished_shapes(self, i, t):
        """The (is_white, shape) pairs a fully-completed segment contributes -
        computed once per index and cached, since a finished segment's shapes
        never change on later frames or later loop cycles. This is the fix
        for the per-frame createStroke() recomputation on already-done
        strokes (up to 5 of them, re-run 60x/sec for the rest of each cycle
        before this): now it only runs once, ever, per segment."""
        cached = self._done_cache.get(i)
        if cached is not None:
            return cached
        cached = []
        if t["kind"] == "stroke":
            is_white = t["color"] == "white"
            for extra in t.get("extras_start", []):
                cached.append((is_white, extra))
            cached.append((is_white, t["stroker"].createStroke(t["path"])))
            for extra in t.get("extras", []):
                cached.append((True, extra))          # extras always land on done_white
        elif t["kind"] == "reveal":
            cached.append((t["color"] == "white", t["full_shape"]))
        elif t["kind"] == "dash":
            cached.append((False, t["shape"]))
        # "travel" contributes nothing persistent - cached stays [].
        self._done_cache[i] = cached
        return cached

    def _resolve(self, progress):
        """Given progress in [0,1] (already de-held, i.e. remapped so 1.0
        means "drawing just finished"), return (done_white, done_green,
        partial_white, partial_green, pen) - mirroring the sprite generator's
        draw_frame() state exactly, just computed continuously instead of
        stepped through discrete frames."""
        target = progress * self._total_length
        done_white, done_green = [], []
        partial_white = partial_green = None
        pen = None

        for i, t in enumerate(self._timeline):
            seg_start, seg_len = self._cum[i], t["length"]
            seg_end = seg_start + seg_len
            fully_done = target >= seg_end or i == len(self._timeline) - 1 and progress >= 1.0

            if fully_done:
                for is_white, shape in self._finished_shapes(i, t):
                    (done_white if is_white else done_green).append(shape)
                continue

            if target < seg_start:
                break

            frac = 0.0 if seg_len <= 0 else max(0.0, min(1.0, (target - seg_start) / seg_len))

            if t["kind"] == "travel":
                f = frac * frac * (3 - 2 * frac)   # same ease in/out as the sprite version
                sx, sy = t["start"].x(), t["start"].y()
                ex, ey = t["end"].x(), t["end"].y()
                pen = (sx + (ex - sx) * f, sy + (ey - sy) * f)
            elif t["kind"] == "stroke":
                for extra in t.get("extras_start", []):
                    (done_white if t["color"] == "white" else done_green).append(extra)
                tip = t["path"].pointAtPercent(frac)
                stroke = t["stroker"].createStroke(partial(t["path"], frac))
                if t["color"] == "white":
                    partial_white = stroke
                else:
                    partial_green = stroke
                pen = (tip.x(), tip.y())
            elif t["kind"] == "reveal":
                tip = t["centerline"].pointAtPercent(frac)
                clip = self._reveal_st.createStroke(partial(t["centerline"], frac))
                revealed = t["full_shape"].intersected(clip)
                if t["color"] == "white":
                    partial_white = revealed
                else:
                    partial_green = revealed
                pen = (tip.x(), tip.y())
            elif t["kind"] == "dash":
                shape = t["shape"]
                bounds = shape.boundingRect()
                center = bounds.center()
                grow = frac
                scaled = QPainterPath()
                scaled.addRoundedRect(
                    QRectF(center.x() - bounds.width() / 2 * grow, center.y() - bounds.height() / 2 * grow,
                           bounds.width() * grow, bounds.height() * grow),
                    bounds.height() / 2 * grow, bounds.height() / 2 * grow)
                partial_green = scaled
                pen = (center.x(), center.y())
            break

        return done_white, done_green, partial_white, partial_green, pen

    # ------------------------------------------------------------- paint ----
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        draw_progress = min(1.0, self._progress / (1.0 - HOLD_FRACTION))
        holding = self._progress > 1.0 - HOLD_FRACTION

        w, h = self.width(), self.height()
        margin = 14 * w / 220
        s = min((w - margin) / self._bw, (h - margin) / self._bh)
        painter.translate((w - self._bw * s) / 2, (h - self._bh * s) / 2)
        painter.scale(s, s)
        painter.translate(-self._bx, -self._by)

        done_white, done_green, partial_white, partial_green, pen = self._resolve(draw_progress)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(WHITE)
        for path in done_white:
            painter.drawPath(path)
        if partial_white is not None:
            painter.drawPath(partial_white)
        painter.setBrush(ACCENT)
        for path in done_green:
            painter.drawPath(path)
        if partial_green is not None:
            painter.drawPath(partial_green)
        if pen is not None and not holding:
            painter.drawEllipse(QPointF(*pen), 44, 44)
