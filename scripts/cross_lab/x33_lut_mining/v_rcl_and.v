// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 Stage B mining — REVERSE cross_lab structure.
// Stage A = 1-input buffer (constant TT=0xAAAA across all rcl_* variants).
// Stage B = 2-input combinational (varies per rcl_* variant).
// (* keep *) on q1 prevents Quartus from folding Stage A into IOB FF —
// we need q1 to consume an LE in the same X=33 LAB pack as Stage B.
module v_rcl_and(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    (* keep *) reg q1;
    always @(posedge clk) begin
        q1   <= key2;             // Stage A: BUF (TT=0xAAAA, constant)
        led0 <= q1 & key3;        // Stage B: AND (TT=0x8888)
    end
endmodule
