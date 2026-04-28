# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage C.2 — mine M9K_MODE cells for new (width, depth) combinations.

NEORV32 places M9Ks at three configurations beyond the already-mined 9x512:
  - 4x2048 SP  (16 instances — IMEM/DMEM)
  - 9x1024 SP  (4 instances — bootloader / icache data)
  - 36x256 SP  (4 instances — regfile / dcache tag)

For each (width, depth), the script:
  1. Builds a baseline (no M9K, same harness) at one Quartus seed.
  2. Builds a per-site specimen (inferred RAM at LOC) across Y positions.
  3. Diffs block-band cells (frames 1692–1738).
  4. Computes universal intersection for site-invariance.
  5. Merges into results/m9k_mode_bits.json.

Pin budget:
  - 4x2048:  4 DIN + 4 DOUT + 11 ADDR + CLK + WE = 22 pins  (fits)
  - 9x1024:  9 DIN + 9 DOUT + 10 ADDR + CLK + WE = 30 pins  (fits)
  - 36x256:  XOR-folded internally → 4 DIN + 4 DOUT + 8 ADDR + CLK + WE = 19 pins

Usage:
    python3 scripts/m9k_mode_width_mine.py --width 9 --depth 1024 --workers 4
    python3 scripts/m9k_mode_width_mine.py --width 4 --depth 2048 --workers 4
    python3 scripts/m9k_mode_width_mine.py --width 36 --depth 256 --workers 4
    python3 scripts/m9k_mode_width_mine.py --all --workers 4
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from m9k_mode_remine_w9 import (
    BLOCK_FRAME_LO,
    BLOCK_FRAME_HI,
    PREAMBLE,
    FRAME,
    M9kSpecimen,
    _block_band_cells,
)
from specimen_base import Harness

WORK_ROOT = ROOT / "tmp" / "m9k_mode_width_mine"
RESULTS_PATH = ROOT / "results" / "m9k_mode_bits.json"

M9K_SITES_X15 = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]
M9K_SITES_X27 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23]

MINE_SITES = (
    [(15, y) for y in M9K_SITES_X15] +
    [(27, y) for y in M9K_SITES_X27]
)

# Pin pool — avoid dedicated clock, JTAG, and config pins
PIN_POOL = [
    "PIN_E15", "PIN_E16", "PIN_M16", "PIN_M15",
    "PIN_A8", "PIN_A11", "PIN_A14", "PIN_B14",
    "PIN_T2", "PIN_T8", "PIN_R1", "PIN_R5",
    "PIN_R9", "PIN_R13", "PIN_R16", "PIN_P1",
    "PIN_P9", "PIN_P15", "PIN_T13", "PIN_G15",
    "PIN_F15", "PIN_B16", "PIN_G16", "PIN_K15",
    "PIN_K16", "PIN_L15", "PIN_L16", "PIN_N16",
    "PIN_D16", "PIN_D15", "PIN_C15", "PIN_C16",
    "PIN_F14", "PIN_F16", "PIN_J14", "PIN_J15",
    "PIN_J16", "PIN_T3", "PIN_T7", "PIN_T12",
    "PIN_T15", "PIN_P3", "PIN_P11", "PIN_P16",
    "PIN_N2", "PIN_N14",
]


def _addr_bits(depth: int) -> int:
    return max(1, int(math.ceil(math.log2(depth))))


def _make_pin_map(width: int, depth: int) -> dict[str, str]:
    """Build a signal→pin mapping that fits the F17 pin budget."""
    addr_bits = _addr_bits(depth)
    if width <= 18:
        ext_din = width
        ext_dout = width
    else:
        ext_din = 4
        ext_dout = 4

    signals = ["CLK", "WE"]
    signals += [f"ADDR{i}" for i in range(addr_bits)]
    signals += [f"DIN{i}" for i in range(ext_din)]
    signals += [f"DOUT{i}" for i in range(ext_dout)]

    if len(signals) > len(PIN_POOL):
        raise ValueError(
            f"Need {len(signals)} pins but only {len(PIN_POOL)} available"
        )

    pin_map = {}
    pin_map["CLK"] = "PIN_E1"
    remaining = [p for p in PIN_POOL if p != "PIN_E1"]
    for sig in signals:
        if sig == "CLK":
            continue
        pin_map[sig] = remaining.pop(0)
    return pin_map


