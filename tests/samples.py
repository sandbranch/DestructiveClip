"""Sample drawings for Destructive Clip, in three kinds of document.

Each case has a clipping object with id "clip" on top and subjects with ids
starting with "s". The same drawing is made in a mm document (A4, viewBox in
mm), a px document (no viewBox) and a scaled document (2 mm per user unit).
Coordinates are written for a 210 x 297 user-unit page and multiplied by K,
the user units per mm of paper.

reference() builds what Object > Clip > Set would show: every subject clipped
by a copy of the clipping shape, and the clipping object itself removed.
"""

import re

KINDS = {
    "mm": ('width="210mm" height="297mm" viewBox="0 0 210 297"', 1.0),
    "px": ('width="793.70081" height="1122.5197"', 96 / 25.4),
    "scaled": ('width="210mm" height="297mm" viewBox="0 0 105 148.5"', 0.5),
}

NS = (
    'xmlns="http://www.w3.org/2000/svg" '
    'xmlns:xlink="http://www.w3.org/1999/xlink" '
    'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
    'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd"'
)

LINE = "fill:none;stroke:#000000;stroke-width:{n1};stroke-linecap:butt"
CLIP_STYLE = "fill:#ffcc00;fill-opacity:0.3;stroke:#ff0000;stroke-width:{n0.3}"

# The rectangle as Inkscape 1.x writes it after Object to Path: H and V.
RECT_PATH = "M {n50},{n50} H {n150} V {n130} H {n50} Z"
CIRCLE_PATH = (
    "M {n150},{n100} A {n50},{n50} 0 0 1 {n100},{n150} A {n50},{n50} 0 0 1 {n50},{n100} "
    "A {n50},{n50} 0 0 1 {n100},{n50} A {n50},{n50} 0 0 1 {n150},{n100} Z"
)

