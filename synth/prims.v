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
