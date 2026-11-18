#!/usr/bin/env python3
"""
---DESTRUCTIVE Clip---
An Inkscape Extension which works like Object|Clip|Set except that the paths
clipped are actually *modified*. Thus the clipping is included when
exported, for example as a DXF file.

Select two or more objects, then choose Extensions|Modify path|Destructive
clip. The topmost object is used to clip the others.

Mark Wilson Feb 2016

Edits by Windell H. Oskay, www.evilmadscientist.com, August 2020:
update calls to the Inkscape 1.0 extension API, handle some errors.

Rewritten for Inkscape 1.4 (sandbranch fork, branch inkscape-1.4):

* the topmost object (in stacking order) is the clip, whatever order the
  objects were selected in; it may be a path, rect, circle, ellipse,
  polygon, polyline or line, with curves and arcs
* subjects may have curves and arcs too: curves are split exactly where
  they cross the clip and stay curves; rects, circles and the like become
  paths; groups in the selection are clipped object by object
* transforms on the objects and on their groups are taken into account
* lines and outlines (no fill) are cut into the pieces inside the clip;
  filled shapes become the closed intersection with the clip, so their
  fill looks as it did under a real clip
* objects left with nothing inside the clip are deleted (an option keeps
  them as they were, the old behaviour)
"""

import math

import inkex
import numpy as np
from inkex.paths import Arc, Curve, Line, Move, Quadratic, ZoneClose

SHAPES = ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon")
GEOMETRY_ATTRS = set("x y width height rx ry cx cy r points x1 y1 x2 y2".split())


def fmt(value):
    text = f"{value:.10g}"
    return "0" if text == "-0" else text


# -- path <-> segments ----------------------------------------------------
#
# A segment is a tuple of complex points: (p0, p1) for a line, (p0, c1, c2,
# p3) for a cubic bezier. A subpath is (segments, closed).


def to_subpaths(path, transform, close_all=False):
    """Split an inkex Path into subpaths of line and cubic segments, with
    transform applied (affine maps keep beziers exact)."""
    t = transform

    def tp(z):
        x, y = t.apply_to_point((z.real, z.imag))
        return complex(x, y)

    subpaths = []
    segs = []
    first = prev = 0j
    closed = False

    def finish():
        nonlocal segs, closed
        if segs:
            if close_all and not closed and abs(segs[-1][-1] - segs[0][0]) > 0:
                segs.append((segs[-1][-1], segs[0][0]))
                closed = True
            subpaths.append((segs, closed))
        segs = []
        closed = False

    for seg in path.to_absolute().to_non_shorthand():
        if isinstance(seg, Move):
            finish()
            first = prev = complex(seg.x, seg.y)
            continue
        if isinstance(seg, ZoneClose):
            if prev != first:
                segs.append((tp(prev), tp(first)))
            prev = first
            closed = True
            finish()
            continue
        if isinstance(seg, Line):
            end = complex(seg.x, seg.y)
            segs.append((tp(prev), tp(end)))
            prev = end
        elif isinstance(seg, Curve):
            a = seg.args
            c1, c2, end = complex(a[0], a[1]), complex(a[2], a[3]), complex(a[4], a[5])
            segs.append((tp(prev), tp(c1), tp(c2), tp(end)))
            prev = end
        elif isinstance(seg, Quadratic):
            a = seg.args
            q, end = complex(a[0], a[1]), complex(a[2], a[3])
            c1 = prev + 2 / 3 * (q - prev)
            c2 = end + 2 / 3 * (q - end)
            segs.append((tp(prev), tp(c1), tp(c2), tp(end)))
            prev = end
        elif isinstance(seg, Arc):
            end = complex(seg.endpoint)
            curves = seg.to_curves(prev) if seg.rx and seg.ry else []
            if not curves:  # zero radius: a straight line, as SVG says
                segs.append((tp(prev), tp(end)))
            start = prev
            for cur in curves:
                a = cur.args
                c1, c2, e = complex(a[0], a[1]), complex(a[2], a[3]), complex(a[4], a[5])
                segs.append((tp(start), tp(c1), tp(c2), tp(e)))
                start = e
            prev = end
        else:  # pragma: no cover (to_non_shorthand leaves nothing else)
            raise ValueError(f"unsupported path command {seg.letter}")
    finish()
    # a lone moveto draws nothing
    return [sp for sp in subpaths if sp[0]]


