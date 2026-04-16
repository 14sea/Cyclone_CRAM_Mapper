# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage B-narrow: specimen-factory mining of IOB output-enable (OE/tristate) bits.

Scope — ONLY the 16 sdram_dq bidir pins NEORV32 uses on AX301
(S_DB[0]..S_DB[15] in config.BOARD_PINS_AX301).  We do not attempt a
general bidir/OE directive for arbitrary pin pairs (see
`iob_cross_axis_not_decomposable.md`); the goal is simply to give
np2fasm something to emit for the sdram_dq tristate nets so the open
toolchain can place/route NEORV32 with functional SDRAM data bus.

Methodology
-----------

For each target bidir pin P we build two specimens that share EVERY
other byte of the design (harness + placement + seed):

  oe_off_{P}   : module top(K, OE, LED); assign DQ = K; assign LED = DQ;
                 -- pure passthrough; DQ is a plain output, NO tristate.

  oe_on_{P}    : module top(K, OE, LED); assign DQ = OE ? K : 1'bz;
                 assign LED = DQ;
                 -- DQ is a true bidir; Quartus inserts the OE CRAM bits.

The CRAM diff between oe_on_{P} and oe_off_{P}, restricted to the CRAM
data bytes (`diff_cram`), is the per-pin OE cell set.  Because the
harness (CLK, K, OE, LED) is fixed and `Specimen.placement` is empty
(no LE pinning — both specimens contain only IOB / passthrough logic),
the only axis varying is "does DQ have a tristate enable path".

Routing-invariance guard
-------------------------

`routing_invariance_probe` rebuilds the oe_on specimen at N additional
SEED values and requires byte-identical CRAM across all of them.  If a
pin drifts under SEED change, we DO NOT emit its cells into
`iob_oe_cell_map.json` — the pin needs a tighter harness / a smaller
design before we trust the diff.

Universal vs per-pin cells
--------------------------

After per-pin cell sets are harvested, we compute the intersection across
all 16 pins → `universal_oe_cells` (the OE-enable bit(s) that Quartus
flips regardless of which sdram_dq pin is bidir).  The remainder
(cells specific to only some pins) → `per_pin_oe_cells[P]`.

JSON schema (mirrors `iob_cell_map.json`):
  {
    "meta": {...},
    "pins":              [list of S_DB[*] pin names],
    "harness":           {"CLK": "E1", "K": "E16", "OE": "M16", "LED": "G15"},
    "per_pin_oe":        {pin: [[off,bp], ...]},
    "universal_oe_cells": [[off,bp], ...],
    "routing_invariant_pins": [pin, ...],
    "drift_pins":        {pin: n_drift_cells},
  }

Usage
-----
  python3 fuzz/iob_oe_specimen.py --work-dir tmp/iob_oe_mining \
      --output results/iob_oe_cell_map.json --invariance-seeds 1,2,3

Hard constraints (see CLAUDE.md memory):
  * `feedback_persite_mining_shared_harness`: harness pins are frozen.
  * `feedback_no_tmp_for_kept_scripts`: this file lives in fuzz/, not tmp/.
  * NO HW flashing is done by this script.  Stop after JSON emission.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from config import BOARD_PINS_AX301, QSF_OPTIMIZATIONS_OFF
from specimen_base import (
    Harness, Specimen, diff_cram, routing_invariance_probe,
)


# Sixteen sdram_dq pin names (S_DB[0]..S_DB[15]) — these are the only
# pins this campaign targets.  Each value is the PIN_XX string.
SDRAM_DQ_PINS: dict[str, str] = {
    name: BOARD_PINS_AX301[name]
    for name in (f"S_DB[{i}]" for i in range(16))
}


# Fixed harness: CLK/K/OE/LED hold invariant across every specimen.
# DQ is added per-specimen as `extra_pins` — that makes DQ the only
# axis that varies geometrically, even before the oe_on vs oe_off
# Verilog swap.
HARNESS_PINS = (
    ("CLK",    "PIN_E1"),    # 50 MHz clock, GCLK pin
    ("K_IN",   "PIN_E16"),   # KEY2 — data input to DQ
    ("OE_IN",  "PIN_M16"),   # KEY3 — output-enable control
    ("LED",    "PIN_G15"),   # LED0 — samples DQ for observability
)


