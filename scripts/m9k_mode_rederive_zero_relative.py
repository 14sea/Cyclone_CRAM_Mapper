# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-derive M9K_MODE buckets relative to nv_zero_global.

The original mining (`scripts/m9k_mode_quartus_gold_mine.py`) defined
each mode bucket as the variant-invariant block-band delta between a
Quartus-built `gold_v{n}.rbf` and a matched no-M9K `baseline.rbf`:

    bucket = ⋂_n (gold_vn ⊕ matched_baseline)   restricted to block band

`m9k_e2e_smoke.py` validates this bucket by applying it to the *mining
baseline* (`base_rbf=matched_baseline ⊕ bucket = gold` byte-identical
modulo INIT-dependent metadata).  In production, however, np2fasm
emits `M9K_MODE_*` directives whose `fasm2rbf` handler XORs the
bucket onto whatever `base_rbf` the caller provides — typically
`results/rbf/nv_zero_global.rbf` (or pure_zero, which agrees with
nv_zero_global at the block-band cells we care about).

Discovery 2026-04-25: the matched_baseline diverges from
nv_zero_global on ~100 of the 117 SDP bucket cells per site (and
similar fractions for SP/TDP), so the production codec path emits
the *wrong polarity* at those cells — silicon resets on flash
(verified at X15_Y16_N0 SDP).  The fix is to redefine the bucket
relative to nv_zero_global directly:

    bucket' = ⋂_n (gold_vn ⊕ nv_zero_global)   restricted to block band

This script reads every existing bucket entry in
`results/m9k_mode_bits.json` and re-derives it from the on-disk
v0/v1/v2 mining variants under `tmp/m9k_mode_quartus_gold/`.

Output: rewrites `results/m9k_mode_bits.json` in place; backs up the
old file to `results/m9k_mode_bits.json.pre_zero_rederive.bak` so the
old (matched_baseline-relative) buckets stay accessible for
m9k_e2e_smoke regression and audit.

Run:

    python3 scripts/m9k_mode_rederive_zero_relative.py
    python3 scripts/m9k_mode_rederive_zero_relative.py --dry-run

Bucket sizes drop ~5x at the SDP/TDP sites we audited (117 → 24 at
X15_Y16_N0 SDP) — expected, since ~100/117 cells were
matched_baseline-quirks rather than M9K mode bits.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "results/m9k_mode_bits.json"
BACKUP_PATH = ROOT / "results/m9k_mode_bits.json.pre_zero_rederive.bak"
ZERO_PATH = ROOT / "results/rbf/nv_zero_global.rbf"
TMP = ROOT / "tmp/m9k_mode_quartus_gold"

PRE = 32
FRAME = 210
DATA_PER_FRAME = 208
BLOCK_LO = 1692
BLOCK_HI = 1738

BUCKET_TO_MODE = {
    "quartus_gold":     "sp",
    "quartus_gold_sdp": "sdp",
    "quartus_gold_tdp": "tdp",
}


def variant_paths(site: str, mode: str, w: int, dd: int) -> list[Path]:
    """Return v0/v1/v2 paths in the order [v0, v1, v2]."""
    suffix = "" if mode == "sp" else f"_{mode}"
    candidates_by_n: dict[int, list[Path]] = {0: [], 1: [], 2: []}
    base_dirs = [TMP / f"{w}x{dd}"]
    if mode != "sp":
        base_dirs.append(TMP / f"{w}x{dd}" / mode)
    for base in base_dirs:
        for site_part in ("", site):
            for vn in (0, 1, 2):
                p = base / site_part / f"m9k_mode_gold_{w}x{dd}{suffix}_v{vn}.rbf"
                if p.exists():
                    candidates_by_n[vn].append(p)
    out = []
    for vn in (0, 1, 2):
        if not candidates_by_n[vn]:
            return []  # incomplete set
        out.append(candidates_by_n[vn][0])  # first match wins
    return out


def block_band_xor_intersection(zero: bytes, variants: list[bytes]) -> list[tuple[int, int]]:
    """Compute (off, bp) cells where (vn ⊕ zero) is set for ALL variants,
    restricted to block-band data bytes (frames 1692..1738, byte<208 of frame).
    """
    out: list[tuple[int, int]] = []
    n = len(zero)
    for off in range(PRE, n):
        frame = (off - PRE) // FRAME
        if frame < BLOCK_LO or frame > BLOCK_HI:
            continue
        if (off - PRE) % FRAME >= DATA_PER_FRAME:
            continue
        common = 0xFF
        for v in variants:
            common &= (v[off] ^ zero[off])
            if common == 0:
                break
        if common == 0:
            continue
        for bp in range(8):
            if common & (1 << bp):
                out.append((off, bp))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="report changes without writing JSON")
    args = ap.parse_args()

    zero = ZERO_PATH.read_bytes()
    d = json.loads(JSON_PATH.read_text())

    rederived = 0
    skipped = 0
    skipped_reasons: dict[str, int] = {}
    size_deltas: list[tuple[str, str, str, int, int]] = []  # (site,mode,wxd,old,new)

    for key, v in list(d.items()):
        if not key.startswith("X"):
            continue
        parts = key.split("_")
        site = "_".join(parts[:3])
        wxd = parts[3]
        w, dd = (int(x) for x in wxd.split("x"))
        cells_by = v.get("cells_by_template", {})
        for bname, mode in BUCKET_TO_MODE.items():
            if bname not in cells_by:
                continue
            paths = variant_paths(site, mode, w, dd)
            if not paths:
                skipped += 1
                skipped_reasons["missing variants"] = skipped_reasons.get("missing variants", 0) + 1
                continue
            variants = [p.read_bytes() for p in paths]
            new_bucket = block_band_xor_intersection(zero, variants)
            old_size = len(cells_by[bname])
            new_size = len(new_bucket)
            size_deltas.append((site, mode, wxd, old_size, new_size))
            cells_by[bname] = [list(c) for c in new_bucket]
            rederived += 1

    print(f"Re-derived {rederived} buckets; skipped {skipped}")
    if skipped_reasons:
        for r, n in skipped_reasons.items():
            print(f"  skip reason: {r} = {n}")
    print(f"\nBucket size deltas (old → new):")
    by_mode: dict[str, list[tuple[int, int]]] = {}
    for site, mode, wxd, o, n in size_deltas:
        by_mode.setdefault(mode, []).append((o, n))
    for mode, pairs in by_mode.items():
        avg_old = sum(p[0] for p in pairs) / max(1, len(pairs))
        avg_new = sum(p[1] for p in pairs) / max(1, len(pairs))
        print(f"  {mode.upper():3} ({len(pairs):3} buckets): "
              f"avg {avg_old:6.1f} → {avg_new:6.1f}  "
              f"min/max old: {min(p[0] for p in pairs)}/{max(p[0] for p in pairs)}  "
              f"min/max new: {min(p[1] for p in pairs)}/{max(p[1] for p in pairs)}")

    if args.dry_run:
        print("\n--dry-run: not writing JSON")
        return 0

    if not BACKUP_PATH.exists():
        shutil.copy(JSON_PATH, BACKUP_PATH)
        print(f"\nBacked up old JSON -> {BACKUP_PATH}")
    else:
        print(f"\nBackup already exists: {BACKUP_PATH} (not overwriting)")
    JSON_PATH.write_text(json.dumps(d, indent=2))
    print(f"Rewrote {JSON_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
