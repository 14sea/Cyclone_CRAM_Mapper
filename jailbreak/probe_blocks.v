// SPDX-License-Identifier: GPL-3.0-or-later
module probe_blocks(input clk, input [7:0] addr, input [15:0] din, input we,
                    output [15:0] dout, input [8:0] a, input [8:0] b, output [17:0] p);
    wire [15:0] douts [0:11];
    genvar i;
    generate for (i = 0; i < 12; i = i + 1) begin : ramg
        altsyncram #(
            .operation_mode("SINGLE_PORT"), .width_a(16), .widthad_a(8),
            .numwords_a(256), .ram_block_type("M9K"),
            .outdata_reg_a("UNREGISTERED"), .init_file("UNUSED")
        ) r (.clock0(clk), .address_a(addr), .data_a(din ^ i[15:0]),
             .wren_a(we), .q_a(douts[i]));
    end endgenerate
    assign dout = douts[0]^douts[1]^douts[2]^douts[3]^douts[4]^douts[5]
                ^ douts[6]^douts[7]^douts[8]^douts[9]^douts[10]^douts[11];

    // explicit 9x9 mult primitives
    wire [17:0] ps [0:7];
    generate for (i = 0; i < 8; i = i + 1) begin : mg
        lpm_mult #(.lpm_widtha(9), .lpm_widthb(9), .lpm_widthp(18),
                   .lpm_representation("SIGNED"),
                   .lpm_type("LPM_MULT"))
        m (.dataa(a ^ i[8:0]), .datab(b + i[8:0]), .result(ps[i]));
    end endgenerate
    assign p = ps[0]^ps[1]^ps[2]^ps[3]^ps[4]^ps[5]^ps[6]^ps[7];
endmodule
