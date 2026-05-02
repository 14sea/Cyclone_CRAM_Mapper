// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 mining variant — cross_lab.v structure with AND combinational
// Stage A: q1 <= key2 & key3 (LUT4 with TT≈0x8888 — 2-input AND)
// Stage B: led0 <= q1
module v_cl_and(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    reg q1;
    always @(posedge clk) begin
        q1   <= key2 & key3;
        led0 <= q1;
    end
endmodule
