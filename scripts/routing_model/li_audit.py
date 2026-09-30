#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""LI audit — is NEORV32's local-interconnect demand emittable by the codec?

STEP 0b/0c counted every LOCAL_INTERCONNECT + LOCAL_LINE wire (9483 = 50.6%
of NEORV32 routing) as "emittable" on an inherited assumption.  This tool
checks that assumption against the complete back-annotated .rcf and the
Quartus gold RBF of the SAME compile.

LI configuration a design actually needs (from the .rcf):
  (a) LAB-line driver MUX  : one per LOCAL_INTERCONNECT wire with a driver pip
                             (C4 / R4 / R24 / C16 / LE_BUFFER -> LI).
  (b) LE input MUX         : one per (dest LE, physical route_port) fed from a
                             LOCAL_INTERCONNECT or LOCAL_LINE wire.
  LOCAL_LINE wires have no driver pip (LE output, hard-wired) -> no config of
  their own; they cost only (b).

What the codec can write (`RouteCodec.write_local_interconnect`): 18 fixed
cells per LAB (9 frame-pairs x base 70/71), addressed by EXPLICIT
(pair, base) — there is no function from an LI wire, a driver pip, or an
(LE, port) sink to cells.  So "emittable per wire" is structurally 0; the
checks below measure whether the codec's 18-cell domain even tracks LI use.

Inputs default to tmp/nv_ba (see rcf_route_census docstring); the RBF is
`quartus_cpf -c -o bitstream_compression=off neorv32_demo.sof neorv32_demo.rbf`.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bitstream as B                      # noqa: E402
import rcf_route_census as rc             # noqa: E402

NV = REPO / "tmp" / "nv_ba"
LOC = re.compile(r'set_location_assignment (LCCOMB|FF)_X(\d+)_Y(\d+)_N(\d+)'
                 r' -to "(.*)"$')
DEST = re.compile(r'dest = \( (.*), (\w+) \), route_port = (\w+);')
XY = re.compile(r'\w+?_X(\d+)_Y(\d+)')


def placement(qsf: Path):
    """(kind, cell name) -> (x, y, n) from a back-annotated .qsf."""
    p = {}
    for line in open(qsf, errors="replace"):
        m = LOC.match(line.strip())
        if m:
            p[(m.group(1), m.group(5).replace("\\\\", "\\"))] = tuple(
                int(m.group(i)) for i in (2, 3, 4))
    return p


def sinks(rcf: Path):
    """Yield (feeding wire, dest cell, logical port, route_port) per dest."""
    last, labels = None, {}
    for line in open(rcf, errors="replace"):
        if line.startswith("signal_name"):
            last, labels = None, {}
            continue
        mb = rc.BRANCH.match(line)
        if mb:
            last = labels.get(mb.group(1))
            continue
        ml = rc.LABEL_DEF.match(line)
        if ml:
            mw = rc.WIRE_RCF.search(ml.group(2))
            if mw:
                last = labels[ml.group(1)] = rc.norm(mw)
            continue
        md = DEST.search(line)
        if md:
            yield last, md.group(1), md.group(2), md.group(3)
            last = None
            continue
        mw = rc.WIRE_RCF.search(line)
        if mw:
            last = rc.norm(mw)


