// SPDX-License-Identifier: GPL-3.0-or-later
// Primitive blackbox declarations for nextpnr-generic EP4CE6 flow.
// Read by Yosys before techmap so the emitted JSON carries explicit
// port_directions for LUT / DFF / GENERIC_SLICE / GENERIC_IOB.
// Adapted from nextpnr upstream generic/synth/prims.v (K fixed to 4).

(* blackbox *)
module LUT #(
	parameter K = 4,
	parameter [2**K-1:0] INIT = 0
) (
	input  [K-1:0] I,
	output         Q
);
endmodule

(* blackbox *)
module DFF (
	input      CLK,
	input      D,
	output reg Q
);
endmodule

(* blackbox *)
module GENERIC_SLICE #(
	parameter K = 4,
	parameter [2**K-1:0] INIT = 0,
	parameter FF_USED = 1'b0
) (
	input          CLK,
	input  [K-1:0] I,
	output         F,
	output         Q
);
endmodule

// Carry chain primitive — one per bit of an arithmetic operation.
// Placed into an arith-mode LE; chained cells occupy contiguous N
// slots in a LAB, with N30 wrapping to N0 of the LAB directly below
// (per cycloneive_carry_chain_topology memory, validated at X=10).
//
// CI routing: CI is a real port. For mid-chain cells it's driven
//   by the previous CE6_CARRY's CO, which nextpnr will route via
//   the dedicated cout→cin carry pip (no LI MUX). For the LSB of
//   each chain it's driven by a Verilog constant (1'b0 for $add,
//   1'b1 for $sub); np2fasm detects this and programs the Cyclone
//   IV silicon chain-start CRAM bit accordingly.
// LUT_MASK: 16-bit arith-mode LUT encoding. Upper byte = sum LUT,
//   lower byte = cout LUT (see cycloneive_arith_mode_lut_encoding).
//   Techmap hardcodes this to 0x96E8 for $alu (a+b+ci); arbitrary
//   user-supplied arith LUTs are out of scope for this pass.
(* blackbox *)
module CE6_CARRY #(
	parameter [15:0] LUT_MASK = 16'h0000
) (
	input  A,
	input  B,
	input  CI,
	output S,
	output CO
);
endmodule

(* blackbox *)
module GENERIC_IOB #(
	parameter INPUT_USED = 1'b0,
	parameter OUTPUT_USED = 1'b0,
	parameter ENABLE_USED = 1'b0
) (
	inout  PAD,
	input  I,
	input  EN,
	output O
);
endmodule

// $__M9K_SDP_ / $__M9K_TDP_ — Yosys libmap-emitted memory cells.
// Declared as blackboxes only so nextpnr-generic can parse the JSON
// without "Failed to get direction" errors. Lowering to EP4CE6_M9K
// belongs in synth/ep4ce6_map.v (Stage C.3 SDP/TDP techmap rules).
(* blackbox *)
module \$__M9K_SDP_ (...);
	parameter INIT = 0;
	parameter PORT_R_WIDTH = 9;
	parameter PORT_W_WIDTH = 9;
	parameter PORT_W_WR_BE_WIDTH = 1;
	input  PORT_R_CLK;
	input  PORT_R_CLK_EN;
	input  [12:0] PORT_R_ADDR;
	output [PORT_R_WIDTH-1:0] PORT_R_RD_DATA;
	input  PORT_W_CLK;
	input  PORT_W_CLK_EN;
	input  PORT_W_WR_EN;
	input  [12:0] PORT_W_ADDR;
	input  [PORT_W_WR_BE_WIDTH-1:0] PORT_W_WR_BE;
	input  [PORT_W_WIDTH-1:0] PORT_W_WR_DATA;
endmodule

(* blackbox *)
module \$__M9K_TDP_ (...);
	parameter INIT = 0;
	parameter PORT_A_WIDTH = 9;
	parameter PORT_B_WIDTH = 9;
	parameter PORT_A_WR_BE_WIDTH = 1;
	parameter PORT_B_WR_BE_WIDTH = 1;
	parameter PORT_A_OPTION_WRITE_MODE = 0;
	parameter PORT_B_OPTION_WRITE_MODE = 0;
	input  PORT_A_CLK;
	input  PORT_A_CLK_EN;
	input  PORT_A_WR_EN;
	input  [12:0] PORT_A_ADDR;
	input  [PORT_A_WR_BE_WIDTH-1:0] PORT_A_WR_BE;
	input  [PORT_A_WIDTH-1:0] PORT_A_WR_DATA;
	output [PORT_A_WIDTH-1:0] PORT_A_RD_DATA;
	input  PORT_B_CLK;
	input  PORT_B_CLK_EN;
	input  PORT_B_WR_EN;
	input  [12:0] PORT_B_ADDR;
	input  [PORT_B_WR_BE_WIDTH-1:0] PORT_B_WR_BE;
	input  [PORT_B_WIDTH-1:0] PORT_B_WR_DATA;
	output [PORT_B_WIDTH-1:0] PORT_B_RD_DATA;
endmodule

// EP4CE6_M9K — single-port M9K BRAM blackbox stub for nextpnr-generic.
//
// STATUS: STUB ONLY.  Wired into the chipdb (`fuzz/chipdb_gen.py`
// emits one EP4CE6_M9K bel per (X∈{15,27}, Y∈[2..21], N=0) site with
// an `anchor` attribute pulled from `M9K_INIT_ANCHORS`), and into the
// fasm2rbf `M9K.INIT_{w}x{d}` directive.  NOT YET wired into the
// Yosys → np2fasm → fasm2rbf pipeline:
//
//   - `synth/m9k.lib` already declares `$__M9K_SP_` / `$__M9K_SDP_` /
//     `$__M9K_TDP_` for `memory_libmap`, but no techmap rule yet
//     converts those library cells into placeable primitives that
//     nextpnr can route.  See draft `\$__M9K_SP_` rule in
//     `synth/ep4ce6_map.v` (currently inside an `M9K_TECHMAP` ifdef
//     so it stays inert until end-to-end is proven).
//   - `synth/np2fasm.py` does not yet recognize M9K cells / extract
//     INIT parameters.  See the `_emit_m9k_init` stub in np2fasm.py.
//
// Port set is the union of the three modes (single-port / SDP / TDP).
// In single-port mode only port A is used; in SDP only R + W; in TDP
// both A + B.  INIT is a flat bit vector (depth*width bits, LSB-first
// as Yosys conventions require).
(* blackbox *)
module EP4CE6_M9K #(
	parameter INIT      = 0,
	parameter WIDTH_A   = 9,
	parameter WIDTH_B   = 9,
	parameter DEPTH     = 512,
	parameter MODE      = "SP"   // "SP" | "SDP" | "TDP"
) (
	// Port A (used by SP / TDP)
	input               CLK_A,
	input               WE_A,
	input               RE_A,
	input  [12:0]       ADDR_A,
	input  [35:0]       DIN_A,
	output [35:0]       DOUT_A,
	// Port B (used by SDP read / TDP)
	input               CLK_B,
	input               WE_B,
	input               RE_B,
	input  [12:0]       ADDR_B,
	input  [35:0]       DIN_B,
	output [35:0]       DOUT_B
);
endmodule
