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

# Pin pool — avoid dedicated clock, JTAG, and config pins.
# PIN_F16 deliberately EXCLUDED: reserved as ALTERA_nCEO on F17, using
# it as user IO requires special QSF flags (see WIDE_PIN_MAP in
# fuzz/m9k_mode_inferred_full_remine.py which substitutes F16→P2).
# Fitter throws "multiple pins assigned to F16" if F16 ever lands in
# the assigned subset (caught by SDP w=9 d=1024 mining 2026-04-28).
PIN_POOL = [
    "PIN_E15", "PIN_E16", "PIN_M16", "PIN_M15",
    "PIN_A8", "PIN_A11", "PIN_A14", "PIN_B14",
    "PIN_T2", "PIN_T8", "PIN_R1", "PIN_R5",
    "PIN_R9", "PIN_R13", "PIN_R16", "PIN_P1",
    "PIN_P9", "PIN_P15", "PIN_T13", "PIN_G15",
    "PIN_F15", "PIN_B16", "PIN_G16", "PIN_K15",
    "PIN_K16", "PIN_L15", "PIN_L16", "PIN_N16",
    "PIN_D16", "PIN_D15", "PIN_C15", "PIN_C16",
    "PIN_F14", "PIN_J14", "PIN_J15", "PIN_J16",
    "PIN_T3", "PIN_T7", "PIN_T12", "PIN_T15",
    "PIN_P3", "PIN_P11", "PIN_P16", "PIN_N2",
    "PIN_N14",
    # Extension for SDP/TDP — additional input-capable F17 GPIOs not
    # in the original (w=4/9/36, d=*) SP set.  Source: results/iob_cell_map.json.
    "PIN_P2", "PIN_G1", "PIN_R3", "PIN_R10",
    "PIN_R11", "PIN_R12", "PIN_T4", "PIN_T10",
    "PIN_T11",
]


def _addr_bits(depth: int) -> int:
    return max(1, int(math.ceil(math.log2(depth))))


def _make_pin_map(width: int, depth: int, mode: str = "sp") -> dict[str, str]:
    """Build a signal→pin mapping that fits the F17 pin budget.

    mode="sp"  : CLK, WE, ADDR{i}, DIN{i}, DOUT{i}
    mode="sdp" : CLK, WE_W, ADDRW{i}, ADDRR{i}, DIN{i}, DOUT{i}
                 (write + read on separate addresses, single shared CLK)
    mode="tdp" : CLK, WE_A, WE_B, ADDRA{i}, ADDRB{i}, DIN{i}, DOUT{i}
                 (BIDIR_DUAL_PORT: both ports read+write; shared CLK; DIN
                 shared between ports, DOUT = douta_r ^ doutb_r — same
                 pin-saving pattern as scripts/m9k_mode_quartus_gold_mine.py)
    """
    addr_bits = _addr_bits(depth)
    if width <= 18:
        ext_din = width
        ext_dout = width
    else:
        ext_din = 4
        ext_dout = 4

    if mode == "sp":
        signals = ["CLK", "WE"]
        signals += [f"ADDR{i}" for i in range(addr_bits)]
        signals += [f"DIN{i}" for i in range(ext_din)]
        signals += [f"DOUT{i}" for i in range(ext_dout)]
    elif mode == "sdp":
        signals = ["CLK", "WE_W"]
        signals += [f"ADDRW{i}" for i in range(addr_bits)]
        signals += [f"ADDRR{i}" for i in range(addr_bits)]
        signals += [f"DIN{i}" for i in range(ext_din)]
        signals += [f"DOUT{i}" for i in range(ext_dout)]
    elif mode == "tdp":
        signals = ["CLK", "WE_A", "WE_B"]
        signals += [f"ADDRA{i}" for i in range(addr_bits)]
        signals += [f"ADDRB{i}" for i in range(addr_bits)]
        signals += [f"DIN{i}" for i in range(ext_din)]
        signals += [f"DOUT{i}" for i in range(ext_dout)]
    else:
        raise ValueError(f"unsupported mode {mode!r}")

    if len(signals) > len(PIN_POOL):
        raise ValueError(
            f"Need {len(signals)} pins (mode={mode}, w={width}, d={depth}) "
            f"but only {len(PIN_POOL)} available"
        )

    pin_map = {}
    pin_map["CLK"] = "PIN_E1"
    remaining = [p for p in PIN_POOL if p != "PIN_E1"]
    for sig in signals:
        if sig == "CLK":
            continue
        pin_map[sig] = remaining.pop(0)
    return pin_map


