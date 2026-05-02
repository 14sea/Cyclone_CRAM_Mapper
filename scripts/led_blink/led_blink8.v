// SPDX-License-Identifier: GPL-3.0-or-later
// 8-bit version of led_blink for single-LAB CE6_CARRY validation.
// Runs at ~196 kHz on 50 MHz / 2^8 = far too fast to see, but used for
// open-toolchain end-to-end smoke testing where the silicon
// observability isn't the goal.
module led_blink (
    input  CLOCK,
    output LED
);
    reg [7:0] cnt = 0;
    always @(posedge CLOCK) cnt <= cnt + 1'b1;
    assign LED = cnt[7];
endmodule
