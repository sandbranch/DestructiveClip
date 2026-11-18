"""The key check: the destructively clipped drawing must look like the same
drawing under a real clip (Object > Clip > Set), rendered with Inkscape and
compared pixel by pixel. Skipped without Inkscape."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness
import pixeldiff
import samples

pytestmark = pytest.mark.skipif(not pixeldiff.have_inkscape(), reason="needs Inkscape")

MATRIX = [(c, k) for c in samples.CASES for k in samples.KINDS]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    out = str(tmp_path_factory.mktemp("render"))
    results = {}
    for case, kind in MATRIX:
        results[(case, kind)] = harness.prepare(case, kind, out)
    harness.render([b for b, rc, _ in results.values() if rc == 0])
    return results


@pytest.mark.parametrize("case,kind", MATRIX)
def test_looks_like_a_real_clip(prepared, case, kind):
    base, rc, err = prepared[(case, kind)]
    assert rc == 0, err
    bad, ink = harness.compare(base)
    assert ink > 500, "nothing drawn"
    assert bad == 0, f"{bad} pixels differ from the clipped original"
