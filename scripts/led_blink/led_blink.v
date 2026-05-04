// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal LED heartbeat: free-running 24-bit counter -> LED[0] (PIN_G15).
// AX301 board, EP4CE6F17C8.  ~3 Hz blink (50 MHz / 2^24).
//
// W=24 design path (re-enabled 2026-05-04 after X=4 cross-LAB R4 sig-cache
// was mined):
//   chain[0..15] @ X4Y18 N=0..30
//   chain[16..23] @ X4Y17 N=0..14  (chain end = cnt[23] at X4Y17N14)
//   led_q buffer  @ X4Y4N16  (pinned via build_open.py's pre-place hook,
//                              picked because X4Y4N16 IS in OUTROUTE_G15)
//   ROUTE         X4Y17N14 -> X4Y4N16.dataa  (cross-LAB R4, NOW in
//                              sigcache: results/route_cells_full.json
//                              entry `4,17,14->4,4,16,dataa`, 150 cells,
//                              mined 2026-05-04 via
//                              scripts/sigcache_remine/mine_x4_cross_lab_route.py)
//
// HISTORY: earlier this session, the same buffer pattern flashed and the
// FPGA reset on configuration because the cross-LAB ROUTE had no sig-
// cache → fell through to silicon-hostile formula path.  See memory
// `d_i_silicon_failed_2026_05_04`.  After mining the sig-cache entry,
// the build_open.py REFUSE-TO-BUILD guard no longer trips, and the
// cross-LAB ROUTE emits its 150 mined cells instead of formula garbage.
//
// `(* keep *)` on led_q prevents Yosys from optimizing it away or
// fusing it back into the chain end; the explicit buffer is what makes
// LED-driver placement decoupled from chain-end position.
module led_blink (
    input  CLOCK,
    output LED
);
    reg [23:0] cnt = 0;
    (* keep = "true" *) reg led_q;
    always @(posedge CLOCK) cnt   <= cnt + 1'b1;
    always @(posedge CLOCK) led_q <= cnt[23];
    assign LED = led_q;
endmodule
