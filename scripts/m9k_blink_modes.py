# SPDX-License-Identifier: GPL-3.0-or-later
"""Verilog templates for full-width m9k_blink builders across modes.

Each render_<mode>(w, d) returns a Verilog file that forces Quartus to
emit a single M9K in the requested mode and shape, without collapsing
the width/depth via optimization.  The XOR-reduce-DOUT-to-LED trick
from scripts/m9k_blink_full_build.py is reused to keep DOUT live.

LOC the resulting altsyncram instance via the QSF target string in
``LOC_TARGETS[mode]`` (the path Quartus exposes after inference).

Modes:
  - sp  : single-port RAM (read+write share the address)
  - sdp : simple dual-port (separate read/write addresses, 1 clock)
  - tdp : true dual-port (two independent read/write ports)
  - rom : read-only memory with initial data

The Verilog parts that change between modes:
  - port list / wire decls
  - always block(s)
  - DOUT live-out reduction

The scaffolding (counter address generation, DIN driving, LED reduction
of port-A DOUT) is shared.
"""
from __future__ import annotations

import math


def _addr_bits(d: int) -> int:
    if d <= 1:
        return 1
    return int(math.ceil(math.log2(d)))


def _din_expr(w: int) -> str:
    """w-bit DIN expression alternating KEY3/KEY2 so every bit is live."""
    bits = []
    for i in range(w):
        bits.append("KEY3" if (i % 2 == 0) else "KEY2")
    return "{" + ", ".join(bits[::-1]) + "}"


def render_sp(w: int, d: int) -> str:
    """Single-port RAM, width=w, depth=d."""
    ab = _addr_bits(d)
    din = _din_expr(w)
    return f"""\
module m9k_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [{ab-1}:0] addr = counter[27 -: {ab}];
    wire        we   = ~KEY2;
    wire [{w-1}:0] din  = {din};

    (* ramstyle = "M9K" *) reg [{w-1}:0] mem [0:{d-1}];
    integer i;
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem[i] = (i < {d//2}) ? {{{w}{{1'b0}}}} : {{{w}{{1'b1}}}};
    end

    reg [{w-1}:0] dout_r;
    always @(posedge CLK) begin
        if (we) mem[addr] <= din;
        dout_r <= mem[addr];
    end

    assign LED0 = ^dout_r;
endmodule
"""


def render_sdp(w: int, d: int) -> str:
    """Simple dual-port: separate write_addr / read_addr, single clock."""
    ab = _addr_bits(d)
    din = _din_expr(w)
    return f"""\
module m9k_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [{ab-1}:0] waddr = counter[27 -: {ab}];
    wire [{ab-1}:0] raddr = counter[26 -: {ab}];
    wire        we    = ~KEY2;
    wire [{w-1}:0] din   = {din};

    (* ramstyle = "M9K" *) reg [{w-1}:0] mem [0:{d-1}];
    integer i;
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem[i] = (i < {d//2}) ? {{{w}{{1'b0}}}} : {{{w}{{1'b1}}}};
    end

    reg [{w-1}:0] dout_r;
    always @(posedge CLK) begin
        if (we) mem[waddr] <= din;
        dout_r <= mem[raddr];
    end

    assign LED0 = ^dout_r;
endmodule
"""


def render_tdp(w: int, d: int) -> str:
    """True dual-port: two independent read/write ports, single clock."""
    ab = _addr_bits(d)
    din = _din_expr(w)
    return f"""\
module m9k_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [{ab-1}:0] addr_a = counter[27 -: {ab}];
    wire [{ab-1}:0] addr_b = counter[26 -: {ab}];
    wire        we_a   = ~KEY2;
    wire        we_b   =  KEY2;
    wire [{w-1}:0] din_a = {din};
    wire [{w-1}:0] din_b = ~{din};

    (* ramstyle = "M9K" *) reg [{w-1}:0] mem [0:{d-1}];
    integer i;
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem[i] = (i < {d//2}) ? {{{w}{{1'b0}}}} : {{{w}{{1'b1}}}};
    end

    reg [{w-1}:0] dout_a, dout_b;
    always @(posedge CLK) begin
        if (we_a) mem[addr_a] <= din_a;
        dout_a <= mem[addr_a];
    end
    always @(posedge CLK) begin
        if (we_b) mem[addr_b] <= din_b;
        dout_b <= mem[addr_b];
    end

    assign LED0 = ^dout_a ^ ^dout_b;
endmodule
"""