def xy(w):
    return tuple(map(int, XY.match(w).groups()))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rcf", type=Path, default=NV / "neorv32_demo.rcf")
    ap.add_argument("--qsf", type=Path, default=NV / "neorv32_demo.qsf")
    ap.add_argument("--rbf", type=Path, default=NV / "neorv32_demo.rbf")
    ap.add_argument("--zero", type=Path,
                    default=REPO / "results" / "rbf" / "nv_zero_global.rbf")
    ap.add_argument("--hw-rbf", type=Path,
                    default=REPO / "tmp" / "neorv32_zeta" / "neorv32_open.rbf",
                    help="silicon-validated NEORV32 build (Linux-booted)")
    a = ap.parse_args()
    for f in (a.rcf, a.qsf, a.rbf, a.zero):
        if not f.exists():
            print(f"missing {f}")
            return 1

    wires, _pips, drivers, _nets = rc.census(a.rcf)
    li, ll = wires["LOCAL_INTERCONNECT"], wires["LOCAL_LINE"]
    gold, zero = a.rbf.read_bytes(), a.zero.read_bytes()
    codec = B.RouteCodec()
    dom = {(x, y) for x in B.LAB_X if x in B.COLUMN_BASE for y in B.LAB_Y}

    # ---- demand ------------------------------------------------------------
    drv_cls = collections.Counter(
        next(iter(drivers[w])).split("_X")[0] for w in li if drivers.get(w))
    n_drv = sum(drv_cls.values())
    ll_driven = sum(1 for w in ll if drivers.get(w))
    P = placement(a.qsf)
    sink_sel = set()                       # (x, y, n, route_port, src class)
    per_lab = collections.defaultdict(lambda: [0, set()])
    for w in li:
        if drivers.get(w):
            per_lab[xy(w)][0] += 1
    for w, cell, _lp, rp in sinks(a.rcf):
        loc = P.get(("LCCOMB", cell)) or P.get(("FF", cell))
        if not w or not loc or not w.startswith(("LOCAL_INTERCONNECT",
                                                  "LOCAL_LINE")):
            continue
        sink_sel.add((*loc, rp))
        per_lab[loc[:2]][1].add((loc[2], rp))
    out_dom = sum(1 for w in li | ll if xy(w) not in dom)

    # ---- codec domain vs gold ---------------------------------------------
    act = collections.Counter()
    for name, *_ in codec.read_local_interconnect(gold, zero):
        lx, ly, *_ = codec._parse_li_name(name)
        act[(lx, ly)] += 1
    used = sorted(l for l in dom if l in per_lab)
    demand = {l: per_lab[l][0] + len(per_lab[l][1]) for l in used}
    corr = st.correlation([per_lab[l][0] for l in used],
                          [act[l] for l in used])
    zero_act = sum(1 for l in used if not act[l])
    over = sum(1 for l in used if demand[l] > 18)
    viol = {"gold": len(codec.validate_safe_for_hardware(
        gold, zero, raise_on_fail=False))}
    if a.hw_rbf.exists():
        viol["hw_validated"] = len(codec.validate_safe_for_hardware(
            a.hw_rbf.read_bytes(), zero, raise_on_fail=False))

    total = n_drv + len(sink_sel)
    print(f"LI wires (LOCAL_INTERCONNECT) {len(li)}, LOCAL_LINE {len(ll)} "
          f"(driver pips on LOCAL_LINE: {ll_driven})")
    print(f"  outside codec LAB domain (CE10 cols/rows, edges): {out_dom}")
    print(f"\nLI CONFIG DEMAND = {total} MUX selections")
    print(f"  (a) LAB-line driver MUX : {n_drv}  "
          + ", ".join(f"{k}={v}" for k, v in drv_cls.most_common()))
    print(f"  (b) LE input MUX        : {len(sink_sel)}  distinct (LE, port)")
    print(f"\nCODEC LI WRITE MODEL: 18 cells/LAB, explicit (pair, base) only")
    print(f"  wire/pip/sink -> cells function        : NONE")
    print(f"  per-wire emittable                     : 0 / {len(li)+len(ll)}")
    print(f"  in-domain LABs using LI                : {len(used)}")
    print(f"    mean demand/LAB {st.mean(demand.values()):.1f} selections vs "
          f"18 cells; {over}/{len(used)} LABs exceed 18 (pigeonhole)")
    print(f"    corr(#LI wires, #active codec cells) : {corr:.3f}")
    print(f"    LI-using LABs with 0 active cells    : {zero_act}/{len(used)}")
    print(f"  validate_safe_for_hardware violations  : "
          + ", ".join(f"{k}={v}" for k, v in viol.items()))
    print("\nVERDICT: the 9483 LI wires are NOT emittable by the live model."
          "\n  Native LI cells exist only inside whole-route sig-cache blobs"
          "\n  (context-dependent, Pitfall #14).  The ~70% headline drops to"
          f"\n  ~{(13121 - len(li) - len(ll)) / 18735 * 100:.0f}% of wires "
          "(C4/R4/R24/C16 only), and LI demand is the largest single gap.")

    res = {
        "rcf": str(a.rcf), "rbf": str(a.rbf),
        "li_wires": len(li), "local_line_wires": len(ll),
        "out_of_domain_wires": out_dom,
        "demand": {"driver_mux": n_drv, "driver_classes": dict(drv_cls),
                   "le_input_mux": len(sink_sel), "total": total},
        "codec": {"cells_per_lab": 18, "labs_in_domain_used": len(used),
                  "mean_demand_per_lab": round(st.mean(demand.values()), 1),
                  "labs_over_18": over, "corr_li_vs_active": round(corr, 3),
                  "labs_zero_active": zero_act,
                  "active_cells_gold": sum(act.values())},
        "validator_violations": viol,
        "emittable_per_wire": 0,
        "rollup_wires_after": 13121 - len(li) - len(ll), "grand": 18735,
    }
    (REPO / "results" / "li_audit.json").write_text(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
