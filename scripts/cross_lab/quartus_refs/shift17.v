// SPDX-License-Identifier: GPL-3.0-or-later
// 17-stage shift register: forces Quartus into 2+ LABs (LAB max is 16 LEs).
// led0 = (key2 & key3) shifted through 17 register stages.
module shift17(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output wire led0
);
    (* preserve *) reg [16:0] q;
    always @(posedge clk) begin
        q[0]    <= key2 & key3;
        q[16:1] <= q[15:0];
    end
    assign led0 = q[16];
endmodule
