"""Combined (A)+(B) analysis on the 21 lits_pair RBFs:
  A) Source-side residual cells at (10,10): per-sample (pair,base) pattern
  B) Total hop count (R4 + C4) parity vs mode

Filters constant-network noise: any C4/R4 wire that appears in MORE than half
of the samples is treated as background and excluded from hop count.
"""
import json
import re
import sys
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))
from bitstream import RouteCodec

RBF_DIR = ROOT / "results" / "rbf"
ZERO = RBF_DIR / "lits_zero_10_10.rbf"
CLASS = ROOT / "results" / "li_lab_classification.json"
SRC = (10, 10)

WIRE_RE = re.compile(r"^(C4|R4)_X(\d+)_Y(\d+)_N0_I(\d+)$")


def main():
    cls = json.loads(CLASS.read_text())
    samples = [s for s in cls["samples"] if s["mode"] in ("paired", "alternating")]
    codec = RouteCodec()
    zero = ZERO.read_bytes()

    # First pass: read everything, build noise frequency table
    per_sample = []
    wire_freq = Counter()
    for s in samples:
        dx, dy, mode = s["dst_x"], s["dst_y"], s["mode"]
        rbf = (RBF_DIR / f"lits_pair_X10Y10_to_X{dx}Y{dy}N0_datab.rbf").read_bytes()
        sw = codec.read_switches(rbf, zero, wire_types={"c4", "r4"})
        wires = {e[0] for lst in sw.values() for e in lst}
        for w in wires:
            wire_freq[w] += 1
        # Source-side LI residuals
        li = codec.read_local_interconnect(rbf, zero)
        src_cells = sorted({(codec._parse_li_name(e[0])[2], codec._parse_li_name(e[0])[3])
                            for e in li
                            if codec._parse_li_name(e[0])[:2] == SRC})
        per_sample.append({"dx": dx, "dy": dy, "mode": mode, "wires": wires, "src_cells": src_cells})

    # Background = wires appearing in >= 70% of samples (constant network)
    THRESH = int(0.7 * len(samples))
    bg = {w for w, c in wire_freq.items() if c >= THRESH}
    print(f"Background wires (≥{THRESH}/{len(samples)} samples): {len(bg)}\n")

    print(f"{'dst':>8} {'mode':>11} {'C4':>3} {'R4':>3} {'tot':>3} {'parity':>6}  src_cells")
    rows = []
    for ps in per_sample:
        clean = ps["wires"] - bg
        c4 = sum(1 for w in clean if w.startswith("C4"))
        r4 = sum(1 for w in clean if w.startswith("R4"))
        tot = c4 + r4
        parity = "P" if tot % 2 == 0 else "A"
        match = "✓" if (parity == "P" and ps["mode"] == "paired") or \
                       (parity == "A" and ps["mode"] == "alternating") else "✗"
        sc = " ".join(f"P{p}B{b}" for p, b in ps["src_cells"])
        print(f"  ({ps['dx']:2d},{ps['dy']:2d}) {ps['mode']:>11} {c4:3d} {r4:3d} {tot:3d}  {parity}({match}) {sc}")
        rows.append({**ps, "wires": None, "c4_clean": c4, "r4_clean": r4,
                     "total_hops": tot, "parity_pred": parity, "match": match})

    # Cross-tab src_cells vs mode
    print("\n=== Source-side residual patterns vs mode ===")
    sc_to_modes = defaultdict(Counter)
    for ps in per_sample:
        sc_to_modes[tuple(ps["src_cells"])][ps["mode"]] += 1
    for sc, ctr in sorted(sc_to_modes.items(), key=lambda kv: -sum(kv[1].values())):
        sc_str = " ".join(f"P{p}B{b}" for p, b in sc) or "(empty)"
        print(f"  {sc_str:30s} → {dict(ctr)}")

    # Parity accuracy
    n_match = sum(1 for r in rows if r["match"] == "✓")
    print(f"\nParity rule accuracy: {n_match}/{len(rows)}")

    out = ROOT / "results" / "li_mode_full_mine.json"
    out.write_text(json.dumps({
        "background_wire_count": len(bg),
        "samples": rows,
        "src_cells_to_modes": {repr(k): dict(v) for k, v in sc_to_modes.items()},
        "parity_match": n_match,
        "total": len(rows),
    }, indent=2, default=str))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
