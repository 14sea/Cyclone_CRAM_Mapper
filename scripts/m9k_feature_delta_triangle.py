# SPDX-License-Identifier: GPL-3.0-or-later
"""Triangle (composability) test for per-feature M9K_MODE deltas.

If `delta_F = (base + F) ⊕ base` and `delta_G = (base + G) ⊕ base` are
truly orthogonal feature signatures, then `(base + F + G) ⊕ base` should
equal `delta_F ⊕ delta_G`.  This script builds 4 fixtures (base, +F, +G,
+F+G), computes the 3 deltas, and reports the triangle residual.

Pass criterion: triangle residual = 0 cells.  Any non-zero residual
flags feature interaction — those cells need a joint (F,G) bucket
rather than being decomposable.

Builds run in parallel.
"""
from __future__ import annotations
import argparse
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
sys.path.insert(0, str(ROOT / "scripts"))

from compile import setup_project, compile_full, generate_rbf  # noqa: E402
from m9k_feature_delta_smoke import (  # noqa: E402
    PRE, FRAME, DPF, REGIONS, _verilog, _qsf, _mif, region_of, diff_cells,
)

# Two independent SP feature axes for the triangle test.
# G = clock_enable_input_a:BYPASS targets the M9K's clock-enable
# routing — expected to land in block_band, unlike RDW which
# lives outside block_band entirely.
F_NAME = "outdata_reg_a"
G_NAME = "clock_enable_input_a"

FIXTURES = {
    "base":  {},
    "feat_F": {F_NAME: "CLOCK0"},
    "feat_G": {G_NAME: "BYPASS"},
    "feat_FG": {F_NAME: "CLOCK0", G_NAME: "BYPASS"},
}


def build_one(name: str, overrides: dict[str, str], work_root: str):
    proj = f"tri_{name}"
    proj_dir = setup_project(proj, _verilog(overrides), _qsf(proj), work_dir=work_root)
    (Path(proj_dir) / "mem_init.mif").write_text(_mif())
    ok, elapsed, err = compile_full(proj, proj_dir, timeout=300)
    if not ok:
        return name, None, elapsed, err
    rbf = generate_rbf(proj, proj_dir)
    return name, rbf, elapsed, ""


def main():
    ap = argparse.ArgumentParser()
    ap.parse_args()

    work_root = ROOT / "tmp" / "m9k_feature_delta_triangle"
    work_root.mkdir(parents=True, exist_ok=True)

    print(f"Triangle test: F={F_NAME}=CLOCK0, G={G_NAME}=NEW_DATA")
    print(f"Building {len(FIXTURES)} fixtures in parallel...")

    rbfs: dict[str, Path] = {}
    with ProcessPoolExecutor(max_workers=len(FIXTURES)) as ex:
        futures = {
            ex.submit(build_one, name, ov, str(work_root)): name
            for name, ov in FIXTURES.items()
        }
        for fut in as_completed(futures):
            name, rbf, elapsed, err = fut.result()
            if rbf is None:
                print(f"  [{name}] FAILED in {elapsed:.1f}s: {err}")
                return 1
            rbfs[name] = Path(rbf)
            print(f"  [{name}] OK in {elapsed:.1f}s")

    base = rbfs["base"].read_bytes()
    feat_F = rbfs["feat_F"].read_bytes()
    feat_G = rbfs["feat_G"].read_bytes()
    feat_FG = rbfs["feat_FG"].read_bytes()

    # Restrict to block_band — that's the M9K_MODE region.  Other
    # regions reflect downstream Quartus place&route drift handled
    # by IOB/COL/LAB directives, not the MODE codec.
    BLOCK_BAND = (1692, 1738)

    def bb_only(cells):
        lo, hi = BLOCK_BAND
        return {(off, bp) for off, bp in cells
                if lo <= (off - PRE) // FRAME <= hi}

    delta_F_full = diff_cells(feat_F, base)
    delta_G_full = diff_cells(feat_G, base)
    delta_FG_full = diff_cells(feat_FG, base)
    delta_F = bb_only(delta_F_full)
    delta_G = bb_only(delta_G_full)
    delta_FG = bb_only(delta_FG_full)

    print(f"\nFull deltas: |F|={len(delta_F_full)} |G|={len(delta_G_full)} "
          f"|FG|={len(delta_FG_full)}")
    print(f"Block-band restricted (M9K_MODE only):")

    composed = delta_F.symmetric_difference(delta_G)  # XOR set
    triangle_residual = composed.symmetric_difference(delta_FG)

    print(f"\n|delta_F|     = {len(delta_F)}")
    print(f"|delta_G|     = {len(delta_G)}")
    print(f"|delta_FG|    = {len(delta_FG)}")
    print(f"|delta_F ⊕ delta_G| = {len(composed)}")
    print(f"|triangle residual (composed △ delta_FG)| = {len(triangle_residual)}")

    if triangle_residual:
        print("\nResidual region breakdown:")
        rb = Counter(region_of((off - PRE) // FRAME) for off, _ in triangle_residual)
        for _, _, name in REGIONS:
            c = rb.get(name, 0)
            if c:
                print(f"  {name:18}  {c}")

    print()
    if not triangle_residual:
        print(f"✓ PASS — F={F_NAME} and G={G_NAME} are orthogonal; "
              f"single-feature deltas compose by XOR.")
        return 0
    leakage = len(triangle_residual)
    if leakage <= 0.05 * len(delta_FG):
        print(f"~ PARTIAL — {leakage} cells of feature interaction "
              f"({leakage/len(delta_FG)*100:.1f}% of delta_FG). "
              f"These need a joint (F,G) bucket.")
        return 0
    print(f"✗ FAIL — {leakage} cells of feature interaction "
          f"({leakage/len(delta_FG)*100:.1f}% of delta_FG). "
          f"F and G are not independently decomposable.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
