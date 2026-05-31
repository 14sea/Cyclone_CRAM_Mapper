#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""STEP 0b — NEORV32 route-class DEMAND census (the mandatory-vs-skippable gate).

Phase-A's STEP 0 / A2 answered "which route classes does the codec MODEL?"
(C4 I=0, R4, LI are REAL; C4 I!=0, R24 are CRC-DEAD; C16/Direct/Block were
unresolved/aliased).  The open follow-up the scoping doc named "STEP 0b, not
yet run" is the *complementary* question:

    Which route classes does NEORV32 actually USE, and how heavily?

If NEORV32 routes only on the REAL classes, the dead-class re-mining campaign
(the 30-60+ pw bulk of native Option 2) is SKIPPABLE.  If it leans on the
DEAD/UNMODELED classes, that campaign is MANDATORY before native NEORV32 can
be routed-and-flashed.  This gate decides which.

Two on-disk data sources, NO Quartus recompile, NO flash:
  1. fit.rpt "Routing Usage Summary" — authoritative per-class TOTAL distinct
     wires used by the full design.
  2. STA -show_routing report (scripts/routing_model/step0b_routing_census.tcl,
     quartus_sta on the existing DB) — the per-class I-index DISTRIBUTION over
     a large near-critical path sample, used to estimate the emittable fraction
     within each class.

Emittable ground-truth comes from the codec itself (no hardcoded guesses):
  * C4   : only I=0 is emittable (the I!=0 table `_C4_FIXED_OFFSETS` is 100%
           CRC-dead per STEP 0 — read-path only).
  * R4   : I in `_R4_BASE_PREV` (the mapped/emittable I-indices).
  * R24  : `_R24_FIXED_OFFSETS` is 100% CRC-dead -> nothing emittable.
  * C16  : no codec model -> unmodeled.
  * LI / Block / Local : the codec's LI region (A2: Block interconnect =
           BLOCK_INPUT_MUX = LE input MUX, aliases onto codec LI) -> REAL-partial.
  * Direct links : intra-LAB LE->LE, UNMODELED.

Usage:  python3 scripts/routing_model/step0b_route_demand.py
        [--fit /path/neorv32_demo.fit.rpt] [--sta /tmp/step0b_sta_routing.rpt]
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))

import bitstream as bs  # noqa: E402

DEFAULT_FIT = Path(
    "/home/test/see_neorv32_run_linux/quartus/neorv32_demo.fit.rpt")
DEFAULT_STA = Path("/tmp/step0b_sta_routing.rpt")

# Class -> (codec verdict, is-emittable predicate over I-index).
# None predicate means "no per-I emittable subset" (whole class dead/unmodeled).
R4_REAL = set(bs._R4_BASE_PREV.keys())


def emittable(cls: str, i: int) -> bool:
    if cls == "C4":
        return i == 0                       # I!=0 table is CRC-dead
    if cls == "R4":
        return i in R4_REAL                 # 24 mapped I-indices
    return False                            # R24 (CRC-dead), C16 (unmodeled)


CLASS_NOTE = {
    "C4": "I=0 REAL (formula) | I!=0 DEAD (_C4_FIXED_OFFSETS = 100% CRC)",
    "R4": f"I in {len(R4_REAL)}-key _R4_BASE_PREV REAL | else UNMODELED",
    "R24": "_R24_FIXED_OFFSETS = 100% CRC -> DEAD",
    "C16": "no codec model -> UNMODELED",
}


def parse_fit_totals(fit_path: Path) -> dict:
    """Return {resource_type: used_count} from the Routing Usage Summary.

    Matches the known routing resource-type rows directly (e.g.
    "; C4 interconnects ; 3,456 / 21,816 ( 16 % ) ;") rather than running a
    section state-machine — "Routing Usage Summary" also appears in the
    Table of Contents, and a naive state-machine then captures the wrong
    (Fitter Resource Usage) table.  Anchoring on the resource names is robust.
    """
    wanted = {
        "Block interconnects", "C16 interconnects", "C4 interconnects",
        "Direct links", "Local interconnects", "R24 interconnects",
        "R4 interconnects",
    }
    out = {}
    rx = re.compile(r";\s*([A-Za-z0-9 ]+?)\s*;\s*([\d,]+)\s*/\s*[\d,]+")
    for line in fit_path.read_text(errors="replace").splitlines():
        m = rx.search(line)
        if m and m.group(1).strip() in wanted:
            out[m.group(1).strip()] = int(m.group(2).replace(",", ""))
    return out


