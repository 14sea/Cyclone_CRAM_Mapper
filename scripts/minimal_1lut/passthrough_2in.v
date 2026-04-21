// SPDX-License-Identifier: GPL-3.0-or-later
// 2-input LUT: KEY2 AND KEY3 -> LED0 (forces Quartus to use a LUT)
module passthrough_2in (
    input  KEY2,   // PIN_E16
    input  KEY3,   // PIN_M16
    output LED0    // PIN_G15
);
    assign LED0 = KEY2 & KEY3;
endmodule
