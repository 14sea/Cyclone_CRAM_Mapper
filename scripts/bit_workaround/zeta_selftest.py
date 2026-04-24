# SPDX-License-Identifier: GPL-3.0-or-later
"""CI-style self-test for the ζ production pipeline.

Runs every no-hardware gate (ζ → fasm2rbf → byte-identity → region diff)
against a known-good Quartus gold that is already HW-validated on silicon.
Designed to be cheap, deterministic, and suitable as a pre-commit or CI
smoke check.

Exits 0 iff every gate passes. Intended failure signal for regressions in:
  - quartus_gold_to_bit_fasm.py (ζ)
  - fuzz/fasm2rbf.py
  - fuzz/bitstream.py CRC path
  - zeta_rbf_diff.py

Fixtures:
  tmp/chipdb_test/quartus_two_lab/output_files/two_lab.rbf
      — two-LAB AND→DFF cross-LAB gold (1053 cells, HW-validated 2026-04-22)
  results/rbf/nv_zero_global.rbf
      — ζ baseline (XOR anchor)

Usage:
    python3 scripts/bit_workaround/zeta_selftest.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PIPELINE = ROOT / "scripts" / "bit_workaround" / "zeta_pipeline.py"
DIFFTOOL = ROOT / "scripts" / "bit_workaround" / "zeta_rbf_diff.py"
GOLD = ROOT / "tmp" / "chipdb_test" / "quartus_two_lab" / "output_files" / "two_lab.rbf"
WORK = ROOT / "tmp" / "zeta_selftest"


def die(msg: str, rc: int = 1):
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(rc)


def step(name: str):
    print(f"\n=== {name} ===")


def main():
    if not GOLD.exists():
        die(f"missing fixture: {GOLD}")

    WORK.mkdir(parents=True, exist_ok=True)
    json_out = WORK / "report.json"

    step("1. zeta_pipeline round-trip on two_lab.rbf (no flash)")
    p = subprocess.run(
        ["python3", str(PIPELINE), str(GOLD),
         "--workdir", str(WORK), "--json", str(json_out)],
        capture_output=True, text=True)
    print(p.stdout)
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        die(f"pipeline rc={p.returncode}")
    rebuilt = WORK / "two_lab.rebuilt.rbf"
    if not rebuilt.exists():
        die(f"rebuilt missing: {rebuilt}")

    step("2. zero-diff self-check against gold")
    p = subprocess.run(
        ["python3", str(DIFFTOOL), str(GOLD), str(rebuilt)],
        capture_output=True, text=True)
    print(p.stdout)
    if p.returncode != 0:
        die(f"rebuilt != gold (rc={p.returncode})")

    step("3. nonzero-diff sanity check: gold vs baseline")
    base = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
    p = subprocess.run(
        ["python3", str(DIFFTOOL), str(base), str(GOLD)],
        capture_output=True, text=True)
    print(p.stdout)
    # expect rc=1 (nonzero diff) and a known cell count
    if p.returncode != 1:
        die(f"expected diff rc=1, got {p.returncode}")
    if "1710 bits" not in p.stdout:
        die("expected '1710 bits' in diff output (two_lab cell count invariant)")

    print("\n[OK] ζ self-test passed — all three gates green.")


if __name__ == "__main__":
    main()
