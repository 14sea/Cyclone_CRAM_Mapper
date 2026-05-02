// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 LUT TT mining variant: 2-input AND -> DFF -> LED
// Pin set identical to cross_lab.v / probe2 (E16+M16+G15+E1).
// Single LE with combinational + DFF.  FAST_*_REGISTER OFF.
module v_and2(
    input  wire clk,
    input  wire key2,   // PIN_E16 -> dataa
    input  wire key3,   // PIN_M16 -> datab
    output reg  led0    // PIN_G15
);
    always @(posedge clk) led0 <= key2 & key3;
endmodule
