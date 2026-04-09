// SPDX-License-Identifier: GPL-3.0-or-later
// EP4CE6 techmap for nextpnr-generic viaduct.
//
// Maps the minimal Yosys post-synth cell set to chipdb bel types:
//   $lut (LUT4) -> EP4CE6_LUT4   (16-bit INIT, 4 inputs, 1 output)
//   $_DFF_P_    -> EP4CE6_DFF    (posedge D-FF, no CE/SRST/ARST)
//
// After async2sync + memory_libmap + dffunmap -ce-only -srst-only
// these are the only two cell kinds left (plus M9K primitives, which
// go through a separate `extract` path, not this techmap).

module \$lut (A, Y);
	parameter WIDTH = 0;
	parameter LUT = 0;
	input  [WIDTH-1:0] A;
	output Y;

	generate
		if (WIDTH == 1) begin
			EP4CE6_LUT4 #(.INIT({8{LUT[1:0]}})) _TECHMAP_REPLACE_ (
				.I0(A[0]), .I1(1'b0), .I2(1'b0), .I3(1'b0), .O(Y));
		end else if (WIDTH == 2) begin
			EP4CE6_LUT4 #(.INIT({4{LUT[3:0]}})) _TECHMAP_REPLACE_ (
				.I0(A[0]), .I1(A[1]), .I2(1'b0), .I3(1'b0), .O(Y));
		end else if (WIDTH == 3) begin
			EP4CE6_LUT4 #(.INIT({2{LUT[7:0]}})) _TECHMAP_REPLACE_ (
				.I0(A[0]), .I1(A[1]), .I2(A[2]), .I3(1'b0), .O(Y));
		end else if (WIDTH == 4) begin
			EP4CE6_LUT4 #(.INIT(LUT)) _TECHMAP_REPLACE_ (
				.I0(A[0]), .I1(A[1]), .I2(A[2]), .I3(A[3]), .O(Y));
		end else begin
			wire _TECHMAP_FAIL_ = 1'b1;
		end
	endgenerate
endmodule

module \$_DFF_P_ (D, C, Q);
	input D, C;
	output Q;
	EP4CE6_DFF _TECHMAP_REPLACE_ (.D(D), .CLK(C), .Q(Q));
endmodule
