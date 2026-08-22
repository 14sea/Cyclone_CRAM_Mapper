#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""COMPLETE routing census from a Quartus back-annotated .rcf.

Why this exists: STEP 0b and the first cut of STEP 0c both estimated route
demand from a `report_timing -show_routing` sample.  That sample is
near-critical-path biased and, for NEORV32, covered only ~3.5% of the design's
C4 wires -- far too thin to rank route classes, and it counts a wire once per
critical path it happens to lie on (so a single hot wire can masquerade as
thousands of "occurrences").

A back-annotated Routing Constraints File has no such problem: it records the
FULL routing tree of EVERY net.  Produce one with

    cp -r <quartus project> <scratch copy>          # back-annotation rewrites
    cd <scratch copy>                               # the .qsf -- use a COPY
    quartus_cdb <rev> -c <rev> --back_annotate=routing

.rcf wire syntax is `TYPE:X<x>Y<y>S<n>I<i>`, equivalent to the STA report's
`TYPE_X<x>_Y<y>_N<n>_I<i>`; this module normalises to the STA spelling so the
existing predictors (pip_prediction_gate) accept it unchanged.

Net structure:
    signal_name = <net> {
        <wire>;                       -- driver-side chain
        label = Label_<w>, <w>;       -- names a fan-out point
        dest = ( <node>, <port> );    -- terminates the branch
        branch_point = Label_<w>;     -- next branch resumes from <w>
        ...
    }
A pip is a consecutive (wire -> wire) pair *within one branch*.
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

WIRE_RCF = re.compile(
    r'\b(C4|R4|R24|C16|LOCAL_INTERCONNECT|LOCAL_LINE|LE_BUFFER|DIRECT_LINK'
    r'|BLOCK_INPUT_MUX):X(\d+)Y(\d+)S(\d+)I(\d+)\b')
LABEL_DEF = re.compile(r'^\s*label\s*=\s*(Label_\S+?),\s*(\S+?);')
BRANCH = re.compile(r'^\s*branch_point\s*=\s*(Label_\S+?);')


def norm(m: re.Match) -> str:
    """.rcf wire match -> STA spelling."""
    return f"{m.group(1)}_X{m.group(2)}_Y{m.group(3)}_N{m.group(4)}_I{m.group(5)}"


def parse_rcf(path: Path):
    """Yield (net_name, branch_wire_sequence) for every branch of every net."""
    net = None
    labels: dict[str, str] = {}
    seq: list[str] = []
    with open(path, errors="replace") as f:
        for line in f:
            if line.startswith("signal_name"):
                if seq:
                    yield net, seq
                net = line.split("=", 1)[1].strip().rstrip("{").strip()
                labels, seq = {}, []
                continue
            if line.startswith("}"):
                if seq:
                    yield net, seq
                seq = []
                continue

            mb = BRANCH.match(line)
            if mb:
                if seq:
                    yield net, seq
                w = labels.get(mb.group(1))
                seq = [w] if w else []
                continue

            ml = LABEL_DEF.match(line)
            if ml:
                mw = WIRE_RCF.search(ml.group(2))
                if mw:
                    w = norm(mw)
                    labels[ml.group(1)] = w
                    if not seq or seq[-1] != w:
                        seq.append(w)
                continue

            if "dest" in line:
                if seq:
                    yield net, seq
                seq = []          # a dest terminates the branch
                continue

            mw = WIRE_RCF.search(line)
            if mw:
                w = norm(mw)
                if not seq or seq[-1] != w:
                    seq.append(w)
    if seq:
        yield net, seq


def census(path: Path):
    """Return (distinct wires per class, pip set, per-wire driver-pip map)."""
    wires = collections.defaultdict(set)
    pips = set()
    drivers = collections.defaultdict(set)   # wire -> {predecessor wire}
    nets = set()
    for net, seq in parse_rcf(path):
        nets.add(net)
        for w in seq:
            wires[w.split("_X", 1)[0]].add(w)
        for a, b in zip(seq, seq[1:]):
            pips.add((a, b))
            drivers[b].add(a)
    return wires, pips, drivers, nets


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rcf", type=Path, nargs="?",
                    default=REPO / "tmp" / "nv_ba" / "neorv32_demo.rcf")
    ap.add_argument("--fit", type=Path,
                    default=REPO / "tmp" / "nv_ba" / "neorv32_demo.fit.rpt")
    a = ap.parse_args()
    if not a.rcf.exists():
        print(f"missing {a.rcf} — see module docstring for how to generate it")
        return 1

    wires, pips, drivers, nets = census(a.rcf)
    print(f"nets: {len(nets)}   pips: {len(pips)}\n")
    print(f"{'class':<22}{'distinct (rcf)':>15}{'fit.rpt':>10}{'delta':>8}")
    print("-" * 55)
    fit = {}
    if a.fit.exists():
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import step0b_route_demand as s0b
        fit = s0b.parse_fit_totals(a.fit)
    NAME = {"C4": "C4 interconnects", "R4": "R4 interconnects",
            "R24": "R24 interconnects", "C16": "C16 interconnects",
            "LOCAL_INTERCONNECT": "Local interconnects",
            "BLOCK_INPUT_MUX": "Block interconnects",
            "DIRECT_LINK": "Direct links"}
    for cls in sorted(wires, key=lambda c: -len(wires[c])):
        f = fit.get(NAME.get(cls, ""), None)
        d = "" if f is None else f"{len(wires[cls]) - f:+d}"
        print(f"{cls:<22}{len(wires[cls]):>15}{('-' if f is None else f):>10}{d:>8}")
    print("\n(LE_BUFFER / LOCAL_LINE are node-side, not counted by the fit"
          "\n Routing Usage Summary; a 0 delta on C4/R4/R24/C16 validates the parse.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