def _oe_off_verilog() -> str:
    """DQ is a plain output driven by K.  No tristate, no OE path.

    The OE_IN pin is referenced (to keep the pin layout identical to
    the oe_on variant) but XOR'd into LED so Quartus doesn't prune it.
    This guarantees the IOB for OE_IN is placed in both variants.
    """
    return """\
module fuzz_top(
    input  wire CLK,
    input  wire K_IN,
    input  wire OE_IN,
    output wire DQ,
    output wire LED
);
    (* keep = "true" *) wire oe_keep = OE_IN;
    assign DQ  = K_IN;
    assign LED = DQ ^ oe_keep;  // OE_IN kept live so pin is not pruned
endmodule
"""


def _oe_on_verilog() -> str:
    """DQ is a true bidir: OE gates K_IN onto DQ; otherwise high-Z.

    LED samples DQ so Quartus cannot prune the tristate buffer.
    """
    return """\
module fuzz_top(
    input  wire CLK,
    input  wire K_IN,
    input  wire OE_IN,
    inout  wire DQ,
    output wire LED
);
    assign DQ  = OE_IN ? K_IN : 1'bz;
    assign LED = DQ;
endmodule
"""


def make_harness(seed: int = 1) -> Harness:
    return Harness(
        iob_pins=HARNESS_PINS,
        clk_signal="CLK",
        seed=seed,
        name="iob_oe",
        optimizations_off=tuple(QSF_OPTIMIZATIONS_OFF),
    )


def make_specimen_pair(pin_name: str, pin_loc: str,
                       harness: Harness) -> tuple[Specimen, Specimen]:
    """Return (oe_off, oe_on) specimens for one sdram_dq pin.

    Both specimens share the same harness + the same DQ pin in
    `extra_pins`; only the Verilog tristate expression differs.
    """
    # Tag makes the project_name unique per (pin, variant, seed) —
    # harness.name is "iob_oe" so hash-based project names don't clash
    # across the 32 builds in one sweep.
    safe = pin_name.replace("[", "_").replace("]", "")
    off = Specimen(
        name=f"oe_off_{safe}",
        harness=harness,
        verilog=_oe_off_verilog(),
        extra_pins={"DQ": pin_loc},
    )
    on = Specimen(
        name=f"oe_on_{safe}",
        harness=harness,
        verilog=_oe_on_verilog(),
        extra_pins={"DQ": pin_loc},
    )
    return off, on


def mine_one_pin(pin_name: str, pin_loc: str, work_dir: Path,
                 invariance_seeds: tuple[int, ...] = (1, 2, 3),
                 ) -> dict:
    """Build oe_off + oe_on for a single pin, diff them, probe invariance.

    Returns a dict with keys:
      pin, loc, oe_cells, drift_cells, invariant, oe_off_rbf, oe_on_rbf,
      error (None on success).
    """
    t0 = time.time()
    harness = make_harness(seed=invariance_seeds[0])
    off, on = make_specimen_pair(pin_name, pin_loc, harness)

    entry = {
        "pin": pin_name,
        "loc": pin_loc,
        "oe_cells": [],
        "drift_cells": [],
        "invariant": False,
        "oe_off_rbf": None,
        "oe_on_rbf": None,
        "error": None,
        "elapsed_s": 0.0,
    }

    try:
        off_rbf = off.build(work_dir).read_bytes()
        on_rbf  = on.build(work_dir).read_bytes()
        entry["oe_off_rbf"] = off.project_name() + ".rbf"
        entry["oe_on_rbf"]  = on.project_name() + ".rbf"
        cells = diff_cram(off_rbf, on_rbf)
        entry["oe_cells"] = sorted(cells)

        # Routing-invariance probe on the oe_on specimen (the one that
        # carries the interesting cells).  If the cell set drifts between
        # seeds, this pin is too loose for per-pin mining — we record
        # the drift but DO NOT trust the oe_cells we just diff'd.
        invariant, drift = routing_invariance_probe(
            on, work_dir, seeds=invariance_seeds,
        )
        entry["invariant"] = bool(invariant)
        entry["drift_cells"] = sorted(drift)
    except Exception as e:  # propagate as a soft failure
        entry["error"] = str(e)

    entry["elapsed_s"] = round(time.time() - t0, 2)
    return entry


def _intersect(sets: list[set[tuple[int, int]]]) -> set[tuple[int, int]]:
    if not sets:
        return set()
    out = set(sets[0])
    for s in sets[1:]:
        out &= s
    return out


