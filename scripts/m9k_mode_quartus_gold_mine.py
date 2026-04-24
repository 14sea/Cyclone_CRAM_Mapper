# SPDX-License-Identifier: GPL-3.0-or-later
"""Quartus-gold M9K_MODE mining — real Quartus mode cells, mode-aware.

Per (width, depth, operation_mode) we build:
  * a matched baseline (same pinout, NO M9K, trivial passthrough)
  * N variants that share the SAME pinout + SAME M9K LOC (altsyncram `u`),
    but vary the INIT pattern and read-pipe depth

Per-variant mode cells =
    block_band(variant_i.rbf ⊕ matched_baseline.rbf)

Site-fixed, mode-invariant cells =
    intersection over all variants

These land in `results/m9k_mode_bits.json`
   → X{x}_Y{y}_N{n}_{W}x{D}.cells_by_template[<bucket>]

Bucket selection via --mode:
    sp  → cells_by_template["quartus_gold"]      (SINGLE_PORT,   default)
    sdp → cells_by_template["quartus_gold_sdp"]  (DUAL_PORT)
    tdp → cells_by_template["quartus_gold_tdp"]  (BIDIR_DUAL_PORT)

SP covers inferred RAM / altsyncram passthrough, SDP covers NEORV32
dmem/imem (8x2048 simple dual-port), TDP covers the NEORV32 regfile
(32x32 true dual-port).  `cells_by_template["quartus_gold"]` is never
overwritten by --mode=sdp/tdp; the buckets stay disjoint.

Usage:
    python3 scripts/m9k_mode_quartus_gold_mine.py --width 4 --depth 2048
    python3 scripts/m9k_mode_quartus_gold_mine.py --mode sdp --width 8 --depth 2048
    python3 scripts/m9k_mode_quartus_gold_mine.py --mode tdp --width 32 --depth 32
    python3 scripts/m9k_mode_quartus_gold_mine.py --all --workers 3
    python3 scripts/m9k_mode_quartus_gold_mine.py --only-analyze --all
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from compile import setup_project, compile_full, generate_rbf

PREAMBLE = 32
FRAME = 210
DATA_PER_FRAME = 208
BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738

WORK_ROOT = ROOT / "tmp" / "m9k_mode_quartus_gold"
RESULTS_PATH = ROOT / "results" / "m9k_mode_bits.json"

DEFAULT_SITE_X = 15
DEFAULT_SITE_Y = 10
DEFAULT_SITE_N = 0
# Populated by main() from --site / --mode; used by the Verilog / QSF
# helpers and by _mine_one for bucket naming + work-dir layout.
SITE_X = DEFAULT_SITE_X
SITE_Y = DEFAULT_SITE_Y
SITE_N = DEFAULT_SITE_N
SITE_MODE = "sp"

# Per-mode bucket names written into cells_by_template.
_BUCKET_FOR_MODE = {
    "sp":  "quartus_gold",
    "sdp": "quartus_gold_sdp",
    "tdp": "quartus_gold_tdp",
}

# altsyncram operation_mode string per --mode flag.
_OPMODE_FOR_MODE = {
    "sp":  "SINGLE_PORT",
    "sdp": "DUAL_PORT",
    "tdp": "BIDIR_DUAL_PORT",
}

TARGET_COMBOS = [
    (4, 2048),
    (9, 512),
    (18, 512),
    (9, 1024),
    (36, 256),
]

# --all combos when --mode is not sp.  Per-M9K geometry drives these —
# each (w, d) below fits in a single M9K (≤9216 bits inc. parity).
# NEORV32 higher-level primitives like dmem/imem 2048x8 are split by
# Quartus into multiple M9Ks (2x 2048x4 per 2048x8 instance), so the
# per-M9K mode-cell mining happens at the split geometry, not the
# logical primitive size.
#
# SDP 4x2048 — per-M9K split of NEORV32 dmem / imem 8x2048 primitive.
# TDP 32x32  — cpu_regfile (fits in a single M9K, 1024 bits).
TARGET_COMBOS_BY_MODE = {
    "sp":  TARGET_COMBOS,
    "sdp": [(4, 2048)],
    # Per-M9K TDP geometry — M9K's BIDIR_DUAL_PORT caps each port's
    # data width at 18 (Cyclone IV datasheet), so NEORV32's logical
    # 32x32 cpu_regfile is split by Quartus into 2x (16x32) TDP M9Ks.
    "tdp": [(16, 32)],
}

PIN_POOL = [
    "PIN_E15", "PIN_E16", "PIN_M16", "PIN_M15",
    "PIN_A8",  "PIN_A11", "PIN_A14", "PIN_B14",
    "PIN_T2",  "PIN_T8",  "PIN_R1",  "PIN_R5",
    "PIN_R9",  "PIN_R13", "PIN_R16", "PIN_P1",
    "PIN_P9",  "PIN_P15", "PIN_T13",
    "PIN_F15", "PIN_B16", "PIN_G16", "PIN_K15",
    "PIN_K16", "PIN_L15", "PIN_L16", "PIN_N16",
    "PIN_D16", "PIN_D15", "PIN_C15", "PIN_C16",
    "PIN_F14", "PIN_P2",  "PIN_J14", "PIN_J15",  # F16 is ALTERA_nCEO on F17
    "PIN_J16", "PIN_T3",  "PIN_T7",  "PIN_T12",
    "PIN_T15", "PIN_P3",  "PIN_P11", "PIN_P16",
    "PIN_N2",  "PIN_N14",
]


def _addr_bits(depth: int) -> int:
    return max(1, int(math.ceil(math.log2(depth))))


def _fold_width(width: int) -> int:
    # Cap external bus at 9 pins; wider M9K modes XOR-fold internally.
    return min(width, 9)


def _port_signals(width: int, depth: int, mode: str = "sp") -> list[str]:
    """Return the port-signal list for a given operation_mode.

    Mode-aware so that SP / SDP / TDP Verilog / QSF use the same naming
    convention throughout (avoids pin-map / port-decl drift).

    SP: CLK, WE, ADDR, DIN, DOUT  (1 CLK)
    SDP: CLK, WE_W, ADDRW, ADDRR, DINW, DOUTR  (1 shared CLK — NEORV32 style)
    TDP: CLK, WE_A, WE_B, ADDRA, ADDRB, DINA, DINB, DOUTA, DOUTB  (1 shared CLK)
    """
    addr_bits = _addr_bits(depth)
    ew = _fold_width(width)
    if mode == "sp":
        sigs = ["CLK", "WE"]
        sigs += [f"ADDR{i}" for i in range(addr_bits)]
        sigs += [f"DIN{i}" for i in range(ew)]
        sigs += [f"DOUT{i}" for i in range(ew)]
        return sigs
    if mode == "sdp":
        sigs = ["CLK", "WE_W"]
        sigs += [f"ADDRW{i}" for i in range(addr_bits)]
        sigs += [f"ADDRR{i}" for i in range(addr_bits)]
        sigs += [f"DIN{i}" for i in range(ew)]
        sigs += [f"DOUTR{i}" for i in range(ew)]
        return sigs
    if mode == "tdp":
        # Shared DIN / DOUT pins to stay within the 45-pin PIN_POOL+CLK
        # budget at (32,32) and (9,1024).  Independent ADDRA/B + WE_A/B
        # + CLK is enough for the altsyncram operation_mode encoding —
        # the BIDIR_DUAL_PORT mode cells are about port-count / direction,
        # not per-port data fanout.
        sigs = ["CLK", "WE_A", "WE_B"]
        sigs += [f"ADDRA{i}" for i in range(addr_bits)]
        sigs += [f"ADDRB{i}" for i in range(addr_bits)]
        sigs += [f"DIN{i}" for i in range(ew)]
        sigs += [f"DOUT{i}" for i in range(ew)]
        return sigs
    raise ValueError(f"unknown mode {mode!r}")


def _pin_map(width: int, depth: int, mode: str = "sp") -> dict[str, str]:
    sigs = _port_signals(width, depth, mode)
    if len(sigs) > 1 + len(PIN_POOL):
        raise ValueError(
            f"mode={mode} {width}x{depth}: {len(sigs)} signals > pin budget "
            f"({1 + len(PIN_POOL)})"
        )
    pins: dict[str, str] = {"CLK": "PIN_E1"}
    remain = [p for p in PIN_POOL]
    for s in sigs:
        if s == "CLK":
            continue
        pins[s] = remain.pop(0)
    return pins


def _port_decl(width: int, depth: int, mode: str = "sp") -> str:
    parts: list[str] = []
    for s in _port_signals(width, depth, mode):
        if s.startswith("DOUT"):
            parts.append(f"output {s}")
        else:
            parts.append(f"input {s}")
    return ",\n    ".join(parts)


def _qsf_common(project: str, width: int, depth: int, mode: str = "sp") -> list[str]:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
    ]
    for sig, pin in _pin_map(width, depth, mode).items():
        lines.append(f"set_location_assignment {pin} -to {sig}")
    return lines


def _qsf_variant(project: str, width: int, depth: int, mode: str = "sp") -> str:
    lines = _qsf_common(project, width, depth, mode)
    # altsyncram instance `u`; LOC pins it to the M9K block site.
    lines.append(
        f'set_location_assignment M9K_X{SITE_X}_Y{SITE_Y}_N{SITE_N} -to "u"'
    )
    return "\n".join(lines) + "\n"


def _qsf_baseline(project: str, width: int, depth: int, mode: str = "sp") -> str:
    return "\n".join(_qsf_common(project, width, depth, mode)) + "\n"


def _init_mif(width: int, depth: int, variant: int) -> str:
    mask = (1 << width) - 1
    lines = [
        f"DEPTH = {depth};",
        f"WIDTH = {width};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    nibbles = (width + 3) // 4
    addr_nibbles = max(1, (_addr_bits(depth) + 3) // 4)
    for i in range(depth):
        if variant == 0:
            v = i & mask
        elif variant == 1:
            v = (~i) & mask
        else:
            v = (i ^ 0x5A5A5A5A) & mask
        lines.append(f"  {i:0{addr_nibbles}X} : {v:0{nibbles}X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _verilog_variant_sdp(width: int, depth: int, variant: int) -> str:
    """altsyncram DUAL_PORT (simple dual-port) template.

    Port A is the write side, port B is the read side.  Pin-budget-
    constrained: both ports share CLK (matches NEORV32 dmem/imem, which
    the fit report lists as Simple Dual Port / Single Clock).
    """
    addr_bits = _addr_bits(depth)
    ew = _fold_width(width)

    addrw_bus = ", ".join(f"ADDRW{i}" for i in range(addr_bits - 1, -1, -1))
    addrr_bus = ", ".join(f"ADDRR{i}" for i in range(addr_bits - 1, -1, -1))
    if width <= ew:
        din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
        din_expr = f"{{{din_bus}}}"
        dout_assign = ", ".join(f"DOUTR{i}" for i in range(width - 1, -1, -1))
        dout_stmt = f"    assign {{{dout_assign}}} = dout_r;"
    else:
        reps = (width + ew - 1) // ew
        din_parts = ", ".join(f"DIN{i}" for i in range(ew - 1, -1, -1))
        repl = f"{{{reps}{{{{{din_parts}}}}}}}"
        if reps * ew > width:
            repl += f"[{width - 1}:0]"
        din_expr = repl
        fold_parts = []
        for i in range(0, width, ew):
            hi = min(i + ew - 1, width - 1)
            if hi - i + 1 == ew:
                fold_parts.append(f"dout_r[{hi}:{i}]")
            else:
                fold_parts.append(
                    f"{{{ew - (hi - i + 1)}'b0, dout_r[{hi}:{i}]}}"
                )
        xor_expr = " ^ ".join(fold_parts)
        dout_assign = ", ".join(f"DOUTR{i}" for i in range(ew - 1, -1, -1))
        dout_stmt = f"    assign {{{dout_assign}}} = {xor_expr};"

    extra_pipe = ""
    if variant == 2:
        extra_pipe = f"""
    reg [{width-1}:0] dout_q;
    always @(posedge CLK) dout_q <= dout_r;
