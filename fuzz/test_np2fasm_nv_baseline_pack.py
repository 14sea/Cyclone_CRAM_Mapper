# SPDX-License-Identifier: GPL-3.0-or-later
"""Test np2fasm baseline= plumbing for NV_BASELINE_PACK emission.

Phase 5 of the nv_zero_global retirement — verify the emitter prepends
the meta directive when the caller opts into the PURE_ZERO base path.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "synth"))
sys.path.insert(0, str(ROOT / "fuzz"))

from np2fasm import convert  # type: ignore


def _empty_design():
    return {"modules": {"top": {"cells": {}, "netnames": {}}}}


def test_baseline_nv_default_no_header():
    fasm, _warns = convert(_empty_design())
    assert "NV_BASELINE_PACK" not in fasm, (
        "default baseline=nv should NOT emit NV_BASELINE_PACK")
    print("  test_baseline_nv_default_no_header: OK")


def test_baseline_pure_emits_header_first():
    fasm, _warns = convert(_empty_design(), baseline="pure")
    assert fasm, "pure baseline should emit at least NV_BASELINE_PACK"
    assert fasm[0] == "NV_BASELINE_PACK", (
        f"NV_BASELINE_PACK must be first line; got {fasm[0]!r}")
    print("  test_baseline_pure_emits_header_first: OK")


def test_baseline_pure_header_parses_and_applies():
    """End-to-end: convert(..., baseline='pure') output feeds fasm2rbf
    with PURE_ZERO and reproduces nv_zero_global.rbf.

    Uses an empty design — the NV_BASELINE_PACK header alone is the
    entire payload, so the byte-exact equivalence to nv_zero_global is
    just the Phase 4 gate re-run through the full emission path.
    """
    import fasm2rbf  # type: ignore
    from pure_zero_rbf import make_pure_zero_rbf  # type: ignore

    nv_path = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
    if not nv_path.exists():
        print("  test_baseline_pure_header_parses_and_applies: SKIP "
              "(nv_zero_global.rbf not present)")
        return

    fasm2rbf._NV_BASELINE_CACHE = None
    fasm, _warns = convert(_empty_design(), baseline="pure")
    fasm_text = "\n".join(fasm) + "\n"
    pz = make_pure_zero_rbf()
    out = fasm2rbf.bitgen(fasm_text, pz)
    gold = nv_path.read_bytes()
    assert out == gold, (
        f"emitted NV_BASELINE_PACK + PURE_ZERO != nv_zero_global; "
        f"{sum(1 for i in range(len(out)) if out[i] != gold[i])} byte diffs")
    print("  test_baseline_pure_header_parses_and_applies: OK "
          f"(emitter output reproduces nv_zero_global byte-for-byte)")


def test_convert_rejects_bad_baseline():
    try:
        convert(_empty_design(), baseline="bogus")
    except ValueError as e:
        assert "bogus" in str(e), e
        print("  test_convert_rejects_bad_baseline: OK")
        return
    raise AssertionError("expected ValueError for bogus baseline")


def _main():
    import traceback
    passed = failed = 0
    for name, fn in sorted(globals().items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        try:
            fn()
        except Exception:
            traceback.print_exc()
            print(f"FAIL {name}")
            failed += 1
        else:
            passed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    _main()
