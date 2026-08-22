#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""STEP 0c — re-measure NEORV32 route demand against the CURRENT write model.

STEP 0b (2026-05-31) answered "how much of NEORV32's routing can the codec
emit?" and got ~31% needing a new/extended model.  Its C4 verdict was
hardcoded:

    * C4 : only I=0 is emittable (the I!=0 table is 100% CRC-dead)

That premise is **stale**.  The 2026-07-06/07 pip-conditioned campaign cracked
the C4 I!=0 write path (key = (I, src, dx, dy, slot), cells anchored on the
attach-end Y), and `write_c4_pip_proto.py` now carries a gated emission
whitelist with fresh-gold byte-identity evidence.  R4 moved too
(`_R4_BASE_PREV` 24 -> 27 keys), though STEP 0b already read that live.

So the strategic number STEP 0b produced is pessimistic by an unknown amount,
and pessimistic *specifically* in the class the recent campaigns targeted.
This tool re-measures with the live model and prints BEFORE vs AFTER, so the
next mining target is chosen by demand, not by momentum.

Method — same shape as STEP 0b, no Quartus recompile, no flash:
  * fit.rpt "Routing Usage Summary" gives the authoritative per-class totals.
  * the STA -show_routing sample gives the per-wire / per-pip distribution,
    which is projected onto those totals.
  * emittability comes from the live codec + the live gate whitelist, never
    from hardcoded guesses.

C4 wires are reached by pips, and one wire can have several driver-pips of
different classes, so two projections are reported:
    STRICT   — a wire counts as emittable only if EVERY observed driver-pip
               into it is whitelisted.  This is the number to plan with.
    OPTIMISTIC — any whitelisted driver-pip counts.  Upper bound.

Usage:
    python3 scripts/routing_model/step0c_emittable_demand.py
        [--fit <neorv32_demo.fit.rpt>] [--sta <step0b_sta_routing.rpt>] [--json]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(HERE))

import bitstream as bs                      # noqa: E402
import pip_prediction_gate as gate          # noqa: E402
import write_c4_pip_proto as proto          # noqa: E402
import step0b_route_demand as step0b        # noqa: E402
import pip_voting_neorv32 as pv             # noqa: E402

DEFAULT_FIT = step0b.DEFAULT_FIT
DEFAULT_STA = REPO / "tmp" / "step0b" / "step0b_sta_routing.rpt"

R4_REAL = set(bs._R4_BASE_PREV.keys())


def parse_paths(sta: Path):
    """Yield one wire sequence per 'Path #' block of the STA report."""
    cur: list[str] = []
    with open(sta, errors="replace") as f:
        for line in f:
            if "Path #" in line:
                if cur:
                    yield cur
                cur = []
            # gate.WIRE is anchored (^...$) for bare names; raw
            # report lines need the unanchored scanner.
            for m in pv.WSEQ.finditer(line):
                w = m.group(1)
                if not cur or cur[-1] != w:
                    cur.append(w)
    if cur:
        yield cur


