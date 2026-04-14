# SPDX-License-Identifier: GPL-3.0-or-later
"""Bridge-delta probe: measure iob_zero_{pin} XOR nv_zero_global on CRAM cells
to decide whether a single pin-invariant bridge can translate pure_common[tgt]
(iob_zero-frame) into absolute cells in the nv_zero_global frame.

Algebra
-------
For a paired mining template with secondary LE + sec_src, and a design built
on the nv_zero_global baseline, the absolute cells in the nv-frame are:

  cells_abs(pin, tgt) = cells_pair(pin, tgt) XOR cells_nv_zero_global
                      = [cells_pair XOR cells_iob_zero(pin)]
                         XOR [cells_iob_zero(pin) XOR cells_nv_zero_global]
                      = delta(pin, tgt) XOR bridge(pin)

`bridge(pin)` is pin-dependent in general. If it is APPROXIMATELY pin-invariant
(pairwise symdiff << bridge size), then a single bridge table unlocks sig-cache
injection for all pins mined so far. If it is NOT pin-invariant, we need either
per-pin bridges (cheap, just store 3 sets) or a single-LE template.

This probe:
  1. Diffs CRAM cells (frames 25..1751, via fuzz/bitstream.py constants) for
     iob_zero_{E16,E15,M16} vs nv_zero_global.
  2. Reports bridge(pin) size per pin.
  3. Reports pairwise symdiff sizes (pin-invariance check).
  4. Reports overlap with pin_footprint(pin) from iob_route_decomposed.json
     — if bridge contains ALL of pin_footprint, then pin-dependence of the
     bridge is explained by the pad-mux footprint, which is expected.

No Quartus builds. Pure XOR algebra.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent

# Match the constants used by mine_iob_routes.py (see fuzz/bitstream.py:221).
CRC_PREAMBLE = 32
FRAME = 210
DATA = 208
FIRST_FRAME = 25
LAST_FRAME = 1751


def read_rbf_cells(path: Path) -> set[tuple[int, int]]:
    """Return set of (byte_offset, bit_pos) where bit is SET, limited to
    CRAM data bytes of frames 25..1751 (matches the mining diff scope)."""
    raw = path.read_bytes()
    cells: set[tuple[int, int]] = set()
    for frame in range(FIRST_FRAME, LAST_FRAME + 1):
        base = CRC_PREAMBLE + frame * FRAME
        for b in range(DATA):
            byte = raw[base + b]
            if byte == 0:
                continue
            off = base + b
            for bp in range(8):
                if byte & (1 << bp):
                    cells.add((off, bp))
    return cells


def main() -> int:
    nv_zero = REPO / "results" / "rbf" / "nv_zero_global.rbf"
    iob_zero_dir = REPO / "scripts" / "iob_slice_mining" / "work"

    pins = ["E16", "E15", "M16"]
    iob_zero_paths = {p: iob_zero_dir / f"iob_zero_{p}.rbf" for p in pins}

    for p in pins:
        if not iob_zero_paths[p].exists():
            print(f"[err] missing {iob_zero_paths[p]}", file=sys.stderr)
            return 1
    if not nv_zero.exists():
        print(f"[err] missing {nv_zero}", file=sys.stderr)
        return 1

    print(f"[load] nv_zero_global = {nv_zero}")
    nv_cells = read_rbf_cells(nv_zero)
    print(f"       |nv_cells|        = {len(nv_cells)}")

    bridges: dict[str, set[tuple[int, int]]] = {}
    for p in pins:
        iob_cells = read_rbf_cells(iob_zero_paths[p])
        bridges[p] = nv_cells ^ iob_cells
        print(f"[pin ] {p}: |iob_zero_{p}|={len(iob_cells)}  "
              f"bridge=|nv ^ iob_zero_{p}|={len(bridges[p])}")

    print("\n=== pairwise bridge symdiff (pin-invariance check) ===")
    for i, a in enumerate(pins):
        for b in pins[i + 1:]:
            sd = bridges[a] ^ bridges[b]
            common = bridges[a] & bridges[b]
            print(f"  {a} <> {b}: symdiff={len(sd)}  "
                  f"intersection={len(common)}")

    # Is the delta explained by pin_footprint?
    decomp_path = REPO / "results" / "iob_route_decomposed.json"
    if decomp_path.exists():
        d = json.loads(decomp_path.read_text())
        fp = {p: {tuple(c) for c in d["pin_footprint"].get(p, [])}
              for p in pins}
        universal = {tuple(c) for c in d["universal_infra"]}
        print("\n=== bridge vs decomposition layers ===")
        for p in pins:
            b = bridges[p]
            overlap_fp = b & fp[p]
            overlap_univ = b & universal
            print(f"  {p}: |bridge|={len(b)}  "
                  f"∩ fp[{p}]({len(fp[p])})={len(overlap_fp)}  "
                  f"∩ universal({len(universal)})={len(overlap_univ)}")

    # Pairwise bridges - shared core (likely pin-invariant substrate)
    shared = set.intersection(*bridges.values())
    print(f"\n=== shared bridge core (all 3 pins) ===")
    print(f"  |intersection(bridges)| = {len(shared)}")
    for p in pins:
        print(f"    bridge[{p}] - shared = {len(bridges[p] - shared)} "
              "(pin-specific bridge slice)")

    out = REPO / "results" / "iob_bridge_delta.json"
    out.write_text(json.dumps({
        "meta": {
            "nv_zero_rbf": str(nv_zero.relative_to(REPO)),
            "iob_zero_rbfs": {p: str(iob_zero_paths[p].relative_to(REPO))
                              for p in pins},
            "scope": f"CRAM cells frames {FIRST_FRAME}..{LAST_FRAME}",
        },
        "bridge": {p: sorted(list(c) for c in bridges[p]) for p in pins},
        "shared_core": sorted(list(c) for c in shared),
    }, indent=2))
    print(f"\n[ok] wrote {out} ({out.stat().st_size} bytes)")

    # Heuristic verdict
    max_sym = max(len(bridges[a] ^ bridges[b])
                  for i, a in enumerate(pins) for b in pins[i + 1:])
    avg_bridge = sum(len(b) for b in bridges.values()) / len(bridges)
    if max_sym < 0.2 * avg_bridge:
        print(f"\n[verdict] bridge is approximately PIN-INVARIANT "
              f"(max symdiff {max_sym} << avg bridge {avg_bridge:.0f}).")
        print("  -> single bridge table is sufficient for sig-cache injection.")
    else:
        print(f"\n[verdict] bridge is PIN-DEPENDENT "
              f"(max symdiff {max_sym} vs avg {avg_bridge:.0f}).")
        print("  -> store per-pin bridges OR check if the variance is "
              "explained by pin_footprint(pin).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