def summarize(entries: list[dict]) -> dict:
    """Reduce per-pin entries into universal + per-pin-specific sets.

    Only pins that passed `routing_invariance_probe` contribute to the
    universal intersection — a drifted pin has noise in its diff which
    would corrupt the intersection.
    """
    good = [e for e in entries if e["invariant"] and not e["error"]
            and e["oe_cells"]]
    sets = [set(tuple(c) for c in e["oe_cells"]) for e in good]
    universal = _intersect(sets)
    per_pin = {}
    for e in entries:
        cells = set(tuple(c) for c in e["oe_cells"])
        per_pin[e["pin"]] = sorted(cells)
    return {
        "universal_oe_cells": sorted(universal),
        "per_pin_oe": per_pin,
        "routing_invariant_pins": [e["pin"] for e in good],
        "drift_pins": {e["pin"]: len(e["drift_cells"])
                       for e in entries if not e["invariant"]},
        "error_pins":  {e["pin"]: e["error"]
                        for e in entries if e["error"]},
        "n_pins_mined": len(entries),
        "n_pins_invariant": len(good),
    }


def run_sweep(pins: dict[str, str], work_dir: Path,
              invariance_seeds: tuple[int, ...]) -> list[dict]:
    work_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for i, (pin_name, pin_loc) in enumerate(pins.items()):
        print(f"[{i+1:2d}/{len(pins)}] mining {pin_name} @ {pin_loc}",
              flush=True)
        entry = mine_one_pin(pin_name, pin_loc, work_dir,
                             invariance_seeds=invariance_seeds)
        if entry["error"]:
            print(f"    ERROR: {entry['error'][:200]}", flush=True)
        else:
            tag = "OK" if entry["invariant"] else "DRIFT"
            print(f"    {tag}  {len(entry['oe_cells']):4d} oe cells  "
                  f"drift={len(entry['drift_cells']):3d}  "
                  f"{entry['elapsed_s']:.1f}s", flush=True)
        entries.append(entry)
    return entries


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="tmp/iob_oe_mining",
                    help="Quartus build dir (gitignored, under tmp/)")
    ap.add_argument("--output", default="results/iob_oe_cell_map.json",
                    help="Path to write the summary JSON")
    ap.add_argument("--invariance-seeds", default="1,2,3",
                    help="Comma-separated seed list for routing "
                         "invariance probe (default: 1,2,3)")
    ap.add_argument("--pins", default=None,
                    help="Comma-separated subset of S_DB[*] names to mine "
                         "(default: all 16).  Example: 'S_DB[0],S_DB[1]'")
    args = ap.parse_args(argv)

    root = Path(__file__).resolve().parent.parent
    work_dir = (root / args.work_dir).resolve()
    out_path = (root / args.output).resolve()
    seeds = tuple(int(s) for s in args.invariance_seeds.split(",") if s)

    if args.pins:
        wanted = {p.strip() for p in args.pins.split(",") if p.strip()}
        pins = {k: v for k, v in SDRAM_DQ_PINS.items() if k in wanted}
        missing = wanted - set(pins)
        if missing:
            print(f"error: unknown pins: {sorted(missing)}", file=sys.stderr)
            return 2
    else:
        pins = dict(SDRAM_DQ_PINS)

    print(f"[plan] {len(pins)} sdram_dq pins, work_dir={work_dir}, "
          f"invariance_seeds={seeds}", flush=True)

    entries = run_sweep(pins, work_dir, seeds)
    summary = summarize(entries)
    payload = {
        "meta": {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                      time.gmtime()),
            "harness": {k: v.removeprefix("PIN_") for k, v in HARNESS_PINS},
            "invariance_seeds": list(seeds),
            "work_dir": str(work_dir),
            "note": (
                "XOR-diff cells between (OE=on, tristate) and "
                "(OE=off, passthrough) specimens at each sdram_dq pin. "
                "Harness (CLK, K_IN, OE_IN, LED) is frozen; only the "
                "Verilog tristate expression and the DQ pin location "
                "vary per specimen.  See fuzz/iob_oe_specimen.py."
            ),
        },
        "pins": list(pins),
        **summary,
        "entries": entries,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"[done] wrote {out_path} ({summary['n_pins_invariant']}"
          f"/{summary['n_pins_mined']} pins invariant, "
          f"universal={len(summary['universal_oe_cells'])} cells)",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
