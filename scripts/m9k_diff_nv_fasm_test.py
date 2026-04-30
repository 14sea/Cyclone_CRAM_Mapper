# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end test of the M9K_MODE_<w>x<d>_m9k_blink_diff_nv directive.

For each test site:
  1. Take m9k_blink_full[A].rbf (Quartus reference at site A)
  2. Strip block-band cells to nv_zero_global state -> stripped[A].rbf
  3. Write FASM:  X{x}Y{y}N0.M9K_MODE_9x512_m9k_blink_diff_nv
  4. Run fasm2rbf with stripped[A].rbf as base
  5. Assert output (post CRC patch) == m9k_blink_full[A] post CRC patch

This validates the entire FASM directive pathway, not just the mining
arithmetic.  If the directive works here for multiple sites, np2fasm
can confidently emit it once Task #5 lands.

Usage:
    python3 scripts/m9k_diff_nv_fasm_test.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
sys.path.insert(0, str(ROOT / "scripts"))

from bitstream import patch_rbf_crc  # noqa: E402
from fasm2rbf import bitgen  # noqa: E402
from m9k_blink_diff_nv_mine import block_band_diff_cells, find_blink_rbf, NV  # noqa: E402

OUT_DIR = ROOT / "tmp/m9k_diff_nv_fasm_test"


def make_stripped(x: int, y: int, n: int) -> tuple[Path, Path] | None:
    rbf_path = find_blink_rbf(x, y, n)
    if rbf_path is None:
        print(f"  no RBF for X={x} Y={y} N={n}")
        return None
    nv = NV.read_bytes()
    rbf = rbf_path.read_bytes()
    diff = block_band_diff_cells(rbf, nv)
    buf = bytearray(rbf)
    for off, bp in diff:
        buf[off] ^= 1 << bp
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stripped = OUT_DIR / f"stripped_X{x}_Y{y}_N{n}.rbf"
    stripped.write_bytes(bytes(buf))
    return stripped, rbf_path


def test_site(x: int, y: int, n: int = 0) -> bool:
    print(f"\n== X={x} Y={y} N={n} ==")
    paths = make_stripped(x, y, n)
    if paths is None:
        return False
    stripped, rbf_path = paths

    fasm_text = f"X{x}Y{y}N{n}.M9K_MODE_9x512_m9k_blink_diff_nv\n"
    rebuilt = bitgen(fasm_text, stripped.read_bytes())
    rebuilt_crc = patch_rbf_crc(rebuilt)

    ref = patch_rbf_crc(rbf_path.read_bytes())

    if rebuilt_crc == ref:
        print(f"  PASS — FASM-driven rebuild byte-identical to Quartus reference")
        out = OUT_DIR / f"v6_X{x}_Y{y}_N{n}.rbf"
        out.write_bytes(rebuilt_crc)
        print(f"  flash candidate: {out.relative_to(ROOT)}")
        return True
    diffs = sum(1 for i in range(len(ref)) if ref[i] != rebuilt_crc[i])
    print(f"  FAIL — {diffs} bytes differ from reference")
    return False


def main() -> int:
    sites = [(15, 4), (15, 5), (15, 6), (15, 7), (15, 8), (15, 9),
             (15, 10), (15, 11), (15, 12)]
    passed = sum(test_site(x, y) for x, y in sites)
    print(f"\nResults: {passed}/{len(sites)} sites byte-identical via FASM directive")
    return 0 if passed == len(sites) else 1


if __name__ == "__main__":
    sys.exit(main())