CASES = {
    "lines_rect": f"""
<path id="s1" d="M {{n20}},{{n70}} L {{n180}},{{n90}}" style="{LINE}"/>
<path id="s2" d="M {{n70}},{{n20}} L {{n90}},{{n170}} L {{n130}},{{n30}}" style="{LINE}"/>
<path id="s3" d="M {{n30}},{{n160}} L {{n170}},{{n40}}" style="{LINE}"/>
<path id="clip" d="{RECT_PATH}" style="{CLIP_STYLE}"/>""",
    "lines_rect_element": f"""
<path id="s1" d="M {{n20}},{{n70}} L {{n180}},{{n90}}" style="{LINE}"/>
<path id="s3" d="M {{n30}},{{n160}} L {{n170}},{{n40}}" style="{LINE}"/>
<rect id="clip" x="{{n50}}" y="{{n50}}" width="{{n100}}" height="{{n80}}" style="{CLIP_STYLE}"/>""",
    "lines_circle": f"""
<path id="s1" d="M {{n20}},{{n80}} L {{n180}},{{n120}}" style="{LINE}"/>
<path id="s2" d="M {{n60}},{{n20}} L {{n140}},{{n180}}" style="{LINE}"/>
<path id="s3" d="M {{n20}},{{n100}} C {{n60}},{{n20}} {{n140}},{{n180}} {{n180}},{{n100}}" style="{LINE}"/>
<path id="clip" d="{CIRCLE_PATH}" style="{CLIP_STYLE}"/>""",
    "lines_circle_element": f"""
<path id="s1" d="M {{n20}},{{n80}} L {{n180}},{{n120}}" style="{LINE}"/>
<path id="s2" d="M {{n20}},{{n100}} C {{n60}},{{n20}} {{n140}},{{n180}} {{n180}},{{n100}}" style="{LINE}"/>
<circle id="clip" cx="{{n100}}" cy="{{n100}}" r="{{n50}}" style="{CLIP_STYLE}"/>""",
    "curves": f"""
<path id="s1" d="M {{n20}},{{n90}} C {{n50}},{{n10}} {{n80}},{{n170}} {{n110}},{{n90}} S {{n170}},{{n10}} {{n190}},{{n90}}" style="{LINE}"/>
<path id="s2" d="M {{n30}},{{n140}} Q {{n100}},{{n20}} {{n170}},{{n140}}" style="{LINE}"/>
<path id="s3" d="M {{n40}},{{n110}} A {{n70}},{{n40}} 0 0 1 {{n160}},{{n110}}" style="{LINE}"/>
<path id="clip" d="{RECT_PATH}" style="{CLIP_STYLE}"/>""",
    "closed_outline": f"""
<path id="s1" d="M {{n30}},{{n60}} L {{n120}},{{n40}} L {{n110}},{{n120}} Z" style="{LINE}"/>
<path id="s2" d="M {{n90}},{{n90}} h {{n90}} v {{n60}} h {{n-90}} z" style="{LINE}"/>
<path id="clip" d="{CIRCLE_PATH}" style="{CLIP_STYLE}"/>""",
    "closed_filled": f"""
<path id="s1" d="M {{n30}},{{n60}} L {{n120}},{{n30}} L {{n110}},{{n120}} Z" style="fill:#4a90d9;stroke:none"/>
<path id="s2" d="M {{n90}},{{n90}} h {{n90}} v {{n60}} h {{n-90}} z M {{n110}},{{n100}} v {{n20}} h {{n20}} v {{n-20}} z"
      style="fill:#e0a020;fill-rule:evenodd;stroke:none"/>
<ellipse id="s3" cx="{{n60}}" cy="{{n140}}" rx="{{n30}}" ry="{{n15}}" style="fill:#40a040;stroke:none"/>
<path id="clip" d="{CIRCLE_PATH}" style="fill:none;stroke:#ff0000;stroke-width:{{n0.3}}"/>""",
    "transformed": f"""
<g transform="translate({{n20}},{{n10}}) rotate(15) scale(1.2)">
  <path id="s1" d="M {{n10}},{{n70}} L {{n160}},{{n80}}" style="{LINE}"/>
  <path id="s2" d="M {{n60}},{{n10}} C {{n80}},{{n80}} {{n100}},{{n80}} {{n120}},{{n150}}" style="{LINE}"/>
</g>
<g transform="matrix(1.1,0.2,-0.1,0.9,{{n5}},{{n-5}})">
  <path id="clip" d="{CIRCLE_PATH}" style="{CLIP_STYLE}"/>
</g>""",
    "inside_outside": f"""
<path id="s1" d="M {{n70}},{{n90}} L {{n130}},{{n100}}" style="{LINE}"/>
<path id="s2" d="M {{n10}},{{n200}} L {{n190}},{{n210}}" style="{LINE}"/>
<path id="s3" d="M {{n20}},{{n70}} L {{n180}},{{n90}}" style="{LINE}"/>
<path id="clip" d="{RECT_PATH}" style="{CLIP_STYLE}"/>""",
    # horizontal hatch lines that pass exactly through the clip's corners
    "hatch_vertices": f"""
<path id="s1" d="M {{n10}},{{n100}} L {{n190}},{{n100}}" style="{LINE}"/>
<path id="s2" d="M {{n10}},{{n60}} L {{n190}},{{n60}}" style="{LINE}"/>
<path id="s3" d="M {{n10}},{{n140}} L {{n190}},{{n140}}" style="{LINE}"/>
<path id="s4" d="M {{n100}},{{n10}} L {{n100}},{{n190}}" style="{LINE}"/>
<path id="clip" d="M {{n100}},{{n40}} L {{n160}},{{n100}} L {{n100}},{{n160}} L {{n40}},{{n100}} Z"
      style="{CLIP_STYLE}"/>""",
    "negative_coords": f"""
<g transform="translate({{n200}},{{n200}})">
  <path id="s1" d="M {{n-180}},{{n-130}} L {{n-20}},{{n-110}}" style="{LINE}"/>
  <path id="clip" d="M {{n-150}},{{n-150}} H {{n-50}} V {{n-70}} H {{n-150}} Z" style="{CLIP_STYLE}"/>
</g>""",
}


def make(case, kind):
    header, k = KINDS[kind]
    body = re.sub(r"\{n(-?[\d.]+)\}", lambda m: f"{float(m.group(1)) * k:.10g}", CASES[case])
    return (
        f'<svg {NS} {header} version="1.1">\n'
        f'<g id="layer1" inkscape:groupmode="layer">{body}\n</g>\n</svg>\n'
    )


def subject_ids(case):
    return re.findall(r'id="(s\d+)"', CASES[case])


def reference(svg_root):
    """Turn a loaded 'before' document into what Object > Clip > Set shows:
    each subject clipped by the clip shape, the clip object removed."""
    import inkex

    clip = svg_root.getElementById("clip")
    clip_ct = clip.composed_transform()
    defs = svg_root.defs
    for sid in subject_ids_in(svg_root):
        subj = svg_root.getElementById(sid)
        cp = inkex.ClipPath()
        cp.set("id", "cp_" + sid)
        cp.set("clipPathUnits", "userSpaceOnUse")
        shape = clip.copy()
        shape.set("id", "cs_" + sid)
        shape.transform = -subj.composed_transform() @ clip_ct
        # clip with the same rule the clip shape is filled with
        shape.style["clip-rule"] = clip.specified_style().get("fill-rule", "nonzero")
        cp.append(shape)
        defs.append(cp)
        subj.set("clip-path", f"url(#cp_{sid})")
    clip.getparent().remove(clip)
    return svg_root


def subject_ids_in(svg_root):
    return [
        e.get("id")
        for e in svg_root.iter()
        if isinstance(e.tag, str) and re.fullmatch(r"s\d+", e.get("id") or "")
    ]
