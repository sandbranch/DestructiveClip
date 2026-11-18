"""Geometry checks that need no Inkscape, in mm, px and scaled documents.

Everything that is left must be inside the clip, everything of the original
that was inside the clip must still be there, filled shapes must have the
area of their intersection with the clip, and the result must not depend on
the order the objects were selected in. Most of these fail on the upstream
code (funnypolynomial/DestructiveClip 984c495).
"""

import io
import os
import sys

import inkex
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import samples

from destructiveclip import DestructiveClip, flatten, to_subpaths

KINDS = list(samples.KINDS)
LINE_CASES = [
    "lines_rect",
    "lines_rect_element",
    "lines_circle",
    "lines_circle_element",
    "curves",
    "closed_outline",
    "transformed",
    "inside_outside",
    "hatch_vertices",
    "negative_coords",
]


def run(text, tmp_path, ids, *extra):
    src = tmp_path / "in.svg"
    src.write_text(text)
    out = io.BytesIO()
    DestructiveClip().run([*[f"--id={i}" for i in ids], *extra, str(src)], output=out)
    data = out.getvalue()
    return inkex.load_svg(io.BytesIO(data)).getroot() if data else None


def load(text):
    return inkex.load_svg(io.BytesIO(text.encode())).getroot()


def points(elem, tol, close=False):
    """Points along an element's outline in document coordinates."""
    subpaths = to_subpaths(elem.path, elem.composed_transform(), close_all=close)
    return [p for poly in flatten(subpaths, tol) for p in poly]


def clip_geometry(root):
    shapely = pytest.importorskip("shapely")
    from shapely.geometry import Polygon

    clip = root.getElementById("clip")
    subpaths = to_subpaths(clip.path, clip.composed_transform(), close_all=True)
    polys = flatten(subpaths, 1e-4)
    shape = Polygon([(p.real, p.imag) for p in polys[0]])
    return shapely, shape


def ids_for(case):
    return samples.subject_ids(case) + ["clip"]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("case", LINE_CASES)
def test_nothing_left_outside(case, kind, tmp_path):
    k = samples.KINDS[kind][1]
    after = run(samples.make(case, kind), tmp_path, ids_for(case))
    shapely, clip = clip_geometry(after)
    from shapely.geometry import Point

    grown = clip.buffer(0.01 * k)
    for sid in samples.subject_ids(case):
        elem = after.getElementById(sid)
        if elem is None:
            continue
        for p in points(elem, 0.001 * k):
            assert grown.contains(Point(p.real, p.imag)), f"{sid} has {p} outside the clip"


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("case", LINE_CASES)
def test_everything_inside_kept(case, kind, tmp_path):
    k = samples.KINDS[kind][1]
    text = samples.make(case, kind)
    before = load(text)
    after = run(text, tmp_path, ids_for(case))
    shapely, clip = clip_geometry(before)
    from shapely.geometry import LineString, Point

    inner = clip.buffer(-0.05 * k)
    for sid in samples.subject_ids(case):
        pts = [p for p in points(before.getElementById(sid), 0.001 * k)]
        wanted = [p for p in pts if inner.contains(Point(p.real, p.imag))]
        if not wanted:
            continue
        elem = after.getElementById(sid)
        assert elem is not None, f"{sid} was deleted"
        res = points(elem, 0.0005 * k)
        line = LineString([(p.real, p.imag) for p in res]) if len(res) > 1 else None
        for p in wanted:
            assert line is not None and line.distance(Point(p.real, p.imag)) < 0.01 * k, (
                f"{sid}: {p} was inside the clip but is gone"
            )


@pytest.mark.parametrize("kind", KINDS)
def test_filled_shapes_become_the_intersection(kind, tmp_path):
    k = samples.KINDS[kind][1]
    text = samples.make("closed_filled", kind)
    before = load(text)
    after = run(text, tmp_path, ids_for("closed_filled"))
    shapely, clip = clip_geometry(before)
    from shapely.geometry import Polygon

    def region(elem):
        subpaths = to_subpaths(elem.path, elem.composed_transform(), close_all=True)
        polys = [
            Polygon([(p.real, p.imag) for p in poly]).buffer(0)
            for poly in flatten(subpaths, 1e-4 * k)
        ]
        shape = polys[0]
        for poly in polys[1:]:  # even-odd: holes cancel
            shape = shape.symmetric_difference(poly)
        return shape

    for sid in samples.subject_ids("closed_filled"):
        want = region(before.getElementById(sid)).intersection(clip)
        got = region(after.getElementById(sid))
        assert got.area == pytest.approx(want.area, rel=1e-3), sid
        assert got.symmetric_difference(want).area < 1e-3 * want.area, sid


