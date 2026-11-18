"""Build the before / after / reference files for one sample and compare
them. Shared by tests/test_render.py and dev/compare.py.

The comparison: the destructively clipped drawing (with the clipping object
removed) against the same drawing clipped with a real clip path (what
Object > Clip > Set shows). A butt stroke end that was cut on the clip edge
is square to the line, while a clip path cuts the stroke along the edge, so
pixels within a band around the clip edge are not compared. The band is
made by drawing the clip outline with a wide stroke.
"""

import io
import os
import subprocess
import sys

import inkex
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import pixeldiff  # noqa: E402
import samples  # noqa: E402

BAND_MM = 3.0


def run_extension(svg_path, ids, extra=(), script=None):
    """Run the extension on svg_path with ids selected; return (rc, stdout,
    stderr)."""
    script = script or os.path.join(REPO, "destructiveclip.py")
    args = [sys.executable, script, *[f"--id={i}" for i in ids], *extra, svg_path]
    env = dict(os.environ)
    res = subprocess.run(args, capture_output=True, env=env, check=False)
    return res.returncode, res.stdout, res.stderr.decode(errors="replace")


def load(path_or_bytes):
    if isinstance(path_or_bytes, bytes):
        return inkex.load_svg(io.BytesIO(path_or_bytes)).getroot()
    return inkex.load_svg(path_or_bytes).getroot()


def write(root, path):
    with open(path, "wb") as f:
        f.write(root.tostring())


def prepare(case, kind, out, script=None):
    """Write <out>/<case>-<kind>-{before,after,ref,band}.svg. Returns
    (base path, return code, stderr)."""
    base = os.path.join(out, f"{case}-{kind}")
    with open(base + "-before.svg", "w") as f:
        f.write(samples.make(case, kind))
    ids = samples.subject_ids(case) + ["clip"]
    if os.environ.get("CLIP_FIRST"):
        # upstream takes the first id as the clipping path
        ids = ids[-1:] + ids[:-1]
    rc, stdout, err = run_extension(base + "-before.svg", ids, script=script)
    if rc != 0 or not stdout:
        return base, rc or 1, err
    after = load(stdout)
    write(after, base + "-result.svg")
    clip = after.getElementById("clip")
    if clip is not None:
        clip.getparent().remove(clip)
    write(after, base + "-after.svg")
    write(samples.reference(load(base + "-before.svg")), base + "-ref.svg")
    band = load(base + "-before.svg")
    for sid in samples.subject_ids_in(band):
        e = band.getElementById(sid)
        e.getparent().remove(e)
    k = samples.KINDS[kind][1]
    band.getElementById("clip").style = inkex.Style(
        f"fill:none;stroke:#000000;stroke-width:{BAND_MM * k}"
    )
    write(band, base + "-band.svg")
    return base, 0, err


def render(bases):
    files = []
    for b in bases:
        files += [b + "-after.svg", b + "-ref.svg", b + "-band.svg"]
    pixeldiff.render(files)


def compare(base, threshold=40):
    """Return (differing pixels outside the band, inked pixels in ref).
    A curve cut into pieces is anti-aliased a little differently from the
    whole curve (up to about 30 levels out of 255 on single pixels), hence
    the threshold; a missing or extra line differs by 200 or more."""
    a = pixeldiff.load(base + "-after.png")
    r = pixeldiff.load(base + "-ref.png")
    band = pixeldiff.load(base + "-band.png").min(axis=2) < 250
    d = np.abs(a - r).max(axis=2) > threshold
    ink = int((r.min(axis=2) < 250).sum())
    return int((d & ~band).sum()), ink
