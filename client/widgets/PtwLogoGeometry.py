"""Shared PtW / شادي mark geometry and typing-animation timeline.

This is the single source of truth for the mark's shapes and for the ordered
"how it gets drawn" plan - both dev-scripts/generate_ptw_logo_assets.py (the
offline still-image generator) and widgets/PtwLogoLive.py (the live-vector-
rendered typing animation used by RefreshOverlay) import from here, so the
two can never silently drift apart. It has no QApplication dependency of its
own - building QPainterPath/QPainterPathStroker objects doesn't need one - so it's safe to
import from the already-running client app or from a standalone script alike.

See dev-scripts/generate_ptw_logo_assets.py's module docstring for the mark's
design history; this file only carries the geometry itself.
"""

import math

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainterPath, QPainterPathStroker

S = 68


def make_stroker(cap, width=S):
    st = QPainterPathStroker()
    st.setWidth(width)
    st.setCapStyle(cap)
    st.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return st


round_st = make_stroker(Qt.PenCapStyle.RoundCap)
flat_st = make_stroker(Qt.PenCapStyle.FlatCap)
dash_st = make_stroker(Qt.PenCapStyle.RoundCap, 48)


# ---------------------------------------------------------------- geometry ----
def bez(t, P0, C1, C2, P3):
    u = 1 - t
    return (u**3*P0[0] + 3*u*u*t*C1[0] + 3*u*t*t*C2[0] + t**3*P3[0],
            u**3*P0[1] + 3*u*u*t*C1[1] + 3*u*t*t*C2[1] + t**3*P3[1])