@pytest.mark.parametrize("case", ["lines_rect", "curves", "closed_filled", "transformed"])
def test_selection_order_does_not_matter(case, tmp_path):
    """The topmost object clips, whichever order the ids arrive in (upstream
    took the first id, so selecting the clip last clipped with a subject)."""
    text = samples.make(case, "mm")
    ids = ids_for(case)
    a = run(text, tmp_path, ids)
    b = run(text, tmp_path, list(reversed(ids)))
    for sid in samples.subject_ids(case):
        ea, eb = a.getElementById(sid), b.getElementById(sid)
        assert (ea is None) == (eb is None)
        if ea is not None:
            assert ea.get("d") == eb.get("d")
    assert a.getElementById("clip").get("d") == load(text).getElementById("clip").get("d")


def test_curves_stay_curves(tmp_path):
    after = run(samples.make("curves", "mm"), tmp_path, ids_for("curves"))
    for sid in ("s1", "s2", "s3"):
        d = after.getElementById(sid).get("d")
        assert "C" in d and "L" not in d, (sid, d)


def test_outside_objects_are_deleted_or_kept(tmp_path):
    text = samples.make("inside_outside", "mm")
    after = run(text, tmp_path, ids_for("inside_outside"))
    assert after.getElementById("s2") is None
    # entirely inside: untouched
    assert after.getElementById("s1").get("d") == load(text).getElementById("s1").get("d")
    kept = run(text, tmp_path, ids_for("inside_outside"), "--keep_outside=true")
    assert kept.getElementById("s2").get("d") == load(text).getElementById("s2").get("d")


def test_delete_clip_option(tmp_path):
    after = run(samples.make("lines_rect", "mm"), tmp_path, ids_for("lines_rect"))
    assert after.getElementById("clip") is not None
    after = run(
        samples.make("lines_rect", "mm"), tmp_path, ids_for("lines_rect"), "--delete_clip=true"
    )
    assert after.getElementById("clip") is None


def test_shapes_become_paths(tmp_path):
    after = run(samples.make("closed_filled", "mm"), tmp_path, ids_for("closed_filled"))
    s3 = after.getElementById("s3")
    assert s3.TAG == "path"
    assert s3.get("rx") is None and s3.style["fill"] == "#40a040"


DEGENERATE = """<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm"
 viewBox="0 0 210 297">
<path id="s1" d="M 50,50 H 150 V 130 H 50 Z" style="fill:#4a90d9"/>
<path id="s2" d="M 50,100 H 100 V 160 H 50 Z" style="fill:#e0a020"/>
<path id="s3" d="M 20,90 H 180" style="fill:#00a000;stroke:#000;stroke-width:1"/>
<path id="clip" d="M 50,50 H 150 V 130 H 50 Z" style="fill:none;stroke:red"/>
</svg>"""


def test_edges_along_the_clip_edge(tmp_path):
    after = run(DEGENERATE, tmp_path, ["s1", "s2", "s3", "clip"])
    # same as the clip: one closed square
    assert after.getElementById("s1").get("d") == "M 50,50 L 150,50 L 150,130 L 50,130 L 50,50 Z"
    # shares its left edge with the clip
    assert after.getElementById("s2").get("d") == (
        "M 50,100 L 100,100 L 100,130 L 50,130 L 50,100 Z"
    )
    # a filled straight line has no fill area: cut as a line
    assert after.getElementById("s3").get("d") == "M 50,90 L 150,90"


def test_clip_must_be_a_shape(tmp_path):
    text = (
        samples.make("lines_rect", "mm")
        .replace('<path id="clip"', '<g id="clipgroup"><path id="clip"')
        .replace("</g>\n</svg>", "</g></g>\n</svg>")
    )
    with pytest.raises(SystemExit):
        run(text, tmp_path, ["s1", "clipgroup"])


def test_inx_file():
    """The .inx loads in Inkscape 1.x (no _name, no inkex.py dependency) and
    declares exactly the options the script takes."""
    from lxml import etree

    path = os.path.join(os.path.dirname(HERE), "destructiveclip.inx")
    text = open(path).read()
    assert "_name" not in text and "inkex.py" not in text
    root = etree.parse(path).getroot()
    ns = {"i": "http://www.inkscape.org/namespace/inkscape/extension"}
    params = {p.get("name") for p in root.iterfind(".//i:param", ns)}
    parser = DestructiveClip().arg_parser
    options = {a.dest for a in parser._actions if a.dest not in ("help",)}
    assert params <= options
    assert root.find(".//i:command", ns).text == "destructiveclip.py"
