// SPDX-License-Identifier: GPL-3.0-or-later
// 1-LE @ SLICE_X33_Y4_N4 TT-variant (M16 ACTIVE — required for X=33 placement).
// Differs from probe2 (1-LE M16-reserved); shares IO topology with v_1le_g15.
// Used by the A corpus build (memory probe2_shim_decomposition_2026_05_04 +
// d-i then a session 2026-05-04).
// Variant: pl_xor    Function: led0 <= key2 ^ key3    Expected TT: 0x6666
module v_pl_xor(
    input  wire clk,
    input  wire key2,
    input  wire key3,
    output reg  led0
);
    always @(posedge clk) led0 <= key2 ^ key3;
endmodule