def build_geometry():
    """Return the mark's building blocks: centerline paths, filled extras, accents."""
    g = {}

    # ي's straight vertical segment (145,350)-(145,585) is lengthened by
    # STEM_EXTEND; the descender cubic below it is translated down by the same
    # amount so its shape/curvature is exactly preserved, just relocated -
    # carrying the tip and the whole tail-split (dots) down with it, per Shady.
    STEM_EXTEND = 60
    dP0 = (145, 585 + STEM_EXTEND)
    dC1 = (142, 660 + STEM_EXTEND)
    dC2 = (110, 730 + STEM_EXTEND)
    dP3 = (62, 768 + STEM_EXTEND)
    dsamp = []
    for i in range(201):
        t = i / 200
        x, y = bez(t, dP0, dC1, dC2, dP3)
        u = 1 - t
        dx = 3*u*u*(dC1[0]-dP0[0]) + 6*u*t*(dC2[0]-dC1[0]) + 3*t*t*(dP3[0]-dC2[0])
        dy = 3*u*u*(dC1[1]-dP0[1]) + 6*u*t*(dC2[1]-dC1[1]) + 3*t*t*(dP3[1]-dC2[1])
        n = (dx*dx + dy*dy) ** 0.5
        dsamp.append((x, y, dy / n, -dx / n, dx / n, dy / n))

    ya = QPainterPath()                            # ي: slit -> stem -> descender start
    ya.moveTo(214, 215)
    ya.cubicTo(175, 219, 147, 265, 145, 350)
    ya.lineTo(*dP0)
    g["ya"] = ya

    # The tail split, per Shady's sketch: the complete original line (true ±H
    # edges and its round end cap) is divided by a thin separator that follows
    # the descender's OWN curvature (not a straight chord - a straight cut
    # across a curving strip produces knife-point artifacts where it meets the
    # strip's edges at a glancing angle). The white part tapers to a point; the
    # green dots part grows from a point and owns the line's rounded ending.
    #
    # sep_c(i) is a SINGLE unbranched linear function of arc length, evaluated
    # for every sample with no piecewise/sentinel logic at all - by
    # construction it cannot have a discontinuity, which is what caused the
    # earlier corner pinching (a hidden jump where a piecewise sentinel met an
    # insufficiently-saturated ramp once the gap/tilt parameters changed).
    # HALF_SPAN is the arc-length half-width of the transition: larger = the
    # cut crosses the stroke more gradually = a shallower tilt angle.
    arcs, acc = [0.0], 0.0
    for a, b in zip(dsamp, dsamp[1:]):
        acc += ((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5
        arcs.append(acc)
    H = S / 2.0
    SEP = 22.0
    CENTER = 0.73 * acc
    HALF_SPAN = 1.05 * acc     # tilt control - larger = shallower/more gradual

    def sep_c(i):
        return 3*H - 6*H * (arcs[i] - (CENTER - HALF_SPAN)) / (2 * HALF_SPAN)

    def off(i, d):
        x, y, nx, ny = dsamp[i][:4]
        return (x + d * nx, y + d * ny)

    # white part: full width until the separator carves in; tapers to a point
    wpts_r, wpts_l = [], []
    for i in range(0, 201):
        r = min(H, sep_c(i) - SEP / 2)
        if r <= -H + 0.5:
            break
        wpts_r.append(off(i, r))
        wpts_l.append(off(i, -H))
    tail_w = QPainterPath()
    tail_w.moveTo(*wpts_r[0])
    for q in wpts_r[1:]:
        tail_w.lineTo(*q)
    for q in reversed(wpts_l):
        tail_w.lineTo(*q)
    tail_w.closeSubpath()
    g["tail_white"] = tail_w

    # green part: grows from a point on the right edge, ends with the line's
    # original round cap.
    #
    # The natural taper's first ~40 samples are only a fraction of a pixel
    # wide - a spike added right at that point is thinner than the mark's own
    # corner-smoothing blur pass and gets rendered away entirely (verified: it
    # changed the vector path but produced a PIXEL-IDENTICAL raster). Instead,
    # discard that too-thin stretch and rejoin at an anchor point where the
    # ribbon already has honest width, with plain straight edges from the new
    # tip - forcing the join to match the natural curve's exact tangent there
    # (tried first, via cubic and then quadratic beziers) swung the curve out
    # before turning sharply in to satisfy that constraint, which read as an
    # S-shaped kink, worse than a straight edge. Every other joint in this
    # mark (the P/ي slit, the t/W crossbar) is plain geometry smoothed by the
    # shared blur+threshold pass below, not a hand-fit curve - this matches
    # that same pattern instead of fighting it.
    ANCHOR_W = 20       # rejoin the natural taper once it's this wide (px)
    TIP_RIGHT = 34      # new tip position, as an offset from the natural
    TIP_UP = 30         # (un-widened) corner - right and up, in real pixels

    i_start = next(i for i in range(201) if max(-H, sep_c(i) + SEP / 2) < H - 0.5)
    i_anchor = next(i for i in range(i_start, 201)
                    if H - max(-H, sep_c(i) + SEP / 2) >= ANCHOR_W)
    corner = off(i_start, H)               # the natural (un-widened) corner
    tip = (corner[0] + TIP_RIGHT, corner[1] - TIP_UP)
    gpts_r = [off(i, H) for i in range(i_anchor, 201)]
    gpts_l = [off(i, max(-H, sep_c(i) + SEP / 2)) for i in range(i_anchor, 201)]

    tail_g = QPainterPath()
    tail_g.moveTo(*tip)
    tail_g.lineTo(*gpts_r[0])
    for q in gpts_r[1:]:
        tail_g.lineTo(*q)
    tipx, tipy, nx_, ny_, tx_, ty_ = dsamp[200]
    a0 = math.atan2(H * ny_, H * nx_)
    a1 = math.atan2(-H * ny_, -H * nx_)
    amid = math.atan2(ty_, tx_)
    while a1 < a0:
        a1 += 2 * math.pi
    m = (a0 + a1) / 2
    if math.cos(m - amid) < 0:                      # sweep through the tangent side
        a0, a1 = a0 + 2 * math.pi, a1
        a0, a1 = a1, a0
    for k in range(1, 17):
        a = a0 + (a1 - a0) * k / 16
        tail_g.lineTo(tipx + H * math.cos(a), tipy + H * math.sin(a))
    for q in reversed(gpts_l):
        tail_g.lineTo(*q)
    tail_g.lineTo(*tip)
    tail_g.closeSubpath()
    g["tail_green"] = tail_g

    # Animation-only centerlines (used by the typing animation, not by the
    # still mark): the filled tail_white/tail_green ribbons vary in width,
    # which isn't something a stroke-reveal animation can trace directly -
    # these are the underlying descender centerline instead, split at the
    # same i_anchor the still mark uses, each already ordered start-to-end in
    # its drawing direction so no separate reverse flag is needed by callers.
    anim_ya = QPainterPath()                       # bottom (anchor) -> top (dome)
    anim_ya.moveTo(*dsamp[i_anchor][:2])
    for i in range(i_anchor - 1, -1, -1):
        anim_ya.lineTo(dsamp[i][0], dsamp[i][1])
    anim_ya.lineTo(145, 350)
    anim_ya.cubicTo(147, 265, 175, 219, 214, 215)
    g["anim_ya"] = anim_ya

    anim_dots = QPainterPath()                     # anchor -> tip
    anim_dots.moveTo(*dsamp[i_anchor][:2])
    for i in range(i_anchor + 1, 201):
        anim_dots.lineTo(dsamp[i][0], dsamp[i][1])
    g["anim_dots"] = anim_dots

    tip = QPainterPath()                           # ي tilted '/' end face at the slit
    tip.moveTo(212, 180)
    tip.lineTo(256, 180)
    tip.lineTo(223, 248)
    tip.lineTo(212, 248)
    tip.closeSubpath()
    g["ya_tip"] = tip

    dal = QPainterPath()                           # د: slit -> bowl -> baseline bar
    dal.moveTo(296, 215)
    dal.cubicTo(352, 224, 452, 290, 458, 385)
    dal.cubicTo(462, 480, 428, 558, 330, 565)
    dal.lineTo(201, 565)
    g["dal"] = dal

    tip2 = QPainterPath()                          # د start face, parallel tilt
    tip2.moveTo(245, 248)
    tip2.lineTo(278, 180)
    tip2.lineTo(302, 180)
    tip2.lineTo(302, 248)
    tip2.closeSubpath()
    g["dal_tip"] = tip2

    ta = QPainterPath()                            # t/ا: stem -> curved foot -> connector
    ta.moveTo(550, 85)
    ta.lineTo(550, 480)
    ta.cubicTo(550, 540, 590, 563, 670, 565)
    ta.lineTo(770, 565)
    g["ta"] = ta

    cross = QPainterPath()                         # t crossbar - right to left
    cross.moveTo(728, 164)                         # (direction only matters for
    cross.lineTo(470, 164)                         # the animation; the stroked
    g["cross"] = cross                             # outline itself is unaffected)

    w1 = QPainterPath()                            # W teeth 1-2 + cup 1
    w1.moveTo(848, 268)
    w1.lineTo(848, 445)
    w1.cubicTo(850, 520, 880, 568, 920, 569)
    w1.cubicTo(962, 568, 990, 520, 992, 445)
    w1.lineTo(992, 268)
    g["w1"] = w1

    w2 = QPainterPath()                            # W cup 2 + tooth 3
    w2.moveTo(992, 445)
    w2.cubicTo(994, 520, 1024, 568, 1064, 569)
    w2.cubicTo(1106, 568, 1134, 520, 1136, 445)
    w2.lineTo(1136, 268)
    g["w2"] = w2

    dashes = []                                    # ش dots: 3 dashes above the teeth
    for cx in (848, 992, 1136):                    # filled rounded rects (corner
        d = QPainterPath()                         # radius softer than a full pill)
        d.addRoundedRect(QRectF(cx - 51, 130, 102, 68), 29, 29)
        dashes.append(d)
    g["sh_dashes"] = dashes

    # connector tip: complementary to the W's first cup - its outer-left contour
    # (tooth 1 into cup 1) offset outward by S/2 + 18px gap, clipped to the
    # connector bar's band, forms the tip's end face
    cP0, cC1, cC2, cP3 = (848, 445), (850, 520), (880, 568), (920, 569)
    off_ = S / 2 + 18
    face = [(848 - off_, 300)]                     # straight tooth edge above the cup
    for i in range(201):
        t = i / 200
        x, y = bez(t, cP0, cC1, cC2, cP3)
        u = 1 - t
        dx = 3*u*u*(cC1[0]-cP0[0]) + 6*u*t*(cC2[0]-cC1[0]) + 3*t*t*(cP3[0]-cC2[0])
        dy = 3*u*u*(cC1[1]-cP0[1]) + 6*u*t*(cC2[1]-cC1[1]) + 3*t*t*(cP3[1]-cC2[1])
        n = (dx*dx + dy*dy) ** 0.5
        face.append((x - off_*dy/n, y + off_*dx/n))  # left/outward normal
    top_y, bot_y = 565 - S / 2, 565 + S / 2

    def x_at(yv):
        for a, b in zip(face, face[1:]):
            if (a[1] - yv) * (b[1] - yv) <= 0 and a[1] != b[1]:
                f = (yv - a[1]) / (b[1] - a[1])
                return a[0] + f * (b[0] - a[0])
        return face[-1][0]

    wedge = QPainterPath()
    wedge.moveTo(766, top_y)
    wedge.lineTo(x_at(top_y), top_y)
    for q in face:
        if top_y < q[1] < bot_y:
            wedge.lineTo(*q)
    wedge.lineTo(x_at(bot_y), bot_y)
    wedge.lineTo(766, bot_y)
    wedge.closeSubpath()
    g["wedge"] = wedge

    return g


def full_white_path(g):
    """All the mark's white geometry as one filled path (stroked outlines + extras)."""
    white = QPainterPath()
    white.setFillRule(Qt.FillRule.WindingFill)
    white.addPath(flat_st.createStroke(g["ya"]))
    white.addPath(g["tail_white"])
    white.addPath(g["ya_tip"])
    white.addPath(flat_st.createStroke(g["dal"]))
    white.addPath(g["dal_tip"])
    white.addPath(round_st.createStroke(g["ta"]))
    white.addPath(g["wedge"])
    white.addPath(round_st.createStroke(g["cross"]))
    white.addPath(round_st.createStroke(g["w1"]))
    white.addPath(round_st.createStroke(g["w2"]))
    return white


# ------------------------------------------------------------ animation plan ----
def partial(path, frac, reverse=False, samples=64):
    """Polyline of the first `frac` of `path` by length (or the LAST `frac` when
    reverse=True, revealing from the path's end backwards)."""
    lo, hi = (1 - frac, 1.0) if reverse else (0.0, frac)
    poly = QPainterPath()
    poly.moveTo(path.pointAtPercent(lo))
    for i in range(1, samples + 1):
        poly.lineTo(path.pointAtPercent(lo + (hi - lo) * i / samples))
    return poly


def path_length(path, samples=200):
    """Approximate a QPainterPath's on-screen length by summing point-to-point
    distances along evenly spaced percent samples."""
    total = 0.0
    prev = path.pointAtPercent(0.0)
    for i in range(1, samples + 1):
        cur = path.pointAtPercent(i / samples)
        total += ((cur.x() - prev.x()) ** 2 + (cur.y() - prev.y()) ** 2) ** 0.5
        prev = cur
    return total


def build_timeline(g):
    """The ordered "how the mark gets drawn" timeline: each entry strokes/
    reveals a path or grows one ش dot in place, with travel segments
    interleaved wherever the pen has to visibly jump. Every entry's raw pixel
    `length` is set, but NO per-segment duration/frame budget is applied here
    - that's a decision for whoever plays this back (the offline sprite
    generator applies its own tuned weights/boosts; the live-vector widget
    uses pure length, for a constant pen speed throughout).

    Order matches Shady's requested sequence: ي bottom-to-top, د top-to-
    bottom, t, W, then the ش dots right-to-left, the crossbar, and finally a
    travel down to the ي dots.

    Returns (timeline, reveal_st, ya_full_shape, dots_full_shape).
    """
    # The tail split, per Shady's sketch: the complete original line (true ±H
    # edges and its round end cap) is divided by a thin separator that follows
    # the descender's OWN curvature - see build_geometry()'s tail_white/
    # tail_green construction. anim_ya/anim_dots trace the descender's plain
    # centerline - a stroker can animate that as a growing constant-width
    # line, but the tail's REAL shape tapers to a hand-tuned sharp tip, not a
    # constant width. Two earlier attempts got this wrong: stroking the
    # centerline and holding that shape forever left a permanent width/tip
    # mismatch against the real logo; swapping to the exact shape only once
    # the stroke finished (a) dropped the stem+dome - they were part of the
    # ONE combined stroke that got replaced wholesale, not appended alongside
    # - making the P's straight stem vanish for the rest of the cycle, and
    # (b) still produced a visible pop at the swap instant (flat cap -> tilted
    # tip).
    #
    # The actual fix: never draw an approximation at all. "reveal" clips the
    # REAL final shape (ya_full_shape/dots_full_shape below, each already the
    # exact geometry the still logo uses) with a wide stroke of the traveled
    # centerline, growing frame by frame. The visible boundary is always the
    # true tapered/tilted geometry - there is nothing to swap and nothing
    # dropped, because the full shape (stem + dome + tail, or just the tail)
    # is what's being revealed from frame one.
    # Width matched to the mark's own ~68-100px stroke width (plus a modest
    # margin for the tip's off-centerline extension) - not "wide enough to
    # cover everything regardless", which is what made the very first frame
    # already reveal a disproportionately large chunk instead of growing
    # gradually like every other stroke in this animation.
    reveal_st = make_stroker(Qt.PenCapStyle.RoundCap, 140)

    # setFillRule(WindingFill): without it, QPainterPath's default even-odd
    # rule treats the OVERLAP between these three separately-built pieces (at
    # the seams where they're meant to join continuously) as a cancelled-out
    # hole rather than solid fill - exactly the gaps seen at the dome/stem and
    # stem/descender joints. WindingFill treats any covered area as filled
    # regardless of how many of the sub-paths cover it.
    ya_full_shape = QPainterPath()
    ya_full_shape.setFillRule(Qt.FillRule.WindingFill)
    ya_full_shape.addPath(flat_st.createStroke(g["ya"]))
    ya_full_shape.addPath(g["ya_tip"])
    ya_full_shape.addPath(g["tail_white"])
    # The stem ends on an exactly vertical tangent (its last segment is a
    # straight lineTo), but the descender curve it hands off to doesn't start
    # perfectly vertical (its first control point leans a few degrees) - each
    # piece's flat-cap end is perpendicular to ITS OWN tangent, so the two
    # caps meet at a slight angle rather than flush, leaving a hairline seam
    # even with the fill rule fixed. A small patch circle at the exact joint,
    # sized to the stroke's own half-width, bridges it regardless of the angle.
    ya_full_shape.addEllipse(g["ya"].pointAtPercent(1.0), S / 2, S / 2)

    dots_full_shape = QPainterPath(g["tail_green"])

    plan = [
        {"kind": "reveal", "centerline": g["anim_ya"], "full_shape": ya_full_shape, "color": "white"},
        {"kind": "stroke", "path": g["dal"], "stroker": flat_st, "color": "white",
         "extras_start": [g["dal_tip"]]},
        {"kind": "stroke", "path": g["ta"], "stroker": round_st, "color": "white",
         "extras": [g["wedge"]]},
        {"kind": "stroke", "path": g["w1"], "stroker": round_st, "color": "white"},
        {"kind": "stroke", "path": g["w2"], "stroker": round_st, "color": "white"},
        {"kind": "dash", "shape": g["sh_dashes"][2]},
        {"kind": "dash", "shape": g["sh_dashes"][1]},
        {"kind": "dash", "shape": g["sh_dashes"][0]},
        {"kind": "stroke", "path": g["cross"], "stroker": round_st, "color": "white"},
        {"kind": "reveal", "centerline": g["anim_dots"], "full_shape": dots_full_shape, "color": "green"},
    ]

    def _step_path(step):
        """The path whose length drives duration - `shape` for a dash,
        `centerline` for a reveal, else `path`."""
        if step["kind"] == "dash":
            return step["shape"]
        return step["centerline"] if step["kind"] == "reveal" else step["path"]

    def _step_point(step, at_end):
        """Where the pen actually sits at a step's start/end - for a dash this
        MUST be its center (not some arbitrary point on the rounded-rect's own
        outline from pointAtPercent), because that's what the dash's own
        reveal uses as its pen position; using a different point here made
        the travel arrive/depart somewhere the dash animation itself never
        visits, showing up as a brief backward flick at the transition."""
        if step["kind"] == "dash":
            return step["shape"].boundingRect().center()
        p = step["centerline"] if step["kind"] == "reveal" else step["path"]
        return p.pointAtPercent(1.0 if at_end else 0.0)

    # Interleave travel segments wherever the pen has to visibly jump.
    timeline = []
    pen = None
    for step in plan:
        start = _step_point(step, at_end=False)
        if pen is not None:
            gap = ((start.x() - pen.x()) ** 2 + (start.y() - pen.y()) ** 2) ** 0.5
            if gap > 4:
                timeline.append({"kind": "travel", "start": pen, "end": start, "length": gap})
        length = 40.0 if step["kind"] == "dash" else path_length(_step_path(step))
        timeline.append({**step, "length": max(length, 1.0)})
        pen = _step_point(step, at_end=True)

    return timeline, reveal_st, ya_full_shape, dots_full_shape