def _make_harness(width: int, depth: int) -> Harness:
    pins = _make_pin_map(width, depth)
    return Harness(
        iob_pins=tuple(pins.items()),
        clk_signal="CLK",
        seed=1,
        name=f"m9k_w{width}d{depth}",
        optimizations_off=(),
    )


def _port_decl(width: int, depth: int) -> str:
    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    parts = ["input CLK", "input WE"]
    parts += [f"input ADDR{i}" for i in range(addr_bits)]
    parts += [f"input DIN{i}" for i in range(ext_din)]
    parts += [f"output DOUT{i}" for i in range(ext_dout)]
    return ",\n    ".join(parts)


def verilog_inferred_ram(width: int, depth: int) -> str:
    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4

    addr_bus = ", ".join(f"ADDR{i}" for i in range(addr_bits - 1, -1, -1))

    if width <= 18:
        din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
        dout_assign = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
        din_expr = f"{{{din_bus}}}"
        dout_lines = f"    assign {{{dout_assign}}} = dout_r;"
    else:
        din_parts = ", ".join(f"DIN{i}" for i in range(ext_din - 1, -1, -1))
        reps = (width + ext_din - 1) // ext_din
        din_expr = f"{{{reps}{{{{{din_parts}}}}}}}"
        if reps * ext_din > width:
            din_expr = f"{din_expr}[{width-1}:0]"
        fold_parts = []
        for i in range(0, width, ext_dout):
            hi = min(i + ext_dout - 1, width - 1)
            if hi - i + 1 == ext_dout:
                fold_parts.append(f"dout_r[{hi}:{i}]")
            else:
                fold_parts.append(
                    f"{{{ext_dout - (hi - i + 1)}'b0, dout_r[{hi}:{i}]}}"
                )
        xor_expr = " ^ ".join(fold_parts)
        dout_assign = ", ".join(f"DOUT{i}" for i in range(ext_dout - 1, -1, -1))
        dout_lines = f"    assign {{{dout_assign}}} = {xor_expr};"

    return f"""\
module fuzz_top(
    {_port_decl(width, depth)}
);
    wire [{addr_bits-1}:0] addr = {{{addr_bus}}};
    wire [{width-1}:0]     din  = {din_expr};
    reg  [{width-1}:0]     dout_r;
{dout_lines}

    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    always @(posedge CLK) begin
        if (WE) mem[addr] <= din;
        dout_r <= mem[addr];
    end
endmodule
"""


def verilog_baseline(width: int, depth: int) -> str:
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    parts = [f"    assign DOUT{i} = DIN{i % ext_din};" for i in range(ext_dout)]
    body = "\n".join(parts)
    return f"""\
module fuzz_top(
    {_port_decl(width, depth)}
);
{body}
endmodule
"""


def _baseline_spec(width: int, depth: int) -> M9kSpecimen:
    h = _make_harness(width, depth)
    return M9kSpecimen(
        m9k_loc=None,
        init_mif=False,
        name=f"m9k_w{width}d{depth}_baseline",
        harness=h,
        verilog=verilog_baseline(width, depth),
        placement={},
    )


def _site_spec(x: int, y: int, width: int, depth: int) -> M9kSpecimen:
    h = _make_harness(width, depth)
    return M9kSpecimen(
        m9k_loc=f"M9K_X{x}_Y{y}_N0",
        init_mif=False,
        name=f"m9k_w{width}d{depth}_X{x}_Y{y}",
        harness=h,
        verilog=verilog_inferred_ram(width, depth),
        placement={},
    )


def _build_job(args):
    x, y, width, depth = args
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    spec = _site_spec(x, y, width, depth)
    t0 = time.time()
    try:
        rbf = spec.build(WORK_ROOT)
        return (x, y, width, depth, str(rbf), None, time.time() - t0)
    except Exception as exc:
        return (x, y, width, depth, None, repr(exc), time.time() - t0)


