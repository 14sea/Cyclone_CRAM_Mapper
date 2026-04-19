# SPDX-License-Identifier: GPL-3.0-or-later
"""Post-CLK_SEL-mining pipeline: per-LE derivation → FASM → RBF.

Run after mass_clk_sel_mine.py completes.  Steps:
  1. Regenerate results/clk_lab_sel_per_le.json (all probe JSONs)
  2. Regenerate FASM from placed JSON
  3. Build RBF from FASM

Usage:
    python3 scripts/stage_a_audit/rebuild_after_clk_sel.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(REPO / "synth"))


def step1_per_le():
    """Regenerate per-LE CLK_SEL data from all probe JSONs."""
    print("=== Step 1: Regenerate clk_lab_sel_per_le.json ===")
    n_probes = len(list((REPO / "results").glob("clk_lab_sel_probe_X*Y*.json")))
    print(f"  Found {n_probes} probe JSONs")

    r = subprocess.run(
        [sys.executable, str(REPO / "fuzz" / "clk_lab_sel_per_le.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"  FAILED: {r.stderr[:500]}")
        return False
    # Show summary
    for line in r.stdout.splitlines():
        if "wrote" in line or "LAB(" in line:
            pass  # skip verbose per-LAB lines
        elif line.strip():
            print(f"  {line.strip()}")

    data = json.loads((REPO / "results" / "clk_lab_sel_per_le.json").read_text())
    print(f"  per-LE entries: {len(data)} LABs")
    return True


def step2_fasm():
    """Regenerate FASM from placed JSON."""
    print("\n=== Step 2: Regenerate FASM ===")
    placed = REPO / "tmp" / "ax301_placed_v2.json"
    fasm_out = REPO / "tmp" / "ax301_v3.fasm"

    from np2fasm import convert
    with open(placed) as f:
        routed = json.load(f)
    lines, warnings = convert(routed, baseline="pure")

    fasm_out.write_text("\n".join(lines) + "\n")
    print(f"  FASM lines: {len(lines)}")
    print(f"  Warnings: {len(warnings)}")

    n_route_miss = 0
    n_iob_miss = 0
    n_clk_miss = 0
    for w in warnings:
        if "iob_to_slice" in w:
            n_iob_miss += 1
        elif "ROUTE" in w and "missing" in w:
            n_route_miss += 1
        elif "CLK_SEL" in w:
            n_clk_miss += 1
    print(f"  Route misses: {n_route_miss}")
    print(f"  IOB_ROUTE misses: {n_iob_miss}")
    print(f"  CLK_SEL misses: {n_clk_miss}")

    # Print the WARN line
    for line in lines:
        if line.startswith("# WARN:"):
            print(f"  {line}")
    for w in warnings:
        print(f"  WARN: {w}")

    return True


def step3_rbf():
    """Build RBF from FASM."""
    print("\n=== Step 3: Build RBF ===")
    fasm_path = REPO / "tmp" / "ax301_v3.fasm"
    rbf_out = REPO / "tmp" / "ax301_v3.rbf"

    fasm_text = fasm_path.read_text()

    from pure_zero_rbf import make_pure_zero_rbf
    import fasm2rbf as f2r

    base = make_pure_zero_rbf()
    rbf = f2r.bitgen(fasm_text, base, lenient=True, patch_crc=True)
    rbf_out.write_bytes(rbf)
    print(f"  RBF size: {len(rbf)} bytes")
    print(f"  Output: {rbf_out}")
    return True


def main():
    t0 = time.time()
    ok = step1_per_le()
    if not ok:
        return 1
    ok = step2_fasm()
    if not ok:
        return 1
    ok = step3_rbf()
    if not ok:
        return 1
    print(f"\nDone in {time.time() - t0:.0f}s")
    print(f"Flash: openFPGALoader -c usb-blaster tmp/ax301_v3.rbf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