def to_path_data(runs, transform):
    """Path data for runs [(segments, closed)], with transform applied."""
    t = transform

    def pt(z):
        x, y = t.apply_to_point((z.real, z.imag))
        return f"{fmt(x)},{fmt(y)}"

    out = []
    for segs, closed in runs:
        out.append("M " + pt(segs[0][0]))
        for s in segs:
            if len(s) == 2:
                out.append("L " + pt(s[1]))
            else:
                out.append("C " + " ".join(pt(z) for z in s[1:]))
        if closed:
            out.append("Z")
    return " ".join(out)


# -- bezier helpers --------------------------------------------------------


def point_at(seg, t):
    if len(seg) == 2:
        return seg[0] + (seg[1] - seg[0]) * t
    p0, c1, c2, p3 = seg
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * c1 + 3 * u * t * t * c2 + t * t * t * p3


def sub_segment(seg, t0, t1):
    """The part of seg between parameters t0 < t1."""
    if len(seg) == 2:
        return (point_at(seg, t0), point_at(seg, t1))
    # split at t1, then split the first half at t0 / t1
    left = _split(seg, t1)[0] if t1 < 1 else seg
    if t0 <= 0:
        return left
    return _split(left, t0 / t1)[1]


def _split(seg, t):
    p0, c1, c2, p3 = seg
    a = p0 + (c1 - p0) * t
    b = c1 + (c2 - c1) * t
    c = c2 + (p3 - c2) * t
    d = a + (b - a) * t
    e = b + (c - b) * t
    f = d + (e - d) * t
    return (p0, a, d, f), (f, e, c, p3)


def reverse(seg):
    return tuple(reversed(seg))


def seg_bbox(seg):
    xs = [z.real for z in seg]
    ys = [z.imag for z in seg]
    return min(xs), min(ys), max(xs), max(ys)


def flatten(subpaths, tol):
    """Polylines (lists of points) approximating the subpaths within tol."""
    polys = []
    for segs, _closed in subpaths:
        pts = [segs[0][0]]
        for s in segs:
            if len(s) == 2:
                pts.append(s[1])
            else:
                _flatten_cubic(s, tol, pts, 0)
        polys.append(pts)
    return polys


def _flatten_cubic(seg, tol, out, depth):
    p0, c1, c2, p3 = seg
    chord = p3 - p0
    length = abs(chord)
    if length > 0:
        d1 = abs((c1 - p0).real * chord.imag - (c1 - p0).imag * chord.real) / length
        d2 = abs((c2 - p0).real * chord.imag - (c2 - p0).imag * chord.real) / length
        flat = max(d1, d2)
    else:
        flat = max(abs(c1 - p0), abs(c2 - p0))
    if flat <= tol or depth > 16:
        out.append(p3)
        return
    a, b = _split(seg, 0.5)
    _flatten_cubic(a, tol, out, depth + 1)
    _flatten_cubic(b, tol, out, depth + 1)


def inside(p, polys, evenodd):
    """Is p inside the closed polylines, by winding number (nonzero) or
    crossing parity (evenodd)? Edges are half open in y, so a ray through
    a vertex counts once."""
    winding = 0
    x, y = p.real, p.imag
    for pts in polys:
        n = len(pts)
        for i in range(n):
            a = pts[i]
            b = pts[(i + 1) % n]
            if a.imag <= y < b.imag or b.imag <= y < a.imag:
                xi = a.real + (y - a.imag) * (b.real - a.real) / (b.imag - a.imag)
                if xi > x:
                    winding += 1 if b.imag > a.imag else -1
    if evenodd:
        return winding % 2 != 0
    return winding != 0


def distance_to_edges(p, edges):
    best = math.inf
    for a, b in edges:
        d = b - a
        dd = abs(d) ** 2
        t = 0.0 if dd == 0 else max(0.0, min(1.0, ((p - a) * d.conjugate()).real / dd))
        best = min(best, abs(p - (a + d * t)))
    return best


def polygon_area(polys):
    """Sum of the absolute areas of closed polylines (shoelace)."""
    total = 0.0
    for pts in polys:
        area = 0.0
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            area += a.real * b.imag - b.real * a.imag
        total += abs(area) / 2
    return total


