"""Render SVG files with Inkscape and compare them pixel by pixel.

Used by the tests (skipped when Inkscape is missing) and by dev/compare.py.
Inkscape runs inside dbus-run-session when that exists, because several
Inkscape instances sharing one session bus render nothing.
"""

import os
import shutil
import subprocess

import numpy as np

INKSCAPE = os.environ.get("INKSCAPE_COMMAND", "inkscape")


def have_inkscape():
    return shutil.which(INKSCAPE) is not None


def render(svg_paths, dpi=96):
    """Export each SVG to a PNG next to it (page area, white background)."""
    cmd = [
        INKSCAPE,
        "--export-type=png",
        "--export-area-page",
        f"--export-dpi={dpi}",
        "--export-background=#ffffff",
        "--export-background-opacity=1",
        "--export-overwrite",
        *svg_paths,
    ]
    if shutil.which("dbus-run-session"):
        cmd = ["dbus-run-session", "--", *cmd]
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    return [os.path.splitext(p)[0] + ".png" for p in svg_paths]


def load(png):
    from PIL import Image

    return np.asarray(Image.open(png).convert("RGB")).astype(np.int16)


def diff(png_a, png_b, threshold=24):
    """Return (pixels differing by more than threshold, max difference,
    pixels that are not background in a). Anti-aliasing along edges moves a
    little when coordinates are rewritten (up to about 23 levels out of 255
    here), so small differences are normal. A blur drawn 1.5 times too
    narrow differs by 33."""
    a, b = load(png_a), load(png_b)
    if a.shape != b.shape:
        return (a.size, 255, 0)
    d = np.abs(a - b).max(axis=2)
    ink = int((a.min(axis=2) < 250).sum())
    return int((d > threshold).sum()), int(d.max()), ink