"""
        if width <= ew:
            dout_stmt = (
                "    assign {"
                + ", ".join(f"DOUTR{i}" for i in range(width - 1, -1, -1))
                + "} = dout_q;"
            )
        else:
            fold_parts = []
            for i in range(0, width, ew):
                hi = min(i + ew - 1, width - 1)
                if hi - i + 1 == ew:
                    fold_parts.append(f"dout_q[{hi}:{i}]")
                else:
                    fold_parts.append(
                        f"{{{ew - (hi - i + 1)}'b0, dout_q[{hi}:{i}]}}"
                    )
            xor_expr = " ^ ".join(fold_parts)
            dout_assign = ", ".join(f"DOUTR{i}" for i in range(ew - 1, -1, -1))
            dout_stmt = f"    assign {{{dout_assign}}} = {xor_expr};"

    return f"""\
// Auto-generated altsyncram DUAL_PORT (SDP) template v{variant} ({width},{depth}).
module fuzz_top(
    {_port_decl(width, depth, "sdp")}
);
    wire [{addr_bits-1}:0] addrw = {{{addrw_bus}}};
    wire [{addr_bits-1}:0] addrr = {{{addrr_bus}}};
    wire [{width-1}:0]     din_w = {din_expr};
    wire [{width-1}:0]     dout;
    reg  [{width-1}:0]     dout_r;
    always @(posedge CLK) dout_r <= dout;
{dout_stmt}
{extra_pipe}

    altsyncram #(
        .operation_mode("DUAL_PORT"),
        .width_a({width}), .widthad_a({addr_bits}), .numwords_a({depth}),
        .width_b({width}), .widthad_b({addr_bits}), .numwords_b({depth}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .address_reg_b("CLOCK0"),
        .outdata_reg_b("UNREGISTERED"),
        .read_during_write_mode_mixed_ports("OLD_DATA"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_input_b("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .clock_enable_output_b("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK),
        .address_a(addrw), .data_a(din_w), .wren_a(WE_W),
        .address_b(addrr), .q_b(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .data_b({{{width}{{1'b0}}}}), .q_a(),
        .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _verilog_variant_tdp(width: int, depth: int, variant: int) -> str:
    """altsyncram BIDIR_DUAL_PORT (true dual-port) template.

    Both port A and port B read + write with independent addresses /
    wren; shared CLK (matches NEORV32 regfile = True Dual Port / Single
    Clock per fit.rpt) so the pin budget stays within the 45-pin
    PIN_POOL + PIN_E1 = 45 total.
    """
    addr_bits = _addr_bits(depth)
    ew = _fold_width(width)

    addra_bus = ", ".join(f"ADDRA{i}" for i in range(addr_bits - 1, -1, -1))
    addrb_bus = ", ".join(f"ADDRB{i}" for i in range(addr_bits - 1, -1, -1))

    def _din_shared() -> str:
        # Shared DIN pins feed both port A and port B inputs identically.
        # Quartus Verilog-2001 does not accept part-select of a
        # concatenation expression (`{N{...}}[hi:lo]`) — the slice has
        # to come from an identifier.  When the replicated width would
        # overflow, generate the expanded concatenation explicitly and
        # let Quartus truncate naturally during the wire assignment
        # (LHS width = `width`, RHS concat = reps*ew ≥ width; Quartus
        # takes the LSBs).
        if width <= ew:
            bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
            return f"{{{bus}}}"
        reps = (width + ew - 1) // ew
        per_rep = ", ".join(f"DIN{i}" for i in range(ew - 1, -1, -1))
        if reps * ew == width:
            return f"{{{reps}{{{{{per_rep}}}}}}}"
        # Emit `reps` explicit copies and LSB-truncate to `width`.
        pieces = [f"{{{per_rep}}}" for _ in range(reps)]
        # Keep only the lowest `width` bits out of `reps*ew` total.
        extra = reps * ew - width
        # Drop the leading `extra` MSB bits from the highest-order
        # replica so the total width matches.
        msb_keep = ew - extra
        top_bus = ", ".join(f"DIN{i}" for i in range(msb_keep - 1, -1, -1))
        pieces[0] = f"{{{top_bus}}}"
        return "{" + ", ".join(pieces) + "}"

    def _dout_fold_single(reg: str) -> str:
        # Fold a width-bit internal register/wire onto the ew-bit DOUT pad
        # bus via LSB-aligned XOR chunks.  All slicing happens on an
        # identifier (never on a concatenation expression) so the Quartus
        # Verilog-2001 parser is happy.
        if width <= ew:
            assign = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
            return f"    assign {{{assign}}} = {reg};"
        fold_parts: list[str] = []
        for i in range(0, width, ew):
            hi = min(i + ew - 1, width - 1)
            if hi - i + 1 == ew:
                fold_parts.append(f"{reg}[{hi}:{i}]")
            else:
                fold_parts.append(
                    f"{{{ew - (hi - i + 1)}'b0, {reg}[{hi}:{i}]}}"
                )
        xor_expr = " ^ ".join(fold_parts)
        assign = ", ".join(f"DOUT{i}" for i in range(ew - 1, -1, -1))
        return f"    assign {{{assign}}} = {xor_expr};"

    din_a_expr = _din_shared()
    din_b_expr = _din_shared()
    # Drive DOUT pins through a named combinational XOR wire
    # (`dout_sum = douta ^ doutb`) rather than piping user-space regs
    # in between M9K.q and the output pads — those get register-packed
    # into the M9K's outdata_reg_* slot, which collides with the TDP
    # mode's limited packable-register capacity and errors with
    # "Cannot place RAM cell ... location out of memory".  For the
    # mining goal we only need the altsyncram placed in the correct
    # operation_mode so the mode cells land in the expected block-band
    # frames — output-pin timing doesn't matter.
    common_wires = (
        f"    wire [{width-1}:0] dout_sum = douta ^ doutb;\n"
    )
    extra_pipe = ""
    dout_stmt = _dout_fold_single("dout_sum")
    if variant == 2:
        # Variant 2 registers the XOR combo in LE fabric (no M9K
        # interaction) so the per-variant intersection tightens under
        # pipe-depth change without re-triggering the packing error.
        extra_pipe = (
            f"    reg [{width-1}:0] dout_sum_q;\n"
            f"    always @(posedge CLK) dout_sum_q <= dout_sum;\n"
        )
        dout_stmt = _dout_fold_single("dout_sum_q")

    return f"""\
// Auto-generated altsyncram BIDIR_DUAL_PORT (TDP) template v{variant} ({width},{depth}).
module fuzz_top(
    {_port_decl(width, depth, "tdp")}
);
    wire [{addr_bits-1}:0] addra = {{{addra_bus}}};
    wire [{addr_bits-1}:0] addrb = {{{addrb_bus}}};
    wire [{width-1}:0]     din_a = {din_a_expr};
    wire [{width-1}:0]     din_b = {din_b_expr};
    wire [{width-1}:0]     douta, doutb;
{common_wires}{extra_pipe}
{dout_stmt}

    altsyncram #(
        .operation_mode("BIDIR_DUAL_PORT"),
        .width_a({width}), .widthad_a({addr_bits}), .numwords_a({depth}),
        .width_b({width}), .widthad_b({addr_bits}), .numwords_b({depth}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .outdata_reg_b("UNREGISTERED"),
        .address_reg_b("CLOCK0"),
        .indata_reg_b("CLOCK0"),
        .wrcontrol_wraddress_reg_b("CLOCK0"),
        .read_during_write_mode_port_a("OLD_DATA"),
        .read_during_write_mode_port_b("OLD_DATA"),
        .read_during_write_mode_mixed_ports("OLD_DATA"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_input_b("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .clock_enable_output_b("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK), .clock1(1'b1),
        .address_a(addra), .data_a(din_a), .wren_a(WE_A), .q_a(douta),
        .address_b(addrb), .data_b(din_b), .wren_b(WE_B), .q_b(doutb),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .rden_a(1'b1), .rden_b(1'b1)
    );
endmodule
"""


def _verilog_variant(width: int, depth: int, variant: int) -> str:
    """altsyncram template with instance name `u` (for LOC stability)."""
    addr_bits = _addr_bits(depth)
    ew = _fold_width(width)

    addr_bus = ", ".join(f"ADDR{i}" for i in range(addr_bits - 1, -1, -1))
    if width <= ew:
        din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
        din_expr = f"{{{din_bus}}}"
        dout_assign = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
        dout_stmt = f"    assign {{{dout_assign}}} = dout_r;"
    else:
        reps = (width + ew - 1) // ew
        din_parts = ", ".join(f"DIN{i}" for i in range(ew - 1, -1, -1))
        repl = f"{{{reps}{{{{{din_parts}}}}}}}"
        if reps * ew > width:
            repl += f"[{width - 1}:0]"
        din_expr = repl
        fold_parts = []
        for i in range(0, width, ew):
            hi = min(i + ew - 1, width - 1)
            if hi - i + 1 == ew:
                fold_parts.append(f"dout_r[{hi}:{i}]")
            else:
                fold_parts.append(
                    f"{{{ew - (hi - i + 1)}'b0, dout_r[{hi}:{i}]}}"
                )
        xor_expr = " ^ ".join(fold_parts)
        dout_assign = ", ".join(f"DOUT{i}" for i in range(ew - 1, -1, -1))
        dout_stmt = f"    assign {{{dout_assign}}} = {xor_expr};"

    # Variant 2 inserts an extra pipeline stage after dout_r
    extra_pipe = ""
    if variant == 2:
        extra_pipe = f"""
    reg [{width-1}:0] dout_q;
    always @(posedge CLK) dout_q <= dout_r;
"""
        if width <= ew:
            dout_stmt = f"    assign {{{', '.join(f'DOUT{i}' for i in range(width-1,-1,-1))}}} = dout_q;"
        else:
            fold_parts = []
            for i in range(0, width, ew):
                hi = min(i + ew - 1, width - 1)
                if hi - i + 1 == ew:
                    fold_parts.append(f"dout_q[{hi}:{i}]")
                else:
                    fold_parts.append(
                        f"{{{ew - (hi - i + 1)}'b0, dout_q[{hi}:{i}]}}"
                    )
            xor_expr = " ^ ".join(fold_parts)
            dout_assign = ", ".join(f"DOUT{i}" for i in range(ew - 1, -1, -1))
            dout_stmt = f"    assign {{{dout_assign}}} = {xor_expr};"

    return f"""\
// Auto-generated altsyncram template variant v{variant} ({width},{depth}).
module fuzz_top(
    {_port_decl(width, depth)}
);
    wire [{addr_bits-1}:0] addr = {{{addr_bus}}};
    wire [{width-1}:0]     din  = {din_expr};
    wire [{width-1}:0]     dout;
    reg  [{width-1}:0]     dout_r;
    always @(posedge CLK) dout_r <= dout;
{dout_stmt}
{extra_pipe}

    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a({width}), .widthad_a({addr_bits}), .numwords_a({depth}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .read_during_write_mode_port_a("OLD_DATA"),
        .read_during_write_mode_mixed_ports("DONT_CARE"),
        .indata_reg_b("CLOCK1"),
        .wrcontrol_wraddress_reg_b("CLOCK1"),
        .rdcontrol_reg_b("CLOCK1"),
        .address_reg_b("CLOCK1"),
        .outdata_reg_b("UNREGISTERED"),
        .byteena_reg_b("CLOCK1"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK), .address_a(addr), .data_a(din),
        .wren_a(WE), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{addr_bits}{{1'b0}}}}), .data_b({{{width}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _verilog_baseline(width: int, depth: int, mode: str = "sp") -> str:
    """No-M9K baseline with matched pinout for a given mode.

    Each DOUT* pin is a cheap XOR of the mode-specific input signals so
    Quartus doesn't optimise the ports away.  Pinout matches the
    corresponding --mode variant 1:1 so the variant⊕baseline diff is
    localized to M9K block cells only.
    """
    ew = _fold_width(width)
    addr_bits = _addr_bits(depth)
    lines: list[str] = []
    if mode == "sp":
        for i in range(ew):
            srcs = ["CLK", "WE",
                    f"ADDR{i % addr_bits}", f"DIN{i % ew}"]
            lines.append(f"    assign DOUT{i} = " + " ^ ".join(srcs) + ";")
    elif mode == "sdp":
        for i in range(ew):
            srcs = ["CLK", "WE_W",
                    f"ADDRW{i % addr_bits}", f"ADDRR{i % addr_bits}",
                    f"DIN{i % ew}"]
            lines.append(f"    assign DOUTR{i} = " + " ^ ".join(srcs) + ";")
    elif mode == "tdp":
        for i in range(ew):
            srcs = ["CLK", "WE_A", "WE_B",
                    f"ADDRA{i % addr_bits}", f"ADDRB{i % addr_bits}",
                    f"DIN{i % ew}"]
            lines.append(f"    assign DOUT{i} = " + " ^ ".join(srcs) + ";")
    else:
        raise ValueError(f"unknown mode {mode!r}")
    body = "\n".join(lines)
    return f"""\
// Auto-generated baseline (no M9K, mode={mode}) matched pinout for ({width},{depth}).
module fuzz_top(
    {_port_decl(width, depth, mode)}
);
{body}
endmodule
"""


def _verilog_for_mode(width: int, depth: int, variant: int, mode: str) -> str:
    if mode == "sp":
        return _verilog_variant(width, depth, variant)
    if mode == "sdp":
        return _verilog_variant_sdp(width, depth, variant)
    if mode == "tdp":
        return _verilog_variant_tdp(width, depth, variant)
    raise ValueError(f"unknown mode {mode!r}")


def _block_band_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    if len(a) != len(b):
        raise ValueError(f"length mismatch {len(a)} vs {len(b)}")
    out: set[tuple[int, int]] = set()
    lo = PREAMBLE + BLOCK_FRAME_LO * FRAME
    hi = PREAMBLE + (BLOCK_FRAME_HI + 1) * FRAME
    for off in range(lo, hi):
        if (off - PREAMBLE) % FRAME >= DATA_PER_FRAME:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bit in range(8):
            if x & (1 << bit):
                out.add((off, bit))
    return out


def _build_one(args) -> tuple[str, str | None, str]:
    project, proj_work, verilog, qsf, mif_text = args
    proj_dir = setup_project(project, verilog, qsf, str(proj_work))
    if mif_text is not None:
        (Path(proj_dir) / "mem_init.mif").write_text(mif_text)
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        return project, None, f"{err} ({el:.1f}s)"
    rbf = generate_rbf(project, proj_dir,
                       os.path.join(proj_work, f"{project}.rbf"))
    if rbf is None:
        return project, None, "RBF generation failed"
    return project, rbf, ""


def _mine_one(width: int, depth: int, n_variants: int,
              workers: int, only_analyze: bool) -> dict:
    combo_tag = f"{width}x{depth}"
    mode = SITE_MODE
    mode_tag = "" if mode == "sp" else f"_{mode}"
    bucket = _BUCKET_FOR_MODE[mode]
    # Encode site + mode in the per-run work dir so multiple site /
    # mode mining calls at the same (w, d) don't clobber each other's
    # baseline / variant RBFs.  The default-site / SP work dir keeps
    # the legacy path `tmp/m9k_mode_quartus_gold/{w}x{d}/` so
    # downstream smoke tests (scripts/m9k_e2e_smoke.py) continue
    # to find the X15_Y10_N0 SP artifacts at the path they expect.
    is_default_site = (SITE_X, SITE_Y, SITE_N) == (
        DEFAULT_SITE_X, DEFAULT_SITE_Y, DEFAULT_SITE_N)
    if is_default_site and mode == "sp":
        work = WORK_ROOT / combo_tag
    elif is_default_site:
        work = WORK_ROOT / combo_tag / mode
    else:
        site_tag = f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}"
        if mode == "sp":
            work = WORK_ROOT / combo_tag / site_tag
        else:
            work = WORK_ROOT / combo_tag / mode / site_tag
    work.mkdir(parents=True, exist_ok=True)

    print(f"\n=== mining ({width},{depth}) mode={mode} "
          f"@ X{SITE_X}_Y{SITE_Y}_N{SITE_N} ===")
    baseline_proj = f"m9k_mode_gold_{combo_tag}{mode_tag}_baseline"
    variant_projs = [
        f"m9k_mode_gold_{combo_tag}{mode_tag}_v{i}" for i in range(n_variants)
    ]

    jobs = []
    jobs.append((baseline_proj, work, _verilog_baseline(width, depth, mode),
                 _qsf_baseline(baseline_proj, width, depth, mode), None))
    for i, p in enumerate(variant_projs):
        jobs.append((p, work, _verilog_for_mode(width, depth, i, mode),
                     _qsf_variant(p, width, depth, mode),
                     _init_mif(width, depth, i)))

    if not only_analyze:
        print(f"[mine] building {len(jobs)} specimens (workers={workers})",
              flush=True)
        with mp.Pool(processes=max(1, workers)) as pool:
            results = list(pool.imap_unordered(_build_one, jobs))
        for proj, rbf, err in results:
            if rbf is None:
                print(f"  FAIL {proj}: {err}")
            else:
                print(f"  OK   {proj} -> {Path(rbf).name}")
        fails = [r for r in results if r[1] is None]
        if fails:
            return {"width": width, "depth": depth, "error": "build_failures",
                    "fails": [r[0] for r in fails]}

    def _rbf_for(proj: str) -> Path:
        return work / f"{proj}.rbf"

    bl_path = _rbf_for(baseline_proj)
    if not bl_path.exists():
        return {"width": width, "depth": depth,
                "error": f"baseline RBF missing: {bl_path}"}
    bl_bytes = bl_path.read_bytes()
    per_variant: list[set[tuple[int, int]]] = []
    per_variant_size: list[int] = []
    for p in variant_projs:
        vp = _rbf_for(p)
        if not vp.exists():
            print(f"  SKIP {p}: RBF missing")
            continue
        v = vp.read_bytes()
        cells = _block_band_cells(bl_bytes, v)
        per_variant.append(cells)
        per_variant_size.append(len(cells))
        print(f"  {p}: {len(cells)} block-band cells vs matched baseline")

    if not per_variant:
        return {"width": width, "depth": depth, "error": "no variants built"}

    gold_cells = set.intersection(*per_variant)
    print(f"[mine] intersection across {len(per_variant)} builds: "
          f"{len(gold_cells)} cells  (sizes={per_variant_size})")

    if RESULTS_PATH.exists():
        mode_bits = json.loads(RESULTS_PATH.read_text())
    else:
        mode_bits = {}
    key = f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}_{combo_tag}"
    entry = mode_bits.get(key, {
        "site": f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}",
        "width": width,
        "depth": depth,
    })
    cbt = entry.get("cells_by_template", {})
    cbt[bucket] = sorted(gold_cells)
    entry["cells_by_template"] = cbt
    # Preserve legacy gi / inferred / altsyncram buckets if this is a
    # first-time entry at (X15, Y10) for this (w, d); copy them from
    # any sibling site with the same geometry so downstream loaders
    # (tests, fasm2rbf fallback path) keep working.
    suffix = f"_{combo_tag}"
    for sibling_key, sibling_entry in mode_bits.items():
        if sibling_key == key or not sibling_key.endswith(suffix):
            continue
        sibling_cbt = sibling_entry.get("cells_by_template", {})
        # NB: different loop var (`legacy_bucket`, not `bucket`) so the
        # outer `bucket` from `_BUCKET_FOR_MODE[mode]` isn't shadowed —
        # prior shadowing wrote the provenance to
        # `inferred_goldintersect_source` for every SDP/TDP mining run.
        for legacy_bucket in ("altsyncram", "inferred", "inferred_goldintersect"):
            if legacy_bucket in sibling_cbt and legacy_bucket not in cbt:
                cbt[legacy_bucket] = list(sibling_cbt[legacy_bucket])
        if "cells" in sibling_entry and "cells" not in entry:
            entry["cells"] = list(sibling_entry["cells"])
        break
    provenance_key = f"{bucket}_source"
    entry[provenance_key] = {
        "date": time.strftime("%Y-%m-%d"),
        "script": "scripts/m9k_mode_quartus_gold_mine.py",
        "operation_mode": _OPMODE_FOR_MODE[mode],
        "mining_mode": mode,
        "n_variants": len(per_variant),
        "variant_sizes": per_variant_size,
        "variants": variant_projs,
        "baseline_proj": baseline_proj,
        "note": f"Site-specific X{SITE_X}_Y{SITE_Y}_N{SITE_N} mode={mode}, "
                f"mode-invariant under INIT/WE/read-pipe variation.",
    }
    mode_bits[key] = entry

    tmp = str(RESULTS_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mode_bits, f, indent=2, default=list)
    os.replace(tmp, str(RESULTS_PATH))
    print(f"[mine] merged quartus_gold ({len(gold_cells)} cells) into {key}")

    return {"width": width, "depth": depth,
            "mode": mode,
            "bucket": bucket,
            "n_variants": len(per_variant),
            "variant_sizes": per_variant_size,
            "gold_cells": len(gold_cells),
            "key": key}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int)
    ap.add_argument("--depth", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only-analyze", action="store_true")
    ap.add_argument("--site", default=f"{DEFAULT_SITE_X},{DEFAULT_SITE_Y},{DEFAULT_SITE_N}",
                    help="M9K site as X,Y,N (default 15,10,0). Real Quartus "
                         "mode cells shift per Y within an M9K column — mine "
                         "each site that np2fasm expects to emit for.")
    ap.add_argument("--mode", choices=("sp", "sdp", "tdp"), default="sp",
                    help="altsyncram operation_mode (sp=SINGLE_PORT default, "
                         "sdp=DUAL_PORT for NEORV32 dmem/imem 8x2048, "
                         "tdp=BIDIR_DUAL_PORT for NEORV32 regfile 32x32). "
                         "Mined cells land in "
                         "cells_by_template['quartus_gold'|'_sdp'|'_tdp'].")
    args = ap.parse_args()

    global SITE_X, SITE_Y, SITE_N, SITE_MODE
    try:
        SITE_X, SITE_Y, SITE_N = (int(s) for s in args.site.split(","))
    except ValueError:
        ap.error(f"--site must be X,Y,N; got {args.site!r}")
        return 1
    SITE_MODE = args.mode

    if args.all:
        combos = TARGET_COMBOS_BY_MODE[SITE_MODE]
    elif args.width and args.depth:
        combos = [(args.width, args.depth)]
    else:
        ap.error("specify --width W --depth D or --all")
        return 1

    summary = []
    for w, d in combos:
        summary.append(_mine_one(w, d, args.variants, args.workers,
                                 args.only_analyze))

    print("\n=== summary ===")
    for r in summary:
        if "error" in r:
            print(f"  ({r['width']},{r['depth']}): ERROR {r['error']}")
        else:
            print(f"  ({r['width']},{r['depth']}): "
                  f"gold={r['gold_cells']} from {r['n_variants']} builds; "
                  f"sizes={r['variant_sizes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
