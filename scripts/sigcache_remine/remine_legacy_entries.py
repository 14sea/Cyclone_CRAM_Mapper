# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-derive legacy sig-cache entries from lits_pair_*.rbf mining sources.

The legacy route_cells.json (1,725 entries, 6-tuple sn=0-only) was extracted
with an older pipeline that dropped LE-adjacent route cells — validated on
2026-04-23 by flashing lits_pair_X16Y4_to_X16Y14N0_dataa.rbf (169 cells)
vs the legacy 66-cell entry: the former is silicon-functional, the latter
caused a dead flash (LED OFF).

This script walks each legacy key, finds the matching lits_pair RBF, and
extracts the full fabric cell diff (frames 25..1751, pos < 208) against
nv_zero_global.rbf. Output goes to results/route_cells_remined.json (NOT
route_cells.json — do not overwrite the original until sampled entries
are HW-verified).

Usage:
    python3 scripts/sigcache_remine/remine_legacy_entries.py

Output stats:
    results/sigcache_remine_report.json   per-entry old/new cell counts
    results/route_cells_remined.json      new 6-tuple table

After review, merge into route_cells_full.json by running:
    cp results/route_cells_remined.json results/route_cells.json
    python3 fuzz/nv_sig_cache_merge.py
"""
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RBF_DIR = ROOT / "results" / "rbf"
ZERO_RBF = RBF_DIR / "nv_zero_global.rbf"
LEGACY = ROOT / "results" / "route_cells.json"
OUT_CELLS = ROOT / "results" / "route_cells_remined.json"
OUT_REPORT = ROOT / "results" / "sigcache_remine_report.json"


def diff_fabric_cells(a: bytes, b: bytes) -> list:
    """Return (off, bp) cells where a != b, restricted to fabric band
    (frame >= 25, pos < 208). Excludes header and CRC positions."""
    out = []
    n = len(a)
    for i in range(n):
        x = a[i] ^ b[i]
        if not x:
            continue
        pos = (i - 32) % 210
        if pos >= 208:
            continue  # CRC
        frame = (i - 32) // 210
        if frame < 25:
            continue  # header
        for bp in range(8):
            if x & (1 << bp):
                out.append([i, bp])
    return out


def find_lits_pair(sx: int, sy: int, dx: int, dy: int, dn: int, port: str) -> Path:
    """Find the lits_pair RBF matching a legacy (sx,sy → dx,dy,dn,port) key.
    Returns Path or None."""
    name = f"lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N{dn}_{port}.rbf"
    p = RBF_DIR / name
    if p.exists():
        return p
    return None


def main():
    zero = ZERO_RBF.read_bytes()
    assert len(zero) == 368011, f"nv_zero unexpected size {len(zero)}"

    legacy = json.loads(LEGACY.read_text())
    print(f"legacy entries: {len(legacy)}")

    remined = {}
    report = []
    key_re = re.compile(r"^(\d+),(\d+)->(\d+),(\d+),(\d+),(\w+)$")

    found = missing = unchanged = grew = shrank = 0
    total_old = total_new = 0

    for idx, (k, old_cells) in enumerate(legacy.items()):
        m = key_re.match(k)
        if not m:
            continue
        sx, sy, dx, dy, dn = [int(x) for x in m.groups()[:5]]
        port = m.group(6)

        pair = find_lits_pair(sx, sy, dx, dy, dn, port)
        if pair is None:
            missing += 1
            report.append({
                "key": k, "status": "no_pair_rbf",
                "old_cells": len(old_cells),
            })
            # keep legacy as-is
            remined[k] = old_cells
            continue

        found += 1
        rbf = pair.read_bytes()
        new_cells = diff_fabric_cells(rbf, zero)
        old_n = len(old_cells)
        new_n = len(new_cells)
        total_old += old_n
        total_new += new_n
        if new_n == old_n:
            unchanged += 1
            status = "equal_count"
        elif new_n > old_n:
            grew += 1
            status = "grew"
        else:
            shrank += 1
            status = "shrank"

        old_set = {tuple(c) for c in old_cells}
        new_set = {tuple(c) for c in new_cells}
        inter = len(old_set & new_set)

        report.append({
            "key": k, "status": status,
            "old_cells": old_n, "new_cells": new_n,
            "intersection": inter,
            "rbf": pair.name,
        })
        remined[k] = new_cells

        if (idx + 1) % 100 == 0:
            print(f"  [{idx+1}/{len(legacy)}] found={found} missing={missing} "
                  f"grew={grew} shrank={shrank}")

    print()
    print(f"== DONE ==")
    print(f"  found matching RBF:   {found}")
    print(f"  no pair RBF (kept):   {missing}")
    print(f"  grew:                 {grew}")
    print(f"  shrank:               {shrank}")
    print(f"  equal count:          {unchanged}")
    print(f"  total cells old→new: {total_old} → {total_new}  "
          f"(delta +{total_new - total_old})")

    OUT_CELLS.write_text(json.dumps(remined))
    OUT_REPORT.write_text(json.dumps(report, indent=1))
    print(f"\nwrote {OUT_CELLS} ({OUT_CELLS.stat().st_size/1e6:.1f} MB)")
    print(f"wrote {OUT_REPORT}")


if __name__ == "__main__":
    main()
