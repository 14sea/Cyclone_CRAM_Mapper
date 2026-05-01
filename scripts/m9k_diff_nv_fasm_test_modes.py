# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end FASM byte-identity test for M9K_MODE_<w>x<d>_m9k_blink_diff_nv
across SP / SDP / TDP / ROM modes at one site (X15_Y10_N0).

For each (mode, w, d):
  1. Locate Quartus reference RBF (m9k_blink_<mode>_<w>x<d>_X15_Y10_N0.rbf)
  2. Strip block-band cells back to nv_zero_global state
  3. Run fasm2rbf with FASM directive  X15Y10N0.M9K_MODE_<w>x<d>_m9k_blink_diff_nv
  4. Assert the rebuilt RBF (post CRC patch) == Quartus reference (post CRC patch)

This validates the directive end-to-end for the new NEORV32-relevant
shapes that scripts/m9k_diff_nv_fasm_test.py (SP 9×512 only) doesn't
exercise.
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

OUT_DIR = ROOT / "tmp/m9k_diff_nv_fasm_test_modes"


def test_one(mode: str, w: int, d: int, x: int = 15, y: int = 10, n: int = 0) -> bool:
    print(f"\n== {mode.upper()} {w}x{d} X={x} Y={y} N={n} ==")
    rbf_path = find_blink_rbf(x, y, n, width=w, depth=d, mode=mode)
    if rbf_path is None:
        print(f"  NO RBF — build with scripts/m9k_blink_{mode}_build.py")
        return False
    nv = NV.read_bytes()
    rbf = rbf_path.read_bytes()
    diff = block_band_diff_cells(rbf, nv)
    buf = bytearray(rbf)
    for off, bp in diff:
        buf[off] ^= 1 << bp
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stripped = OUT_DIR / f"stripped_{mode}_{w}x{d}_X{x}_Y{y}_N{n}.rbf"
    stripped.write_bytes(bytes(buf))

    fasm_text = f"X{x}Y{y}N{n}.M9K_MODE_{w}x{d}_m9k_blink_diff_nv\n"
    rebuilt = bitgen(fasm_text, stripped.read_bytes())
    rebuilt_crc = patch_rbf_crc(rebuilt)
    ref = patch_rbf_crc(rbf_path.read_bytes())

    if rebuilt_crc == ref:
        print(f"  PASS ({len(diff)} cells) — byte-identical to Quartus reference")
        return True
    diffs = sum(1 for i in range(len(ref)) if ref[i] != rebuilt_crc[i])
    print(f"  FAIL — {diffs} bytes differ")
    return False


def main() -> int:
    cases = [
        ("sp",  8,   64),
        ("sp",  36,  256),
        ("sdp", 8,   1024),
        ("tdp", 16,  32),
        ("rom", 32,  256),
    ]
    passed = sum(test_one(m, w, d) for m, w, d in cases)
    print(f"\nResults: {passed}/{len(cases)} (mode, w, d) shapes byte-identical "
          f"via FASM M9K_MODE_<w>x<d>_m9k_blink_diff_nv directive")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    sys.exit(main())
