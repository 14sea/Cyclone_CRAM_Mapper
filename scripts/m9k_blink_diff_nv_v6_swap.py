# SPDX-License-Identifier: GPL-3.0-or-later
"""v6 silicon test for the m9k_blink_diff_nv directive.

Mode-correctness (NOT fabric-safety) test, structurally identical to
the 2026-04-30 v5 ζ-swap (memory
m9k_mode_v5_finding_gi_codec_unnecessary_2026_04_30.md).  Difference:
v5 kept Quartus's full block-band cells minus 1 inferred-overlap; v6
forces block-band entirely to nv_zero_global state, then re-applies
ONLY the per-site `m9k_blink_diff_nv` bucket as XOR delta.

Strategy:
  R_ref       = m9k_blink_full_X{x}_Y{y}_N{n}.rbf (Quartus 9x512 SP)
  R_strip     = R_ref XOR (block_band_diff(R_ref, nv_zero_global))
                — block-band frames now match nv_zero_global state
                exactly; everything else (counter, IOBs, clock, M9K
                INIT, M9K I/O routing) stays Quartus-built.
  R_v6        = R_strip XOR (cells_by_template["m9k_blink_diff_nv"][site])
                — by construction, R_v6 block-band == R_ref block-band,
                so this MUST silicon-pass when fed the right bucket.

That equality (R_v6 == R_ref byte-for-byte after CRC patch) IS the
silicon test: if HW behavior matches Quartus reference, it confirms
the bucket fully captures what's needed for M9K mode operation.

This is a tautological round-trip BY DESIGN — the point is to verify
that the bucket we mined contains exactly the right cells.  Then the
final consumer pipeline (np2fasm + nv_zero_global base) uses these
SAME cells to configure M9K mode under arbitrary user designs.

Usage:
    python3 scripts/m9k_blink_diff_nv_v6_swap.py X=15 Y=4
    python3 scripts/m9k_blink_diff_nv_v6_swap.py X=15 Y=10
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
from m9k_blink_diff_nv_mine import (  # noqa: E402
    block_band_diff_cells, find_blink_rbf, NV, MODE_BITS,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, required=True)
    ap.add_argument("--y", type=int, required=True)
    ap.add_argument("--n", type=int, default=0)
    ap.add_argument("--out", type=Path, default=None,
                    help="output RBF path (default: tmp/m9k_diff_nv_v6/...)")
    args = ap.parse_args()

    nv = NV.read_bytes()
    rbf_path = find_blink_rbf(args.x, args.y, args.n)
    if rbf_path is None:
        print(f"FAIL: no m9k_blink RBF found for X={args.x} Y={args.y} N={args.n}")
        return 1
    print(f"reference: {rbf_path.relative_to(ROOT)}")
    r_ref = rbf_path.read_bytes()
    assert len(r_ref) == len(nv) == 368011

    # Step 1: identify Quartus block-band cells differing from nv
    quartus_bb = block_band_diff_cells(r_ref, nv)
    print(f"Quartus block-band ⊕ nv: {len(quartus_bb)} cells")

    # Step 2: load mined diff_nv bucket for this site
    db = json.loads(MODE_BITS.read_text())
    key = f"X{args.x}_Y{args.y}_N{args.n}_9x512"
    if key not in db:
        print(f"FAIL: {key} not in m9k_mode_bits.json")
        return 1
    bucket = db[key].get("cells_by_template", {}).get("m9k_blink_diff_nv")
    if bucket is None:
        print(f"FAIL: {key} has no m9k_blink_diff_nv bucket; run "
              f"scripts/m9k_blink_diff_nv_mine.py")
        return 1
    bucket = [tuple(c) for c in bucket]
    print(f"diff_nv bucket: {len(bucket)} cells")

    # Sanity: bucket should equal Quartus block-band diff (by construction)
    if set(bucket) != set(quartus_bb):
        extras = set(bucket) - set(quartus_bb)
        missing = set(quartus_bb) - set(bucket)
        print(f"  WARN: bucket != live diff "
              f"(extras={len(extras)}, missing={len(missing)})")

    # Step 3: build v6 — strip then re-apply
    buf = bytearray(r_ref)
    for off, bp in quartus_bb:
        buf[off] ^= 1 << bp
    # buf now matches nv in block-band. Verify:
    stripped = block_band_diff_cells(bytes(buf), nv)
    assert not stripped, f"strip failed: {len(stripped)} cells remain"
    for off, bp in bucket:
        buf[off] ^= 1 << bp

    # Step 4: re-CRC and write
    out = patch_rbf_crc(bytes(buf))
    out_path = args.out or (
        ROOT / f"tmp/m9k_diff_nv_v6/m9k_diff_nv_v6_X{args.x}_Y{args.y}_N{args.n}.rbf"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(out)

    # Step 5: byte-identity check vs CRC-patched reference
    ref_crc = patch_rbf_crc(r_ref)
    if out == ref_crc:
        print(f"BYTE-IDENTICAL to CRC-patched reference (sanity ✓)")
    else:
        diff = sum(1 for i in range(len(out)) if out[i] != ref_crc[i])
        print(f"DIFFERS from reference by {diff} bytes — investigate")

    print(f"\n[wrote] {out_path.relative_to(ROOT)}  ({len(out)} bytes)")
    print("Flash with:")
    print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader "
          f"-c usb-blaster {out_path.relative_to(ROOT)}")
    print("Expected: same alternating fast↔long-on/long-off LED0 pattern as "
          "Quartus m9k_blink reference at the same site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