# ---------------------------------------------------------------------------
# Smoke-gold helpers (added 2026-04-28 after Step 1a silicon-fail).
#
# The cross-site ∩ alone is silicon-broken: at (w=8, d=64) it produces a
# 58-cell bucket that loads but breaks the simple_led KEY2→LED0 fabric
# path on AX301.  Same failure mode previously seen at (w=4, d=2048).
# Diagnosis in memory `m9k_mode_width_mine_gi_definition_silicon_broken_2026_04_28.md`.
#
# Original silicon-validated gi (w=9 d=512, w=18 d=512) was
# `inferred ∩ smoke_gold` — where smoke_gold is a separately-built
# inferred-RAM RBF whose harness DIFFERS from the mining harness in
# structural ways (no GLOBAL_SIGNAL clock assignment, no SEED, bus-style
# RTL, flat QSF).  Cells in the cross-site ∩ but NOT in smoke_gold are
# mining-harness drift (clock-net infra, IOB wrapper artifacts) — the
# 2nd ∩ filters them.
#
# Mirror of `tmp/m9k_smoke/ram_9x512.v` + `ram_9x512.qsf` parametrised
# over (width, depth).  Built by direct setup_project + compile_full +
# generate_rbf, bypassing M9kSpecimen / Specimen.render_qsf.
# ---------------------------------------------------------------------------

# Anchor site for smoke gold — same site the original w=9 smoke_gold
# (`tmp/m9k_smoke/ram_9x512.rbf`) used.  Must match a Y in M9K_SITES_X15.
SMOKE_ANCHOR_SITE = (15, 10, 0)

# Minimal pin pool, ordered to match the original ram_9x512.qsf.  Same
# 29 base pins as WIDE_PIN_MAP[narrow w=9 subset]; smaller w/d use a
# prefix; wider widths overflow into the next-9-pin extension.  This
# overlap is intentional — IOB-pad placement is the SAME, so the only
# structural divergence vs mining is the absence of GLOBAL_SIGNAL +
# SEED + the bit-sliced→bus-style RTL change.
SMOKE_PIN_POOL = [
    "PIN_R1", "PIN_R5", "PIN_R9", "PIN_R13", "PIN_R16",
    "PIN_P1", "PIN_P9", "PIN_P15", "PIN_T13",
    # extension for w>9
    "PIN_T3", "PIN_T7", "PIN_T12", "PIN_T15",
    "PIN_P3", "PIN_P11", "PIN_P16", "PIN_N2", "PIN_N14",
]
SMOKE_DOUT_POOL = [
    "PIN_G15", "PIN_F15", "PIN_B16", "PIN_G16", "PIN_K15",
    "PIN_K16", "PIN_L15", "PIN_L16", "PIN_N16",
    # extension for w>9
    "PIN_D16", "PIN_D15", "PIN_C15", "PIN_C16", "PIN_F14",
    "PIN_P2", "PIN_J14", "PIN_J15", "PIN_J16",
]
SMOKE_ADDR_POOL = [
    "PIN_E15", "PIN_E16", "PIN_M16", "PIN_A8", "PIN_A11",
    "PIN_A14", "PIN_B14", "PIN_T2", "PIN_T8",
    # extension for d>512 (need addr_bits up to 12)
    "PIN_J1", "PIN_J2", "PIN_F1",
]


def _smoke_qsf(width: int, depth: int, m9k_loc: str | None) -> str:
    """Flat smoke-gold QSF — mirrors `tmp/m9k_smoke/ram_9x512.qsf` style.

    Crucially differs from `Specimen.render_qsf()` in:
      * NO `GLOBAL_SIGNAL "GLOBAL CLOCK"` assignment (mining forces this)
      * NO `SEED` global assignment (mining sets seed=1)
      * Bus-indexed pin assignments (`PIN_E15 -to ADDR[0]`) instead of
        bit-sliced names — paired with bus-style Verilog ports

    These structural differences are what makes the smoke ⊕ baseline diff
    distinct from mining ⊕ baseline diffs, so their ∩ cancels harness
    drift while preserving M9K-mode cells.
    """
    addr_bits = _addr_bits(depth)
    if width > len(SMOKE_PIN_POOL):
        raise ValueError(f"smoke pin pool too small for width={width}")
    if width > len(SMOKE_DOUT_POOL):
        raise ValueError(f"smoke dout pool too small for width={width}")
    if addr_bits > len(SMOKE_ADDR_POOL):
        raise ValueError(f"smoke addr pool too small for depth={depth}")

    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_location_assignment PIN_E1  -to CLK',
        'set_location_assignment PIN_M15 -to WE',
    ]
    for i in range(addr_bits):
        lines.append(f'set_location_assignment {SMOKE_ADDR_POOL[i]} -to ADDR[{i}]')
    for i in range(width):
        lines.append(f'set_location_assignment {SMOKE_PIN_POOL[i]} -to DIN[{i}]')
    for i in range(width):
        lines.append(f'set_location_assignment {SMOKE_DOUT_POOL[i]} -to DOUT[{i}]')
    if m9k_loc is not None:
        # Mirror ram_9x512.qsf's ALTSYNCRAM hierarchical name.  Quartus
        # auto-generates the wrapper as `mem_rtl_0|...|ram_block1a0`
        # for an inferred (* ramstyle = "M9K" *) reg array.
        lines.append(
            f'set_instance_assignment -name LOCATION {m9k_loc} '
            f'-to "mem_rtl_0|auto_generated|ram_block1a0"'
        )
    return "\n".join(lines) + "\n"


