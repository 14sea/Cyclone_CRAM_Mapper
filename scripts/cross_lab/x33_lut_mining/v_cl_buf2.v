// SPDX-License-Identifier: GPL-3.0-or-later
// X=33 mining variant — cross_lab.v structure with BUFFER (key2 only)
// Goal: same Stage A 2-LE shape but TT only depends on dataa.
// (* keep *) on q1 prevents Quartus from collapsing the cascade.
module v_cl_buf2(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    (* keep *) reg q1;
    always @(posedge clk) begin
        q1   <= key2 ^ (key3 & 1'b0);  // forces datab tie but yields TT 0xAAAA
        led0 <= q1;
    end
endmodule