def edges_of(polys):
    edges = []
    for pts in polys:
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            if a != b:
                edges.append((a, b))
    return edges


def intersections(seg, a, b):
    """[(t on seg, u on edge a-b, point)] where seg crosses the edge."""
    d = b - a
    dd = abs(d) ** 2
    if dd == 0:
        return []
    n = complex(-d.imag, d.real)  # normal of the edge

    def dot(z, w):
        return z.real * w.real + z.imag * w.imag

    if len(seg) == 2:
        p0, p1 = seg
        e = p1 - p0
        den = dot(e, n)
        if den == 0:
            return []  # parallel (or along the edge)
        t = dot(a - p0, n) / den
        ts = [t]
    else:
        p0, c1, c2, p3 = seg
        ca = -p0 + 3 * c1 - 3 * c2 + p3
        cb = 3 * p0 - 6 * c1 + 3 * c2
        cc = -3 * p0 + 3 * c1
        cd = p0 - a
        coeffs = [dot(ca, n), dot(cb, n), dot(cc, n), dot(cd, n)]
        scale = max(abs(c) for c in coeffs)
        if scale == 0:
            return []
        coeffs = [c / scale for c in coeffs]
        while coeffs and abs(coeffs[0]) < 1e-12:
            coeffs.pop(0)
        if len(coeffs) < 2:
            return []
        ts = [r.real for r in np.roots(coeffs) if abs(r.imag) < 1e-9]
    out = []
    eps = 1e-9
    for t in ts:
        if -eps <= t <= 1 + eps:
            t = min(max(t, 0.0), 1.0)
            p = point_at(seg, t)
            u = dot(p - a, d) / dd
            if -eps <= u <= 1 + eps:
                out.append((t, min(max(u, 0.0), 1.0), p))
    return out


# -- clipping --------------------------------------------------------------


class Clipper:
    """The clip region: the clipping shape's subpaths in document
    coordinates, flattened within tol for crossing and inside tests."""

    def __init__(self, subpaths, evenodd, tol):
        self.evenodd = evenodd
        self.tol = tol
        self.polys = flatten(subpaths, tol)
        self.edges = edges_of(self.polys)
        self.edge_boxes = [
            (min(a.real, b.real), min(a.imag, b.imag), max(a.real, b.real), max(a.imag, b.imag))
            for a, b in self.edges
        ]

    def contains(self, p):
        return inside(p, self.polys, self.evenodd)

    def crossings(self, subpaths):
        """For every subject segment, the crossings with clip edges:
        {(subpath index, segment index): [(t, edge index, u, point)]}."""
        found = {}
        tol = self.tol
        for i, (segs, _c) in enumerate(subpaths):
            for j, seg in enumerate(segs):
                x0, y0, x1, y1 = seg_bbox(seg)
                hits = []
                for k, (ex0, ey0, ex1, ey1) in enumerate(self.edge_boxes):
                    if ex1 < x0 - tol or ex0 > x1 + tol or ey1 < y0 - tol or ey0 > y1 + tol:
                        continue
                    a, b = self.edges[k]
                    for t, u, p in intersections(seg, a, b):
                        hits.append((t, k, u, p))
                if hits:
                    found[(i, j)] = hits
        return found


def split_subject(subpaths, crossings, tol):
    """Cut every subject segment where it crosses the clip. Returns, per
    subpath, the list of pieces in order. Crossings closer than tol along a
    segment are merged (a crossing through a clip vertex shows up on both
    edges)."""
    result = []
    for i, (segs, _closed) in enumerate(subpaths):
        pieces = []
        for j, seg in enumerate(segs):
            hits = sorted(crossings.get((i, j), []), key=lambda h: h[0])
            cuts = []  # (t, point)
            for t, _k, _u, p in hits:
                if cuts and abs(p - cuts[-1][1]) <= tol:
                    continue
                cuts.append((t, p))
            cuts = [c for c in cuts if abs(c[1] - seg[0]) > tol and abs(c[1] - seg[-1]) > tol]
            bounds = [(0.0, seg[0])] + cuts + [(1.0, seg[-1])]
            for (t0, q0), (t1, q1) in zip(bounds, bounds[1:]):
                piece = sub_segment(seg, t0, t1)
                # end exactly on the shared points, so pieces chain
                piece = (q0,) + tuple(piece[1:-1]) + (q1,)
                pieces.append((piece, point_at(seg, (t0 + t1) / 2)))
        result.append(pieces)
    return result


