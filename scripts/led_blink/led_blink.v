// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal LED heartbeat: free-running counter -> LED[0] (PIN_G15).
// AX301 board, EP4CE6F17C8.  No KEY input, no UART — designed to fit
// inside the open-toolchain's mined sigcache coverage:
//   - CLOCK on PIN_E1 (GCLK_PIN directive, 12 mined F17 pins)
//   - LED on PIN_G15 via led_q buffer (OUTROUTE_G15 sigcache)
// 50 MHz / 2^24 = ~3 Hz toggle on LED[0] (visible blink).
//
// `led_q` is an explicit single-LE buffer added 2026-05-04 (D-i fix from
// memory `d_triage_led_blink_open_2026_05_04`).  Without it, the LED
// signal was driven directly by the chain-end DFF (cnt[23]) which lands
// at SLICE_X4_Y17_N14 — NOT in OUTROUTE_G15 sigcache (only N0 and N12
// mined at X4Y17).  np2fasm therefore emitted 0 OUTROUTE_G15 → no
// signal routing to G15 → LED stuck always-on on silicon.  The buffer
// breaks the chain dependency, lets the pre-place hook pin led_q to a
// known-mined slice (X4Y4N16 by default), and decouples LED-routability
// from chain length so future N-bit variants work uniformly.
module led_blink (
    input  CLOCK,
    output LED
);
    reg [23:0] cnt = 0;
    (* keep = "true" *) reg led_q;  // keep attribute prevents Yosys from
                                    // renaming led_q during synthesis,
                                    // so the build_open.py pre-place hook
                                    // can find it by name and pin it to
                                    // a known-mined OUTROUTE_G15 slice.
    always @(posedge CLOCK) cnt   <= cnt + 1'b1;
    always @(posedge CLOCK) led_q <= cnt[23];
    assign LED = led_q;
endmodule