def verilog_smoke_gold(width: int, depth: int) -> str:
    """Bus-style inferred-RAM Verilog (mirror of ram_9x512.v).

    Module name `fuzz_top` (so compile.py's hardcoded fuzz_top.v works)
    but signals are flat busses, not bit-sliced.
    """
    addr_bits = _addr_bits(depth)
    return f"""\
module fuzz_top(
    input  wire                CLK,
    input  wire                WE,
    input  wire [{addr_bits-1}:0]  ADDR,
    input  wire [{width-1}:0]      DIN,
    output reg  [{width-1}:0]      DOUT
);
    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    integer i;
    initial begin
        for (i = 0; i < {depth}; i = i + 1)
            mem[i] = i[{width-1}:0] ^ {width}'h1A5;
    end
    always @(posedge CLK) begin
        if (WE) mem[ADDR] <= DIN;
        DOUT <= mem[ADDR];
    end
endmodule
"""


def verilog_smoke_baseline(width: int, depth: int) -> str:
    """Bus-style pass-through (no M9K) — paired baseline for smoke gold.

    Same port shape as `verilog_smoke_gold` so the QSF is identical
    and the diff isolates only the M9K block-band cells.
    """
    addr_bits = _addr_bits(depth)
    return f"""\
module fuzz_top(
    input  wire                CLK,
    input  wire                WE,
    input  wire [{addr_bits-1}:0]  ADDR,
    input  wire [{width-1}:0]      DIN,
    output wire [{width-1}:0]      DOUT
);
    // CLK/WE/ADDR are intentionally unused — only DIN→DOUT routing.
    assign DOUT = DIN;
endmodule
"""


def _build_smoke(verilog: str, qsf: str, name: str, work: Path) -> Path:
    """Direct Quartus build, bypassing M9kSpecimen / Specimen wrapper.

    Used for both smoke_gold and smoke_baseline to keep their harness
    structurally distinct from the mining specimens.
    """
    from compile import setup_project, compile_full, generate_rbf
    work.mkdir(parents=True, exist_ok=True)
    rbf_out = str(work / f"{name}.rbf")
    if Path(rbf_out).exists():
        return Path(rbf_out)
    proj_dir = setup_project(name, verilog, qsf, str(work))
    ok, _t, err = compile_full(name, proj_dir)
    if not ok:
        raise RuntimeError(f"smoke build failed for {name!r}: {err}")
    rbf = generate_rbf(name, proj_dir, rbf_out)
    if rbf is None:
        raise RuntimeError(f"smoke RBF generation failed for {name!r}")
    return Path(rbf)


def _build_smoke_gold(width: int, depth: int) -> tuple[Path, Path]:
    """Build (smoke_gold, smoke_baseline) for the given (w, d).  Returns
    a path pair suitable for `_block_band_cells(smoke_gold, smoke_baseline)`.
    """
    sx, sy, sn = SMOKE_ANCHOR_SITE
    m9k_loc = f"M9K_X{sx}_Y{sy}_N{sn}"
    smoke_v = verilog_smoke_gold(width, depth)
    base_v = verilog_smoke_baseline(width, depth)
    smoke_q = _smoke_qsf(width, depth, m9k_loc=m9k_loc)
    base_q = _smoke_qsf(width, depth, m9k_loc=None)
    name_g = f"smoke_gold_w{width}d{depth}"
    name_b = f"smoke_base_w{width}d{depth}"
    rbf_g = _build_smoke(smoke_v, smoke_q, name_g, WORK_ROOT)
    rbf_b = _build_smoke(base_v, base_q, name_b, WORK_ROOT)
    return rbf_g, rbf_b


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine M9K_MODE for new widths")
    ap.add_argument("--width", type=int, help="Data width (4, 9, 36)")
    ap.add_argument("--depth", type=int, help="Address depth (256, 1024, 2048)")
    ap.add_argument("--all", action="store_true",
                    help="Mine all three NEORV32-needed combos")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sites", type=int, default=8,
                    help="Number of Y sites per X column to mine (default 8)")
    ap.add_argument("--only-analyze", action="store_true")
    args = ap.parse_args()

    if args.all:
        combos = [(4, 2048), (9, 1024), (36, 256)]
    elif args.width and args.depth:
        combos = [(args.width, args.depth)]
    else:
        ap.error("Specify --width W --depth D or --all")
        return 1

    for width, depth in combos:
        rc = _mine_one(width, depth, args.workers, args.sites, args.only_analyze)
        if rc != 0:
            return rc
    return 0


