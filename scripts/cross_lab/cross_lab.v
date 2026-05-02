// SPDX-License-Identifier: GPL-3.0-or-later
//
// Two-stage cross-LAB register cascade for cross-LAB byte-identity test.
//
// Stage A (X16Y4N0):  q1   <= key2 & key3   -- AND-LUT + DFF (apr21-validated cell)
// Stage B (X16Y14N0): led0 <= q1            -- buffer-LUT + DFF, drives LED0
//
// Topology rationale:
//   * Stage A holds both IOB inputs (E16->dataa, M16->datab via padnv
//     bucket; only X16Y4N0 has both ports mined for these pins).  Its
//     LI MUX state matches the apr21 AND-gate's silicon-validated
//     "alternating" envelope.
//   * Stage B is a single-input register at X16Y14N0 (OUTROUTE_G15
//     mined, LAB_CLK_SEL_LE n0 mined, route_cells_full has full 4-port
//     sig-cache from X16Y4N0).
//
// Mined paths used:
//   IOB_E16 -> X16Y4N0.dataa            (padnv_cells)
//   IOB_M16 -> X16Y4N0.datab            (padnv_cells)
//   X16Y4N0 -> X16Y14N0.dataa           (route_cells_full)
//   OUTROUTE_G15 X16Y14N0               (output_route_sigcache)
module top(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    reg q1;
    always @(posedge clk) begin
        q1   <= key2 & key3;
        led0 <= q1;
    end
endmodule