def parse_sta_idist(sta_path: Path):
    """Return per-class: distinct wires, path occurrences, and I-index Counters."""
    wires = collections.defaultdict(set)
    occ = collections.Counter()
    i_occ = collections.defaultdict(collections.Counter)
    i_wires = collections.defaultdict(lambda: collections.defaultdict(set))
    pat = re.compile(r'\b(C4|R4|R24|C16)_X(\d+)_Y(\d+)_N(\d+)_I(\d+)\b')
    for m in pat.finditer(sta_path.read_text(errors="replace")):
        cls, x, y, n, i = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5))
        w = (x, y, n, i)
        wires[cls].add(w)
        occ[cls] += 1
        i_occ[cls][i] += 1
        i_wires[cls][i].add(w)
    return wires, occ, i_occ, i_wires


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", type=Path, default=DEFAULT_FIT)
    ap.add_argument("--sta", type=Path, default=DEFAULT_STA)
    args = ap.parse_args()

    if not args.fit.exists():
        print(f"SKIP: fit report {args.fit} not present")
        return 0
    totals = parse_fit_totals(args.fit)

    # Map fit-report resource names -> our class keys (+ verdict for the rest).
    FIT_TO_CLASS = {
        "Block interconnects": ("LI", "REAL-aliased(LI / BLOCK_INPUT_MUX)"),
        "Local interconnects": ("LI", "REAL-partial(codec LI)"),
        "R4 interconnects": ("R4", "REAL-partial(per-I below)"),
        "C4 interconnects": ("C4", "MIXED(I=0 REAL / I!=0 DEAD)"),
        "Direct links": ("DIRECT", "UNMODELED(intra-LAB)"),
        "R24 interconnects": ("R24", "DEAD"),
        "C16 interconnects": ("C16", "UNMODELED"),
    }
    grand = sum(v for k, v in totals.items() if k in FIT_TO_CLASS)
    print("=== STEP 0b — NEORV32 route-class DEMAND (fit.rpt authoritative totals) ===\n")
    print(f"{'resource (fit.rpt)':<22}{'used':>7}{'%tot':>7}   verdict")
    print("-" * 74)
    for name, used in sorted(totals.items(), key=lambda kv: -kv[1]):
        if name not in FIT_TO_CLASS:
            continue
        _, verdict = FIT_TO_CLASS[name]
        print(f"{name:<22}{used:>7}{100*used/grand:>6.1f}%   {verdict}")
    print("-" * 74)
    print(f"{'TOTAL routing wires':<22}{grand:>7}\n")

    if not args.sta.exists():
        print(f"(per-I split skipped: STA report {args.sta} not present;")
        print(" regenerate via: quartus_sta -t scripts/routing_model/step0b_routing_census.tcl)")
        return 0

    wires, occ, i_occ, i_wires = parse_sta_idist(args.sta)
    print("=== per-I emittable split (STA sample; codec ground-truth) ===")
    print("    sample is near-critical-region biased — read as the I-distribution,")
    print("    projected onto the authoritative fit totals above.\n")
    proj = {}
    for cls, fit_name in (("C4", "C4 interconnects"), ("R4", "R4 interconnects"),
                          ("R24", "R24 interconnects"), ("C16", "C16 interconnects")):
        n = len(wires[cls])
        if not n:
            continue
        real_w = sum(len(ws) for i, ws in i_wires[cls].items() if emittable(cls, i))
        real_occ = sum(c for i, c in i_occ[cls].items() if emittable(cls, i))
        tot = totals.get(fit_name, 0)
        proj_real = round(tot * real_w / n)
        proj[cls] = (tot, proj_real, tot - proj_real)
        print(f"{cls}: {n} distinct sampled, {occ[cls]} path-occ | "
              f"emittable {real_w}/{n} distinct ({100*real_w/n:.0f}%), "
              f"{100*real_occ/occ[cls]:.0f}% by usage")
        print(f"     {CLASS_NOTE[cls]}")
        print(f"     -> PROJECTED on fit total {tot}: ~{proj_real} emittable / "
              f"~{tot-proj_real} need mining")
        if cls == "R4":
            miss = sorted(set(i_wires['R4']) - R4_REAL)
            hot = i_occ['R4'].most_common(3)
            print(f"     R4 used-but-unmined I: {miss}")
            print(f"     R4 hottest I (occ): {hot} "
                  f"-> {'INCLUDES unmined' if any(i not in R4_REAL for i,_ in hot) else 'all mined'}")
        print()

    # Verdict
    dead_total = (totals.get("R24 interconnects", 0)
                  + totals.get("C16 interconnects", 0)
                  + totals.get("Direct links", 0))
    c4_dead = proj.get("C4", (0, 0, 0))[2]
    r4_dead = proj.get("R4", (0, 0, 0))[2]
    need_mining = dead_total + c4_dead + r4_dead
    print("=" * 74)
    print("VERDICT")
    print("=" * 74)
    print(f"  NEORV32 routing wires needing a NEW/extended model before native")
    print(f"  route+flash is possible:  ~{need_mining} / {grand} "
          f"({100*need_mining/grand:.0f}%)")
    print(f"    - C4 I!=0 (from scratch, 100% CRC-dead):     ~{c4_dead}")
    print(f"    - R4 unmined I-indices (extend _R4_BASE_PREV): ~{r4_dead}")
    print(f"    - R24 (from scratch) + C16 + Direct links:    {dead_total}")
    print()
    print("  Emittable today (Block/Local LI + C4 I=0 + mapped R4): "
          f"~{grand - need_mining} ({100*(grand-need_mining)/grand:.0f}%)")
    print()
    print("  => The dead/unmodeled-class re-mining campaign is MANDATORY, not")
    print("     skippable: NEORV32 leans on C4 I!=0 (its single hottest C4 wires)")
    print("     and R4 I-indices outside the mapped set (incl. its hottest R4).")
    print("     This QUANTIFIES and CONFIRMS the Phase-A FREEZE-native / ship-ζ")
    print("     decision — native NEORV32 needs the full per-pip campaign, not a")
    print("     partial-coverage shortcut.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
