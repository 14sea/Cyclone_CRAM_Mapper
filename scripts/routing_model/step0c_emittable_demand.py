#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""STEP 0c — NEORV32 route demand vs the LIVE write model, on COMPLETE data.

STEP 0b (2026-05-31) hardcoded "C4: only I=0 is emittable", a premise the
2026-07-06/07 pip-conditioned campaign invalidated.  This re-measures against
the live codec + live gate whitelist.

Data source is a back-annotated .rcf (see rcf_route_census), NOT a
`report_timing -show_routing` sample.  That matters: the STA sample covered
only ~3.5% of NEORV32's C4 wires, was near-critical-path biased, and counted a
wire once per critical path it lay on -- three ways to get the class ranking
wrong at once.  The .rcf carries every net's full routing tree and reproduces
the fit.rpt per-class totals exactly (0 delta on C4/R4/R24/C16), so the census
is complete and self-validating.

The unit is the DISTINCT WIRE, matching what fit.rpt counts.  Routing is a
tree, so every wire has exactly one driver pip and there is no strict-vs-
optimistic ambiguity to resolve.

Usage:
    python3 scripts/routing_model/step0c_emittable_demand.py
        [--rcf tmp/nv_ba/neorv32_demo.rcf] [--fit ...] [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(HERE))

import bitstream as bs                      # noqa: E402
import pip_prediction_gate as gate          # noqa: E402
import write_c4_pip_proto as proto          # noqa: E402
import rcf_route_census as rcf              # noqa: E402
import step0b_route_demand as step0b        # noqa: E402

