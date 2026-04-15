// SPDX-License-Identifier: GPL-3.0-or-later
// EP4CE6 techmap for nextpnr-generic. Matches the canonical cell
// names/pins used by nextpnr's default generic packer (upstream
// generic/synth/cells_map.v): LUT with vector I / output Q, and DFF
// with D/CLK/Q.
module \$lut (A, Y);
	parameter WIDTH = 0;
	parameter LUT = 0;
	input  [WIDTH-1:0] A;
	output Y;
	localparam rep = 1 << (4 - WIDTH);
	LUT #(.K(4), .INIT({rep{LUT}})) _TECHMAP_REPLACE_ (
		.I({ {(4-WIDTH){1'b0}}, A }), .Q(Y));
endmodule

module \$_DFF_P_ (input D, C, output Q);
	DFF _TECHMAP_REPLACE_ (.D(D), .CLK(C), .Q(Q));
endmodule

// $alu → per-bit CE6_CARRY chain. Yosys's alumacc pass folds $add,
// $sub and compares into $alu, so this one rule covers all of them.
//
// BI handles $sub's two's-complement via (B ^ BI) per bit; when BI
// is a constant (the common case) Yosys const-folds this out before
// synthesis sees it.
//
// Chain-start: the LSB's CI port is wired to $alu.CI. For $add /
// incrementers Yosys feeds a constant 1'b0; for $sub it's 1'b1.
// np2fasm detects the chain-start by checking whether the LSB
// CE6_CARRY's CI net is driven by a constant (chain start) or by a
// prior CE6_CARRY's CO (mid-chain).
//
// LE-internal feedback (2026-04-13, replacing Route-A buffers):
// Quartus carry counters have ZERO external route cells — DFF.Q →
// carry input feedback is LE-internal on Cyclone IV silicon. The
// previous Route-A approach inserted a LUT1 identity buffer per bit
// to break the self-loop into two routable arcs; this doubled LE
// usage and required sig-cache coverage for the buffer→carry route.
// Now we connect B_used directly to CE6_CARRY.B and rely on the
// LE-internal feedback path — no LI MUX routing needed, no CRAM
// cells to flip. np2fasm skips ROUTE emission for same-LE arcs.
// ---------------------------------------------------------------------------
// M9K BRAM techmap — DRAFT, DISABLED.
//
// This rule maps Yosys's libmap-emitted `$__M9K_SP_` cell (declared in
// `synth/m9k.lib`) to the EP4CE6_M9K blackbox declared in
// `synth/prims.v`.  The downstream pipeline (np2fasm + nextpnr-generic
// chipdb M9K bels) does not yet have working M9K placement and INIT
// extraction, so the rule is gated behind `M9K_TECHMAP`.  When you're
// ready to test end-to-end, enable by adding `-D M9K_TECHMAP` to the
// `techmap -map synth/ep4ce6_map.v` invocation in `synth_ep4ce6.ys`,
// or unconditionally, once np2fasm grows the matching `EP4CE6_M9K →
// M9K.INIT` extraction (see `synth/np2fasm.py:_emit_m9k_init` stub).
//
// Pin mapping below follows the m9k.lib `$__M9K_SP_` port spec
// (port "A": clock posedge, srsw, clken).  SDP / TDP rules will be
// added as separate stanzas.  All disabled until the np2fasm side is
// drafted in lockstep.
`ifdef M9K_TECHMAP
module \$__M9K_SP_ (CLK_A, A1ADDR, A1DATA, A1EN, B1ADDR, B1DATA, B1EN);
	parameter INIT = 0;
	parameter PORT_A_WIDTH = 9;
	parameter PORT_A_WR_BE_WIDTH = 1;
	parameter PORT_A_OPTION_WRITE_MODE = 0;
	input  CLK_A;
	input  [12:0] A1ADDR;
	input  [PORT_A_WIDTH-1:0] A1DATA;
	input  [PORT_A_WR_BE_WIDTH-1:0] A1EN;
	input  [12:0] B1ADDR;
	output [PORT_A_WIDTH-1:0] B1DATA;
	input  B1EN;
	EP4CE6_M9K #(
		.INIT(INIT),
		.WIDTH_A(PORT_A_WIDTH),
		.DEPTH(8192 / PORT_A_WIDTH),
		.MODE("SP")
	) _TECHMAP_REPLACE_ (
		.CLK_A (CLK_A),
		.WE_A  (|A1EN),
		.RE_A  (B1EN),
		.ADDR_A(A1ADDR),
		.DIN_A ({{(36 - PORT_A_WIDTH){1'b0}}, A1DATA}),
		.DOUT_A(/* connected externally */)
	);
endmodule
`endif
// ---------------------------------------------------------------------------

module \$alu (A, B, CI, BI, X, Y, CO);
	parameter A_SIGNED = 0;
	parameter B_SIGNED = 0;
	parameter A_WIDTH = 1;
	parameter B_WIDTH = 1;
	parameter Y_WIDTH = 1;

	input  [A_WIDTH-1:0] A;
	input  [B_WIDTH-1:0] B;
	input  CI, BI;
	output [Y_WIDTH-1:0] X, Y, CO;

	wire [Y_WIDTH-1:0] A_ext, B_ext;
	\$pos #(
		.A_SIGNED(A_SIGNED), .A_WIDTH(A_WIDTH), .Y_WIDTH(Y_WIDTH)
	) Aext (.A(A), .Y(A_ext));
	\$pos #(
		.A_SIGNED(B_SIGNED), .A_WIDTH(B_WIDTH), .Y_WIDTH(Y_WIDTH)
	) Bext (.A(B), .Y(B_ext));

	wire [Y_WIDTH-1:0] B_used = B_ext ^ {Y_WIDTH{BI}};

	wire [Y_WIDTH:0] C;
	assign C[0] = CI;

	assign X = A_ext ^ B_used;

	genvar i;
	generate
		for (i = 0; i < Y_WIDTH; i = i + 1) begin : chain
			CE6_CARRY #(
				.LUT_MASK(16'h96E8)
			) bit_ (
				.A(A_ext[i]),
				.B(B_used[i]),
				.CI(C[i]),
				.S(Y[i]),
				.CO(C[i+1])
			);
		end
	endgenerate

	assign CO = C[Y_WIDTH:1];
endmodule
