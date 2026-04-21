// SPDX-License-Identifier: GPL-3.0-or-later
// Minimal 1-LUT design: KEY2 inverted -> LED0
// Target: EP4CE6F17C8 (AX301)
module passthrough (
    input  KEY2,   // PIN_E16, active-low
    output LED0    // PIN_G15, active-high
);
    assign LED0 = ~KEY2;
endmodule
