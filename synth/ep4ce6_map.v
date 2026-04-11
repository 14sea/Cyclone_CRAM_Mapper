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
// Per-bit is deliberate: the Cyclone IV silicon carry is per-LE and
// the packer gets best placement freedom when each bit is its own
// cell (see chipdb_carry_pips_piece2 memory).
//
// BI handles $sub's two's-complement via (B ^ BI) per bit; when BI
// is a constant (the common case) Yosys const-folds this out before
// synthesis sees it.
//
// Chain-start: the LSB's CI port is wired to $alu.CI. For $add /
// incrementers Yosys feeds a constant 1'b0; for $sub it's 1'b1.
// np2fasm detects the chain-start by checking whether the LSB
// CE6_CARRY's CI net is driven by a constant (chain start) or by a
// prior CE6_CARRY's CO (mid-chain) and sets the silicon chain-start
// CRAM bit accordingly.  Real-net CI (carry passed in from outside
// an $alu, e.g. cascaded arithmetic) is not yet supported and will
// raise an error at np2fasm time.
//
// LUT_MASK: arith-mode LUT encoding for (A + B + CI):
//   upper byte (sum)  = A ^ B ^ CI  → 0x96 (odd-popcount positions)
//   lower byte (cout) = majority(A,B,CI) → 0xE8
// Combined → 0x96E8. Every chain cell emits the same mask; $alu
// semantics guarantee the per-bit function is identical.
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

	// Sign / zero extend A and B to Y_WIDTH so every chain bit has
	// well-defined operands.
	wire [Y_WIDTH-1:0] A_ext, B_ext;
	\$pos #(
		.A_SIGNED(A_SIGNED), .A_WIDTH(A_WIDTH), .Y_WIDTH(Y_WIDTH)
	) Aext (.A(A), .Y(A_ext));
	\$pos #(
		.A_SIGNED(B_SIGNED), .A_WIDTH(B_WIDTH), .Y_WIDTH(Y_WIDTH)
	) Bext (.A(B), .Y(B_ext));

	wire [Y_WIDTH-1:0] B_used = B_ext ^ {Y_WIDTH{BI}};

	// Carry chain: C[0] is CI, C[i+1] is the cout of bit i.
	wire [Y_WIDTH:0] C;
	assign C[0] = CI;

	// $alu.X is A^B (pre-carry xor) — some compare passes consume
	// it. Emit directly; Yosys drops it during clean if unused.
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
