// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 OUTROUTE_G15 mining probe — minimal 1-LE.
// Goal: register at any SLICE_X33_Y4_N* driving G15, no second LE in cascade.
// With pin map E1/E16/M16/G15 (same as cl_*), Quartus's IO-bank topology
// constraints should naturally place this at X=33Y4 column.
module v_1le_g15(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    always @(posedge clk) led0 <= key2 & key3;
endmodule
