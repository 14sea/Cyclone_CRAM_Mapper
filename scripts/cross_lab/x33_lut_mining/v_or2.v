// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 LUT TT mining variant: 2-input OR -> DFF -> LED
module v_or2(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    always @(posedge clk) led0 <= key2 | key3;
endmodule
