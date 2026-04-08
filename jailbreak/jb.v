// SPDX-License-Identifier: GPL-3.0-or-later
module jb(input key_in, input key2, output led_out);
    wire q /* synthesis keep */;
    assign q = key_in ^ key2 ^ 1'b1;
    assign led_out = q;
endmodule