R4_REAL = set(bs._R4_BASE_PREV.keys())
DEF_RCF = REPO / "tmp" / "nv_ba" / "neorv32_demo.rcf"
DEF_FIT = REPO / "tmp" / "nv_ba" / "neorv32_demo.fit.rpt"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rcf", type=Path, default=DEF_RCF)
    ap.add_argument("--fit", type=Path, default=DEF_FIT)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not a.rcf.exists():
        print(f"missing {a.rcf}\n  generate it per rcf_route_census's docstring")
        return 1

    wl, tbl = proto.load_whitelist()          # NB: returns (whitelist, table)
    wires, pips, drivers, nets = rcf.census(a.rcf)
    totals = step0b.parse_fit_totals(a.fit) if a.fit.exists() else {}
    grand = sum(totals.values()) or sum(
        len(wires[c]) for c in ("C4", "R4", "R24", "C16",
                                "LOCAL_INTERCONNECT", "LOCAL_LINE"))
    print(f"source: {a.rcf.name}  ({len(nets)} nets, {len(pips)} pips)")
    print(f"C4 table: {len(tbl)} classes, {len(wl)} whitelisted for emission\n")

    # ---------------- C4 -------------------------------------------------
    c4 = wires["C4"]
    i0 = {w for w in c4 if w.endswith("_I0")}
    cls_w = collections.defaultdict(set)
    oo_reason = collections.Counter()
    for w in c4 - i0:
        keys = set()
        for src in drivers.get(w, ()):
            p = gate.predict_c4_pip(tbl, src, w)
            if p:
                keys.add(p[0])
        if not keys:
            m = gate.WIRE.match(w)
            x, y = int(m.group(2)), int(m.group(3))
            oo_reason["non-LAB column (M9K/mult/edge)" if x not in gate.CB
                      else ("I/O-ring row" if not 2 <= y <= 21
                            else "net source (no driver pip)")] += 1
            continue
        for k in keys:
            cls_w[k].add(w)

    modelled = {w for s in cls_w.values() for w in s}
    emit = {w for k, s in cls_w.items() if k in wl for w in s}
    tabled = {k for k in cls_w if k in tbl and k not in wl}
    unmined = {k for k in cls_w if k not in tbl}
    t_w = {w for k in tabled for w in cls_w[k]}
    u_w = {w for k in unmined for w in cls_w[k]}

    print("=== C4 (the class STEP 0b wrote off entirely) ===")
    print(f"  wires used by NEORV32          : {len(c4)}")
    print(f"    I=0, emittable by formula    : {len(i0):5d}  "
          f"({100*len(i0)/len(c4):4.1f}%)")
    print(f"    I!=0 inside model domain     : {len(modelled):5d}")
    print(f"    I!=0 OUTSIDE model domain    : {sum(oo_reason.values()):5d}  "
          f"({100*sum(oo_reason.values())/len(c4):4.1f}%)")
    for r, n in oo_reason.most_common():
        print(f"        {n:5d}  {r}")
    print(f"  EMITTABLE TODAY (I=0 + whitelisted): "
          f"{len(i0)+len(emit):5d}  ({100*(len(i0)+len(emit))/len(c4):4.1f}%)")
    print(f"    of which whitelisted I!=0    : {len(emit):5d}")
    print(f"\n  class space seen in ONE design : {len(cls_w)} distinct classes")
    print(f"    whitelisted   {len(set(wl) & set(cls_w)):4d} classes -> "
          f"{len(emit):5d} wires")
    print(f"    tabled, gated {len(tabled):4d} classes -> {len(t_w):5d} wires")
    print(f"    unmined       {len(unmined):4d} classes -> {len(u_w):5d} wires")

    rank = sorted(cls_w.items(), key=lambda kv: -len(kv[1]))
    print(f"\n  demand is FLAT — cumulative share of the {len(modelled)} "
          "modelled wires:")
    for n in (1, 5, 10, 20, 40, 80):
        cum = sum(len(s) for _, s in rank[:n])
        print(f"    top {n:>3} classes -> {100*cum/len(modelled):5.1f}%")
    print(f"  {'rank':>4}{'wires':>7}  status   class")
    for n, (k, s) in enumerate(rank[:8], 1):
        st = "WL" if k in wl else ("TABLED" if k in tbl else "unmined")
        print(f"  {n:>4}{len(s):>7}  {st:<8} {gate.class_name(k)}")

    # ---------------- R4 -------------------------------------------------
    r4 = wires["R4"]
    r4_ok = {w for w in r4
             if (m := gate.WIRE.match(w)) and m.group(5)
             and int(m.group(5)) in R4_REAL}
    print(f"\n=== R4 ({len(R4_REAL)}-key _R4_BASE_PREV, read live) ===")
    print(f"  wires {len(r4)}, I in table {len(r4_ok)} "
          f"({100*len(r4_ok)/len(r4):.1f}%)")
    miss = collections.Counter(
        int(gate.WIRE.match(w).group(5)) for w in r4 - r4_ok)
    print("  unmined I by wire count: "
          + ", ".join(f"I={i}({c})" for i, c in miss.most_common(10)))

    # ---------------- roll-up -------------------------------------------
    li = len(wires["LOCAL_INTERCONNECT"]) + len(wires["LOCAL_LINE"])
    c4_before, c4_after = len(i0), len(i0) + len(emit)
    before = li + c4_before + len(r4_ok)
    after = li + c4_after + len(r4_ok)
    print("\n" + "=" * 74)
    print("VERDICT — NEORV32 routing wires emittable by the LIVE model")
    print("=" * 74)
    print(f"  total routing wires: {grand}")
    print(f"  BEFORE (STEP 0b premise, C4 = I=0 only): {before} "
          f"({100*before/grand:.1f}%)")
    print(f"  AFTER  (live C4 whitelist):              {after} "
          f"({100*after/grand:.1f}%)")
    print(f"  movement: {after-before:+d} wires "
          f"({100*(after-before)/grand:+.2f} pts)")
    print("\n  remaining gap:")
    for name, v in (("C4 not emittable", len(c4) - c4_after),
                    ("R4 unmined I", len(r4) - len(r4_ok)),
                    ("Direct links (UNMODELED)",
                     totals.get("Direct links", 0)),
                    ("R24 (CRC-dead)", len(wires["R24"])),
                    ("C16 (UNMODELED)", len(wires["C16"]))):
        print(f"    {name:<28}{v:>6}  ({100*v/grand:4.1f}% of all wires)")
    print(f"\n  !! UNAUDITED: the {li} LI wires ({100*li/grand:.1f}% of all "
          "routing — the single\n     largest 'emittable' block) are counted "
          "emittable on STEP 0b's inherited\n     assumption, never verified "
          "per-wire against the codec's LI model.\n     The .rcf also shows "
          "fit.rpt's 'Block interconnects' (7406) are rcf\n     "
          "LOCAL_INTERCONNECT and its 'Local interconnects' (2077) are rcf\n"
          "     LOCAL_LINE — worth re-checking against the A2 aliasing claim.")
    print("\n  NOTE: 'emittable' = the write model produces cells the gate "
          "trusts\n  (fresh-gold byte-identity). NOT a silicon claim, NOT a "
          "whole-route\n  completeness claim.")

    if a.json:
        out = REPO / "results" / "step0c_emittable_demand.json"
        out.write_text(json.dumps({
            "source": str(a.rcf), "nets": len(nets), "pips": len(pips),
            "grand": grand,
            "c4": {"total": len(c4), "i0": len(i0), "modelled": len(modelled),
                   "out_of_domain": dict(oo_reason), "whitelisted": len(emit),
                   "classes": len(cls_w), "tabled_classes": len(tabled),
                   "unmined_classes": len(unmined),
                   "tabled_wires": len(t_w), "unmined_wires": len(u_w),
                   "rank": [[gate.class_name(k), len(s),
                             "WL" if k in wl else
                             ("TABLED" if k in tbl else "unmined")]
                            for k, s in rank[:60]]},
            "r4": {"total": len(r4), "emittable": len(r4_ok),
                   "unmined_I": dict(miss)},
            "li_unaudited": li, "before": before, "after": after,
        }, indent=1))
        print(f"\n[json] {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