def _make_harness(width: int, depth: int, mode: str = "sp") -> Harness:
    pins = _make_pin_map(width, depth, mode=mode)
    return Harness(
        iob_pins=tuple(pins.items()),
        clk_signal="CLK",
        seed=1,
        name=f"m9k_{mode}_w{width}d{depth}",
        optimizations_off=(),
    )


def _port_decl(width: int, depth: int, mode: str = "sp") -> str:
    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    if mode == "sp":
        parts = ["input CLK", "input WE"]
        parts += [f"input ADDR{i}" for i in range(addr_bits)]
        parts += [f"input DIN{i}" for i in range(ext_din)]
        parts += [f"output DOUT{i}" for i in range(ext_dout)]
    elif mode == "sdp":
        parts = ["input CLK", "input WE_W"]
        parts += [f"input ADDRW{i}" for i in range(addr_bits)]
        parts += [f"input ADDRR{i}" for i in range(addr_bits)]
        parts += [f"input DIN{i}" for i in range(ext_din)]
        parts += [f"output DOUT{i}" for i in range(ext_dout)]
    elif mode == "tdp":
        parts = ["input CLK", "input WE_A", "input WE_B"]
        parts += [f"input ADDRA{i}" for i in range(addr_bits)]
        parts += [f"input ADDRB{i}" for i in range(addr_bits)]
        parts += [f"input DIN{i}" for i in range(ext_din)]
        parts += [f"output DOUT{i}" for i in range(ext_dout)]
    else:
        raise ValueError(f"unsupported mode {mode!r}")
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


def verilog_inferred_sdp_ram(width: int, depth: int) -> str:
    """Inferred Simple Dual Port RAM — separate read/write addresses,
    shared CLK.  Quartus + Yosys both infer SDP from this idiom because
    the read and write paths use distinct addresses with no read-during-
    write same-address contention.
    """
    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4

    addrw_bus = ", ".join(f"ADDRW{i}" for i in range(addr_bits - 1, -1, -1))
    addrr_bus = ", ".join(f"ADDRR{i}" for i in range(addr_bits - 1, -1, -1))

    if width <= ext_din:
        din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
        din_expr = f"{{{din_bus}}}"
        dout_assign = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
        dout_lines = f"    assign {{{dout_assign}}} = dout_r;"
    else:
        # width > ext_din path (folded data; not exercised at NEORV32 SDP shapes)
        raise ValueError(
            f"SDP wide-data folding not implemented (w={width}, ext_din={ext_din})")

    return f"""\
module fuzz_top(
    {_port_decl(width, depth, "sdp")}
);
    wire [{addr_bits-1}:0] addrw = {{{addrw_bus}}};
    wire [{addr_bits-1}:0] addrr = {{{addrr_bus}}};
    wire [{width-1}:0]     din   = {din_expr};
    reg  [{width-1}:0]     dout_r;
{dout_lines}

    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    integer i;
    initial begin
        for (i = 0; i < {depth}; i = i + 1)
            mem[i] = i[{width-1}:0] ^ {width}'h1A5;
    end
    always @(posedge CLK) begin
        if (WE_W) mem[addrw] <= din;
    end
    always @(posedge CLK) begin
        dout_r <= mem[addrr];
    end
endmodule
"""


def verilog_baseline_sdp(width: int, depth: int) -> str:
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    parts = [f"    assign DOUT{i} = DIN{i % ext_din};" for i in range(ext_dout)]
    body = "\n".join(parts)
    return f"""\
module fuzz_top(
    {_port_decl(width, depth, "sdp")}
);
{body}
endmodule
"""