def clip_lines(subpaths, clipper):
    """Open-line clipping: the parts of the subject inside the clip.
    Returns (runs [(segments, closed)], changed)."""
    crossings = clipper.crossings(subpaths)
    split = split_subject(subpaths, crossings, clipper.tol)
    runs = []
    changed = bool(crossings)
    for (segs, closed), pieces in zip(subpaths, split):
        keep = [clipper.contains(mid) for _piece, mid in pieces]
        changed = changed or not all(keep)
        if all(keep):
            runs.append(([p for p, _m in pieces], closed))
            continue
        groups = []
        current = None
        for (piece, _mid), k in zip(pieces, keep):
            if k:
                if current is None:
                    current = []
                    groups.append(current)
                current.append(piece)
            else:
                current = None
        if closed and len(groups) > 1 and keep[0] and keep[-1]:
            # the run through the start point of a closed subpath is one
            groups[0] = groups.pop() + groups[0]
        runs.extend((g, False) for g in groups)
    return runs, changed


def clip_region(subpaths, clipper, subject_evenodd):
    """Filled-shape clipping: the closed intersection of the subject's fill
    with the clip, as loops [(segments, True)]. Returns (loops, complete)
    where complete is False if some boundary could not be closed."""
    tol = clipper.tol
    crossings = clipper.crossings(subpaths)
    split = split_subject(subpaths, crossings, tol)
    subject_polys = flatten(subpaths, tol)

    def in_both(p):
        return clipper.contains(p) and inside(p, subject_polys, subject_evenodd)

    # A piece is part of the outline of the intersection when the
    # intersection lies on exactly one side of it. Looking just off both
    # sides also settles pieces that run along the other shape's edge.
    eps = 10 * tol

    def on_outline(piece):
        m = point_at(piece, 0.5)
        tangent = point_at(piece, 0.501) - point_at(piece, 0.499)
        if abs(tangent) == 0:
            tangent = piece[-1] - piece[0]
        if abs(tangent) == 0:
            return False
        side = tangent / abs(tangent) * 1j * eps
        return in_both(m + side) != in_both(m - side)

    pieces = []
    for plist in split:
        for piece, _mid in plist:
            if on_outline(piece):
                pieces.append(piece)
    kept_edges = []
    for pts in flatten([([p], False) for p in pieces], tol):
        kept_edges.extend(zip(pts, pts[1:]))

    # clip edges, cut at the same crossing points, kept where inside the subject
    cuts_on_edge = {}
    for hits in crossings.values():
        for _t, k, u, p in hits:
            cuts_on_edge.setdefault(k, []).append((u, p))
    # crossings that were merged on the subject side must use that side's
    # point, so collect the points the subject pieces actually end on
    subject_points = [piece[0] for plist in split for piece, _m in plist]
    subject_points += [piece[-1] for plist in split for piece, _m in plist]

    def snap(p):
        best = min(subject_points, key=lambda q: abs(q - p), default=None)
        if best is not None and abs(best - p) <= tol:
            return best
        return p

    for k, (a, b) in enumerate(clipper.edges):
        cuts = sorted(cuts_on_edge.get(k, []), key=lambda c: c[0])
        points = [a] + [snap(p) for _u, p in cuts] + [b]
        for q0, q1 in zip(points, points[1:]):
            if abs(q1 - q0) <= tol * 1e-3:
                continue
            piece = (q0, q1)
            # where the clip edge runs along a kept subject piece, that
            # piece is already there
            if on_outline(piece) and distance_to_edges((q0 + q1) / 2, kept_edges) > 4 * tol:
                pieces.append(piece)

    return chain(pieces, tol)


def chain(pieces, tol):
    """Join pieces end to end into closed loops."""
    unused = list(pieces)
    loops = []
    complete = True
    while unused:
        loop = [unused.pop(0)]
        start = loop[0][0]
        while abs(loop[-1][-1] - start) > tol:
            end = loop[-1][-1]
            best = None
            for idx, p in enumerate(unused):
                if abs(p[0] - end) <= tol:
                    best = (idx, p)
                    break
                if abs(p[-1] - end) <= tol:
                    best = (idx, reverse(p))
                    break
            if best is None:
                complete = False
                break
            unused.pop(best[0])
            loop.append(best[1])
        loops.append((loop, abs(loop[-1][-1] - start) <= tol))
    return loops, complete