def render_rom(w: int, d: int) -> str:
    """ROM: read-only, initial data, no writes.

    Variable name MUST be `mem` so Quartus auto-generates the inferred
    altsyncram instance as `altsyncram:mem_rtl_0` — matching the QSF
    LOC target.  Using any other name (e.g. `rom`) silently breaks the
    LOC binding (Quartus places the M9K wherever it likes; LOC is
    parsed but doesn't bind to any matching node) and yields byte-
    identical RBFs across all Y assignments.
    """
    ab = _addr_bits(d)
    return f"""\
module m9k_blink(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire [{ab-1}:0] addr = counter[27 -: {ab}] ^ {{{ab}{{KEY3}}}};

    (* ramstyle = "M9K" *) reg [{w-1}:0] mem [0:{d-1}];
    integer i;
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem[i] = i[{w-1}:0] ^ {{{w}{{1'b1}}}};
    end

    reg [{w-1}:0] dout_r;
    always @(posedge CLK) dout_r <= mem[addr];

    assign LED0 = ^dout_r ^ KEY2;
endmodule
"""


RENDERERS = {
    "sp":  render_sp,
    "sdp": render_sdp,
    "tdp": render_tdp,
    "rom": render_rom,
}


# LOC target string (after the colon in the QSF set_location_assignment).
# For inferred altsyncram, this is the canonical instance path Quartus
# emits regardless of mode.  The ":mem_rtl_0" suffix matches the
# auto-generated wrapper from the inference flow (see
# m9k_mining_loc_fix_silicon_validated_2026_04_28.md).
LOC_TARGET = "altsyncram:mem_rtl_0"


def render_qsf(mode: str, w: int, d: int, x: int, y: int, n: int) -> str:
    return f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY m9k_blink
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
set_location_assignment M9K_X{x}_Y{y}_N{n} -to "{LOC_TARGET}"
"""


import subprocess
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_WORK_ROOT = _ROOT / "tmp"


def work_dir(mode: str, w: int, d: int, x: int, y: int, n: int) -> Path:
    return _WORK_ROOT / f"m9k_blink_{mode}_{w}x{d}_X{x}_Y{y}_N{n}"


def rbf_path(mode: str, w: int, d: int, x: int, y: int, n: int) -> Path:
    return work_dir(mode, w, d, x, y, n) / f"m9k_blink_{mode}_{w}x{d}_X{x}_Y{y}_N{n}.rbf"


def build_one(mode: str, w: int, d: int, x: int, y: int, n: int = 0) -> Path | None:
    """Run quartus_map → fit → asm → cpf for one (mode, w, d, site)."""
    if mode not in RENDERERS:
        raise ValueError(f"unknown mode {mode!r}, expected one of {list(RENDERERS)}")
    work = work_dir(mode, w, d, x, y, n)
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(RENDERERS[mode](w, d))
    (work / "fuzz_top.qsf").write_text(render_qsf(mode, w, d, x, y, n))
    rbf = rbf_path(mode, w, d, x, y, n)
    if rbf.exists():
        print(f"  exists: {rbf.relative_to(_ROOT)}")
        return rbf
    qbin = Path.home() / "intelFPGA_lite/21.1/quartus/bin"
    import os
    env = {**os.environ, "PATH": f"{qbin}:" + os.environ.get("PATH", "")}
    for tool in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run([str(qbin / tool), "fuzz_top",
                            "--read_settings_files=on",
                            "--write_settings_files=off"],
                           cwd=work, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAIL {tool}: {r.stderr[-300:]}")
            return None
    r = subprocess.run([str(qbin / "quartus_cpf"), "-c",
                        "-o", "bitstream_compression=off",
                        "output_files/fuzz_top.sof", str(rbf)],
                       cwd=work, env=env, capture_output=True, text=True)
    if r.returncode != 0 or not rbf.exists():
        print(f"  FAIL cpf: {r.stderr[-300:]}")
        return None
    return rbf