def verilog_inferred_tdp_ram(width: int, depth: int) -> str:
    """Inferred BIDIR_DUAL_PORT (true dual-port) RAM.

    Both ports read AND write the shared `mem` array on the same CLK edge.
    DIN is shared between port A and port B (saves 18 pins for w=18 d=32);
    DOUT = douta_r ^ doutb_r drives a single shared output bus (saves
    another 18 pins).  Same pin-folding pattern as
    scripts/m9k_mode_quartus_gold_mine.py:_verilog_variant_tdp.

    NEORV32 regfile is registered as TDP/Single-Clock per fit.rpt — this
    matches.
    """
    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4

    addra_bus = ", ".join(f"ADDRA{i}" for i in range(addr_bits - 1, -1, -1))
    addrb_bus = ", ".join(f"ADDRB{i}" for i in range(addr_bits - 1, -1, -1))

    if width <= ext_din:
        din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
        din_expr = f"{{{din_bus}}}"
        dout_assign = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
        dout_lines = (
            f"    wire [{width-1}:0] dout_xor = douta_r ^ doutb_r;\n"
            f"    assign {{{dout_assign}}} = dout_xor;"
        )
    else:
        # Wide-data folding (not exercised at NEORV32 TDP shapes 18x32).
        raise ValueError(
            f"TDP wide-data folding not implemented (w={width}, ext_din={ext_din})"
        )

    return f"""\
module fuzz_top(
    {_port_decl(width, depth, "tdp")}
);
    wire [{addr_bits-1}:0] addra = {{{addra_bus}}};
    wire [{addr_bits-1}:0] addrb = {{{addrb_bus}}};
    wire [{width-1}:0]     din   = {din_expr};
    reg  [{width-1}:0]     douta_r;
    reg  [{width-1}:0]     doutb_r;
{dout_lines}

    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    always @(posedge CLK) begin
        if (WE_A) mem[addra] <= din;
        douta_r <= mem[addra];
    end
    always @(posedge CLK) begin
        if (WE_B) mem[addrb] <= din;
        doutb_r <= mem[addrb];
    end
endmodule
"""


def verilog_baseline_tdp(width: int, depth: int) -> str:
    """Bit-sliced pass-through baseline for TDP — no M9K, same pin set."""
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    parts = [f"    assign DOUT{i} = DIN{i % ext_din};" for i in range(ext_dout)]
    body = "\n".join(parts)
    return f"""\
module fuzz_top(
    {_port_decl(width, depth, "tdp")}
);
{body}
endmodule
"""


class M9kInferredSpecimen(M9kSpecimen):
    """M9kSpecimen variant that LOCs by the user reg name `mem_rtl_0`
    rather than `"u"`.  M9kSpecimen.render_qsf emits
    `set_location_assignment <m9k_loc> -to "u"` — but inferred-RAM
    Verilog has NO instance named `u`, so Quartus silently ignores
    the LOC and free-places the M9K (verified 2026-04-28 via
    `tmp/loc_test/run_loc_variants.py`: only `mem_rtl_0` and
    `altsyncram:mem_rtl_0` LOC targets are honored for inferred RAM
    whose user reg is named `mem`).

    This subclass overrides render_qsf to emit the working LOC.
    Verilog naming convention: the user `(* ramstyle = "M9K" *) reg`
    array MUST be named `mem` (matches verilog_inferred_ram /
    verilog_inferred_sdp_ram in this file).
    """

    def render_qsf(self) -> str:
        from specimen_base import Specimen
        # Skip M9kSpecimen.render_qsf to avoid the broken `-to "u"` line.
        qsf = Specimen.render_qsf(self)
        if self._m9k_loc is not None:
            qsf += (
                f'set_location_assignment {self._m9k_loc} '
                f'-to "altsyncram:mem_rtl_0"\n'
            )
        return qsf


