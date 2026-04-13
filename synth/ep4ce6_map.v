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
//
// Self-loop buffer (Route A, 2026-04-11):
// A counter ( cnt <= cnt + 1 ) creates a DFF.Q → CE6_CARRY feedback
// inside a single LE. The sig-cache's 61 existing self-loop entries
// don't cover a contiguous chain at any LAB, so routing the feedback
// inside one LE is a hard stop. Workaround: insert a (* keep *) LUT1
// identity buffer on the feedback operand so nextpnr places the
// buffer in a DIFFERENT LE, turning one unroutable self-loop into
// two standard LI routes that are covered by route_cells_full.json.
//
// Physical routing constraint: first-flash placement at LAB(4,18).
// -----------------------------------------------------------------
// LAB(4,18) is the only LAB with BOTH (a) full 16×16 LUT minterm
// calibration in the bitdb (so fasm2rbf can bake arbitrary LUT masks
// at every N slot) AND (b) enough sig-cache intra-LAB feedback entries
// to carry a 3-bit CE6_CARRY chain. The (6,17) uniform-datab chain
// from the feasibility solver would have been cleaner to describe but
// (6,17) has zero minterm_* calibration in ep4ce6_bitdb.sqlite, so any
// LUT cell at (6,17) fails LutCodec.from_db at bitgen time. See the
// chain-feasibility solver for the four mixed-port (4,18) options.
//
// The (4,18) 3-bit layout (from the solver) is mixed-port:
//   bit 0: CARRY @ N4, buffer @ N12, feedback pip = dataa
//   bit 1: CARRY @ N6, buffer @ N14, feedback pip = datac
//   bit 2: CARRY @ N8, buffer @ N2,  feedback pip = datad
//
// Each buffer must therefore route its input through a *different*
// LUT4 pin, which is fine because the INIT we pick (16'hfffe = Q =
// OR(I[0..3])) is symmetric in all four inputs: driving only one I[k]
// and tying the others to constant 0 leaves Q = I[k]. The per-bit
// wire plug on `.I()` selects which physical dataX pin nextpnr routes
// the feedback onto, and the buffer still computes an identity.
//
// Yosys alumacc natively assigns A=const-1, B=cnt for `cnt + 1'b1`,
// so the CE6_CARRY instantiation here leaves A=A_ext (constant) and
// B=B_buffered (buffered feedback). CE6_CARRY.B → silicon `datab`
// unconditionally (np2fasm's chipdb fixes this pin), so the buf.Q →
// CARRY.datab arc is the same at every bit and already covered by
// the (4,18) sig-cache. See route_a_buffer_insertion memory for the
// operand-order reasoning and the chain-feasibility solver for the
// per-bit buffer-input port choice.
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

	// Self-loop buffer: identity LUT4 on the feedback operand (B_used).
	// INIT=16'hfffe is Q = OR(I[0..3]); with only one I[k] driven and
	// the other three tied to Verilog 0, this collapses to Q = I[k],
	// so the same INIT works regardless of which physical LUT4 pin
	// the wire is plugged into. Per-bit plug selection below selects
	// the dataX pin that the (4,18) sig-cache has coverage for, which
	// is different per chain bit (see the block comment above).
	// (* keep *) is mandatory — without it Yosys's opt_clean folds
	// the buffer out and re-exposes the self-loop to the packer.
	wire [Y_WIDTH-1:0] B_buffered;

	// Per-bit buffer input-pin table for the (4,18) mixed-port layout.
	// Index = chain bit (0..Y_WIDTH-1); value = LUT4 input index 0..3
	// (0=dataa, 1=datab, 2=datac, 3=datad). Fall-back for bits beyond
	// the 3-bit first-flash target is dataa, but any counter wider
	// than 3 bits is outside the currently-covered feasibility set
	// and will not route against the sig-cache.
	function [1:0] buf_port_for_bit;
		input integer idx;
		case (idx)
			0: buf_port_for_bit = 2'd0;  // dataa
			1: buf_port_for_bit = 2'd2;  // datac
			2: buf_port_for_bit = 2'd3;  // datad
			default: buf_port_for_bit = 2'd0;
		endcase
	endfunction

	genvar i;
	generate
		for (i = 0; i < Y_WIDTH; i = i + 1) begin : chain
			// Build the 4-bit I vector for this bit's buffer LUT with
			// B_used plugged into the per-bit port and the other
			// three tied to 0.
			wire [3:0] b_in =
				(buf_port_for_bit(i) == 2'd0) ? {3'b000, B_used[i]}        :
				(buf_port_for_bit(i) == 2'd1) ? {2'b00, B_used[i], 1'b0}   :
				(buf_port_for_bit(i) == 2'd2) ? {1'b0, B_used[i], 2'b00}   :
				                                {B_used[i], 3'b000};

			(* keep *) LUT #(
				.K(4),
				.INIT(16'hfffe)
			) b_buf (
				.I(b_in),
				.Q(B_buffered[i])
			);
			// Yosys alumacc native layout: A=const-1, B=cnt feedback.
			// CE6_CARRY.B → silicon `datab` at every LE (chipdb fixes
			// pin B to I[1] = datab), so the buf→CARRY arc is
			// uniformly datab regardless of which buffer input port
			// the feedback enters on. np2fasm const-folds LUT_MASK
			// per bit from the literal A/CI values.
			CE6_CARRY #(
				.LUT_MASK(16'h96E8)
			) bit_ (
				.A(A_ext[i]),
				.B(B_buffered[i]),
				.CI(C[i]),
				.S(Y[i]),
				.CO(C[i+1])
			);
		end
	endgenerate

	assign CO = C[Y_WIDTH:1];
endmodule