# -- the extension ----------------------------------------------------------


def local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else None


class DestructiveClip(inkex.EffectExtension):
    def add_arguments(self, pars):
        pars.add_argument("--keep_outside", type=inkex.Boolean, default=False)
        pars.add_argument("--delete_clip", type=inkex.Boolean, default=False)

    def effect(self):
        order = list(self.svg.selection.rendering_order().values())
        if len(order) < 2:
            raise inkex.AbortExtension(
                "Select the objects to clip and, on top of them, the clipping object."
            )
        clip = order[-1]
        if local(clip.tag) not in SHAPES:
            raise inkex.AbortExtension(
                f"The topmost selected object ({clip.get_id()}) is a {local(clip.tag)}; "
                "the clipping object must be a single shape or path "
                "(use Path > Combine or Object to Path first)."
            )
        clip_subpaths = to_subpaths(clip.path, clip.composed_transform(), close_all=True)
        if not clip_subpaths:
            raise inkex.AbortExtension("The clipping object is empty.")
        xs = [z.real for segs, _c in clip_subpaths for s in segs for z in s]
        ys = [z.imag for segs, _c in clip_subpaths for s in segs for z in s]
        diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
        evenodd = clip.specified_style().get("fill-rule") == "evenodd"
        clipper = Clipper(clip_subpaths, evenodd, diag * 1e-5)

        messages = []
        for node in order[:-1]:
            for subject in self.subjects(node, clip, messages):
                self.clip_one(subject, clipper, messages)
        if self.options.delete_clip:
            clip.getparent().remove(clip)
        for msg in messages:
            inkex.errormsg(msg)

    def subjects(self, node, clip, messages):
        name = local(node.tag)
        if node is clip or name is None:
            return
        if name in SHAPES:
            yield node
        elif name in ("g", "a", "switch"):
            for child in list(node):
                yield from self.subjects(child, clip, messages)
        elif name in ("text", "flowRoot"):
            messages.append(f"Text {node.get_id()} was not clipped (convert it to a path first).")
        elif name in ("defs", "metadata", "namedview", "title", "desc"):
            return
        else:
            messages.append(f"{node.get_id()} ({name}) was not clipped.")

    def clip_one(self, node, clipper, messages):
        to_doc = node.composed_transform()
        style = node.specified_style()
        filled = style.get("fill", "black") not in ("none", None) and str(
            style.get("fill-opacity", "1")
        ).strip() not in ("0", "0.0")
        subpaths = to_subpaths(node.path, to_doc, close_all=filled)
        if not subpaths:
            return
        if filled and polygon_area(flatten(subpaths, clipper.tol)) <= clipper.tol**2:
            # a fill with no area (a filled straight line) draws nothing:
            # clip it as a line
            filled = False
            subpaths = to_subpaths(node.path, to_doc)
        if filled:
            loops, complete = clip_region(subpaths, clipper, style.get("fill-rule") == "evenodd")
            if not complete:
                messages.append(
                    f"{node.get_id()}: the outline could not be closed everywhere "
                    "(edges along the clip edge?); check the result."
                )
            runs = loops
            changed = True
        else:
            runs, changed = clip_lines(subpaths, clipper)

        if not runs:
            if self.options.keep_outside:
                messages.append(f"{node.get_id()} is outside the clip and was left as it was.")
            else:
                node.getparent().remove(node)
            return
        if not changed:
            return  # entirely inside: leave it exactly as it was
        d = to_path_data(runs, -to_doc)
        if local(node.tag) != "path":
            new = inkex.PathElement()
            for key, value in node.attrib.items():
                if local(key) not in GEOMETRY_ATTRS:
                    new.set(key, value)
            node.getparent().replace(node, new)
            node = new
        for key in list(node.attrib):
            # Inkscape regenerates arcs, stars and path effects from these
            if key.startswith("{" + inkex.NSS["sodipodi"] + "}") or local(key) in (
                "original-d",
                "path-effect",
            ):
                del node.attrib[key]
        node.set("d", d)
        if filled:
            node.style["fill-rule"] = "evenodd"


if __name__ == "__main__":
    DestructiveClip().run()