def _baseline_spec(width: int, depth: int, mode: str = "sp") -> M9kSpecimen:
    h = _make_harness(width, depth, mode=mode)
    if mode == "sp":
        verilog = verilog_baseline(width, depth)
    elif mode == "sdp":
        verilog = verilog_baseline_sdp(width, depth)
    elif mode == "tdp":
        verilog = verilog_baseline_tdp(width, depth)
    else:
        raise ValueError(f"unsupported mode {mode!r}")
    # Baseline has no M9K, so M9kInferredSpecimen vs M9kSpecimen difference
    # doesn't matter (m9k_loc=None either way).
    return M9kInferredSpecimen(
        m9k_loc=None,
        init_mif=False,
        name=f"m9k_{mode}_w{width}d{depth}_baseline",
        harness=h,
        verilog=verilog,
        placement={},
    )


def _site_spec(x: int, y: int, width: int, depth: int, mode: str = "sp") -> M9kSpecimen:
    h = _make_harness(width, depth, mode=mode)
    if mode == "sp":
        verilog = verilog_inferred_ram(width, depth)
    elif mode == "sdp":
        verilog = verilog_inferred_sdp_ram(width, depth)
    elif mode == "tdp":
        verilog = verilog_inferred_tdp_ram(width, depth)
    else:
        raise ValueError(f"unsupported mode {mode!r}")
    return M9kInferredSpecimen(
        m9k_loc=f"M9K_X{x}_Y{y}_N0",
        init_mif=False,
        name=f"m9k_{mode}_w{width}d{depth}_X{x}_Y{y}",
        harness=h,
        verilog=verilog,
        placement={},
    )


def _build_job(args):
    x, y, width, depth, mode = args
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    spec = _site_spec(x, y, width, depth, mode=mode)
    t0 = time.time()
    try:
        rbf = spec.build(WORK_ROOT)
        return (x, y, width, depth, mode, str(rbf), None, time.time() - t0)
    except Exception as exc:
        return (x, y, width, depth, mode, None, repr(exc), time.time() - t0)


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
    # extension for SDP/TDP (need 2× addr) — input-capable pins not
    # otherwise allocated to SMOKE_PIN_POOL or SMOKE_DOUT_POOL.
    # Source: results/iob_cell_map.json::input_pins, minus pins already
    # used elsewhere in this smoke harness.
    "PIN_G1", "PIN_R3", "PIN_R10", "PIN_R11",
    "PIN_R12", "PIN_T4", "PIN_T10", "PIN_T11",
    # additional F17 GPIOs validated in mining harness PIN_POOL —
    # safe for input use even though not in iob_cell_map's
    # narrowly-validated input_pins set (mining proves this).
    "PIN_T15", "PIN_P3", "PIN_P11", "PIN_N2", "PIN_N14",
]


