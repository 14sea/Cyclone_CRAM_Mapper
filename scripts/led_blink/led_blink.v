// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal LED heartbeat: free-running counter -> LED[0] (PIN_G15).
// AX301 board, EP4CE6F17C8.
//
// Design constraint (silicon-validated): LED is tapped from cnt[22], not
// cnt[23], because chain[22] (= cnt[22]) lands at SLICE_X4_Y17_N12, which
// IS in the OUTROUTE_G15 sigcache.  Yosys then trims unused cnt[23] →
// effective 23-bit chain → byte-identical to silicon-validated
// `led_blink_open23.rbf` (md5 905dfc85ad37c44da9966dfbd9cf3a16).
//
// 50 MHz / 2^23 = ~5.96 Hz toggle on LED[0] (visible blink).
//
// HISTORY 2026-05-04: an earlier W=24 variant tapped cnt[23] directly and
// added a separate `led_q` buffer pinned to X4Y4N16 to escape the unmined
// X4Y17N14 OUTROUTE_G15.  That introduced a cross-LAB ROUTE
// X4Y17N14 → X4Y4N16.dataa with no sig-cache entry, which fell through to
// the formula path.  Silicon flash REJECTED the bitstream (FPGA reset on
// configuration — config controller validation failed).  See memory
// `d_i_silicon_failed_2026_05_04`.  The pure-software fix is the cnt[22]
// tap below; arbitrary chain widths require either mined OUTROUTE_G15 at
// the natural chain-end slice OR a sig-cache entry for the cross-LAB hop
// to a buffer (Quartus mining campaign, deferred).
module led_blink (
    input  CLOCK,
    output LED
);
    reg [23:0] cnt = 0;
    always @(posedge CLOCK) cnt <= cnt + 1'b1;
    assign LED = cnt[22];
endmodule
