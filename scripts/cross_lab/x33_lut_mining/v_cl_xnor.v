// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 mining variant — cross_lab.v structure with XNOR combinational
// TT16 = 0x9999 → bits {0,3,4,7,8,11,12,15} — pairs with NOR for nibble-bit pin-down
module v_cl_xnor(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    reg q1;
    always @(posedge clk) begin
        q1   <= ~(key2 ^ key3);
        led0 <= q1;
    end
endmodule