def _smoke_qsf(width: int, depth: int, m9k_loc: str | None,
               mode: str = "sp") -> str:
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
    needed_addr = addr_bits * (2 if mode in ("sdp", "tdp") else 1)
    if needed_addr > len(SMOKE_ADDR_POOL):
        raise ValueError(
            f"smoke addr pool too small for depth={depth} mode={mode} "
            f"(need {needed_addr}, have {len(SMOKE_ADDR_POOL)})")

    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        'set_global_assignment -name DEVICE EP4CE6F17C8',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_location_assignment PIN_E1  -to CLK',
    ]
    addr_pool_iter = iter(SMOKE_ADDR_POOL)
    if mode == "sp":
        lines.append('set_location_assignment PIN_M15 -to WE')
        for i in range(addr_bits):
            lines.append(f'set_location_assignment {next(addr_pool_iter)} -to ADDR[{i}]')
    elif mode == "sdp":
        lines.append('set_location_assignment PIN_M15 -to WE_W')
        for i in range(addr_bits):
            lines.append(f'set_location_assignment {next(addr_pool_iter)} -to ADDRW[{i}]')
        for i in range(addr_bits):
            lines.append(f'set_location_assignment {next(addr_pool_iter)} -to ADDRR[{i}]')
    elif mode == "tdp":
        # PIN_M15 ↔ WE_A (matches SP/SDP convention); WE_B borrows from
        # the input-capable spare M16 (also in SMOKE_ADDR_POOL but pulled
        # out here so addr_bits draw doesn't over-allocate).
        lines.append('set_location_assignment PIN_M15 -to WE_A')
        lines.append('set_location_assignment PIN_M16 -to WE_B')
        # Skip M16 from the addr pool draw so we don't double-assign it.
        addr_pool_iter = iter([p for p in SMOKE_ADDR_POOL if p != "PIN_M16"])
        for i in range(addr_bits):
            lines.append(f'set_location_assignment {next(addr_pool_iter)} -to ADDRA[{i}]')
        for i in range(addr_bits):
            lines.append(f'set_location_assignment {next(addr_pool_iter)} -to ADDRB[{i}]')
    else:
        raise ValueError(f"unsupported mode {mode!r}")
    for i in range(width):
        lines.append(f'set_location_assignment {SMOKE_PIN_POOL[i]} -to DIN[{i}]')
    for i in range(width):
        lines.append(f'set_location_assignment {SMOKE_DOUT_POOL[i]} -to DOUT[{i}]')
    if m9k_loc is not None:
        # Quartus's inferred-RAM LOC matches at the WRAPPER level only
        # (`altsyncram:mem_rtl_0` or just `mem_rtl_0` — the user reg
        # name `mem` becomes `mem_rtl_0` after Quartus's RAM
        # inferencing).  Empirically verified 2026-04-28: hierarchical
        # paths to the leaf ALTSYNCRAM (full or wildcard) ARE silently
        # ignored — `set_location_assignment ... -to <leaf>` registers
        # in QSF Assignments but the M9K still free-places.  See
        # `tmp/loc_test/run_loc_variants.py` for the 10-variant sweep.
        lines.append(
            f'set_instance_assignment -name LOCATION {m9k_loc} '
            f'-to "altsyncram:mem_rtl_0"'
        )
    return "\n".join(lines) + "\n"


def verilog_smoke_gold(width: int, depth: int) -> str:
    """Bus-style inferred-SP-RAM Verilog (mirror of ram_9x512.v)."""
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
    """Bus-style pass-through (no M9K) — paired baseline for SP smoke gold."""
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


def verilog_smoke_gold_sdp(width: int, depth: int) -> str:
    """Bus-style inferred-SDP-RAM Verilog — separate read/write addresses,
    shared CLK.  Two-always idiom forces Quartus to infer SDP.
    """
    addr_bits = _addr_bits(depth)
    return f"""\
module fuzz_top(
    input  wire                CLK,
    input  wire                WE_W,
    input  wire [{addr_bits-1}:0]  ADDRW,
    input  wire [{addr_bits-1}:0]  ADDRR,
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
        if (WE_W) mem[ADDRW] <= DIN;
    end
    always @(posedge CLK) begin
        DOUT <= mem[ADDRR];
    end
endmodule
"""


def verilog_smoke_baseline_sdp(width: int, depth: int) -> str:
    """Bus-style pass-through (no M9K) — paired baseline for SDP smoke gold."""
    addr_bits = _addr_bits(depth)
    return f"""\
module fuzz_top(
    input  wire                CLK,
    input  wire                WE_W,
    input  wire [{addr_bits-1}:0]  ADDRW,
    input  wire [{addr_bits-1}:0]  ADDRR,
    input  wire [{width-1}:0]      DIN,
    output wire [{width-1}:0]      DOUT
);
    assign DOUT = DIN;
endmodule
"""


def verilog_smoke_gold_tdp(width: int, depth: int) -> str:
    """Bus-style inferred-TDP-RAM Verilog — both ports read+write,
    independent ADDR/WE, shared DIN, DOUT = douta_r ^ doutb_r.
    Two-always idiom with same `mem` array forces Quartus inference of
    BIDIR_DUAL_PORT.
    """
    addr_bits = _addr_bits(depth)
    return f"""\
module fuzz_top(
    input  wire                CLK,
    input  wire                WE_A,
    input  wire                WE_B,
    input  wire [{addr_bits-1}:0]  ADDRA,
    input  wire [{addr_bits-1}:0]  ADDRB,
    input  wire [{width-1}:0]      DIN,
    output wire [{width-1}:0]      DOUT
);
    reg  [{width-1}:0] douta_r;
    reg  [{width-1}:0] doutb_r;
    assign DOUT = douta_r ^ doutb_r;

    (* ramstyle = "M9K" *) reg [{width-1}:0] mem [0:{depth-1}];
    integer i;
    initial begin
        for (i = 0; i < {depth}; i = i + 1)
            mem[i] = i[{width-1}:0] ^ {width}'h1A5;
    end
    always @(posedge CLK) begin
        if (WE_A) mem[ADDRA] <= DIN;
        douta_r <= mem[ADDRA];
    end
    always @(posedge CLK) begin
        if (WE_B) mem[ADDRB] <= DIN;
        doutb_r <= mem[ADDRB];
    end
endmodule
"""


