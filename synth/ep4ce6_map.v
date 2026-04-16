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
// M9K BRAM techmap.
//
// Maps Yosys's libmap-emitted `$__M9K_SP_` cell (declared in
// `synth/m9k.lib`) to the EP4CE6_M9K blackbox declared in
// `synth/prims.v`.  np2fasm's `_emit_m9k_init` is wired to extract
// the matching `M9K.INIT_{w}x{d}` directives.  Pin mapping follows
// the m9k.lib `$__M9K_SP_` port spec (port "A": clock posedge, srsw,
// clken).  SDP / TDP rules will be added as separate stanzas.
// Port names (PORT_A_*) follow Yosys's `memory_libmap` calling
// convention — same scheme used by gowin/brams_map.v upstream. The
// older `memory_bram`-format names (A1ADDR/A1DATA/A1EN) do NOT match
// what libmap emits and would leave `$__M9K_SP_` unmapped.
module \$__M9K_SP_ (...);
	parameter INIT = 0;
	parameter PORT_A_WIDTH = 9;
	parameter PORT_A_WR_BE_WIDTH = 1;
	parameter PORT_A_OPTION_WRITE_MODE = 0;
	input  PORT_A_CLK;
	input  PORT_A_CLK_EN;
	input  PORT_A_WR_EN;
	input  [12:0] PORT_A_ADDR;
	input  [PORT_A_WR_BE_WIDTH-1:0] PORT_A_WR_BE;
	input  [PORT_A_WIDTH-1:0] PORT_A_WR_DATA;
	output [PORT_A_WIDTH-1:0] PORT_A_RD_DATA;
	// Fixed 36-bit DOUT sink + slice (same fix as SDP/TDP rules) so
	// PORT_A_WIDTH=36 doesn't overflow EP4CE6_M9K's 36-bit DOUT_A port.
	wire [35:0] _m9k_sp_dout_full;
	// M9K capacity is 8 192 data bits (widths 1/2/4) or 9 216 bits incl.
	// parity (widths 9/18/36); pick the matching depth.
	localparam M9K_DEPTH = (PORT_A_WIDTH <= 8)
		? (8192 / PORT_A_WIDTH)
		: (9216 / PORT_A_WIDTH);
	assign PORT_A_RD_DATA = _m9k_sp_dout_full[PORT_A_WIDTH-1:0];
	EP4CE6_M9K #(
		.INIT(INIT),
		.WIDTH_A(PORT_A_WIDTH),
		.DEPTH(M9K_DEPTH),
		.MODE("SP")
	) _TECHMAP_REPLACE_ (
		.CLK_A (PORT_A_CLK),
		.WE_A  (PORT_A_WR_EN & PORT_A_CLK_EN),
		.RE_A  (PORT_A_CLK_EN),
		.ADDR_A(PORT_A_ADDR),
		.DIN_A ({{(36 - PORT_A_WIDTH){1'b0}}, PORT_A_WR_DATA}),
		.DOUT_A(_m9k_sp_dout_full)
	);
endmodule
// ---------------------------------------------------------------------------
// $__M9K_SDP_ (simple dual-port: independent R + W, separate clocks).
// memory_libmap names the read side PORT_R_* and write side PORT_W_*.
// We map W → port A (write side of EP4CE6_M9K) and R → port B (read side).
// Geometry: 9 216 data bits incl. parity → DEPTH = 9216 / max(R_W,W_W).
// NEORV32's regfile uses width=36 / depth=32; deeper / narrower configs
// (e.g. 9×1024) drop into the same formula.
//
// STATUS: scaffold to unblock nextpnr-generic JSON parse on NEORV32.
// Not yet exercised end-to-end (no SDP smoke build); revisit alongside
// Stage C.3 once a single-leaf SDP design lands.
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
	// Sink wire for the unused upper bits of DOUT_B (output read data is
	// always 36 bits at the EP4CE6_M9K level, regardless of the user's
	// requested PORT_R_WIDTH). Use a fixed 36-bit sink and slice the
	// requested width off the bottom — avoids the [35:PORT_R_WIDTH]
	// reverse-range trap when PORT_R_WIDTH=36 (which Yosys treats as
	// a 2-bit wire and overflows the EP4CE6_M9K port).
	wire [35:0] _m9k_sdp_doutb_full;
	localparam _MAX_W = (PORT_R_WIDTH > PORT_W_WIDTH)
		? PORT_R_WIDTH : PORT_W_WIDTH;
	localparam M9K_DEPTH = (_MAX_W <= 8)
		? (8192 / _MAX_W)
		: (9216 / _MAX_W);
	assign PORT_R_RD_DATA = _m9k_sdp_doutb_full[PORT_R_WIDTH-1:0];
	EP4CE6_M9K #(
		.INIT(INIT),
		.WIDTH_A(PORT_W_WIDTH),
		.WIDTH_B(PORT_R_WIDTH),
		.DEPTH(M9K_DEPTH),
		.MODE("SDP")
	) _TECHMAP_REPLACE_ (
		.CLK_A (PORT_W_CLK),
		.WE_A  (PORT_W_WR_EN & PORT_W_CLK_EN),
		.RE_A  (1'b0),
		.ADDR_A(PORT_W_ADDR),
		.DIN_A ({{(36 - PORT_W_WIDTH){1'b0}}, PORT_W_WR_DATA}),
		.DOUT_A(),
		.CLK_B (PORT_R_CLK),
		.WE_B  (1'b0),
		.RE_B  (PORT_R_CLK_EN),
		.ADDR_B(PORT_R_ADDR),
		.DIN_B (36'd0),
		.DOUT_B(_m9k_sdp_doutb_full)
	);
endmodule
// ---------------------------------------------------------------------------
// $__M9K_TDP_ (true dual-port: independent A + B, both R/W).
// memory_libmap names ports PORT_A_* / PORT_B_*. Direct 1:1 to EP4CE6_M9K.
//
// STATUS: scaffold (no NEORV32 design uses TDP; included for completeness
// so the techmap leaves no $-prefixed memory cells behind).
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
	// Fixed-width DOUT sinks: same fix as the SDP rule — slice off the
	// requested width instead of using a reverse-range upper-bits wire,
	// so that PORT_*_WIDTH=36 doesn't overflow EP4CE6_M9K's 36-bit port.
	wire [35:0] _m9k_tdp_douta_full;
	wire [35:0] _m9k_tdp_doutb_full;
	localparam _MAX_W = (PORT_A_WIDTH > PORT_B_WIDTH)
		? PORT_A_WIDTH : PORT_B_WIDTH;
	localparam M9K_DEPTH = (_MAX_W <= 8)
		? (8192 / _MAX_W)
		: (9216 / _MAX_W);
	assign PORT_A_RD_DATA = _m9k_tdp_douta_full[PORT_A_WIDTH-1:0];
	assign PORT_B_RD_DATA = _m9k_tdp_doutb_full[PORT_B_WIDTH-1:0];
	EP4CE6_M9K #(
		.INIT(INIT),
		.WIDTH_A(PORT_A_WIDTH),
		.WIDTH_B(PORT_B_WIDTH),
		.DEPTH(M9K_DEPTH),
		.MODE("TDP")
	) _TECHMAP_REPLACE_ (
		.CLK_A (PORT_A_CLK),
		.WE_A  (PORT_A_WR_EN & PORT_A_CLK_EN),
		.RE_A  (PORT_A_CLK_EN),
		.ADDR_A(PORT_A_ADDR),
		.DIN_A ({{(36 - PORT_A_WIDTH){1'b0}}, PORT_A_WR_DATA}),
		.DOUT_A(_m9k_tdp_douta_full),
		.CLK_B (PORT_B_CLK),
		.WE_B  (PORT_B_WR_EN & PORT_B_CLK_EN),
		.RE_B  (PORT_B_CLK_EN),
		.ADDR_B(PORT_B_ADDR),
		.DIN_B ({{(36 - PORT_B_WIDTH){1'b0}}, PORT_B_WR_DATA}),
		.DOUT_B(_m9k_tdp_doutb_full)
	);
endmodule
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
