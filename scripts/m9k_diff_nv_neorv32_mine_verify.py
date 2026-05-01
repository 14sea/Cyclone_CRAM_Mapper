# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine + FASM byte-identity verify the diff_nv bucket at every NEORV32
M9K site, for the mode/shape NEORV32 places at each site.

Operates over the placement table in scripts/m9k_blink_neorv32_sites.py.
For each (mode, w, d, X, Y) tuple:
  1. Mine cells_by_template["m9k_blink_diff_nv"] into m9k_mode_bits.json
     (auto-creates the JSON key if missing).
  2. Strip block-band cells back to nv_zero_global; FASM-rebuild via
     M9K_MODE_<w>x<d>_m9k_blink_diff_nv directive.
  3. Assert byte-identical to the Quartus reference (post CRC patch).

Usage:
    python3 scripts/m9k_diff_nv_neorv32_mine_verify.py            # mine + verify
    python3 scripts/m9k_diff_nv_neorv32_mine_verify.py --skip-mine  # verify only
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
sys.path.insert(0, str(ROOT / "scripts"))

from bitstream import patch_rbf_crc  # noqa: E402
from fasm2rbf import bitgen  # noqa: E402
from m9k_blink_diff_nv_mine import block_band_diff_cells, find_blink_rbf, NV  # noqa: E402
from m9k_blink_neorv32_sites import NEORV32_PLACEMENTS  # noqa: E402

MODE_BITS = ROOT / "results/m9k_mode_bits.json"
OUT_DIR = ROOT / "tmp/m9k_diff_nv_neorv32_verify"


def mine_one(db: dict, mode: str, w: int, d: int, x: int, y: int, n: int = 0
             ) -> int | None:
    rbf_path = find_blink_rbf(x, y, n, width=w, depth=d, mode=mode)
    if rbf_path is None:
        return None
    nv = NV.read_bytes()
    rbf = rbf_path.read_bytes()
    cells = block_band_diff_cells(rbf, nv)
    key = f"X{x}_Y{y}_N{n}_{w}x{d}"
    if key not in db:
        db[key] = {
            "cells_by_template": {},
            "template_probe_source": {},
            "_origin": "m9k_diff_nv_neorv32_mine_verify.py",
        }
    entry = db[key]
    entry.setdefault("cells_by_template", {})
    entry["cells_by_template"]["m9k_blink_diff_nv"] = [list(c) for c in cells]
    entry.setdefault("template_probe_source", {})
    entry["template_probe_source"]["m9k_blink_diff_nv"] = str(
        rbf_path.relative_to(ROOT)
    )
    return len(cells)


def verify_one(mode: str, w: int, d: int, x: int, y: int, n: int = 0) -> bool:
    rbf_path = find_blink_rbf(x, y, n, width=w, depth=d, mode=mode)
    if rbf_path is None:
        print(f"  NO RBF for {mode} {w}x{d} X={x} Y={y}")
        return False
    nv = NV.read_bytes()
    rbf = rbf_path.read_bytes()
    diff = block_band_diff_cells(rbf, nv)
    buf = bytearray(rbf)
    for off, bp in diff:
        buf[off] ^= 1 << bp
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fasm_text = f"X{x}Y{y}N{n}.M9K_MODE_{w}x{d}_m9k_blink_diff_nv\n"
    rebuilt = bitgen(fasm_text, bytes(buf))
    rebuilt_crc = patch_rbf_crc(rebuilt)
    ref = patch_rbf_crc(rbf_path.read_bytes())
    return rebuilt_crc == ref


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-mine", action="store_true",
                    help="don't update m9k_mode_bits.json — verify only")
    args = ap.parse_args()

    db = json.loads(MODE_BITS.read_text())

    print("=== mining ===")
    mined: list[tuple[str, int]] = []
    missing: list[str] = []
    for mode, w, d, sites in NEORV32_PLACEMENTS:
        for x, y in sites:
            tag = f"{mode} {w}x{d} X{x}_Y{y}"
            n_cells = mine_one(db, mode, w, d, x, y) if not args.skip_mine \
                else (len(db.get(f"X{x}_Y{y}_N0_{w}x{d}", {})
                       .get("cells_by_template", {})
                       .get("m9k_blink_diff_nv", [])) or None)
            if n_cells is None:
                missing.append(tag)
                print(f"  MISS  {tag}")
            else:
                mined.append((tag, n_cells))
                print(f"  {n_cells:3d}   {tag}")

    if not args.skip_mine and mined:
        MODE_BITS.write_text(json.dumps(db, indent=2, sort_keys=True))
        print(f"\n[wrote] {MODE_BITS.relative_to(ROOT)}")

    print("\n=== verifying byte-identity ===")
    passed = 0
    failed: list[str] = []
    for mode, w, d, sites in NEORV32_PLACEMENTS:
        for x, y in sites:
            tag = f"{mode} {w}x{d} X{x}_Y{y}"
            if any(t == tag for t in missing):
                continue
            ok = verify_one(mode, w, d, x, y)
            if ok:
                passed += 1
                print(f"  PASS  {tag}")
            else:
                failed.append(tag)
                print(f"  FAIL  {tag}")

    total = sum(len(s) for _, _, _, s in NEORV32_PLACEMENTS) - len(missing)
    print(f"\nVerify: {passed}/{total} byte-identical")
    if missing:
        print(f"Missing RBFs ({len(missing)}):")
        for m in missing:
            print(f"  {m}")
    return 0 if (not failed and not missing) else 1


if __name__ == "__main__":
    sys.exit(main())