def _mine_one(width: int, depth: int, workers: int, n_sites: int,
              only_analyze: bool) -> int:
    print(f"\n{'='*60}")
    print(f"Mining M9K_MODE {width}x{depth}")
    print(f"{'='*60}")

    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    print(f"  addr_bits={addr_bits}, ext_din={ext_din}, ext_dout={ext_dout}")
    print(f"  total pins = {2 + addr_bits + ext_din + ext_dout}")

    sites_x15 = [(15, y) for y in M9K_SITES_X15[:n_sites]]
    sites_x27 = [(27, y) for y in M9K_SITES_X27[:n_sites]]
    sites = sites_x15 + sites_x27
    print(f"  mining {len(sites)} sites ({n_sites} per column)")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    # Step 1: build baseline
    bl_spec = _baseline_spec(width, depth)
    bl_rbf_path = WORK_ROOT / f"{bl_spec.project_name()}.rbf"
    if not only_analyze:
        print(f"\n[mine] building baseline ...", flush=True)
        t0 = time.time()
        bl_rbf_path = bl_spec.build(WORK_ROOT)
        print(f"  -> {bl_rbf_path.name}  ({time.time()-t0:.1f}s)", flush=True)
    else:
        if not bl_rbf_path.exists():
            print(f"ERROR: baseline RBF not found: {bl_rbf_path}")
            return 1

    # Step 2: build per-site specimens
    if not only_analyze:
        print(f"\n[mine] building {len(sites)} per-site specimens "
              f"(workers={workers})", flush=True)
        todo = [(x, y, width, depth) for x, y in sites]
        with mp.Pool(processes=max(1, workers)) as pool:
            results = list(pool.imap_unordered(_build_job, todo))
        errors = [r for r in results if r[5] is not None]
        for x, y, w, d, _rbf, err, _el in errors:
            print(f"  FAIL X{x}_Y{y} {w}x{d}: {err}", flush=True)
        ok_results = [r for r in results if r[5] is None]
        for x, y, w, d, rbf, _err, el in sorted(ok_results):
            print(f"  OK   X{x:>2}_Y{y:<2}  ({el:.1f}s)", flush=True)
        if errors:
            print(f"[mine] {len(errors)} build(s) failed; continuing with "
                  f"{len(ok_results)} OK sites")
            sites = [(r[0], r[1]) for r in ok_results]

    # Step 3: extract block-band cells
    bl_bytes = bl_rbf_path.read_bytes()
    per_site: dict[str, set[tuple[int, int]]] = {}
    for x, y in sites:
        spec = _site_spec(x, y, width, depth)
        rbf_path = WORK_ROOT / f"{spec.project_name()}.rbf"
        if not rbf_path.exists():
            print(f"  SKIP X{x}_Y{y}: RBF not found")
            continue
        cells = _block_band_cells(bl_bytes, rbf_path.read_bytes())
        key = f"X{x}_Y{y}_N0_{width}x{depth}"
        per_site[key] = cells
        print(f"  {key}: {len(cells)} cells")

    if not per_site:
        print("ERROR: no sites produced cells")
        return 1

    # Step 4: universal intersection
    all_sets = list(per_site.values())
    universal = set.intersection(*all_sets)
    print(f"\n[mine] universal intersection across {len(all_sets)} sites: "
          f"{len(universal)} cells")
    counts = [len(s) for s in all_sets]
    print(f"  cell counts min/median/max: "
          f"{min(counts)}/{sorted(counts)[len(counts)//2]}/{max(counts)}")

    # Check site-invariance (all same count = perfect)
    if min(counts) == max(counts):
        print(f"  PERFECT site-invariance: all sites have {min(counts)} cells")
    else:
        print(f"  site-specific cells exist: spread = {max(counts) - min(counts)}")

    # Step 4b: build smoke-gold + smoke-baseline at the anchor site,
    # compute smoke_cells = block_band(smoke_gold ⊕ smoke_baseline),
    # gi = cross-site ∩ ∩ smoke_cells.  Filters mining-harness drift
    # (clock-net infra, IOB wrapper artifacts) that survives cross-site
    # ∩ alone.  Mirrors the original 2026-04-17 w=9 / 2026-04-24 w=18
    # silicon-validated methodology.
    if not only_analyze:
        print(f"\n[mine] building smoke-gold + smoke-baseline ...", flush=True)
        t0 = time.time()
        smoke_gold_rbf, smoke_base_rbf = _build_smoke_gold(width, depth)
        print(f"  smoke_gold      -> {smoke_gold_rbf.name}")
        print(f"  smoke_baseline  -> {smoke_base_rbf.name}")
        print(f"  ({time.time()-t0:.1f}s for both)", flush=True)
    else:
        sx, sy, sn = SMOKE_ANCHOR_SITE
        smoke_gold_rbf = WORK_ROOT / f"smoke_gold_w{width}d{depth}.rbf"
        smoke_base_rbf = WORK_ROOT / f"smoke_base_w{width}d{depth}.rbf"
        if not smoke_gold_rbf.exists() or not smoke_base_rbf.exists():
            print(f"ERROR: smoke RBFs not found for --only-analyze")
            return 1

    smoke_cells = _block_band_cells(
        smoke_base_rbf.read_bytes(), smoke_gold_rbf.read_bytes(),
    )
    gi = universal & smoke_cells
    print(f"\n[mine] smoke_gold cells (block_band(gold ⊕ baseline)): "
          f"{len(smoke_cells)}")
    print(f"[mine] inferred_goldintersect = cross-site ∩ ∩ smoke_cells = "
          f"{len(gi)} cells")
    if not gi:
        print(f"  WARN: empty gi bucket — smoke gold may diverge too "
              f"much from mining harness for {width}x{depth}.  Check "
              f"smoke RBF builds and consider widening the smoke harness.")

    # Step 5: merge into m9k_mode_bits.json
    if RESULTS_PATH.exists():
        mode_bits = json.loads(RESULTS_PATH.read_text())
    else:
        mode_bits = {}

    for key, cells in per_site.items():
        parts = key.split("_")
        site = f"{parts[0]}_{parts[1]}_{parts[2]}"
        entry = mode_bits.get(key, {
            "site": site,
            "width": width,
            "depth": depth,
            "source": f"scripts/m9k_mode_width_mine.py {width}x{depth}",
        })
        entry["cells"] = sorted(cells)
        cbt = entry.get("cells_by_template", {})
        cbt["inferred"] = sorted(cells)
        cbt["inferred_goldintersect"] = sorted(gi)
        entry["cells_by_template"] = cbt
        entry["inferred_goldintersect_source"] = {
            "method": "cross-site ∩ ∩ smoke_gold(block_band)",
            "smoke_gold_rbf": smoke_gold_rbf.name,
            "smoke_baseline_rbf": smoke_base_rbf.name,
            "smoke_anchor_site": f"X{SMOKE_ANCHOR_SITE[0]}_Y{SMOKE_ANCHOR_SITE[1]}_N{SMOKE_ANCHOR_SITE[2]}",
            "cross_site_universal_count": len(universal),
            "smoke_cells_count": len(smoke_cells),
            "gi_count": len(gi),
        }
        mode_bits[key] = entry

    tmp = str(RESULTS_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mode_bits, f, indent=2, default=list)
    import os
    os.replace(tmp, str(RESULTS_PATH))
    print(f"\n[mine] merged {len(per_site)} entries into {RESULTS_PATH}")
    print(f"  total entries: {len(mode_bits)}")

    # Step 6: summary
    print(f"\n[mine] {width}x{depth} DONE: cross-site ∩ = {len(universal)} "
          f"cells; gi = {len(gi)} cells (after smoke ∩)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
