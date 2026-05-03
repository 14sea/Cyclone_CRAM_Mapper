// SPDX-License-Identifier: GPL-3.0-or-later
module v_rcl_or(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    (* keep *) reg q1;
    always @(posedge clk) begin
        q1   <= key2;
        led0 <= q1 | key3;        // Stage B: OR (TT=0xEEEE)
    end
endmodule
