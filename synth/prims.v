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