def classify(sta: Path, table, whitelist):
    """Per-wire emittability for C4, plus R4 / other class wire counts."""
    c4_all = collections.Counter()       # wire -> occurrences
    c4_wl = collections.defaultdict(lambda: [0, 0])   # wire -> [wl_pips, pips]
    c4_i0 = set()
    c4_unmined = collections.Counter()   # class key -> occurrences
    c4_tabled = collections.Counter()    # mined but not whitelisted
    c4_wl_cls = collections.Counter()
    other = collections.defaultdict(set)  # class -> wires
    r4_i = collections.defaultdict(set)   # I -> wires

    for seq in parse_paths(sta):
        for a, b in zip(seq, seq[1:]):
            m = gate.WIRE.match(b)
            if not m:
                continue
            cls, i = m.group(1), (int(m.group(5)) if m.group(5) else None)
            if cls == "C4":
                c4_all[b] += 1
                if i == 0:
                    c4_i0.add(b)
                    continue
                p = gate.predict_c4_pip(table, a, b)
                if not p:
                    continue           # outside the model's x/y domain
                key, pred = p
                c4_wl[b][1] += 1
                if key in whitelist:
                    c4_wl[b][0] += 1
                    c4_wl_cls[key] += 1
                elif pred is not None:
                    c4_tabled[key] += 1
                else:
                    c4_unmined[key] += 1
            elif cls == "R4":
                r4_i[i].add(b)
            else:
                other[cls].add(b)
    return dict(c4_all=c4_all, c4_wl=c4_wl, c4_i0=c4_i0,
                c4_unmined=c4_unmined, c4_tabled=c4_tabled,
                c4_wl_cls=c4_wl_cls, other=other, r4_i=r4_i)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", type=Path, default=DEFAULT_FIT)
    ap.add_argument("--sta", type=Path, default=DEFAULT_STA)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    for p, what in ((a.fit, "fit report"), (a.sta, "STA report")):
        if not p.exists():
            print(f"MISSING {what}: {p}")
            if p is a.sta:
                print("  regenerate: cd ~/see_neorv32_run_linux/quartus && "
                      "quartus_sta -t "
                      f"{REPO}/scripts/routing_model/step0b_routing_census.tcl")
            return 1

    totals = step0b.parse_fit_totals(a.fit)
    grand = sum(totals.values())
    table, src = gate.load_c4_table()
    whitelist, _ = proto.load_whitelist()   # returns (whitelist, table)
    print(f"C4 table: {src}  ({len(table)} classes, "
          f"{len(whitelist)} whitelisted for emission)")
    print(f"gate criteria: cell_rate >= {proto.CELL_RATE_MIN}, "
          f"cell_tot >= {proto.CELL_TOT_MIN}, non-ambiguous, family A only\n")

    d = classify(a.sta, table, whitelist)

    # ---- C4 -----------------------------------------------------------
    c4_tot = totals.get("C4 interconnects", 0)
    n_c4 = len(d["c4_all"])
    n_i0 = len(d["c4_i0"])
    strict = sum(1 for w, (wl, tot) in d["c4_wl"].items() if tot and wl == tot)
    opt = sum(1 for w, (wl, _) in d["c4_wl"].items() if wl)
    before_frac = n_i0 / n_c4 if n_c4 else 0
    strict_frac = (n_i0 + strict) / n_c4 if n_c4 else 0
    opt_frac = (n_i0 + opt) / n_c4 if n_c4 else 0

    print("=== C4 (the class STEP 0b wrote off entirely) ===")
    print(f"  distinct C4 wires sampled : {n_c4}")
    print(f"    I=0 (formula, emittable): {n_i0}")
    print(f"    I!=0 with >=1 modelled pip: {len(d['c4_wl'])}")
    print(f"      all driver-pips whitelisted (STRICT): {strict}")
    print(f"      >=1 driver-pip whitelisted (OPTIMISTIC): {opt}")
    print(f"  emittable fraction  BEFORE (I=0 only) : {100*before_frac:5.1f}%")
    print(f"                      AFTER  (STRICT)   : {100*strict_frac:5.1f}%")
    print(f"                      AFTER  (OPTIMISTIC): {100*opt_frac:5.1f}%")
    print(f"  -> projected on fit total {c4_tot}: "
          f"{round(c4_tot*before_frac)} -> {round(c4_tot*strict_frac)} emittable "
          f"(STRICT), gap {c4_tot-round(c4_tot*strict_frac)}")
    print(f"  unmined classes seen: {len(d['c4_unmined'])} "
          f"({sum(d['c4_unmined'].values())} pip-occ)")
    print(f"  mined-but-not-whitelisted: {len(d['c4_tabled'])} classes "
          f"({sum(d['c4_tabled'].values())} pip-occ)")
    print("  top unmined C4 classes by demand:")
    for k, c in d["c4_unmined"].most_common(8):
        print(f"     {c:6d}  {gate.class_name(k)}")
    print("  top mined-but-withheld classes by demand:")
    for k, c in d["c4_tabled"].most_common(6):
        print(f"     {c:6d}  {gate.class_name(k)}")

    # ---- demand-ranked mining plan ------------------------------------
    seen = collections.Counter()
    seen.update(d["c4_unmined"])
    seen.update(d["c4_tabled"])
    c4_occ = sum(seen.values())
    print("\n=== C4 mining plan, ranked by NEORV32 demand ===")
    print(f"  {c4_occ} modelled pip-occurrences over {len(seen)} classes")
    print(f"  {'rank':>4}{'occ':>7}{'cum%':>7}  status   class")
    cum = 0
    for rank, (k, c) in enumerate(seen.most_common(12), 1):
        cum += c
        st = "TABLED" if k in d["c4_tabled"] else "unmined"
        print(f"  {rank:>4}{c:>7}{100*cum/c4_occ:>6.1f}%  {st:<8} {gate.class_name(k)}")
    for n in (1, 2, 3, 5, 10, 20):
        cum = sum(c for _, c in seen.most_common(n))
        print(f"    top {n:>2} classes -> {100*cum/c4_occ:5.1f}% of C4 pip demand")
    t_occ = sum(d["c4_tabled"].values())
    print(f"  ALREADY IN TABLE, withheld only by the gate: {t_occ} occ "
          f"({100*t_occ/c4_occ:.0f}% of C4 demand) over {len(d['c4_tabled'])} "
          "classes\n  -> these need mining DIVERSITY (Y-group treatment), not new physics.")

    # ---- R4 -----------------------------------------------------------
    r4_tot = totals.get("R4 interconnects", 0)
    r4_all = sum(len(v) for v in d["r4_i"].values())
    r4_ok = sum(len(v) for i, v in d["r4_i"].items() if i in R4_REAL)
    r4_frac = r4_ok / r4_all if r4_all else 0
    print(f"\n=== R4 ({len(R4_REAL)}-key _R4_BASE_PREV, read live) ===")
    print(f"  distinct wires {r4_all}, emittable {r4_ok} ({100*r4_frac:.0f}%)")
    print(f"  -> projected on fit total {r4_tot}: {round(r4_tot*r4_frac)} "
          f"emittable, gap {r4_tot-round(r4_tot*r4_frac)}")
    miss = sorted((i for i in d["r4_i"] if i not in R4_REAL),
                  key=lambda i: -len(d["r4_i"][i]))
    print("  unmined I by distinct-wire demand: "
          + ", ".join(f"I={i}({len(d['r4_i'][i])})" for i in miss[:10]))

    # ---- roll-up ------------------------------------------------------
    dead = (totals.get("R24 interconnects", 0) + totals.get("C16 interconnects", 0)
            + totals.get("Direct links", 0))
    li = totals.get("Block interconnects", 0) + totals.get("Local interconnects", 0)
    before_emit = li + round(c4_tot*before_frac) + round(r4_tot*r4_frac)
    after_emit = li + round(c4_tot*strict_frac) + round(r4_tot*r4_frac)
    print("\n" + "=" * 74)
    print("VERDICT — NEORV32 routing wires emittable by the LIVE model")
    print("=" * 74)
    print(f"  total routing wires (fit.rpt): {grand}")
    print(f"  BEFORE (STEP 0b premise, C4 = I=0 only): "
          f"{before_emit} ({100*before_emit/grand:.0f}%) emittable, "
          f"gap {grand-before_emit} ({100*(grand-before_emit)/grand:.0f}%)")
    print(f"  AFTER  (live C4 whitelist, STRICT):      "
          f"{after_emit} ({100*after_emit/grand:.0f}%) emittable, "
          f"gap {grand-after_emit} ({100*(grand-after_emit)/grand:.0f}%)")
    print(f"  movement: {after_emit-before_emit:+d} wires "
          f"({100*(after_emit-before_emit)/grand:+.1f} pts)")
    print("\n  remaining gap by class (STRICT):")
    for name, v in (("C4 I!=0 not whitelisted", c4_tot-round(c4_tot*strict_frac)),
                    ("R4 unmined I", r4_tot-round(r4_tot*r4_frac)),
                    ("Direct links (UNMODELED)", totals.get("Direct links", 0)),
                    ("R24 (CRC-dead)", totals.get("R24 interconnects", 0)),
                    ("C16 (UNMODELED)", totals.get("C16 interconnects", 0))):
        print(f"    {name:<28}{v:>6}  ({100*v/grand:4.1f}% of all wires)")
    print("\n  NOTE: 'emittable' here means the write model produces cells the"
          "\n  gate trusts (fresh-gold byte-identity evidence). It is NOT a"
          "\n  silicon claim and NOT a completeness claim for a whole route.")

    if a.json:
        out = REPO / "results" / "step0c_emittable_demand.json"
        out.write_text(json.dumps({
            "fit_totals": totals, "grand": grand,
            "c4": {"sampled": n_c4, "i0": n_i0, "strict": strict,
                   "optimistic": opt, "before_frac": before_frac,
                   "strict_frac": strict_frac, "opt_frac": opt_frac},
            "r4": {"sampled": r4_all, "emittable": r4_ok, "frac": r4_frac,
                   "unmined_I": {str(i): len(d["r4_i"][i]) for i in miss}},
            "before_emit": before_emit, "after_emit": after_emit,
            "unmined_c4_classes": {gate.class_name(k): c
                                   for k, c in d["c4_unmined"].most_common()},
            "withheld_c4_classes": {gate.class_name(k): c
                                    for k, c in d["c4_tabled"].most_common()},
        }, indent=1))
        print(f"\n[json] {out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
