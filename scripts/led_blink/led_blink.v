// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal LED heartbeat: free-running counter -> LED[0] (PIN_G15).
// AX301 board, EP4CE6F17C8.  No KEY input, no UART — designed to fit
// inside the open-toolchain's mined sigcache coverage:
//   - CLOCK on PIN_E1 (GCLK_PIN directive, 12 mined F17 pins)
//   - LED on PIN_G15 (OUTROUTE_G15 sigcache, 33 mined driver slices)
// 50 MHz / 2^24 = ~3 Hz toggle on LED[0] (visible blink).
module led_blink (
    input  CLOCK,
    output LED
);
    reg [23:0] cnt = 0;
    always @(posedge CLOCK) cnt <= cnt + 1'b1;
    assign LED = cnt[23];
endmodule
