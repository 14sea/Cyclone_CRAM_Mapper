// SPDX-License-Identifier: GPL-3.0-or-later
// 24-bit visible-blink, exercises chain end at SLICE_X4_Y17_N14
// (our_n=14, Quartus chain-only LE).  At 50 MHz / 2^24 → ~2.98 Hz.
//
// Placement (after prepack_carry mode=nextpnr):
//   - chain[0..15]  at LAB(4, 18) N=0..30 (full LAB)
//   - chain[16..23] at LAB(4, 17) N=0..14 (8 LEs)
//   - LED-driving DFF (cnt[23]) lands at SLICE_X4_Y17_N14 — newly
//     OUTROUTE_G15-mined via Path B chain template (memory
//     `path_b_chain_template_landed_2026_05_07`).
//
// Companion to led_blink23.v (W=23 silicon-validated, md5 905dfc85).
// W=24 differs only by extending the chain by one bit, exercising the
// previously-missing OUTROUTE_G15 X4Y17N14 sigcache entry.
module led_blink (
    input  CLOCK,
    output LED
);
    reg [23:0] cnt = 0;
    always @(posedge CLOCK) cnt <= cnt + 1'b1;
    assign LED = cnt[23];
endmodule
