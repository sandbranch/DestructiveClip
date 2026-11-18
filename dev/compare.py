#!/usr/bin/env python3
"""Run Destructive Clip on every sample in every document kind and compare
the result with a real clip (Object > Clip > Set), rendered with Inkscape.

    python3 dev/compare.py [OUTDIR] [CASE ...]

Set SCRIPT=/path/to/destructiveclip.py to try another version. Files stay
in OUTDIR (default ./compare-out). Needs inkex on PYTHONPATH.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tests"))

import harness  # noqa: E402
import samples  # noqa: E402


def main():
    args = sys.argv[1:]
    out = args.pop(0) if args else "compare-out"
    cases = args or list(samples.CASES)
    os.makedirs(out, exist_ok=True)
    rows = []
    for case in cases:
        for kind in samples.KINDS:
            base, rc, err = harness.prepare(case, kind, out, os.environ.get("SCRIPT"))
            rows.append((case, kind, base, rc, " | ".join(err.strip().splitlines())))
    harness.render([b for _, _, b, rc, _ in rows if rc == 0])
    for case, kind, base, rc, err in rows:
        if rc:
            print(f"{case:22} {kind:7} CRASH {err[-160:]}")
            continue
        bad, ink = harness.compare(base)
        flag = "ok " if bad == 0 else "BAD"
        print(f"{case:22} {kind:7} {flag} differing={bad:7} ink={ink:7} {err[:140]}")


if __name__ == "__main__":
    main()
