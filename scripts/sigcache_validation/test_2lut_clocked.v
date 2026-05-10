// SPDX-License-Identifier: GPL-3.0-or-later
// Generic 2-LUT clocked test fixture for cross-LAB R4 sigcache
// silicon validation.  LE positions are pinned by build_test.py via
// nextpnr --pre-place hook; this Verilog itself is route-agnostic.
//
// Uses LUT blackbox primitives directly so Yosys won't collapse the
// 2-LUT chain into a single LUT.  Both cells survive synthesis as
// distinct GENERIC_SLICEs.
//
// Topology:
//   KEY2 (PIN_E16) -> A   -> LE_A.dataa
//   KEY3 (PIN_M16) -> B   -> LE_A.datab
//   le_a: LUT mask 0x8888 = AND(I[0], I[1]) = AND(A, B)
//   le_a.combout -> LE_B.dataa
//   le_b: LUT mask 0xAAAA = I[0] = passthrough of LE_A.combout
//   le_b -> DFF -> Q -> LED (PIN_G15)
//   CLK = PIN_E1
//
// Expected silicon (when codec is correct):
//   LED follows registered NOT(KEY2_pressed) AND NOT(KEY3_pressed)
//   (AX301 keys are active-LOW).  LED solid ON when neither key
//   pressed; OFF when KEY2 or KEY3 pressed.

module fuzz_top(
    input  wire CLK,
    input  wire A,    // KEY2 / PIN_E16
    input  wire B,    // KEY3 / PIN_M16
    output reg  Q     // LED  / PIN_G15
);
    wire le_a_out;
    wire le_b_out;

    // LE_A: AND of A,B (mask 0x8888).  I[3:0] = {datad, datac, datab, dataa}
    LUT #(.K(4), .INIT(16'h8888)) le_a (
        .I({1'b0, 1'b0, B, A}),
        .Q(le_a_out)
    );

    // LE_B: passthrough of dataa (mask 0xAAAA).  Only I[0] is used.
    LUT #(.K(4), .INIT(16'hAAAA)) le_b (
        .I({1'b0, 1'b0, 1'b0, le_a_out}),
        .Q(le_b_out)
    );

    always @(posedge CLK)
        Q <= le_b_out;
endmodule
