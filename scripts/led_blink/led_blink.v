// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal LED heartbeat: free-running counter -> LED[0] (PIN_G15).
// AX301 board, EP4CE6F17C8.  ~5.96 Hz blink (50 MHz / 2^23).
//
// REVERTED to cnt[22] tap (effective W=23 chain) after the W=24 buffer-LE
// + cross-LAB ROUTE silicon test FAILED at flash on AX301.  Both Y=4 and
// Y=21 buffer placements gave "LED constantly on" despite SAFE codec
// state and (in Y=21's case) correctly-decoded LUT TT.  Two distinct
// silicon-hostile gaps surfaced today:
//
//   1. Phase 3 LI MUX restoration corrupts std_lut LUT TT for ~half of
//      LAB_Y values (memory `phase3_li_mux_lut_tt_collision_2026_05_04`).
//   2. Even with Phase 3 sidestepped, mined cross-LAB R4 sigcache cells
//      (from a bare 2-LUT Quartus design) don't reproduce a silicon-
//      functional route in the 24-LE carry-chain runtime context — the
//      chain's competing routing resources prevent the mined route from
//      forming correctly.  Memory `d_i_silicon_two_failures_2026_05_04`.
//
// cnt[22] tap → Yosys trims unused cnt[23] → chain[22] (= cnt[22]) lands
// at SLICE_X4_Y17_N12 (mined OUTROUTE_G15) via intra-LAB output → no
// cross-LAB hop, no buffer LE, no Phase 3 collision risk.  Byte-identical
// to silicon-validated `led_blink_open23.rbf` (md5 905dfc85ad37c44da9966dfbd9cf3a16).
module led_blink (
    input  CLOCK,
    output LED
);
    reg [23:0] cnt = 0;
    always @(posedge CLOCK) cnt <= cnt + 1'b1;
    assign LED = cnt[22];
endmodule
