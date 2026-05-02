// SPDX-License-Identifier: GPL-3.0-or-later
// 23-bit visible-blink, sized to match the W=23 silicon-validated
// hand-FASM demo (memory `multi_lab_carry_silicon_validated_2026_05_03`).
//
// At 50 MHz / 2^23 the LED toggles ~5.96 Hz — visible blink.
//
// Placement (after prepack_carry mode=nextpnr):
//   - chain[0..15] at LAB(4, 18) N=0..30 (full LAB)
//   - chain[16..22] at LAB(4, 17) N=0..12 (7 LEs)
//   - LED-driving DFF (cnt[22]) lands at SLICE_X4_Y17_N12, which is
//     OUTROUTE_G15-mined per `results/output_route_sigcache.json`.
module led_blink (
    input  CLOCK,
    output LED
);
    reg [22:0] cnt = 0;
    always @(posedge CLOCK) cnt <= cnt + 1'b1;
    assign LED = cnt[22];
endmodule