def verilog_smoke_baseline_tdp(width: int, depth: int) -> str:
    """Bus-style pass-through (no M9K) — paired baseline for TDP smoke gold."""
    addr_bits = _addr_bits(depth)
    return f"""\
module fuzz_top(
    input  wire                CLK,
    input  wire                WE_A,
    input  wire                WE_B,
    input  wire [{addr_bits-1}:0]  ADDRA,
    input  wire [{addr_bits-1}:0]  ADDRB,
    input  wire [{width-1}:0]      DIN,
    output wire [{width-1}:0]      DOUT
);
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


def _build_smoke_gold(width: int, depth: int, mode: str = "sp") -> tuple[Path, Path]:
    """Build (smoke_gold, smoke_baseline) for the given (w, d, mode).
    Returns a path pair suitable for
    `_block_band_cells(smoke_gold, smoke_baseline)`.
    """
    sx, sy, sn = SMOKE_ANCHOR_SITE
    m9k_loc = f"M9K_X{sx}_Y{sy}_N{sn}"
    if mode == "sp":
        smoke_v = verilog_smoke_gold(width, depth)
        base_v = verilog_smoke_baseline(width, depth)
    elif mode == "sdp":
        smoke_v = verilog_smoke_gold_sdp(width, depth)
        base_v = verilog_smoke_baseline_sdp(width, depth)
    elif mode == "tdp":
        smoke_v = verilog_smoke_gold_tdp(width, depth)
        base_v = verilog_smoke_baseline_tdp(width, depth)
    else:
        raise ValueError(f"unsupported mode {mode!r}")
    smoke_q = _smoke_qsf(width, depth, m9k_loc=m9k_loc, mode=mode)
    base_q = _smoke_qsf(width, depth, m9k_loc=None, mode=mode)
    name_g = f"smoke_gold_{mode}_w{width}d{depth}"
    name_b = f"smoke_base_{mode}_w{width}d{depth}"
    rbf_g = _build_smoke(smoke_v, smoke_q, name_g, WORK_ROOT)
    rbf_b = _build_smoke(base_v, base_q, name_b, WORK_ROOT)
    return rbf_g, rbf_b


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine M9K_MODE for new widths")
    ap.add_argument("--width", type=int, help="Data width (4, 9, 36)")
    ap.add_argument("--depth", type=int, help="Address depth (256, 1024, 2048)")
    ap.add_argument("--mode", type=str, default="sp", choices=["sp", "sdp", "tdp"],
                    help="M9K operation mode (default sp)")
    ap.add_argument("--all", action="store_true",
                    help="Mine all three NEORV32-needed SP combos")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sites", type=int, default=8,
                    help="Number of Y sites per X column to mine (default 8)")
    ap.add_argument("--only-analyze", action="store_true")
    ap.add_argument("--skip-smoke", action="store_true",
                    help="Skip smoke-gold + smoke-baseline build.  Post-LOC-fix "
                         "(memo m9k_mining_loc_fix_silicon_validated_2026_04_28.md) "
                         "the smoke ∩ is diagnostic-only; required for w>18 where "
                         "the bus-style smoke harness exceeds the 18-pin DIN/DOUT pool.")
    args = ap.parse_args()

    if args.all:
        combos = [(4, 2048), (9, 1024), (36, 256)]
    elif args.width and args.depth:
        combos = [(args.width, args.depth)]
    else:
        ap.error("Specify --width W --depth D or --all")
        return 1

    for width, depth in combos:
        rc = _mine_one(width, depth, args.workers, args.sites, args.only_analyze,
                       mode=args.mode, skip_smoke=args.skip_smoke)
        if rc != 0:
            return rc
    return 0


def _mine_one(width: int, depth: int, workers: int, n_sites: int,
              only_analyze: bool, mode: str = "sp",
              skip_smoke: bool = False) -> int:
    print(f"\n{'='*60}")
    print(f"Mining M9K_MODE {mode.upper()} {width}x{depth}")
    print(f"{'='*60}")

    addr_bits = _addr_bits(depth)
    ext_din = width if width <= 18 else 4
    ext_dout = width if width <= 18 else 4
    addr_pins = addr_bits * (2 if mode in ("sdp", "tdp") else 1)
    we_pins = 2 if mode == "tdp" else 1
    print(f"  addr_bits={addr_bits}, ext_din={ext_din}, ext_dout={ext_dout}")
    print(f"  total pins = {1 + we_pins + addr_pins + ext_din + ext_dout}")

    sites_x15 = [(15, y) for y in M9K_SITES_X15[:n_sites]]
    sites_x27 = [(27, y) for y in M9K_SITES_X27[:n_sites]]
    sites = sites_x15 + sites_x27
    print(f"  mining {len(sites)} sites ({n_sites} per column)")

    WORK_ROOT.mkdir(parents=True, exist_ok=True)

    # Step 1: build baseline
    bl_spec = _baseline_spec(width, depth, mode=mode)
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
        todo = [(x, y, width, depth, mode) for x, y in sites]
        with mp.Pool(processes=max(1, workers)) as pool:
            results = list(pool.imap_unordered(_build_job, todo))
        errors = [r for r in results if r[6] is not None]
        for x, y, w, d, _m, _rbf, err, _el in errors:
            print(f"  FAIL X{x}_Y{y} {w}x{d}: {err}", flush=True)
        ok_results = [r for r in results if r[6] is None]
        for x, y, w, d, _m, rbf, _err, el in sorted(ok_results):
            print(f"  OK   X{x:>2}_Y{y:<2}  ({el:.1f}s)", flush=True)
        if errors:
            print(f"[mine] {len(errors)} build(s) failed; continuing with "
                  f"{len(ok_results)} OK sites")
            sites = [(r[0], r[1]) for r in ok_results]

    # Step 3: extract block-band cells
    bl_bytes = bl_rbf_path.read_bytes()
    per_site: dict[str, set[tuple[int, int]]] = {}
    for x, y in sites:
        spec = _site_spec(x, y, width, depth, mode=mode)
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
    # compute smoke_cells = block_band(smoke_gold ⊕ smoke_baseline).
    # Diagnostic-only post-LOC-fix (memo
    # m9k_mining_loc_fix_silicon_validated_2026_04_28.md): the smoke ∩
    # over-filters because the smoke harness omits GLOBAL_SIGNAL+SEED.
    # Skipped when --skip-smoke or when smoke pin pool overflows (w>18).
    smoke_cells: set[tuple[int, int]] = set()
    smoke_filtered: set[tuple[int, int]] = set()
    smoke_gold_rbf: Path | None = None
    smoke_base_rbf: Path | None = None
    if skip_smoke:
        print(f"\n[mine] --skip-smoke: smoke build skipped (diagnostic only)")
    elif not only_analyze:
        print(f"\n[mine] building smoke-gold + smoke-baseline ({mode.upper()}) ...", flush=True)
        t0 = time.time()
        try:
            smoke_gold_rbf, smoke_base_rbf = _build_smoke_gold(width, depth, mode=mode)
            print(f"  smoke_gold      -> {smoke_gold_rbf.name}")
            print(f"  smoke_baseline  -> {smoke_base_rbf.name}")
            print(f"  ({time.time()-t0:.1f}s for both)", flush=True)
        except ValueError as exc:
            print(f"  smoke skipped: {exc}")
            smoke_gold_rbf = smoke_base_rbf = None
    else:
        smoke_gold_rbf = WORK_ROOT / f"smoke_gold_{mode}_w{width}d{depth}.rbf"
        smoke_base_rbf = WORK_ROOT / f"smoke_base_{mode}_w{width}d{depth}.rbf"
        if not smoke_gold_rbf.exists() or not smoke_base_rbf.exists():
            print(f"  smoke RBFs not found for --only-analyze; skipping smoke")
            smoke_gold_rbf = smoke_base_rbf = None

    if smoke_gold_rbf is not None and smoke_base_rbf is not None:
        smoke_cells = _block_band_cells(
            smoke_base_rbf.read_bytes(), smoke_gold_rbf.read_bytes(),
        )
        smoke_filtered = universal & smoke_cells
        print(f"\n[mine] smoke_gold cells (block_band(gold ⊕ baseline)): "
              f"{len(smoke_cells)}")
        print(f"[mine] cross-site ∩ ∩ smoke_cells (diagnostic): "
              f"{len(smoke_filtered)} cells")
    # Post-LOC-fix methodology (memo m9k_mining_loc_fix_silicon_validated_2026_04_28.md):
    # cross-site ∩ alone IS the site-invariant bucket; smoke ∩ over-filters
    # because the smoke harness omits GLOBAL_SIGNAL+SEED so its diff is
    # structurally divergent from mining diffs.  Use cross-site ∩ as gi;
    # keep smoke_cells_count in metadata for audit.
    gi = universal
    print(f"[mine] inferred_goldintersect = cross-site ∩ = {len(gi)} cells "
          f"(post-LOC-fix: smoke ∩ filter dropped)")
    if not gi:
        print(f"  WARN: empty cross-site ∩ — sites built byte-identically?  "
              f"Check that M9kInferredSpecimen LOC is honored (per-site "
              f"cell counts should vary).")

    # Step 5: merge into m9k_mode_bits.json
    if RESULTS_PATH.exists():
        mode_bits = json.loads(RESULTS_PATH.read_text())
    else:
        mode_bits = {}

    # Bucket naming: SP -> "inferred" / "inferred_goldintersect"
    # SDP -> "inferred_sdp" / "inferred_goldintersect_sdp" (mirrors the
    # existing "quartus_gold_sdp" precedent so np2fasm's per-mode
    # dispatch table can pick the right bucket on pivot to gi).
    if mode == "sp":
        inf_key, gi_key = "inferred", "inferred_goldintersect"
    elif mode == "sdp":
        inf_key, gi_key = "inferred_sdp", "inferred_goldintersect_sdp"
    elif mode == "tdp":
        inf_key, gi_key = "inferred_tdp", "inferred_goldintersect_tdp"
    else:
        raise ValueError(f"unsupported mode {mode!r}")

    for key, cells in per_site.items():
        parts = key.split("_")
        site = f"{parts[0]}_{parts[1]}_{parts[2]}"
        entry = mode_bits.get(key, {
            "site": site,
            "width": width,
            "depth": depth,
            "source": f"scripts/m9k_mode_width_mine.py {mode} {width}x{depth}",
        })
        entry["cells"] = sorted(cells)
        cbt = entry.get("cells_by_template", {})
        cbt[inf_key] = sorted(cells)
        cbt[gi_key] = sorted(gi)
        entry["cells_by_template"] = cbt
        entry[f"{gi_key}_source"] = {
            "method": "cross-site ∩ (post-LOC-fix; smoke ∩ filter dropped per 2026-04-28 memo)",
            "mode": mode,
            "smoke_gold_rbf": smoke_gold_rbf.name if smoke_gold_rbf else None,
            "smoke_baseline_rbf": smoke_base_rbf.name if smoke_base_rbf else None,
            "smoke_anchor_site": f"X{SMOKE_ANCHOR_SITE[0]}_Y{SMOKE_ANCHOR_SITE[1]}_N{SMOKE_ANCHOR_SITE[2]}",
            "cross_site_universal_count": len(universal),
            "smoke_cells_count": len(smoke_cells),
            "smoke_filtered_count_diagnostic": len(smoke_filtered),
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
