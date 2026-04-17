# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage C.1 — populate `cells_by_template["inferred"]` for all anchors.

Re-mine every anchor in `results/m9k_mode_bits.json` against the *verbatim
inferred-RAM* Verilog idiom (the construct Yosys's `memory_libmap` →
`$__M9K_SP_` → `EP4CE6_M9K` techmap corresponds to on the user-source
side).  Use the shared specimen-factory harness from Stage 2(a).D so
per-site diffs cancel harness/placement drift.

Outcome:

  * Per-anchor MODE cell set under the inferred-style specimen.
  * Universal intersection across all anchors (the "inferred-equivalent"
    of DSPMULT's 23-cell universal core).
  * Per-Y N-invariance histogram (currently all anchors are N=0, so
    this just records the cell-count distribution).
  * Sym_gap at X15_Y10_N0 width=9 vs smoke-gold (Quartus inferred RAM
    reference).

This probe is a re-mine — it does NOT decide whether np2fasm emission
gets ungated.  Gating stays on the sym_gap acceptance criterion.

Parallel Pool pattern follows `fuzz/clk_lab_sel_n2_batch.py`.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from specimen_base import Harness
from m9k_mode_remine_w9 import (
    BLOCK_FRAME_LO,
    BLOCK_FRAME_HI,
    PREAMBLE,
    FRAME,
    M9kSpecimen,
    _block_band_cells,
)


WORK_ROOT = ROOT / "tmp" / "m9k_mode_inferred_full"
RESULTS_PATH = ROOT / "results" / "m9k_mode_bits.json"
PROBE_OUT = ROOT / "results" / "m9k_mode_inferred_full_remine.json"
SMOKE_GOLD = ROOT / "tmp" / "m9k_smoke" / "ram_9x512.rbf"


# Wide harness — 18 DIN + 18 DOUT pins.  Width=9 specimens tie the
# upper 9 bits internally (DIN18..DIN9 unused, DOUT18..DOUT9 grounded),
# width=18 specimens use all 18.  Same harness for both → one shared
# baseline per (width, depth).
#
# PIN_MAP is lifted from the smoke gold's ram_9x512.qsf for the first
# 9 DIN/DOUT pins; the additional 9 DIN/DOUT pins pick from the remaining
# free F17 pins (avoiding dedicated-clock pins and the JTAG/CONFIG bank).
WIDE_PIN_MAP = {
    "CLK":    "PIN_E1",
    "WE":     "PIN_M15",
    "ADDR0":  "PIN_E15",
    "ADDR1":  "PIN_E16",
    "ADDR2":  "PIN_M16",
    "ADDR3":  "PIN_A8",
    "ADDR4":  "PIN_A11",
    "ADDR5":  "PIN_A14",
    "ADDR6":  "PIN_B14",
    "ADDR7":  "PIN_T2",
    "ADDR8":  "PIN_T8",
    "DIN0":   "PIN_R1",
    "DIN1":   "PIN_R5",
    "DIN2":   "PIN_R9",
    "DIN3":   "PIN_R13",
    "DIN4":   "PIN_R16",
    "DIN5":   "PIN_P1",
    "DIN6":   "PIN_P9",
    "DIN7":   "PIN_P15",
    "DIN8":   "PIN_T13",
    "DIN9":   "PIN_T3",
    "DIN10":  "PIN_T7",
    "DIN11":  "PIN_T12",
    "DIN12":  "PIN_T15",
    "DIN13":  "PIN_P3",
    "DIN14":  "PIN_P11",
    "DIN15":  "PIN_P16",
    "DIN16":  "PIN_N2",
    "DIN17":  "PIN_N14",
    "DOUT0":  "PIN_G15",
    "DOUT1":  "PIN_F15",
    "DOUT2":  "PIN_B16",
    "DOUT3":  "PIN_G16",
    "DOUT4":  "PIN_K15",
    "DOUT5":  "PIN_K16",
    "DOUT6":  "PIN_L15",
    "DOUT7":  "PIN_L16",
    "DOUT8":  "PIN_N16",
    "DOUT9":  "PIN_D16",
    "DOUT10": "PIN_D15",
    "DOUT11": "PIN_C15",
    "DOUT12": "PIN_C16",
    "DOUT13": "PIN_F14",
    "DOUT14": "PIN_F16",
    "DOUT15": "PIN_J14",
    "DOUT16": "PIN_J15",
    "DOUT17": "PIN_J16",
}


def _make_harness(width: int) -> Harness:
    """Return the mining harness for the given data width.

    Width=9 uses the narrow pin subset (matches smoke gold 1:1).
    Width=18 uses the wide pin subset.  Both use the SAME IOB prefix
    so the 9-bit case shares ADDR/CLK/WE pins with the smoke gold.

    We do NOT disable QSF_OPTIMIZATIONS here — the smoke-gold QSF has
    them at defaults, and the probe (`m9k_mode_template_probe.py`)
    showed stripping them is the closer match to the gold's harness.
    """
    if width == 9:
        # Same 29-pin subset as m9k_mode_remine_w9.PIN_MAP.
        pins = {k: v for k, v in WIDE_PIN_MAP.items()
                if not (k.startswith("DIN") and int(k[3:]) >= 9)
                and not (k.startswith("DOUT") and int(k[4:]) >= 9)}
        name = "m9k_infer_w9"
    elif width == 18:
        pins = dict(WIDE_PIN_MAP)
        name = "m9k_infer_w18"
    else:
        raise ValueError(f"unsupported width {width}")
    return Harness(
        iob_pins=tuple(pins.items()),
        clk_signal="CLK",
        seed=1,
        name=name,
        # Match the probe's `_make_harness_ram_inference`: leave all
        # optimizations at Quartus defaults so AUTO_RAM_RECOGNITION is
        # ON (otherwise inferred RAM falls back to distributed LUTs).
        optimizations_off=(),
    )


def _port_decl(width: int, addr_bits: int = 9) -> str:
    parts = ["input CLK", "input WE"]
    parts += [f"input ADDR{i}" for i in range(addr_bits)]
    parts += [f"input DIN{i}" for i in range(width)]
    parts += [f"output DOUT{i}" for i in range(width)]
    return ",\n    ".join(parts)


def verilog_inferred_ram(width: int, depth: int) -> str:
    """Verbatim inferred-RAM idiom: (* ramstyle = "M9K" *) reg array +
    sync write + sync read (registered DOUT).  Matches the smoke gold's
    `ram_9x512.v` structure.  Parametric over width/depth.
    """
    addr_bits = 9  # all current anchors use depth=512
    addr_bus = ", ".join(f"ADDR{i}" for i in range(addr_bits - 1, -1, -1))
    din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
    dout_bus = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
    return f"""\
module fuzz_top(
    {_port_decl(width, addr_bits)}
);
    wire [{addr_bits-1}:0] addr = {{{addr_bus}}};
    wire [{width-1}:0]     din  = {{{din_bus}}};
    reg  [{width-1}:0]     dout_r;
    assign {{{dout_bus}}} = dout_r;

    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    integer i;
    initial begin
        for (i = 0; i < {depth}; i = i + 1)
            mem[i] = i[{width-1}:0] ^ {width}'h1A5;
    end
    always @(posedge CLK) begin
        if (WE) mem[addr] <= din;
        dout_r <= mem[addr];
    end
endmodule
"""


def verilog_baseline(width: int) -> str:
    """Pass-through baseline — SAME harness, NO M9K.  Paired diff."""
    parts = [f"    assign DOUT{i} = DIN{i};" for i in range(width)]
    body = "\n".join(parts)
    return f"""\
module fuzz_top(
    {_port_decl(width)}
);
{body}
endmodule
"""


def _baseline_spec(width: int) -> M9kSpecimen:
    h = _make_harness(width)
    return M9kSpecimen(
        m9k_loc=None,
        init_mif=False,
        name=f"m9k_infer_w{width}_baseline",
        harness=h,
        verilog=verilog_baseline(width),
        placement={},
    )


def _site_spec(x: int, y: int, width: int, depth: int) -> M9kSpecimen:
    h = _make_harness(width)
    return M9kSpecimen(
        m9k_loc=f"M9K_X{x}_Y{y}_N0",
        init_mif=False,
        name=f"m9k_infer_w{width}d{depth}_X{x}_Y{y}",
        harness=h,
        verilog=verilog_inferred_ram(width, depth),
        placement={},
    )


def _build_or_reuse(spec: M9kSpecimen, work: Path) -> Path:
    rbf_path = work / f"{spec.project_name()}.rbf"
    if rbf_path.exists():
        return rbf_path
    return spec.build(work)


def _anchor_key(x: int, y: int, width: int, depth: int) -> str:
    return f"X{x}_Y{y}_N0_{width}x{depth}"


def load_anchors() -> list[tuple[int, int, int, int]]:
    d = json.loads(RESULTS_PATH.read_text())
    out = []
    for key, entry in d.items():
        site = entry["site"]  # e.g. "X15_Y10_N0"
        sx, sy, _sn = site.split("_")
        x = int(sx[1:]); y = int(sy[1:])
        out.append((x, y, int(entry["width"]), int(entry["depth"])))
    return out


def _build_baseline_job(width: int):
    """Pool-friendly closure for building a baseline RBF."""
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    spec = _baseline_spec(width)
    t0 = time.time()
    rbf = _build_or_reuse(spec, WORK_ROOT)
    return width, str(rbf), time.time() - t0


def _build_site_job(args):
    """Pool-friendly closure for building a per-site RBF.

    args = (x, y, width, depth)
    """
    x, y, width, depth = args
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    spec = _site_spec(x, y, width, depth)
    t0 = time.time()
    try:
        rbf = _build_or_reuse(spec, WORK_ROOT)
        return (x, y, width, depth, str(rbf), None, time.time() - t0)
    except Exception as exc:
        return (x, y, width, depth, None, repr(exc), time.time() - t0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only-analyze", action="store_true",
                    help="skip builds; re-analyze existing RBFs")
    ap.add_argument("--widths", type=str, default="9,18",
                    help="comma-separated widths to process (e.g. '9' or '9,18')")
    args = ap.parse_args()

    wanted = {int(w.strip()) for w in args.widths.split(",") if w.strip()}
    anchors = [a for a in load_anchors() if a[2] in wanted]
    print(f"[remine] {len(anchors)} anchors (widths={sorted(wanted)}) from {RESULTS_PATH.name}")
    widths = sorted(set(w for _, _, w, _ in anchors))
    print(f"[remine] widths: {widths}")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    # Step 1 — build baselines (one per width).  Serial; only 2 of them.
    baseline_rbf: dict[int, Path] = {}
    if not args.only_analyze:
        for w in widths:
            print(f"[remine] building baseline w={w} …", flush=True)
            _w, rbf_str, elapsed = _build_baseline_job(w)
            baseline_rbf[w] = Path(rbf_str)
            print(f"  -> {Path(rbf_str).name}  ({elapsed:.1f}s)", flush=True)
    else:
        for w in widths:
            spec = _baseline_spec(w)
            rbf = WORK_ROOT / f"{spec.project_name()}.rbf"
            baseline_rbf[w] = rbf

    # Step 2 — build every per-site specimen in parallel.
    todo = list(anchors)
    if not args.only_analyze:
        print(f"\n[remine] building {len(todo)} per-site specimens "
              f"(workers={args.workers})", flush=True)
        with mp.Pool(processes=max(1, args.workers)) as pool:
            results = list(pool.imap_unordered(_build_site_job, todo))
        # Fail fast on first error, but report all.
        errors = [r for r in results if r[5] is not None]
        for x, y, w, d, _rbf, err, _el in errors:
            print(f"  FAIL X{x}_Y{y} {w}x{d}: {err}", flush=True)
        if errors:
            print(f"[remine] {len(errors)} build(s) failed; aborting")
            return 1
        for x, y, w, d, rbf, _err, el in sorted(
                results, key=lambda r: (r[2], r[0], r[1])):
            print(f"  OK   X{x:>2}_Y{y:<2} {w}x{d}  ({el:.1f}s)", flush=True)
    else:
        print("[remine] --only-analyze: skipping builds")

    # Step 3 — extract MODE cells per anchor via same-baseline block-band diff.
    per_anchor: dict[str, set[tuple[int, int]]] = {}
    per_anchor_meta: dict[str, dict] = {}
    for x, y, w, d in anchors:
        key = _anchor_key(x, y, w, d)
        spec = _site_spec(x, y, w, d)
        rbf_path = WORK_ROOT / f"{spec.project_name()}.rbf"
        if not rbf_path.exists():
            print(f"[remine] missing RBF for {key}: {rbf_path}")
            return 1
        bl_path = baseline_rbf[w]
        mode_cells = _block_band_cells(
            bl_path.read_bytes(), rbf_path.read_bytes(),
        )
        per_anchor[key] = mode_cells
        per_anchor_meta[key] = {
            "site": f"X{x}_Y{y}_N0",
            "width": w,
            "depth": d,
            "rbf": rbf_path.name,
            "baseline_rbf": bl_path.name,
            "cell_count": len(mode_cells),
        }
        print(f"  {key}: {len(mode_cells)} cells", flush=True)

    # Step 4 — aggregate stats.
    by_wd: dict[tuple[int, int], list[set[tuple[int, int]]]] = {}
    for (x, y, w, d), k in zip(anchors, [_anchor_key(*a) for a in anchors]):
        by_wd.setdefault((w, d), []).append(per_anchor[k])

    universal_by_wd: dict[str, list] = {}
    for wd, sets in by_wd.items():
        u = set.intersection(*sets) if sets else set()
        universal_by_wd[f"{wd[0]}x{wd[1]}"] = sorted(u)
        print(f"\n[remine] (w={wd[0]}, d={wd[1]}) universal intersection "
              f"across {len(sets)} anchors: {len(u)} cells")
        counts = [len(s) for s in sets]
        print(f"  cell counts min/median/max: "
              f"{min(counts)}/{sorted(counts)[len(counts)//2]}/{max(counts)}")

    # Global universal across ALL anchors (all widths).
    all_sets = [per_anchor[k] for k in per_anchor]
    global_universal = set.intersection(*all_sets) if all_sets else set()
    print(f"\n[remine] global universal across all {len(all_sets)} anchors: "
          f"{len(global_universal)} cells")

    # N-invariance: all anchors are N=0, so this is just a cell-count
    # histogram per Y.  Record it for completeness.
    per_y_counts: dict[int, list[int]] = {}
    for (x, y, w, d), k in zip(anchors, [_anchor_key(*a) for a in anchors]):
        per_y_counts.setdefault(y, []).append(len(per_anchor[k]))

    # Step 5 — sym_gap at X15_Y10_N0 width=9 vs smoke gold.
    #
    # The smoke gold was built under a slightly different harness
    # (smoke's QSF, no specimen factory wrapper), so this diff is
    # apples-to-oranges — but it's the comparison the plan asks for.
    gap_entry = ("X15_Y10_N0_9x512", )[0]
    sym_gap = None
    if SMOKE_GOLD.exists() and gap_entry in per_anchor:
        bl = baseline_rbf[9].read_bytes()
        gold_mode = _block_band_cells(bl, SMOKE_GOLD.read_bytes())
        our_mode = per_anchor[gap_entry]
        inter = our_mode & gold_mode
        gap = len(our_mode ^ gold_mode)
        sym_gap = gap
        print(f"\n[remine] X15_Y10_N0 w=9 inferred ({len(our_mode)}) vs "
              f"smoke gold ({len(gold_mode)}): match={len(inter)} sym_gap={gap}")

    # Step 6 — persist everything.
    payload = {
        "anchors": [
            {
                **per_anchor_meta[_anchor_key(*a)],
                "cells": sorted(per_anchor[_anchor_key(*a)]),
            }
            for a in anchors
        ],
        "universal_by_wd": universal_by_wd,
        "global_universal_count": len(global_universal),
        "global_universal_cells": sorted(global_universal),
        "per_y_cell_counts": {str(y): v for y, v in per_y_counts.items()},
        "x15_y10_w9_vs_smoke_gold_sym_gap": sym_gap,
        "harness": {
            "w9_pins": len([k for k in WIDE_PIN_MAP
                            if not (k.startswith("DIN") and int(k[3:]) >= 9)
                            and not (k.startswith("DOUT") and int(k[4:]) >= 9)]),
            "w18_pins": len(WIDE_PIN_MAP),
            "seed": 1,
            "optimizations_off": "",
        },
    }
    PROBE_OUT.write_text(json.dumps(payload, indent=2, default=list))
    print(f"\n[remine] wrote {PROBE_OUT}")

    # Step 7 — merge into m9k_mode_bits.json as cells_by_template["inferred"].
    mode_bits = json.loads(RESULTS_PATH.read_text())
    for x, y, w, d in anchors:
        key = _anchor_key(x, y, w, d)
        entry = mode_bits[key]
        cbt = entry.get("cells_by_template", {})
        if "altsyncram" not in cbt:
            # Preserve legacy bucket as the altsyncram bucket (matches
            # the existing _load_m9k_mode_cells legacy-fallback logic).
            cbt["altsyncram"] = entry.get("cells", [])
        cbt["inferred"] = [list(c) for c in sorted(per_anchor[key])]
        entry["cells_by_template"] = cbt
        # Metadata so we don't have to re-derive provenance.
        entry.setdefault("inferred_probe_source", {})
        entry["inferred_probe_source"] = {
            "script": "fuzz/m9k_mode_inferred_full_remine.py",
            "baseline_rbf": baseline_rbf[w].name,
            "specimen_rbf": per_anchor_meta[key]["rbf"],
            "cell_count": len(per_anchor[key]),
        }
    RESULTS_PATH.write_text(json.dumps(mode_bits, indent=2))
    print(f"[remine] merged inferred buckets into {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
