// SPDX-License-Identifier: GPL-3.0-or-later
module jbscan(input k1, input k2, output led);
    wire [1840:0] chain /* synthesis keep */;
    assign chain[0] = k1 ^ k2;
    (* keep = 1, preserve = 1 *) wire w0;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u0 (
        .dataa(chain[0]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w0));
    assign chain[1] = w0;
    (* keep = 1, preserve = 1 *) wire w1;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1 (
        .dataa(chain[1]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1));
    assign chain[2] = w1;
    (* keep = 1, preserve = 1 *) wire w2;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u2 (
        .dataa(chain[2]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w2));
    assign chain[3] = w2;
    (* keep = 1, preserve = 1 *) wire w3;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u3 (
        .dataa(chain[3]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w3));
    assign chain[4] = w3;
    (* keep = 1, preserve = 1 *) wire w4;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u4 (
        .dataa(chain[4]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w4));
    assign chain[5] = w4;
    (* keep = 1, preserve = 1 *) wire w5;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u5 (
        .dataa(chain[5]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w5));
    assign chain[6] = w5;
    (* keep = 1, preserve = 1 *) wire w6;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u6 (
        .dataa(chain[6]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w6));
    assign chain[7] = w6;
    (* keep = 1, preserve = 1 *) wire w7;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u7 (
        .dataa(chain[7]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w7));
    assign chain[8] = w7;
    (* keep = 1, preserve = 1 *) wire w8;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u8 (
        .dataa(chain[8]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w8));
    assign chain[9] = w8;
    (* keep = 1, preserve = 1 *) wire w9;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u9 (
        .dataa(chain[9]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w9));
    assign chain[10] = w9;
    (* keep = 1, preserve = 1 *) wire w10;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u10 (
        .dataa(chain[10]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w10));
    assign chain[11] = w10;
    (* keep = 1, preserve = 1 *) wire w11;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u11 (
        .dataa(chain[11]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w11));
    assign chain[12] = w11;
    (* keep = 1, preserve = 1 *) wire w12;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u12 (
        .dataa(chain[12]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w12));
    assign chain[13] = w12;
    (* keep = 1, preserve = 1 *) wire w13;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u13 (
        .dataa(chain[13]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w13));
    assign chain[14] = w13;
    (* keep = 1, preserve = 1 *) wire w14;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u14 (
        .dataa(chain[14]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w14));
    assign chain[15] = w14;
    (* keep = 1, preserve = 1 *) wire w15;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u15 (
        .dataa(chain[15]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w15));
    assign chain[16] = w15;
    (* keep = 1, preserve = 1 *) wire w16;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u16 (
        .dataa(chain[16]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w16));
    assign chain[17] = w16;
    (* keep = 1, preserve = 1 *) wire w17;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u17 (
        .dataa(chain[17]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w17));
    assign chain[18] = w17;
    (* keep = 1, preserve = 1 *) wire w18;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u18 (
        .dataa(chain[18]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w18));
    assign chain[19] = w18;
    (* keep = 1, preserve = 1 *) wire w19;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u19 (
        .dataa(chain[19]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w19));
    assign chain[20] = w19;
    (* keep = 1, preserve = 1 *) wire w20;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u20 (
        .dataa(chain[20]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w20));
    assign chain[21] = w20;
    (* keep = 1, preserve = 1 *) wire w21;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u21 (
        .dataa(chain[21]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w21));
    assign chain[22] = w21;
    (* keep = 1, preserve = 1 *) wire w22;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u22 (
        .dataa(chain[22]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w22));
    assign chain[23] = w22;
    (* keep = 1, preserve = 1 *) wire w23;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u23 (
        .dataa(chain[23]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w23));
    assign chain[24] = w23;
    (* keep = 1, preserve = 1 *) wire w24;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u24 (
        .dataa(chain[24]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w24));
    assign chain[25] = w24;
    (* keep = 1, preserve = 1 *) wire w25;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u25 (
        .dataa(chain[25]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w25));
    assign chain[26] = w25;
    (* keep = 1, preserve = 1 *) wire w26;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u26 (
        .dataa(chain[26]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w26));
    assign chain[27] = w26;
    (* keep = 1, preserve = 1 *) wire w27;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u27 (
        .dataa(chain[27]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w27));
    assign chain[28] = w27;
    (* keep = 1, preserve = 1 *) wire w28;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u28 (
        .dataa(chain[28]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w28));
    assign chain[29] = w28;
    (* keep = 1, preserve = 1 *) wire w29;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u29 (
        .dataa(chain[29]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w29));
    assign chain[30] = w29;
    (* keep = 1, preserve = 1 *) wire w30;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u30 (
        .dataa(chain[30]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w30));
    assign chain[31] = w30;
    (* keep = 1, preserve = 1 *) wire w31;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u31 (
        .dataa(chain[31]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w31));
    assign chain[32] = w31;
    (* keep = 1, preserve = 1 *) wire w32;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u32 (
        .dataa(chain[32]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w32));
    assign chain[33] = w32;
    (* keep = 1, preserve = 1 *) wire w33;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u33 (
        .dataa(chain[33]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w33));
    assign chain[34] = w33;
    (* keep = 1, preserve = 1 *) wire w34;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u34 (
        .dataa(chain[34]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w34));
    assign chain[35] = w34;
    (* keep = 1, preserve = 1 *) wire w35;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u35 (
        .dataa(chain[35]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w35));
    assign chain[36] = w35;
    (* keep = 1, preserve = 1 *) wire w36;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u36 (
        .dataa(chain[36]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w36));
    assign chain[37] = w36;
    (* keep = 1, preserve = 1 *) wire w37;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u37 (
        .dataa(chain[37]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w37));
    assign chain[38] = w37;
    (* keep = 1, preserve = 1 *) wire w38;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u38 (
        .dataa(chain[38]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w38));
    assign chain[39] = w38;
    (* keep = 1, preserve = 1 *) wire w39;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u39 (
        .dataa(chain[39]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w39));
    assign chain[40] = w39;
    (* keep = 1, preserve = 1 *) wire w40;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u40 (
        .dataa(chain[40]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w40));
    assign chain[41] = w40;
    (* keep = 1, preserve = 1 *) wire w41;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u41 (
        .dataa(chain[41]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w41));
    assign chain[42] = w41;
    (* keep = 1, preserve = 1 *) wire w42;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u42 (
        .dataa(chain[42]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w42));
    assign chain[43] = w42;
    (* keep = 1, preserve = 1 *) wire w43;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u43 (
        .dataa(chain[43]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w43));
    assign chain[44] = w43;
    (* keep = 1, preserve = 1 *) wire w44;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u44 (
        .dataa(chain[44]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w44));
    assign chain[45] = w44;
    (* keep = 1, preserve = 1 *) wire w45;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u45 (
        .dataa(chain[45]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w45));
    assign chain[46] = w45;
    (* keep = 1, preserve = 1 *) wire w46;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u46 (
        .dataa(chain[46]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w46));
    assign chain[47] = w46;
    (* keep = 1, preserve = 1 *) wire w47;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u47 (
        .dataa(chain[47]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w47));
    assign chain[48] = w47;
    (* keep = 1, preserve = 1 *) wire w48;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u48 (
        .dataa(chain[48]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w48));
    assign chain[49] = w48;
    (* keep = 1, preserve = 1 *) wire w49;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u49 (
        .dataa(chain[49]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w49));
    assign chain[50] = w49;
    (* keep = 1, preserve = 1 *) wire w50;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u50 (
        .dataa(chain[50]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w50));
    assign chain[51] = w50;
    (* keep = 1, preserve = 1 *) wire w51;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u51 (
        .dataa(chain[51]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w51));
    assign chain[52] = w51;
    (* keep = 1, preserve = 1 *) wire w52;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u52 (
        .dataa(chain[52]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w52));
    assign chain[53] = w52;
    (* keep = 1, preserve = 1 *) wire w53;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u53 (
        .dataa(chain[53]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w53));
    assign chain[54] = w53;
    (* keep = 1, preserve = 1 *) wire w54;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u54 (
        .dataa(chain[54]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w54));
    assign chain[55] = w54;
    (* keep = 1, preserve = 1 *) wire w55;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u55 (
        .dataa(chain[55]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w55));
    assign chain[56] = w55;
    (* keep = 1, preserve = 1 *) wire w56;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u56 (
        .dataa(chain[56]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w56));
    assign chain[57] = w56;
    (* keep = 1, preserve = 1 *) wire w57;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u57 (
        .dataa(chain[57]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w57));
    assign chain[58] = w57;
    (* keep = 1, preserve = 1 *) wire w58;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u58 (
        .dataa(chain[58]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w58));
    assign chain[59] = w58;
    (* keep = 1, preserve = 1 *) wire w59;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u59 (
        .dataa(chain[59]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w59));
    assign chain[60] = w59;
    (* keep = 1, preserve = 1 *) wire w60;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u60 (
        .dataa(chain[60]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w60));
    assign chain[61] = w60;
    (* keep = 1, preserve = 1 *) wire w61;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u61 (
        .dataa(chain[61]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w61));
    assign chain[62] = w61;
    (* keep = 1, preserve = 1 *) wire w62;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u62 (
        .dataa(chain[62]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w62));
    assign chain[63] = w62;
    (* keep = 1, preserve = 1 *) wire w63;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u63 (
        .dataa(chain[63]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w63));
    assign chain[64] = w63;
    (* keep = 1, preserve = 1 *) wire w64;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u64 (
        .dataa(chain[64]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w64));
    assign chain[65] = w64;
    (* keep = 1, preserve = 1 *) wire w65;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u65 (
        .dataa(chain[65]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w65));
    assign chain[66] = w65;
    (* keep = 1, preserve = 1 *) wire w66;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u66 (
        .dataa(chain[66]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w66));
    assign chain[67] = w66;
    (* keep = 1, preserve = 1 *) wire w67;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u67 (
        .dataa(chain[67]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w67));
    assign chain[68] = w67;
    (* keep = 1, preserve = 1 *) wire w68;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u68 (
        .dataa(chain[68]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w68));
    assign chain[69] = w68;
    (* keep = 1, preserve = 1 *) wire w69;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u69 (
        .dataa(chain[69]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w69));
    assign chain[70] = w69;
    (* keep = 1, preserve = 1 *) wire w70;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u70 (
        .dataa(chain[70]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w70));
    assign chain[71] = w70;
    (* keep = 1, preserve = 1 *) wire w71;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u71 (
        .dataa(chain[71]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w71));
    assign chain[72] = w71;
    (* keep = 1, preserve = 1 *) wire w72;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u72 (
        .dataa(chain[72]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w72));
    assign chain[73] = w72;
    (* keep = 1, preserve = 1 *) wire w73;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u73 (
        .dataa(chain[73]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w73));
    assign chain[74] = w73;
    (* keep = 1, preserve = 1 *) wire w74;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u74 (
        .dataa(chain[74]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w74));
    assign chain[75] = w74;
    (* keep = 1, preserve = 1 *) wire w75;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u75 (
        .dataa(chain[75]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w75));
    assign chain[76] = w75;
    (* keep = 1, preserve = 1 *) wire w76;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u76 (
        .dataa(chain[76]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w76));
    assign chain[77] = w76;
    (* keep = 1, preserve = 1 *) wire w77;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u77 (
        .dataa(chain[77]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w77));
    assign chain[78] = w77;
    (* keep = 1, preserve = 1 *) wire w78;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u78 (
        .dataa(chain[78]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w78));
    assign chain[79] = w78;
    (* keep = 1, preserve = 1 *) wire w79;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u79 (
        .dataa(chain[79]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w79));
    assign chain[80] = w79;
    (* keep = 1, preserve = 1 *) wire w80;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u80 (
        .dataa(chain[80]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w80));
    assign chain[81] = w80;
    (* keep = 1, preserve = 1 *) wire w81;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u81 (
        .dataa(chain[81]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w81));
    assign chain[82] = w81;
    (* keep = 1, preserve = 1 *) wire w82;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u82 (
        .dataa(chain[82]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w82));
    assign chain[83] = w82;
    (* keep = 1, preserve = 1 *) wire w83;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u83 (
        .dataa(chain[83]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w83));
    assign chain[84] = w83;
    (* keep = 1, preserve = 1 *) wire w84;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u84 (
        .dataa(chain[84]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w84));
    assign chain[85] = w84;
    (* keep = 1, preserve = 1 *) wire w85;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u85 (
        .dataa(chain[85]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w85));
    assign chain[86] = w85;
    (* keep = 1, preserve = 1 *) wire w86;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u86 (
        .dataa(chain[86]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w86));
    assign chain[87] = w86;
    (* keep = 1, preserve = 1 *) wire w87;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u87 (
        .dataa(chain[87]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w87));
    assign chain[88] = w87;
    (* keep = 1, preserve = 1 *) wire w88;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u88 (
        .dataa(chain[88]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w88));
    assign chain[89] = w88;
    (* keep = 1, preserve = 1 *) wire w89;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u89 (
        .dataa(chain[89]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w89));
    assign chain[90] = w89;
    (* keep = 1, preserve = 1 *) wire w90;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u90 (
        .dataa(chain[90]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w90));
    assign chain[91] = w90;
    (* keep = 1, preserve = 1 *) wire w91;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u91 (
        .dataa(chain[91]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w91));
    assign chain[92] = w91;
    (* keep = 1, preserve = 1 *) wire w92;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u92 (
        .dataa(chain[92]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w92));
    assign chain[93] = w92;
    (* keep = 1, preserve = 1 *) wire w93;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u93 (
        .dataa(chain[93]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w93));
    assign chain[94] = w93;
    (* keep = 1, preserve = 1 *) wire w94;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u94 (
        .dataa(chain[94]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w94));
    assign chain[95] = w94;
    (* keep = 1, preserve = 1 *) wire w95;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u95 (
        .dataa(chain[95]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w95));
    assign chain[96] = w95;
    (* keep = 1, preserve = 1 *) wire w96;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u96 (
        .dataa(chain[96]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w96));
    assign chain[97] = w96;
    (* keep = 1, preserve = 1 *) wire w97;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u97 (
        .dataa(chain[97]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w97));
    assign chain[98] = w97;
    (* keep = 1, preserve = 1 *) wire w98;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u98 (
        .dataa(chain[98]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w98));
    assign chain[99] = w98;
    (* keep = 1, preserve = 1 *) wire w99;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u99 (
        .dataa(chain[99]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w99));
    assign chain[100] = w99;
    (* keep = 1, preserve = 1 *) wire w100;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u100 (
        .dataa(chain[100]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w100));
    assign chain[101] = w100;
    (* keep = 1, preserve = 1 *) wire w101;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u101 (
        .dataa(chain[101]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w101));
    assign chain[102] = w101;
    (* keep = 1, preserve = 1 *) wire w102;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u102 (
        .dataa(chain[102]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w102));
    assign chain[103] = w102;
    (* keep = 1, preserve = 1 *) wire w103;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u103 (
        .dataa(chain[103]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w103));
    assign chain[104] = w103;
    (* keep = 1, preserve = 1 *) wire w104;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u104 (
        .dataa(chain[104]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w104));
    assign chain[105] = w104;
    (* keep = 1, preserve = 1 *) wire w105;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u105 (
        .dataa(chain[105]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w105));
    assign chain[106] = w105;
    (* keep = 1, preserve = 1 *) wire w106;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u106 (
        .dataa(chain[106]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w106));
    assign chain[107] = w106;
    (* keep = 1, preserve = 1 *) wire w107;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u107 (
        .dataa(chain[107]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w107));
    assign chain[108] = w107;
    (* keep = 1, preserve = 1 *) wire w108;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u108 (
        .dataa(chain[108]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w108));
    assign chain[109] = w108;
    (* keep = 1, preserve = 1 *) wire w109;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u109 (
        .dataa(chain[109]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w109));
    assign chain[110] = w109;
    (* keep = 1, preserve = 1 *) wire w110;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u110 (
        .dataa(chain[110]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w110));
    assign chain[111] = w110;
    (* keep = 1, preserve = 1 *) wire w111;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u111 (
        .dataa(chain[111]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w111));
    assign chain[112] = w111;
    (* keep = 1, preserve = 1 *) wire w112;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u112 (
        .dataa(chain[112]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w112));
    assign chain[113] = w112;
    (* keep = 1, preserve = 1 *) wire w113;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u113 (
        .dataa(chain[113]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w113));
    assign chain[114] = w113;
    (* keep = 1, preserve = 1 *) wire w114;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u114 (
        .dataa(chain[114]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w114));
    assign chain[115] = w114;
    (* keep = 1, preserve = 1 *) wire w115;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u115 (
        .dataa(chain[115]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w115));
    assign chain[116] = w115;
    (* keep = 1, preserve = 1 *) wire w116;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u116 (
        .dataa(chain[116]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w116));
    assign chain[117] = w116;
    (* keep = 1, preserve = 1 *) wire w117;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u117 (
        .dataa(chain[117]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w117));
    assign chain[118] = w117;
    (* keep = 1, preserve = 1 *) wire w118;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u118 (
        .dataa(chain[118]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w118));
    assign chain[119] = w118;
    (* keep = 1, preserve = 1 *) wire w119;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u119 (
        .dataa(chain[119]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w119));
    assign chain[120] = w119;
    (* keep = 1, preserve = 1 *) wire w120;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u120 (
        .dataa(chain[120]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w120));
    assign chain[121] = w120;
    (* keep = 1, preserve = 1 *) wire w121;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u121 (
        .dataa(chain[121]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w121));
    assign chain[122] = w121;
    (* keep = 1, preserve = 1 *) wire w122;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u122 (
        .dataa(chain[122]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w122));
    assign chain[123] = w122;
    (* keep = 1, preserve = 1 *) wire w123;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u123 (
        .dataa(chain[123]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w123));
    assign chain[124] = w123;
    (* keep = 1, preserve = 1 *) wire w124;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u124 (
        .dataa(chain[124]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w124));
    assign chain[125] = w124;
    (* keep = 1, preserve = 1 *) wire w125;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u125 (
        .dataa(chain[125]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w125));
    assign chain[126] = w125;
    (* keep = 1, preserve = 1 *) wire w126;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u126 (
        .dataa(chain[126]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w126));
    assign chain[127] = w126;
    (* keep = 1, preserve = 1 *) wire w127;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u127 (
        .dataa(chain[127]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w127));
    assign chain[128] = w127;
    (* keep = 1, preserve = 1 *) wire w128;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u128 (
        .dataa(chain[128]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w128));
    assign chain[129] = w128;
    (* keep = 1, preserve = 1 *) wire w129;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u129 (
        .dataa(chain[129]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w129));
    assign chain[130] = w129;
    (* keep = 1, preserve = 1 *) wire w130;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u130 (
        .dataa(chain[130]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w130));
    assign chain[131] = w130;
    (* keep = 1, preserve = 1 *) wire w131;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u131 (
        .dataa(chain[131]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w131));
    assign chain[132] = w131;
    (* keep = 1, preserve = 1 *) wire w132;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u132 (
        .dataa(chain[132]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w132));
    assign chain[133] = w132;
    (* keep = 1, preserve = 1 *) wire w133;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u133 (
        .dataa(chain[133]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w133));
    assign chain[134] = w133;
    (* keep = 1, preserve = 1 *) wire w134;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u134 (
        .dataa(chain[134]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w134));
    assign chain[135] = w134;
    (* keep = 1, preserve = 1 *) wire w135;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u135 (
        .dataa(chain[135]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w135));
    assign chain[136] = w135;
    (* keep = 1, preserve = 1 *) wire w136;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u136 (
        .dataa(chain[136]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w136));
    assign chain[137] = w136;
    (* keep = 1, preserve = 1 *) wire w137;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u137 (
        .dataa(chain[137]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w137));
    assign chain[138] = w137;
    (* keep = 1, preserve = 1 *) wire w138;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u138 (
        .dataa(chain[138]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w138));
    assign chain[139] = w138;
    (* keep = 1, preserve = 1 *) wire w139;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u139 (
        .dataa(chain[139]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w139));
    assign chain[140] = w139;
    (* keep = 1, preserve = 1 *) wire w140;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u140 (
        .dataa(chain[140]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w140));
    assign chain[141] = w140;
    (* keep = 1, preserve = 1 *) wire w141;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u141 (
        .dataa(chain[141]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w141));
    assign chain[142] = w141;
    (* keep = 1, preserve = 1 *) wire w142;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u142 (
        .dataa(chain[142]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w142));
    assign chain[143] = w142;
    (* keep = 1, preserve = 1 *) wire w143;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u143 (
        .dataa(chain[143]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w143));
    assign chain[144] = w143;
    (* keep = 1, preserve = 1 *) wire w144;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u144 (
        .dataa(chain[144]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w144));
    assign chain[145] = w144;
    (* keep = 1, preserve = 1 *) wire w145;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u145 (
        .dataa(chain[145]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w145));
    assign chain[146] = w145;
    (* keep = 1, preserve = 1 *) wire w146;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u146 (
        .dataa(chain[146]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w146));
    assign chain[147] = w146;
    (* keep = 1, preserve = 1 *) wire w147;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u147 (
        .dataa(chain[147]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w147));
    assign chain[148] = w147;
    (* keep = 1, preserve = 1 *) wire w148;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u148 (
        .dataa(chain[148]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w148));
    assign chain[149] = w148;
    (* keep = 1, preserve = 1 *) wire w149;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u149 (
        .dataa(chain[149]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w149));
    assign chain[150] = w149;
    (* keep = 1, preserve = 1 *) wire w150;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u150 (
        .dataa(chain[150]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w150));
    assign chain[151] = w150;
    (* keep = 1, preserve = 1 *) wire w151;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u151 (
        .dataa(chain[151]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w151));
    assign chain[152] = w151;
    (* keep = 1, preserve = 1 *) wire w152;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u152 (
        .dataa(chain[152]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w152));
    assign chain[153] = w152;
    (* keep = 1, preserve = 1 *) wire w153;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u153 (
        .dataa(chain[153]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w153));
    assign chain[154] = w153;
    (* keep = 1, preserve = 1 *) wire w154;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u154 (
        .dataa(chain[154]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w154));
    assign chain[155] = w154;
    (* keep = 1, preserve = 1 *) wire w155;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u155 (
        .dataa(chain[155]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w155));
    assign chain[156] = w155;
    (* keep = 1, preserve = 1 *) wire w156;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u156 (
        .dataa(chain[156]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w156));
    assign chain[157] = w156;
    (* keep = 1, preserve = 1 *) wire w157;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u157 (
        .dataa(chain[157]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w157));
    assign chain[158] = w157;
    (* keep = 1, preserve = 1 *) wire w158;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u158 (
        .dataa(chain[158]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w158));
    assign chain[159] = w158;
    (* keep = 1, preserve = 1 *) wire w159;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u159 (
        .dataa(chain[159]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w159));
    assign chain[160] = w159;
    (* keep = 1, preserve = 1 *) wire w160;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u160 (
        .dataa(chain[160]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w160));
    assign chain[161] = w160;
    (* keep = 1, preserve = 1 *) wire w161;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u161 (
        .dataa(chain[161]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w161));
    assign chain[162] = w161;
    (* keep = 1, preserve = 1 *) wire w162;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u162 (
        .dataa(chain[162]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w162));
    assign chain[163] = w162;
    (* keep = 1, preserve = 1 *) wire w163;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u163 (
        .dataa(chain[163]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w163));
    assign chain[164] = w163;
    (* keep = 1, preserve = 1 *) wire w164;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u164 (
        .dataa(chain[164]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w164));
    assign chain[165] = w164;
    (* keep = 1, preserve = 1 *) wire w165;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u165 (
        .dataa(chain[165]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w165));
    assign chain[166] = w165;
    (* keep = 1, preserve = 1 *) wire w166;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u166 (
        .dataa(chain[166]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w166));
    assign chain[167] = w166;
    (* keep = 1, preserve = 1 *) wire w167;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u167 (
        .dataa(chain[167]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w167));
    assign chain[168] = w167;
    (* keep = 1, preserve = 1 *) wire w168;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u168 (
        .dataa(chain[168]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w168));
    assign chain[169] = w168;
    (* keep = 1, preserve = 1 *) wire w169;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u169 (
        .dataa(chain[169]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w169));
    assign chain[170] = w169;
    (* keep = 1, preserve = 1 *) wire w170;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u170 (
        .dataa(chain[170]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w170));
    assign chain[171] = w170;
    (* keep = 1, preserve = 1 *) wire w171;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u171 (
        .dataa(chain[171]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w171));
    assign chain[172] = w171;
    (* keep = 1, preserve = 1 *) wire w172;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u172 (
        .dataa(chain[172]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w172));
    assign chain[173] = w172;
    (* keep = 1, preserve = 1 *) wire w173;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u173 (
        .dataa(chain[173]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w173));
    assign chain[174] = w173;
    (* keep = 1, preserve = 1 *) wire w174;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u174 (
        .dataa(chain[174]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w174));
    assign chain[175] = w174;
    (* keep = 1, preserve = 1 *) wire w175;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u175 (
        .dataa(chain[175]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w175));
    assign chain[176] = w175;
    (* keep = 1, preserve = 1 *) wire w176;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u176 (
        .dataa(chain[176]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w176));
    assign chain[177] = w176;
    (* keep = 1, preserve = 1 *) wire w177;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u177 (
        .dataa(chain[177]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w177));
    assign chain[178] = w177;
    (* keep = 1, preserve = 1 *) wire w178;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u178 (
        .dataa(chain[178]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w178));
    assign chain[179] = w178;
    (* keep = 1, preserve = 1 *) wire w179;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u179 (
        .dataa(chain[179]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w179));
    assign chain[180] = w179;
    (* keep = 1, preserve = 1 *) wire w180;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u180 (
        .dataa(chain[180]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w180));
    assign chain[181] = w180;
    (* keep = 1, preserve = 1 *) wire w181;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u181 (
        .dataa(chain[181]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w181));
    assign chain[182] = w181;
    (* keep = 1, preserve = 1 *) wire w182;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u182 (
        .dataa(chain[182]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w182));
    assign chain[183] = w182;
    (* keep = 1, preserve = 1 *) wire w183;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u183 (
        .dataa(chain[183]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w183));
    assign chain[184] = w183;
    (* keep = 1, preserve = 1 *) wire w184;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u184 (
        .dataa(chain[184]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w184));
    assign chain[185] = w184;
    (* keep = 1, preserve = 1 *) wire w185;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u185 (
        .dataa(chain[185]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w185));
    assign chain[186] = w185;
    (* keep = 1, preserve = 1 *) wire w186;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u186 (
        .dataa(chain[186]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w186));
    assign chain[187] = w186;
    (* keep = 1, preserve = 1 *) wire w187;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u187 (
        .dataa(chain[187]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w187));
    assign chain[188] = w187;
    (* keep = 1, preserve = 1 *) wire w188;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u188 (
        .dataa(chain[188]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w188));
    assign chain[189] = w188;
    (* keep = 1, preserve = 1 *) wire w189;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u189 (
        .dataa(chain[189]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w189));
    assign chain[190] = w189;
    (* keep = 1, preserve = 1 *) wire w190;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u190 (
        .dataa(chain[190]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w190));
    assign chain[191] = w190;
    (* keep = 1, preserve = 1 *) wire w191;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u191 (
        .dataa(chain[191]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w191));
    assign chain[192] = w191;
    (* keep = 1, preserve = 1 *) wire w192;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u192 (
        .dataa(chain[192]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w192));
    assign chain[193] = w192;
    (* keep = 1, preserve = 1 *) wire w193;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u193 (
        .dataa(chain[193]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w193));
    assign chain[194] = w193;
    (* keep = 1, preserve = 1 *) wire w194;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u194 (
        .dataa(chain[194]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w194));
    assign chain[195] = w194;
    (* keep = 1, preserve = 1 *) wire w195;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u195 (
        .dataa(chain[195]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w195));
    assign chain[196] = w195;
    (* keep = 1, preserve = 1 *) wire w196;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u196 (
        .dataa(chain[196]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w196));
    assign chain[197] = w196;
    (* keep = 1, preserve = 1 *) wire w197;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u197 (
        .dataa(chain[197]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w197));
    assign chain[198] = w197;
    (* keep = 1, preserve = 1 *) wire w198;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u198 (
        .dataa(chain[198]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w198));
    assign chain[199] = w198;
    (* keep = 1, preserve = 1 *) wire w199;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u199 (
        .dataa(chain[199]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w199));
    assign chain[200] = w199;
    (* keep = 1, preserve = 1 *) wire w200;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u200 (
        .dataa(chain[200]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w200));
    assign chain[201] = w200;
    (* keep = 1, preserve = 1 *) wire w201;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u201 (
        .dataa(chain[201]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w201));
    assign chain[202] = w201;
    (* keep = 1, preserve = 1 *) wire w202;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u202 (
        .dataa(chain[202]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w202));
    assign chain[203] = w202;
    (* keep = 1, preserve = 1 *) wire w203;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u203 (
        .dataa(chain[203]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w203));
    assign chain[204] = w203;
    (* keep = 1, preserve = 1 *) wire w204;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u204 (
        .dataa(chain[204]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w204));
    assign chain[205] = w204;
    (* keep = 1, preserve = 1 *) wire w205;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u205 (
        .dataa(chain[205]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w205));
    assign chain[206] = w205;
    (* keep = 1, preserve = 1 *) wire w206;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u206 (
        .dataa(chain[206]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w206));
    assign chain[207] = w206;
    (* keep = 1, preserve = 1 *) wire w207;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u207 (
        .dataa(chain[207]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w207));
    assign chain[208] = w207;
    (* keep = 1, preserve = 1 *) wire w208;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u208 (
        .dataa(chain[208]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w208));
    assign chain[209] = w208;
    (* keep = 1, preserve = 1 *) wire w209;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u209 (
        .dataa(chain[209]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w209));
    assign chain[210] = w209;
    (* keep = 1, preserve = 1 *) wire w210;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u210 (
        .dataa(chain[210]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w210));
    assign chain[211] = w210;
    (* keep = 1, preserve = 1 *) wire w211;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u211 (
        .dataa(chain[211]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w211));
    assign chain[212] = w211;
    (* keep = 1, preserve = 1 *) wire w212;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u212 (
        .dataa(chain[212]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w212));
    assign chain[213] = w212;
    (* keep = 1, preserve = 1 *) wire w213;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u213 (
        .dataa(chain[213]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w213));
    assign chain[214] = w213;
    (* keep = 1, preserve = 1 *) wire w214;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u214 (
        .dataa(chain[214]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w214));
    assign chain[215] = w214;
    (* keep = 1, preserve = 1 *) wire w215;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u215 (
        .dataa(chain[215]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w215));
    assign chain[216] = w215;
    (* keep = 1, preserve = 1 *) wire w216;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u216 (
        .dataa(chain[216]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w216));
    assign chain[217] = w216;
    (* keep = 1, preserve = 1 *) wire w217;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u217 (
        .dataa(chain[217]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w217));
    assign chain[218] = w217;
    (* keep = 1, preserve = 1 *) wire w218;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u218 (
        .dataa(chain[218]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w218));
    assign chain[219] = w218;
    (* keep = 1, preserve = 1 *) wire w219;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u219 (
        .dataa(chain[219]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w219));
    assign chain[220] = w219;
    (* keep = 1, preserve = 1 *) wire w220;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u220 (
        .dataa(chain[220]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w220));
    assign chain[221] = w220;
    (* keep = 1, preserve = 1 *) wire w221;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u221 (
        .dataa(chain[221]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w221));
    assign chain[222] = w221;
    (* keep = 1, preserve = 1 *) wire w222;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u222 (
        .dataa(chain[222]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w222));
    assign chain[223] = w222;
    (* keep = 1, preserve = 1 *) wire w223;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u223 (
        .dataa(chain[223]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w223));
    assign chain[224] = w223;
    (* keep = 1, preserve = 1 *) wire w224;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u224 (
        .dataa(chain[224]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w224));
    assign chain[225] = w224;
    (* keep = 1, preserve = 1 *) wire w225;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u225 (
        .dataa(chain[225]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w225));
    assign chain[226] = w225;
    (* keep = 1, preserve = 1 *) wire w226;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u226 (
        .dataa(chain[226]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w226));
    assign chain[227] = w226;
    (* keep = 1, preserve = 1 *) wire w227;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u227 (
        .dataa(chain[227]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w227));
    assign chain[228] = w227;
    (* keep = 1, preserve = 1 *) wire w228;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u228 (
        .dataa(chain[228]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w228));
    assign chain[229] = w228;
    (* keep = 1, preserve = 1 *) wire w229;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u229 (
        .dataa(chain[229]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w229));
    assign chain[230] = w229;
    (* keep = 1, preserve = 1 *) wire w230;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u230 (
        .dataa(chain[230]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w230));
    assign chain[231] = w230;
    (* keep = 1, preserve = 1 *) wire w231;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u231 (
        .dataa(chain[231]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w231));
    assign chain[232] = w231;
    (* keep = 1, preserve = 1 *) wire w232;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u232 (
        .dataa(chain[232]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w232));
    assign chain[233] = w232;
    (* keep = 1, preserve = 1 *) wire w233;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u233 (
        .dataa(chain[233]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w233));
    assign chain[234] = w233;
    (* keep = 1, preserve = 1 *) wire w234;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u234 (
        .dataa(chain[234]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w234));
    assign chain[235] = w234;
    (* keep = 1, preserve = 1 *) wire w235;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u235 (
        .dataa(chain[235]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w235));
    assign chain[236] = w235;
    (* keep = 1, preserve = 1 *) wire w236;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u236 (
        .dataa(chain[236]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w236));
    assign chain[237] = w236;
    (* keep = 1, preserve = 1 *) wire w237;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u237 (
        .dataa(chain[237]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w237));
    assign chain[238] = w237;
    (* keep = 1, preserve = 1 *) wire w238;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u238 (
        .dataa(chain[238]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w238));
    assign chain[239] = w238;
    (* keep = 1, preserve = 1 *) wire w239;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u239 (
        .dataa(chain[239]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w239));
    assign chain[240] = w239;
    (* keep = 1, preserve = 1 *) wire w240;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u240 (
        .dataa(chain[240]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w240));
    assign chain[241] = w240;
    (* keep = 1, preserve = 1 *) wire w241;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u241 (
        .dataa(chain[241]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w241));
    assign chain[242] = w241;
    (* keep = 1, preserve = 1 *) wire w242;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u242 (
        .dataa(chain[242]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w242));
    assign chain[243] = w242;
    (* keep = 1, preserve = 1 *) wire w243;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u243 (
        .dataa(chain[243]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w243));
    assign chain[244] = w243;
    (* keep = 1, preserve = 1 *) wire w244;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u244 (
        .dataa(chain[244]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w244));
    assign chain[245] = w244;
    (* keep = 1, preserve = 1 *) wire w245;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u245 (
        .dataa(chain[245]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w245));
    assign chain[246] = w245;
    (* keep = 1, preserve = 1 *) wire w246;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u246 (
        .dataa(chain[246]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w246));
    assign chain[247] = w246;
    (* keep = 1, preserve = 1 *) wire w247;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u247 (
        .dataa(chain[247]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w247));
    assign chain[248] = w247;
    (* keep = 1, preserve = 1 *) wire w248;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u248 (
        .dataa(chain[248]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w248));
    assign chain[249] = w248;
    (* keep = 1, preserve = 1 *) wire w249;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u249 (
        .dataa(chain[249]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w249));
    assign chain[250] = w249;
    (* keep = 1, preserve = 1 *) wire w250;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u250 (
        .dataa(chain[250]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w250));
    assign chain[251] = w250;
    (* keep = 1, preserve = 1 *) wire w251;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u251 (
        .dataa(chain[251]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w251));
    assign chain[252] = w251;
    (* keep = 1, preserve = 1 *) wire w252;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u252 (
        .dataa(chain[252]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w252));
    assign chain[253] = w252;
    (* keep = 1, preserve = 1 *) wire w253;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u253 (
        .dataa(chain[253]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w253));
    assign chain[254] = w253;
    (* keep = 1, preserve = 1 *) wire w254;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u254 (
        .dataa(chain[254]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w254));
    assign chain[255] = w254;
    (* keep = 1, preserve = 1 *) wire w255;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u255 (
        .dataa(chain[255]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w255));
    assign chain[256] = w255;
    (* keep = 1, preserve = 1 *) wire w256;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u256 (
        .dataa(chain[256]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w256));
    assign chain[257] = w256;
    (* keep = 1, preserve = 1 *) wire w257;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u257 (
        .dataa(chain[257]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w257));
    assign chain[258] = w257;
    (* keep = 1, preserve = 1 *) wire w258;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u258 (
        .dataa(chain[258]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w258));
    assign chain[259] = w258;
    (* keep = 1, preserve = 1 *) wire w259;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u259 (
        .dataa(chain[259]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w259));
    assign chain[260] = w259;
    (* keep = 1, preserve = 1 *) wire w260;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u260 (
        .dataa(chain[260]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w260));
    assign chain[261] = w260;
    (* keep = 1, preserve = 1 *) wire w261;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u261 (
        .dataa(chain[261]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w261));
    assign chain[262] = w261;
    (* keep = 1, preserve = 1 *) wire w262;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u262 (
        .dataa(chain[262]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w262));
    assign chain[263] = w262;
    (* keep = 1, preserve = 1 *) wire w263;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u263 (
        .dataa(chain[263]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w263));
    assign chain[264] = w263;
    (* keep = 1, preserve = 1 *) wire w264;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u264 (
        .dataa(chain[264]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w264));
    assign chain[265] = w264;
    (* keep = 1, preserve = 1 *) wire w265;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u265 (
        .dataa(chain[265]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w265));
    assign chain[266] = w265;
    (* keep = 1, preserve = 1 *) wire w266;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u266 (
        .dataa(chain[266]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w266));
    assign chain[267] = w266;
    (* keep = 1, preserve = 1 *) wire w267;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u267 (
        .dataa(chain[267]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w267));
    assign chain[268] = w267;
    (* keep = 1, preserve = 1 *) wire w268;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u268 (
        .dataa(chain[268]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w268));
    assign chain[269] = w268;
    (* keep = 1, preserve = 1 *) wire w269;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u269 (
        .dataa(chain[269]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w269));
    assign chain[270] = w269;
    (* keep = 1, preserve = 1 *) wire w270;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u270 (
        .dataa(chain[270]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w270));
    assign chain[271] = w270;
    (* keep = 1, preserve = 1 *) wire w271;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u271 (
        .dataa(chain[271]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w271));
    assign chain[272] = w271;
    (* keep = 1, preserve = 1 *) wire w272;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u272 (
        .dataa(chain[272]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w272));
    assign chain[273] = w272;
    (* keep = 1, preserve = 1 *) wire w273;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u273 (
        .dataa(chain[273]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w273));
    assign chain[274] = w273;
    (* keep = 1, preserve = 1 *) wire w274;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u274 (
        .dataa(chain[274]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w274));
    assign chain[275] = w274;
    (* keep = 1, preserve = 1 *) wire w275;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u275 (
        .dataa(chain[275]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w275));
    assign chain[276] = w275;
    (* keep = 1, preserve = 1 *) wire w276;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u276 (
        .dataa(chain[276]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w276));
    assign chain[277] = w276;
    (* keep = 1, preserve = 1 *) wire w277;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u277 (
        .dataa(chain[277]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w277));
    assign chain[278] = w277;
    (* keep = 1, preserve = 1 *) wire w278;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u278 (
        .dataa(chain[278]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w278));
    assign chain[279] = w278;
    (* keep = 1, preserve = 1 *) wire w279;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u279 (
        .dataa(chain[279]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w279));
    assign chain[280] = w279;
    (* keep = 1, preserve = 1 *) wire w280;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u280 (
        .dataa(chain[280]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w280));
    assign chain[281] = w280;
    (* keep = 1, preserve = 1 *) wire w281;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u281 (
        .dataa(chain[281]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w281));
    assign chain[282] = w281;
    (* keep = 1, preserve = 1 *) wire w282;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u282 (
        .dataa(chain[282]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w282));
    assign chain[283] = w282;
    (* keep = 1, preserve = 1 *) wire w283;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u283 (
        .dataa(chain[283]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w283));
    assign chain[284] = w283;
    (* keep = 1, preserve = 1 *) wire w284;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u284 (
        .dataa(chain[284]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w284));
    assign chain[285] = w284;
    (* keep = 1, preserve = 1 *) wire w285;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u285 (
        .dataa(chain[285]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w285));
    assign chain[286] = w285;
    (* keep = 1, preserve = 1 *) wire w286;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u286 (
        .dataa(chain[286]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w286));
    assign chain[287] = w286;
    (* keep = 1, preserve = 1 *) wire w287;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u287 (
        .dataa(chain[287]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w287));
    assign chain[288] = w287;
    (* keep = 1, preserve = 1 *) wire w288;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u288 (
        .dataa(chain[288]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w288));
    assign chain[289] = w288;
    (* keep = 1, preserve = 1 *) wire w289;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u289 (
        .dataa(chain[289]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w289));
    assign chain[290] = w289;
    (* keep = 1, preserve = 1 *) wire w290;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u290 (
        .dataa(chain[290]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w290));
    assign chain[291] = w290;
    (* keep = 1, preserve = 1 *) wire w291;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u291 (
        .dataa(chain[291]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w291));
    assign chain[292] = w291;
    (* keep = 1, preserve = 1 *) wire w292;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u292 (
        .dataa(chain[292]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w292));
    assign chain[293] = w292;
    (* keep = 1, preserve = 1 *) wire w293;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u293 (
        .dataa(chain[293]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w293));
    assign chain[294] = w293;
    (* keep = 1, preserve = 1 *) wire w294;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u294 (
        .dataa(chain[294]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w294));
    assign chain[295] = w294;
    (* keep = 1, preserve = 1 *) wire w295;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u295 (
        .dataa(chain[295]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w295));
    assign chain[296] = w295;
    (* keep = 1, preserve = 1 *) wire w296;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u296 (
        .dataa(chain[296]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w296));
    assign chain[297] = w296;
    (* keep = 1, preserve = 1 *) wire w297;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u297 (
        .dataa(chain[297]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w297));
    assign chain[298] = w297;
    (* keep = 1, preserve = 1 *) wire w298;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u298 (
        .dataa(chain[298]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w298));
    assign chain[299] = w298;
    (* keep = 1, preserve = 1 *) wire w299;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u299 (
        .dataa(chain[299]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w299));
    assign chain[300] = w299;
    (* keep = 1, preserve = 1 *) wire w300;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u300 (
        .dataa(chain[300]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w300));
    assign chain[301] = w300;
    (* keep = 1, preserve = 1 *) wire w301;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u301 (
        .dataa(chain[301]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w301));
    assign chain[302] = w301;
    (* keep = 1, preserve = 1 *) wire w302;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u302 (
        .dataa(chain[302]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w302));
    assign chain[303] = w302;
    (* keep = 1, preserve = 1 *) wire w303;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u303 (
        .dataa(chain[303]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w303));
    assign chain[304] = w303;
    (* keep = 1, preserve = 1 *) wire w304;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u304 (
        .dataa(chain[304]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w304));
    assign chain[305] = w304;
    (* keep = 1, preserve = 1 *) wire w305;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u305 (
        .dataa(chain[305]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w305));
    assign chain[306] = w305;
    (* keep = 1, preserve = 1 *) wire w306;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u306 (
        .dataa(chain[306]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w306));
    assign chain[307] = w306;
    (* keep = 1, preserve = 1 *) wire w307;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u307 (
        .dataa(chain[307]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w307));
    assign chain[308] = w307;
    (* keep = 1, preserve = 1 *) wire w308;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u308 (
        .dataa(chain[308]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w308));
    assign chain[309] = w308;
    (* keep = 1, preserve = 1 *) wire w309;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u309 (
        .dataa(chain[309]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w309));
    assign chain[310] = w309;
    (* keep = 1, preserve = 1 *) wire w310;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u310 (
        .dataa(chain[310]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w310));
    assign chain[311] = w310;
    (* keep = 1, preserve = 1 *) wire w311;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u311 (
        .dataa(chain[311]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w311));
    assign chain[312] = w311;
    (* keep = 1, preserve = 1 *) wire w312;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u312 (
        .dataa(chain[312]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w312));
    assign chain[313] = w312;
    (* keep = 1, preserve = 1 *) wire w313;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u313 (
        .dataa(chain[313]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w313));
    assign chain[314] = w313;
    (* keep = 1, preserve = 1 *) wire w314;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u314 (
        .dataa(chain[314]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w314));
    assign chain[315] = w314;
    (* keep = 1, preserve = 1 *) wire w315;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u315 (
        .dataa(chain[315]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w315));
    assign chain[316] = w315;
    (* keep = 1, preserve = 1 *) wire w316;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u316 (
        .dataa(chain[316]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w316));
    assign chain[317] = w316;
    (* keep = 1, preserve = 1 *) wire w317;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u317 (
        .dataa(chain[317]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w317));
    assign chain[318] = w317;
    (* keep = 1, preserve = 1 *) wire w318;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u318 (
        .dataa(chain[318]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w318));
    assign chain[319] = w318;
    (* keep = 1, preserve = 1 *) wire w319;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u319 (
        .dataa(chain[319]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w319));
    assign chain[320] = w319;
    (* keep = 1, preserve = 1 *) wire w320;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u320 (
        .dataa(chain[320]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w320));
    assign chain[321] = w320;
    (* keep = 1, preserve = 1 *) wire w321;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u321 (
        .dataa(chain[321]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w321));
    assign chain[322] = w321;
    (* keep = 1, preserve = 1 *) wire w322;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u322 (
        .dataa(chain[322]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w322));
    assign chain[323] = w322;
    (* keep = 1, preserve = 1 *) wire w323;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u323 (
        .dataa(chain[323]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w323));
    assign chain[324] = w323;
    (* keep = 1, preserve = 1 *) wire w324;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u324 (
        .dataa(chain[324]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w324));
    assign chain[325] = w324;
    (* keep = 1, preserve = 1 *) wire w325;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u325 (
        .dataa(chain[325]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w325));
    assign chain[326] = w325;
    (* keep = 1, preserve = 1 *) wire w326;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u326 (
        .dataa(chain[326]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w326));
    assign chain[327] = w326;
    (* keep = 1, preserve = 1 *) wire w327;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u327 (
        .dataa(chain[327]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w327));
    assign chain[328] = w327;
    (* keep = 1, preserve = 1 *) wire w328;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u328 (
        .dataa(chain[328]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w328));
    assign chain[329] = w328;
    (* keep = 1, preserve = 1 *) wire w329;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u329 (
        .dataa(chain[329]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w329));
    assign chain[330] = w329;
    (* keep = 1, preserve = 1 *) wire w330;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u330 (
        .dataa(chain[330]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w330));
    assign chain[331] = w330;
    (* keep = 1, preserve = 1 *) wire w331;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u331 (
        .dataa(chain[331]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w331));
    assign chain[332] = w331;
    (* keep = 1, preserve = 1 *) wire w332;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u332 (
        .dataa(chain[332]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w332));
    assign chain[333] = w332;
    (* keep = 1, preserve = 1 *) wire w333;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u333 (
        .dataa(chain[333]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w333));
    assign chain[334] = w333;
    (* keep = 1, preserve = 1 *) wire w334;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u334 (
        .dataa(chain[334]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w334));
    assign chain[335] = w334;
    (* keep = 1, preserve = 1 *) wire w335;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u335 (
        .dataa(chain[335]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w335));
    assign chain[336] = w335;
    (* keep = 1, preserve = 1 *) wire w336;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u336 (
        .dataa(chain[336]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w336));
    assign chain[337] = w336;
    (* keep = 1, preserve = 1 *) wire w337;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u337 (
        .dataa(chain[337]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w337));
    assign chain[338] = w337;
    (* keep = 1, preserve = 1 *) wire w338;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u338 (
        .dataa(chain[338]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w338));
    assign chain[339] = w338;
    (* keep = 1, preserve = 1 *) wire w339;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u339 (
        .dataa(chain[339]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w339));
    assign chain[340] = w339;
    (* keep = 1, preserve = 1 *) wire w340;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u340 (
        .dataa(chain[340]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w340));
    assign chain[341] = w340;
    (* keep = 1, preserve = 1 *) wire w341;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u341 (
        .dataa(chain[341]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w341));
    assign chain[342] = w341;
    (* keep = 1, preserve = 1 *) wire w342;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u342 (
        .dataa(chain[342]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w342));
    assign chain[343] = w342;
    (* keep = 1, preserve = 1 *) wire w343;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u343 (
        .dataa(chain[343]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w343));
    assign chain[344] = w343;
    (* keep = 1, preserve = 1 *) wire w344;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u344 (
        .dataa(chain[344]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w344));
    assign chain[345] = w344;
    (* keep = 1, preserve = 1 *) wire w345;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u345 (
        .dataa(chain[345]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w345));
    assign chain[346] = w345;
    (* keep = 1, preserve = 1 *) wire w346;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u346 (
        .dataa(chain[346]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w346));
    assign chain[347] = w346;
    (* keep = 1, preserve = 1 *) wire w347;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u347 (
        .dataa(chain[347]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w347));
    assign chain[348] = w347;
    (* keep = 1, preserve = 1 *) wire w348;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u348 (
        .dataa(chain[348]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w348));
    assign chain[349] = w348;
    (* keep = 1, preserve = 1 *) wire w349;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u349 (
        .dataa(chain[349]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w349));
    assign chain[350] = w349;
    (* keep = 1, preserve = 1 *) wire w350;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u350 (
        .dataa(chain[350]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w350));
    assign chain[351] = w350;
    (* keep = 1, preserve = 1 *) wire w351;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u351 (
        .dataa(chain[351]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w351));
    assign chain[352] = w351;
    (* keep = 1, preserve = 1 *) wire w352;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u352 (
        .dataa(chain[352]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w352));
    assign chain[353] = w352;
    (* keep = 1, preserve = 1 *) wire w353;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u353 (
        .dataa(chain[353]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w353));
    assign chain[354] = w353;
    (* keep = 1, preserve = 1 *) wire w354;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u354 (
        .dataa(chain[354]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w354));
    assign chain[355] = w354;
    (* keep = 1, preserve = 1 *) wire w355;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u355 (
        .dataa(chain[355]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w355));
    assign chain[356] = w355;
    (* keep = 1, preserve = 1 *) wire w356;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u356 (
        .dataa(chain[356]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w356));
    assign chain[357] = w356;
    (* keep = 1, preserve = 1 *) wire w357;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u357 (
        .dataa(chain[357]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w357));
    assign chain[358] = w357;
    (* keep = 1, preserve = 1 *) wire w358;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u358 (
        .dataa(chain[358]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w358));
    assign chain[359] = w358;
    (* keep = 1, preserve = 1 *) wire w359;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u359 (
        .dataa(chain[359]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w359));
    assign chain[360] = w359;
    (* keep = 1, preserve = 1 *) wire w360;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u360 (
        .dataa(chain[360]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w360));
    assign chain[361] = w360;
    (* keep = 1, preserve = 1 *) wire w361;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u361 (
        .dataa(chain[361]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w361));
    assign chain[362] = w361;
    (* keep = 1, preserve = 1 *) wire w362;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u362 (
        .dataa(chain[362]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w362));
    assign chain[363] = w362;
    (* keep = 1, preserve = 1 *) wire w363;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u363 (
        .dataa(chain[363]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w363));
    assign chain[364] = w363;
    (* keep = 1, preserve = 1 *) wire w364;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u364 (
        .dataa(chain[364]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w364));
    assign chain[365] = w364;
    (* keep = 1, preserve = 1 *) wire w365;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u365 (
        .dataa(chain[365]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w365));
    assign chain[366] = w365;
    (* keep = 1, preserve = 1 *) wire w366;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u366 (
        .dataa(chain[366]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w366));
    assign chain[367] = w366;
    (* keep = 1, preserve = 1 *) wire w367;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u367 (
        .dataa(chain[367]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w367));
    assign chain[368] = w367;
    (* keep = 1, preserve = 1 *) wire w368;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u368 (
        .dataa(chain[368]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w368));
    assign chain[369] = w368;
    (* keep = 1, preserve = 1 *) wire w369;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u369 (
        .dataa(chain[369]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w369));
    assign chain[370] = w369;
    (* keep = 1, preserve = 1 *) wire w370;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u370 (
        .dataa(chain[370]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w370));
    assign chain[371] = w370;
    (* keep = 1, preserve = 1 *) wire w371;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u371 (
        .dataa(chain[371]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w371));
    assign chain[372] = w371;
    (* keep = 1, preserve = 1 *) wire w372;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u372 (
        .dataa(chain[372]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w372));
    assign chain[373] = w372;
    (* keep = 1, preserve = 1 *) wire w373;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u373 (
        .dataa(chain[373]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w373));
    assign chain[374] = w373;
    (* keep = 1, preserve = 1 *) wire w374;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u374 (
        .dataa(chain[374]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w374));
    assign chain[375] = w374;
    (* keep = 1, preserve = 1 *) wire w375;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u375 (
        .dataa(chain[375]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w375));
    assign chain[376] = w375;
    (* keep = 1, preserve = 1 *) wire w376;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u376 (
        .dataa(chain[376]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w376));
    assign chain[377] = w376;
    (* keep = 1, preserve = 1 *) wire w377;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u377 (
        .dataa(chain[377]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w377));
    assign chain[378] = w377;
    (* keep = 1, preserve = 1 *) wire w378;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u378 (
        .dataa(chain[378]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w378));
    assign chain[379] = w378;
    (* keep = 1, preserve = 1 *) wire w379;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u379 (
        .dataa(chain[379]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w379));
    assign chain[380] = w379;
    (* keep = 1, preserve = 1 *) wire w380;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u380 (
        .dataa(chain[380]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w380));
    assign chain[381] = w380;
    (* keep = 1, preserve = 1 *) wire w381;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u381 (
        .dataa(chain[381]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w381));
    assign chain[382] = w381;
    (* keep = 1, preserve = 1 *) wire w382;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u382 (
        .dataa(chain[382]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w382));
    assign chain[383] = w382;
    (* keep = 1, preserve = 1 *) wire w383;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u383 (
        .dataa(chain[383]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w383));
    assign chain[384] = w383;
    (* keep = 1, preserve = 1 *) wire w384;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u384 (
        .dataa(chain[384]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w384));
    assign chain[385] = w384;
    (* keep = 1, preserve = 1 *) wire w385;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u385 (
        .dataa(chain[385]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w385));
    assign chain[386] = w385;
    (* keep = 1, preserve = 1 *) wire w386;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u386 (
        .dataa(chain[386]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w386));
    assign chain[387] = w386;
    (* keep = 1, preserve = 1 *) wire w387;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u387 (
        .dataa(chain[387]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w387));
    assign chain[388] = w387;
    (* keep = 1, preserve = 1 *) wire w388;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u388 (
        .dataa(chain[388]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w388));
    assign chain[389] = w388;
    (* keep = 1, preserve = 1 *) wire w389;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u389 (
        .dataa(chain[389]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w389));
    assign chain[390] = w389;
    (* keep = 1, preserve = 1 *) wire w390;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u390 (
        .dataa(chain[390]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w390));
    assign chain[391] = w390;
    (* keep = 1, preserve = 1 *) wire w391;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u391 (
        .dataa(chain[391]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w391));
    assign chain[392] = w391;
    (* keep = 1, preserve = 1 *) wire w392;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u392 (
        .dataa(chain[392]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w392));
    assign chain[393] = w392;
    (* keep = 1, preserve = 1 *) wire w393;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u393 (
        .dataa(chain[393]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w393));
    assign chain[394] = w393;
    (* keep = 1, preserve = 1 *) wire w394;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u394 (
        .dataa(chain[394]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w394));
    assign chain[395] = w394;
    (* keep = 1, preserve = 1 *) wire w395;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u395 (
        .dataa(chain[395]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w395));
    assign chain[396] = w395;
    (* keep = 1, preserve = 1 *) wire w396;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u396 (
        .dataa(chain[396]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w396));
    assign chain[397] = w396;
    (* keep = 1, preserve = 1 *) wire w397;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u397 (
        .dataa(chain[397]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w397));
    assign chain[398] = w397;
    (* keep = 1, preserve = 1 *) wire w398;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u398 (
        .dataa(chain[398]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w398));
    assign chain[399] = w398;
    (* keep = 1, preserve = 1 *) wire w399;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u399 (
        .dataa(chain[399]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w399));
    assign chain[400] = w399;
    (* keep = 1, preserve = 1 *) wire w400;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u400 (
        .dataa(chain[400]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w400));
    assign chain[401] = w400;
    (* keep = 1, preserve = 1 *) wire w401;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u401 (
        .dataa(chain[401]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w401));
    assign chain[402] = w401;
    (* keep = 1, preserve = 1 *) wire w402;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u402 (
        .dataa(chain[402]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w402));
    assign chain[403] = w402;
    (* keep = 1, preserve = 1 *) wire w403;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u403 (
        .dataa(chain[403]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w403));
    assign chain[404] = w403;
    (* keep = 1, preserve = 1 *) wire w404;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u404 (
        .dataa(chain[404]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w404));
    assign chain[405] = w404;
    (* keep = 1, preserve = 1 *) wire w405;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u405 (
        .dataa(chain[405]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w405));
    assign chain[406] = w405;
    (* keep = 1, preserve = 1 *) wire w406;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u406 (
        .dataa(chain[406]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w406));
    assign chain[407] = w406;
    (* keep = 1, preserve = 1 *) wire w407;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u407 (
        .dataa(chain[407]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w407));
    assign chain[408] = w407;
    (* keep = 1, preserve = 1 *) wire w408;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u408 (
        .dataa(chain[408]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w408));
    assign chain[409] = w408;
    (* keep = 1, preserve = 1 *) wire w409;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u409 (
        .dataa(chain[409]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w409));
    assign chain[410] = w409;
    (* keep = 1, preserve = 1 *) wire w410;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u410 (
        .dataa(chain[410]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w410));
    assign chain[411] = w410;
    (* keep = 1, preserve = 1 *) wire w411;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u411 (
        .dataa(chain[411]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w411));
    assign chain[412] = w411;
    (* keep = 1, preserve = 1 *) wire w412;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u412 (
        .dataa(chain[412]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w412));
    assign chain[413] = w412;
    (* keep = 1, preserve = 1 *) wire w413;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u413 (
        .dataa(chain[413]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w413));
    assign chain[414] = w413;
    (* keep = 1, preserve = 1 *) wire w414;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u414 (
        .dataa(chain[414]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w414));
    assign chain[415] = w414;
    (* keep = 1, preserve = 1 *) wire w415;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u415 (
        .dataa(chain[415]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w415));
    assign chain[416] = w415;
    (* keep = 1, preserve = 1 *) wire w416;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u416 (
        .dataa(chain[416]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w416));
    assign chain[417] = w416;
    (* keep = 1, preserve = 1 *) wire w417;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u417 (
        .dataa(chain[417]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w417));
    assign chain[418] = w417;
    (* keep = 1, preserve = 1 *) wire w418;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u418 (
        .dataa(chain[418]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w418));
    assign chain[419] = w418;
    (* keep = 1, preserve = 1 *) wire w419;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u419 (
        .dataa(chain[419]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w419));
    assign chain[420] = w419;
    (* keep = 1, preserve = 1 *) wire w420;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u420 (
        .dataa(chain[420]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w420));
    assign chain[421] = w420;
    (* keep = 1, preserve = 1 *) wire w421;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u421 (
        .dataa(chain[421]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w421));
    assign chain[422] = w421;
    (* keep = 1, preserve = 1 *) wire w422;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u422 (
        .dataa(chain[422]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w422));
    assign chain[423] = w422;
    (* keep = 1, preserve = 1 *) wire w423;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u423 (
        .dataa(chain[423]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w423));
    assign chain[424] = w423;
    (* keep = 1, preserve = 1 *) wire w424;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u424 (
        .dataa(chain[424]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w424));
    assign chain[425] = w424;
    (* keep = 1, preserve = 1 *) wire w425;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u425 (
        .dataa(chain[425]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w425));
    assign chain[426] = w425;
    (* keep = 1, preserve = 1 *) wire w426;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u426 (
        .dataa(chain[426]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w426));
    assign chain[427] = w426;
    (* keep = 1, preserve = 1 *) wire w427;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u427 (
        .dataa(chain[427]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w427));
    assign chain[428] = w427;
    (* keep = 1, preserve = 1 *) wire w428;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u428 (
        .dataa(chain[428]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w428));
    assign chain[429] = w428;
    (* keep = 1, preserve = 1 *) wire w429;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u429 (
        .dataa(chain[429]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w429));
    assign chain[430] = w429;
    (* keep = 1, preserve = 1 *) wire w430;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u430 (
        .dataa(chain[430]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w430));
    assign chain[431] = w430;
    (* keep = 1, preserve = 1 *) wire w431;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u431 (
        .dataa(chain[431]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w431));
    assign chain[432] = w431;
    (* keep = 1, preserve = 1 *) wire w432;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u432 (
        .dataa(chain[432]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w432));
    assign chain[433] = w432;
    (* keep = 1, preserve = 1 *) wire w433;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u433 (
        .dataa(chain[433]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w433));
    assign chain[434] = w433;
    (* keep = 1, preserve = 1 *) wire w434;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u434 (
        .dataa(chain[434]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w434));
    assign chain[435] = w434;
    (* keep = 1, preserve = 1 *) wire w435;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u435 (
        .dataa(chain[435]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w435));
    assign chain[436] = w435;
    (* keep = 1, preserve = 1 *) wire w436;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u436 (
        .dataa(chain[436]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w436));
    assign chain[437] = w436;
    (* keep = 1, preserve = 1 *) wire w437;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u437 (
        .dataa(chain[437]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w437));
    assign chain[438] = w437;
    (* keep = 1, preserve = 1 *) wire w438;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u438 (
        .dataa(chain[438]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w438));
    assign chain[439] = w438;
    (* keep = 1, preserve = 1 *) wire w439;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u439 (
        .dataa(chain[439]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w439));
    assign chain[440] = w439;
    (* keep = 1, preserve = 1 *) wire w440;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u440 (
        .dataa(chain[440]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w440));
    assign chain[441] = w440;
    (* keep = 1, preserve = 1 *) wire w441;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u441 (
        .dataa(chain[441]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w441));
    assign chain[442] = w441;
    (* keep = 1, preserve = 1 *) wire w442;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u442 (
        .dataa(chain[442]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w442));
    assign chain[443] = w442;
    (* keep = 1, preserve = 1 *) wire w443;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u443 (
        .dataa(chain[443]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w443));
    assign chain[444] = w443;
    (* keep = 1, preserve = 1 *) wire w444;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u444 (
        .dataa(chain[444]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w444));
    assign chain[445] = w444;
    (* keep = 1, preserve = 1 *) wire w445;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u445 (
        .dataa(chain[445]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w445));
    assign chain[446] = w445;
    (* keep = 1, preserve = 1 *) wire w446;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u446 (
        .dataa(chain[446]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w446));
    assign chain[447] = w446;
    (* keep = 1, preserve = 1 *) wire w447;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u447 (
        .dataa(chain[447]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w447));
    assign chain[448] = w447;
    (* keep = 1, preserve = 1 *) wire w448;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u448 (
        .dataa(chain[448]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w448));
    assign chain[449] = w448;
    (* keep = 1, preserve = 1 *) wire w449;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u449 (
        .dataa(chain[449]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w449));
    assign chain[450] = w449;
    (* keep = 1, preserve = 1 *) wire w450;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u450 (
        .dataa(chain[450]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w450));
    assign chain[451] = w450;
    (* keep = 1, preserve = 1 *) wire w451;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u451 (
        .dataa(chain[451]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w451));
    assign chain[452] = w451;
    (* keep = 1, preserve = 1 *) wire w452;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u452 (
        .dataa(chain[452]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w452));
    assign chain[453] = w452;
    (* keep = 1, preserve = 1 *) wire w453;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u453 (
        .dataa(chain[453]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w453));
    assign chain[454] = w453;
    (* keep = 1, preserve = 1 *) wire w454;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u454 (
        .dataa(chain[454]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w454));
    assign chain[455] = w454;
    (* keep = 1, preserve = 1 *) wire w455;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u455 (
        .dataa(chain[455]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w455));
    assign chain[456] = w455;
    (* keep = 1, preserve = 1 *) wire w456;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u456 (
        .dataa(chain[456]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w456));
    assign chain[457] = w456;
    (* keep = 1, preserve = 1 *) wire w457;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u457 (
        .dataa(chain[457]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w457));
    assign chain[458] = w457;
    (* keep = 1, preserve = 1 *) wire w458;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u458 (
        .dataa(chain[458]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w458));
    assign chain[459] = w458;
    (* keep = 1, preserve = 1 *) wire w459;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u459 (
        .dataa(chain[459]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w459));
    assign chain[460] = w459;
    (* keep = 1, preserve = 1 *) wire w460;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u460 (
        .dataa(chain[460]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w460));
    assign chain[461] = w460;
    (* keep = 1, preserve = 1 *) wire w461;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u461 (
        .dataa(chain[461]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w461));
    assign chain[462] = w461;
    (* keep = 1, preserve = 1 *) wire w462;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u462 (
        .dataa(chain[462]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w462));
    assign chain[463] = w462;
    (* keep = 1, preserve = 1 *) wire w463;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u463 (
        .dataa(chain[463]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w463));
    assign chain[464] = w463;
    (* keep = 1, preserve = 1 *) wire w464;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u464 (
        .dataa(chain[464]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w464));
    assign chain[465] = w464;
    (* keep = 1, preserve = 1 *) wire w465;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u465 (
        .dataa(chain[465]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w465));
    assign chain[466] = w465;
    (* keep = 1, preserve = 1 *) wire w466;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u466 (
        .dataa(chain[466]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w466));
    assign chain[467] = w466;
    (* keep = 1, preserve = 1 *) wire w467;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u467 (
        .dataa(chain[467]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w467));
    assign chain[468] = w467;
    (* keep = 1, preserve = 1 *) wire w468;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u468 (
        .dataa(chain[468]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w468));
    assign chain[469] = w468;
    (* keep = 1, preserve = 1 *) wire w469;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u469 (
        .dataa(chain[469]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w469));
    assign chain[470] = w469;
    (* keep = 1, preserve = 1 *) wire w470;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u470 (
        .dataa(chain[470]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w470));
    assign chain[471] = w470;
    (* keep = 1, preserve = 1 *) wire w471;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u471 (
        .dataa(chain[471]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w471));
    assign chain[472] = w471;
    (* keep = 1, preserve = 1 *) wire w472;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u472 (
        .dataa(chain[472]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w472));
    assign chain[473] = w472;
    (* keep = 1, preserve = 1 *) wire w473;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u473 (
        .dataa(chain[473]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w473));
    assign chain[474] = w473;
    (* keep = 1, preserve = 1 *) wire w474;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u474 (
        .dataa(chain[474]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w474));
    assign chain[475] = w474;
    (* keep = 1, preserve = 1 *) wire w475;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u475 (
        .dataa(chain[475]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w475));
    assign chain[476] = w475;
    (* keep = 1, preserve = 1 *) wire w476;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u476 (
        .dataa(chain[476]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w476));
    assign chain[477] = w476;
    (* keep = 1, preserve = 1 *) wire w477;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u477 (
        .dataa(chain[477]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w477));
    assign chain[478] = w477;
    (* keep = 1, preserve = 1 *) wire w478;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u478 (
        .dataa(chain[478]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w478));
    assign chain[479] = w478;
    (* keep = 1, preserve = 1 *) wire w479;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u479 (
        .dataa(chain[479]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w479));
    assign chain[480] = w479;
    (* keep = 1, preserve = 1 *) wire w480;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u480 (
        .dataa(chain[480]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w480));
    assign chain[481] = w480;
    (* keep = 1, preserve = 1 *) wire w481;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u481 (
        .dataa(chain[481]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w481));
    assign chain[482] = w481;
    (* keep = 1, preserve = 1 *) wire w482;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u482 (
        .dataa(chain[482]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w482));
    assign chain[483] = w482;
    (* keep = 1, preserve = 1 *) wire w483;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u483 (
        .dataa(chain[483]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w483));
    assign chain[484] = w483;
    (* keep = 1, preserve = 1 *) wire w484;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u484 (
        .dataa(chain[484]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w484));
    assign chain[485] = w484;
    (* keep = 1, preserve = 1 *) wire w485;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u485 (
        .dataa(chain[485]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w485));
    assign chain[486] = w485;
    (* keep = 1, preserve = 1 *) wire w486;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u486 (
        .dataa(chain[486]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w486));
    assign chain[487] = w486;
    (* keep = 1, preserve = 1 *) wire w487;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u487 (
        .dataa(chain[487]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w487));
    assign chain[488] = w487;
    (* keep = 1, preserve = 1 *) wire w488;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u488 (
        .dataa(chain[488]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w488));
    assign chain[489] = w488;
    (* keep = 1, preserve = 1 *) wire w489;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u489 (
        .dataa(chain[489]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w489));
    assign chain[490] = w489;
    (* keep = 1, preserve = 1 *) wire w490;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u490 (
        .dataa(chain[490]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w490));
    assign chain[491] = w490;
    (* keep = 1, preserve = 1 *) wire w491;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u491 (
        .dataa(chain[491]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w491));
    assign chain[492] = w491;
    (* keep = 1, preserve = 1 *) wire w492;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u492 (
        .dataa(chain[492]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w492));
    assign chain[493] = w492;
    (* keep = 1, preserve = 1 *) wire w493;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u493 (
        .dataa(chain[493]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w493));
    assign chain[494] = w493;
    (* keep = 1, preserve = 1 *) wire w494;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u494 (
        .dataa(chain[494]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w494));
    assign chain[495] = w494;
    (* keep = 1, preserve = 1 *) wire w495;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u495 (
        .dataa(chain[495]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w495));
    assign chain[496] = w495;
    (* keep = 1, preserve = 1 *) wire w496;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u496 (
        .dataa(chain[496]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w496));
    assign chain[497] = w496;
    (* keep = 1, preserve = 1 *) wire w497;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u497 (
        .dataa(chain[497]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w497));
    assign chain[498] = w497;
    (* keep = 1, preserve = 1 *) wire w498;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u498 (
        .dataa(chain[498]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w498));
    assign chain[499] = w498;
    (* keep = 1, preserve = 1 *) wire w499;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u499 (
        .dataa(chain[499]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w499));
    assign chain[500] = w499;
    (* keep = 1, preserve = 1 *) wire w500;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u500 (
        .dataa(chain[500]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w500));
    assign chain[501] = w500;
    (* keep = 1, preserve = 1 *) wire w501;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u501 (
        .dataa(chain[501]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w501));
    assign chain[502] = w501;
    (* keep = 1, preserve = 1 *) wire w502;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u502 (
        .dataa(chain[502]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w502));
    assign chain[503] = w502;
    (* keep = 1, preserve = 1 *) wire w503;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u503 (
        .dataa(chain[503]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w503));
    assign chain[504] = w503;
    (* keep = 1, preserve = 1 *) wire w504;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u504 (
        .dataa(chain[504]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w504));
    assign chain[505] = w504;
    (* keep = 1, preserve = 1 *) wire w505;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u505 (
        .dataa(chain[505]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w505));
    assign chain[506] = w505;
    (* keep = 1, preserve = 1 *) wire w506;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u506 (
        .dataa(chain[506]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w506));
    assign chain[507] = w506;
    (* keep = 1, preserve = 1 *) wire w507;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u507 (
        .dataa(chain[507]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w507));
    assign chain[508] = w507;
    (* keep = 1, preserve = 1 *) wire w508;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u508 (
        .dataa(chain[508]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w508));
    assign chain[509] = w508;
    (* keep = 1, preserve = 1 *) wire w509;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u509 (
        .dataa(chain[509]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w509));
    assign chain[510] = w509;
    (* keep = 1, preserve = 1 *) wire w510;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u510 (
        .dataa(chain[510]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w510));
    assign chain[511] = w510;
    (* keep = 1, preserve = 1 *) wire w511;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u511 (
        .dataa(chain[511]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w511));
    assign chain[512] = w511;
    (* keep = 1, preserve = 1 *) wire w512;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u512 (
        .dataa(chain[512]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w512));
    assign chain[513] = w512;
    (* keep = 1, preserve = 1 *) wire w513;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u513 (
        .dataa(chain[513]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w513));
    assign chain[514] = w513;
    (* keep = 1, preserve = 1 *) wire w514;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u514 (
        .dataa(chain[514]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w514));
    assign chain[515] = w514;
    (* keep = 1, preserve = 1 *) wire w515;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u515 (
        .dataa(chain[515]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w515));
    assign chain[516] = w515;
    (* keep = 1, preserve = 1 *) wire w516;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u516 (
        .dataa(chain[516]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w516));
    assign chain[517] = w516;
    (* keep = 1, preserve = 1 *) wire w517;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u517 (
        .dataa(chain[517]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w517));
    assign chain[518] = w517;
    (* keep = 1, preserve = 1 *) wire w518;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u518 (
        .dataa(chain[518]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w518));
    assign chain[519] = w518;
    (* keep = 1, preserve = 1 *) wire w519;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u519 (
        .dataa(chain[519]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w519));
    assign chain[520] = w519;
    (* keep = 1, preserve = 1 *) wire w520;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u520 (
        .dataa(chain[520]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w520));
    assign chain[521] = w520;
    (* keep = 1, preserve = 1 *) wire w521;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u521 (
        .dataa(chain[521]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w521));
    assign chain[522] = w521;
    (* keep = 1, preserve = 1 *) wire w522;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u522 (
        .dataa(chain[522]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w522));
    assign chain[523] = w522;
    (* keep = 1, preserve = 1 *) wire w523;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u523 (
        .dataa(chain[523]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w523));
    assign chain[524] = w523;
    (* keep = 1, preserve = 1 *) wire w524;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u524 (
        .dataa(chain[524]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w524));
    assign chain[525] = w524;
    (* keep = 1, preserve = 1 *) wire w525;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u525 (
        .dataa(chain[525]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w525));
    assign chain[526] = w525;
    (* keep = 1, preserve = 1 *) wire w526;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u526 (
        .dataa(chain[526]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w526));
    assign chain[527] = w526;
    (* keep = 1, preserve = 1 *) wire w527;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u527 (
        .dataa(chain[527]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w527));
    assign chain[528] = w527;
    (* keep = 1, preserve = 1 *) wire w528;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u528 (
        .dataa(chain[528]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w528));
    assign chain[529] = w528;
    (* keep = 1, preserve = 1 *) wire w529;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u529 (
        .dataa(chain[529]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w529));
    assign chain[530] = w529;
    (* keep = 1, preserve = 1 *) wire w530;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u530 (
        .dataa(chain[530]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w530));
    assign chain[531] = w530;
    (* keep = 1, preserve = 1 *) wire w531;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u531 (
        .dataa(chain[531]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w531));
    assign chain[532] = w531;
    (* keep = 1, preserve = 1 *) wire w532;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u532 (
        .dataa(chain[532]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w532));
    assign chain[533] = w532;
    (* keep = 1, preserve = 1 *) wire w533;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u533 (
        .dataa(chain[533]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w533));
    assign chain[534] = w533;
    (* keep = 1, preserve = 1 *) wire w534;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u534 (
        .dataa(chain[534]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w534));
    assign chain[535] = w534;
    (* keep = 1, preserve = 1 *) wire w535;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u535 (
        .dataa(chain[535]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w535));
    assign chain[536] = w535;
    (* keep = 1, preserve = 1 *) wire w536;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u536 (
        .dataa(chain[536]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w536));
    assign chain[537] = w536;
    (* keep = 1, preserve = 1 *) wire w537;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u537 (
        .dataa(chain[537]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w537));
    assign chain[538] = w537;
    (* keep = 1, preserve = 1 *) wire w538;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u538 (
        .dataa(chain[538]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w538));
    assign chain[539] = w538;
    (* keep = 1, preserve = 1 *) wire w539;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u539 (
        .dataa(chain[539]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w539));
    assign chain[540] = w539;
    (* keep = 1, preserve = 1 *) wire w540;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u540 (
        .dataa(chain[540]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w540));
    assign chain[541] = w540;
    (* keep = 1, preserve = 1 *) wire w541;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u541 (
        .dataa(chain[541]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w541));
    assign chain[542] = w541;
    (* keep = 1, preserve = 1 *) wire w542;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u542 (
        .dataa(chain[542]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w542));
    assign chain[543] = w542;
    (* keep = 1, preserve = 1 *) wire w543;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u543 (
        .dataa(chain[543]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w543));
    assign chain[544] = w543;
    (* keep = 1, preserve = 1 *) wire w544;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u544 (
        .dataa(chain[544]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w544));
    assign chain[545] = w544;
    (* keep = 1, preserve = 1 *) wire w545;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u545 (
        .dataa(chain[545]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w545));
    assign chain[546] = w545;
    (* keep = 1, preserve = 1 *) wire w546;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u546 (
        .dataa(chain[546]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w546));
    assign chain[547] = w546;
    (* keep = 1, preserve = 1 *) wire w547;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u547 (
        .dataa(chain[547]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w547));
    assign chain[548] = w547;
    (* keep = 1, preserve = 1 *) wire w548;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u548 (
        .dataa(chain[548]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w548));
    assign chain[549] = w548;
    (* keep = 1, preserve = 1 *) wire w549;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u549 (
        .dataa(chain[549]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w549));
    assign chain[550] = w549;
    (* keep = 1, preserve = 1 *) wire w550;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u550 (
        .dataa(chain[550]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w550));
    assign chain[551] = w550;
    (* keep = 1, preserve = 1 *) wire w551;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u551 (
        .dataa(chain[551]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w551));
    assign chain[552] = w551;
    (* keep = 1, preserve = 1 *) wire w552;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u552 (
        .dataa(chain[552]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w552));
    assign chain[553] = w552;
    (* keep = 1, preserve = 1 *) wire w553;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u553 (
        .dataa(chain[553]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w553));
    assign chain[554] = w553;
    (* keep = 1, preserve = 1 *) wire w554;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u554 (
        .dataa(chain[554]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w554));
    assign chain[555] = w554;
    (* keep = 1, preserve = 1 *) wire w555;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u555 (
        .dataa(chain[555]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w555));
    assign chain[556] = w555;
    (* keep = 1, preserve = 1 *) wire w556;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u556 (
        .dataa(chain[556]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w556));
    assign chain[557] = w556;
    (* keep = 1, preserve = 1 *) wire w557;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u557 (
        .dataa(chain[557]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w557));
    assign chain[558] = w557;
    (* keep = 1, preserve = 1 *) wire w558;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u558 (
        .dataa(chain[558]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w558));
    assign chain[559] = w558;
    (* keep = 1, preserve = 1 *) wire w559;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u559 (
        .dataa(chain[559]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w559));
    assign chain[560] = w559;
    (* keep = 1, preserve = 1 *) wire w560;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u560 (
        .dataa(chain[560]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w560));
    assign chain[561] = w560;
    (* keep = 1, preserve = 1 *) wire w561;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u561 (
        .dataa(chain[561]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w561));
    assign chain[562] = w561;
    (* keep = 1, preserve = 1 *) wire w562;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u562 (
        .dataa(chain[562]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w562));
    assign chain[563] = w562;
    (* keep = 1, preserve = 1 *) wire w563;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u563 (
        .dataa(chain[563]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w563));
    assign chain[564] = w563;
    (* keep = 1, preserve = 1 *) wire w564;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u564 (
        .dataa(chain[564]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w564));
    assign chain[565] = w564;
    (* keep = 1, preserve = 1 *) wire w565;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u565 (
        .dataa(chain[565]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w565));
    assign chain[566] = w565;
    (* keep = 1, preserve = 1 *) wire w566;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u566 (
        .dataa(chain[566]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w566));
    assign chain[567] = w566;
    (* keep = 1, preserve = 1 *) wire w567;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u567 (
        .dataa(chain[567]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w567));
    assign chain[568] = w567;
    (* keep = 1, preserve = 1 *) wire w568;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u568 (
        .dataa(chain[568]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w568));
    assign chain[569] = w568;
    (* keep = 1, preserve = 1 *) wire w569;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u569 (
        .dataa(chain[569]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w569));
    assign chain[570] = w569;
    (* keep = 1, preserve = 1 *) wire w570;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u570 (
        .dataa(chain[570]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w570));
    assign chain[571] = w570;
    (* keep = 1, preserve = 1 *) wire w571;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u571 (
        .dataa(chain[571]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w571));
    assign chain[572] = w571;
    (* keep = 1, preserve = 1 *) wire w572;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u572 (
        .dataa(chain[572]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w572));
    assign chain[573] = w572;
    (* keep = 1, preserve = 1 *) wire w573;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u573 (
        .dataa(chain[573]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w573));
    assign chain[574] = w573;
    (* keep = 1, preserve = 1 *) wire w574;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u574 (
        .dataa(chain[574]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w574));
    assign chain[575] = w574;
    (* keep = 1, preserve = 1 *) wire w575;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u575 (
        .dataa(chain[575]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w575));
    assign chain[576] = w575;
    (* keep = 1, preserve = 1 *) wire w576;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u576 (
        .dataa(chain[576]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w576));
    assign chain[577] = w576;
    (* keep = 1, preserve = 1 *) wire w577;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u577 (
        .dataa(chain[577]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w577));
    assign chain[578] = w577;
    (* keep = 1, preserve = 1 *) wire w578;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u578 (
        .dataa(chain[578]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w578));
    assign chain[579] = w578;
    (* keep = 1, preserve = 1 *) wire w579;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u579 (
        .dataa(chain[579]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w579));
    assign chain[580] = w579;
    (* keep = 1, preserve = 1 *) wire w580;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u580 (
        .dataa(chain[580]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w580));
    assign chain[581] = w580;
    (* keep = 1, preserve = 1 *) wire w581;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u581 (
        .dataa(chain[581]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w581));
    assign chain[582] = w581;
    (* keep = 1, preserve = 1 *) wire w582;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u582 (
        .dataa(chain[582]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w582));
    assign chain[583] = w582;
    (* keep = 1, preserve = 1 *) wire w583;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u583 (
        .dataa(chain[583]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w583));
    assign chain[584] = w583;
    (* keep = 1, preserve = 1 *) wire w584;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u584 (
        .dataa(chain[584]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w584));
    assign chain[585] = w584;
    (* keep = 1, preserve = 1 *) wire w585;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u585 (
        .dataa(chain[585]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w585));
    assign chain[586] = w585;
    (* keep = 1, preserve = 1 *) wire w586;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u586 (
        .dataa(chain[586]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w586));
    assign chain[587] = w586;
    (* keep = 1, preserve = 1 *) wire w587;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u587 (
        .dataa(chain[587]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w587));
    assign chain[588] = w587;
    (* keep = 1, preserve = 1 *) wire w588;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u588 (
        .dataa(chain[588]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w588));
    assign chain[589] = w588;
    (* keep = 1, preserve = 1 *) wire w589;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u589 (
        .dataa(chain[589]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w589));
    assign chain[590] = w589;
    (* keep = 1, preserve = 1 *) wire w590;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u590 (
        .dataa(chain[590]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w590));
    assign chain[591] = w590;
    (* keep = 1, preserve = 1 *) wire w591;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u591 (
        .dataa(chain[591]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w591));
    assign chain[592] = w591;
    (* keep = 1, preserve = 1 *) wire w592;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u592 (
        .dataa(chain[592]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w592));
    assign chain[593] = w592;
    (* keep = 1, preserve = 1 *) wire w593;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u593 (
        .dataa(chain[593]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w593));
    assign chain[594] = w593;
    (* keep = 1, preserve = 1 *) wire w594;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u594 (
        .dataa(chain[594]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w594));
    assign chain[595] = w594;
    (* keep = 1, preserve = 1 *) wire w595;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u595 (
        .dataa(chain[595]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w595));
    assign chain[596] = w595;
    (* keep = 1, preserve = 1 *) wire w596;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u596 (
        .dataa(chain[596]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w596));
    assign chain[597] = w596;
    (* keep = 1, preserve = 1 *) wire w597;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u597 (
        .dataa(chain[597]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w597));
    assign chain[598] = w597;
    (* keep = 1, preserve = 1 *) wire w598;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u598 (
        .dataa(chain[598]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w598));
    assign chain[599] = w598;
    (* keep = 1, preserve = 1 *) wire w599;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u599 (
        .dataa(chain[599]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w599));
    assign chain[600] = w599;
    (* keep = 1, preserve = 1 *) wire w600;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u600 (
        .dataa(chain[600]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w600));
    assign chain[601] = w600;
    (* keep = 1, preserve = 1 *) wire w601;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u601 (
        .dataa(chain[601]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w601));
    assign chain[602] = w601;
    (* keep = 1, preserve = 1 *) wire w602;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u602 (
        .dataa(chain[602]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w602));
    assign chain[603] = w602;
    (* keep = 1, preserve = 1 *) wire w603;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u603 (
        .dataa(chain[603]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w603));
    assign chain[604] = w603;
    (* keep = 1, preserve = 1 *) wire w604;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u604 (
        .dataa(chain[604]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w604));
    assign chain[605] = w604;
    (* keep = 1, preserve = 1 *) wire w605;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u605 (
        .dataa(chain[605]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w605));
    assign chain[606] = w605;
    (* keep = 1, preserve = 1 *) wire w606;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u606 (
        .dataa(chain[606]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w606));
    assign chain[607] = w606;
    (* keep = 1, preserve = 1 *) wire w607;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u607 (
        .dataa(chain[607]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w607));
    assign chain[608] = w607;
    (* keep = 1, preserve = 1 *) wire w608;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u608 (
        .dataa(chain[608]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w608));
    assign chain[609] = w608;
    (* keep = 1, preserve = 1 *) wire w609;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u609 (
        .dataa(chain[609]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w609));
    assign chain[610] = w609;
    (* keep = 1, preserve = 1 *) wire w610;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u610 (
        .dataa(chain[610]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w610));
    assign chain[611] = w610;
    (* keep = 1, preserve = 1 *) wire w611;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u611 (
        .dataa(chain[611]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w611));
    assign chain[612] = w611;
    (* keep = 1, preserve = 1 *) wire w612;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u612 (
        .dataa(chain[612]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w612));
    assign chain[613] = w612;
    (* keep = 1, preserve = 1 *) wire w613;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u613 (
        .dataa(chain[613]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w613));
    assign chain[614] = w613;
    (* keep = 1, preserve = 1 *) wire w614;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u614 (
        .dataa(chain[614]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w614));
    assign chain[615] = w614;
    (* keep = 1, preserve = 1 *) wire w615;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u615 (
        .dataa(chain[615]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w615));
    assign chain[616] = w615;
    (* keep = 1, preserve = 1 *) wire w616;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u616 (
        .dataa(chain[616]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w616));
    assign chain[617] = w616;
    (* keep = 1, preserve = 1 *) wire w617;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u617 (
        .dataa(chain[617]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w617));
    assign chain[618] = w617;
    (* keep = 1, preserve = 1 *) wire w618;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u618 (
        .dataa(chain[618]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w618));
    assign chain[619] = w618;
    (* keep = 1, preserve = 1 *) wire w619;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u619 (
        .dataa(chain[619]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w619));
    assign chain[620] = w619;
    (* keep = 1, preserve = 1 *) wire w620;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u620 (
        .dataa(chain[620]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w620));
    assign chain[621] = w620;
    (* keep = 1, preserve = 1 *) wire w621;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u621 (
        .dataa(chain[621]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w621));
    assign chain[622] = w621;
    (* keep = 1, preserve = 1 *) wire w622;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u622 (
        .dataa(chain[622]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w622));
    assign chain[623] = w622;
    (* keep = 1, preserve = 1 *) wire w623;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u623 (
        .dataa(chain[623]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w623));
    assign chain[624] = w623;
    (* keep = 1, preserve = 1 *) wire w624;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u624 (
        .dataa(chain[624]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w624));
    assign chain[625] = w624;
    (* keep = 1, preserve = 1 *) wire w625;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u625 (
        .dataa(chain[625]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w625));
    assign chain[626] = w625;
    (* keep = 1, preserve = 1 *) wire w626;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u626 (
        .dataa(chain[626]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w626));
    assign chain[627] = w626;
    (* keep = 1, preserve = 1 *) wire w627;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u627 (
        .dataa(chain[627]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w627));
    assign chain[628] = w627;
    (* keep = 1, preserve = 1 *) wire w628;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u628 (
        .dataa(chain[628]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w628));
    assign chain[629] = w628;
    (* keep = 1, preserve = 1 *) wire w629;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u629 (
        .dataa(chain[629]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w629));
    assign chain[630] = w629;
    (* keep = 1, preserve = 1 *) wire w630;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u630 (
        .dataa(chain[630]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w630));
    assign chain[631] = w630;
    (* keep = 1, preserve = 1 *) wire w631;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u631 (
        .dataa(chain[631]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w631));
    assign chain[632] = w631;
    (* keep = 1, preserve = 1 *) wire w632;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u632 (
        .dataa(chain[632]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w632));
    assign chain[633] = w632;
    (* keep = 1, preserve = 1 *) wire w633;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u633 (
        .dataa(chain[633]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w633));
    assign chain[634] = w633;
    (* keep = 1, preserve = 1 *) wire w634;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u634 (
        .dataa(chain[634]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w634));
    assign chain[635] = w634;
    (* keep = 1, preserve = 1 *) wire w635;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u635 (
        .dataa(chain[635]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w635));
    assign chain[636] = w635;
    (* keep = 1, preserve = 1 *) wire w636;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u636 (
        .dataa(chain[636]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w636));
    assign chain[637] = w636;
    (* keep = 1, preserve = 1 *) wire w637;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u637 (
        .dataa(chain[637]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w637));
    assign chain[638] = w637;
    (* keep = 1, preserve = 1 *) wire w638;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u638 (
        .dataa(chain[638]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w638));
    assign chain[639] = w638;
    (* keep = 1, preserve = 1 *) wire w639;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u639 (
        .dataa(chain[639]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w639));
    assign chain[640] = w639;
    (* keep = 1, preserve = 1 *) wire w640;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u640 (
        .dataa(chain[640]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w640));
    assign chain[641] = w640;
    (* keep = 1, preserve = 1 *) wire w641;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u641 (
        .dataa(chain[641]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w641));
    assign chain[642] = w641;
    (* keep = 1, preserve = 1 *) wire w642;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u642 (
        .dataa(chain[642]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w642));
    assign chain[643] = w642;
    (* keep = 1, preserve = 1 *) wire w643;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u643 (
        .dataa(chain[643]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w643));
    assign chain[644] = w643;
    (* keep = 1, preserve = 1 *) wire w644;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u644 (
        .dataa(chain[644]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w644));
    assign chain[645] = w644;
    (* keep = 1, preserve = 1 *) wire w645;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u645 (
        .dataa(chain[645]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w645));
    assign chain[646] = w645;
    (* keep = 1, preserve = 1 *) wire w646;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u646 (
        .dataa(chain[646]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w646));
    assign chain[647] = w646;
    (* keep = 1, preserve = 1 *) wire w647;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u647 (
        .dataa(chain[647]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w647));
    assign chain[648] = w647;
    (* keep = 1, preserve = 1 *) wire w648;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u648 (
        .dataa(chain[648]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w648));
    assign chain[649] = w648;
    (* keep = 1, preserve = 1 *) wire w649;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u649 (
        .dataa(chain[649]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w649));
    assign chain[650] = w649;
    (* keep = 1, preserve = 1 *) wire w650;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u650 (
        .dataa(chain[650]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w650));
    assign chain[651] = w650;
    (* keep = 1, preserve = 1 *) wire w651;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u651 (
        .dataa(chain[651]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w651));
    assign chain[652] = w651;
    (* keep = 1, preserve = 1 *) wire w652;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u652 (
        .dataa(chain[652]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w652));
    assign chain[653] = w652;
    (* keep = 1, preserve = 1 *) wire w653;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u653 (
        .dataa(chain[653]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w653));
    assign chain[654] = w653;
    (* keep = 1, preserve = 1 *) wire w654;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u654 (
        .dataa(chain[654]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w654));
    assign chain[655] = w654;
    (* keep = 1, preserve = 1 *) wire w655;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u655 (
        .dataa(chain[655]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w655));
    assign chain[656] = w655;
    (* keep = 1, preserve = 1 *) wire w656;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u656 (
        .dataa(chain[656]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w656));
    assign chain[657] = w656;
    (* keep = 1, preserve = 1 *) wire w657;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u657 (
        .dataa(chain[657]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w657));
    assign chain[658] = w657;
    (* keep = 1, preserve = 1 *) wire w658;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u658 (
        .dataa(chain[658]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w658));
    assign chain[659] = w658;
    (* keep = 1, preserve = 1 *) wire w659;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u659 (
        .dataa(chain[659]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w659));
    assign chain[660] = w659;
    (* keep = 1, preserve = 1 *) wire w660;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u660 (
        .dataa(chain[660]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w660));
    assign chain[661] = w660;
    (* keep = 1, preserve = 1 *) wire w661;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u661 (
        .dataa(chain[661]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w661));
    assign chain[662] = w661;
    (* keep = 1, preserve = 1 *) wire w662;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u662 (
        .dataa(chain[662]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w662));
    assign chain[663] = w662;
    (* keep = 1, preserve = 1 *) wire w663;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u663 (
        .dataa(chain[663]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w663));
    assign chain[664] = w663;
    (* keep = 1, preserve = 1 *) wire w664;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u664 (
        .dataa(chain[664]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w664));
    assign chain[665] = w664;
    (* keep = 1, preserve = 1 *) wire w665;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u665 (
        .dataa(chain[665]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w665));
    assign chain[666] = w665;
    (* keep = 1, preserve = 1 *) wire w666;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u666 (
        .dataa(chain[666]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w666));
    assign chain[667] = w666;
    (* keep = 1, preserve = 1 *) wire w667;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u667 (
        .dataa(chain[667]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w667));
    assign chain[668] = w667;
    (* keep = 1, preserve = 1 *) wire w668;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u668 (
        .dataa(chain[668]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w668));
    assign chain[669] = w668;
    (* keep = 1, preserve = 1 *) wire w669;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u669 (
        .dataa(chain[669]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w669));
    assign chain[670] = w669;
    (* keep = 1, preserve = 1 *) wire w670;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u670 (
        .dataa(chain[670]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w670));
    assign chain[671] = w670;
    (* keep = 1, preserve = 1 *) wire w671;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u671 (
        .dataa(chain[671]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w671));
    assign chain[672] = w671;
    (* keep = 1, preserve = 1 *) wire w672;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u672 (
        .dataa(chain[672]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w672));
    assign chain[673] = w672;
    (* keep = 1, preserve = 1 *) wire w673;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u673 (
        .dataa(chain[673]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w673));
    assign chain[674] = w673;
    (* keep = 1, preserve = 1 *) wire w674;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u674 (
        .dataa(chain[674]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w674));
    assign chain[675] = w674;
    (* keep = 1, preserve = 1 *) wire w675;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u675 (
        .dataa(chain[675]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w675));
    assign chain[676] = w675;
    (* keep = 1, preserve = 1 *) wire w676;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u676 (
        .dataa(chain[676]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w676));
    assign chain[677] = w676;
    (* keep = 1, preserve = 1 *) wire w677;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u677 (
        .dataa(chain[677]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w677));
    assign chain[678] = w677;
    (* keep = 1, preserve = 1 *) wire w678;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u678 (
        .dataa(chain[678]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w678));
    assign chain[679] = w678;
    (* keep = 1, preserve = 1 *) wire w679;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u679 (
        .dataa(chain[679]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w679));
    assign chain[680] = w679;
    (* keep = 1, preserve = 1 *) wire w680;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u680 (
        .dataa(chain[680]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w680));
    assign chain[681] = w680;
    (* keep = 1, preserve = 1 *) wire w681;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u681 (
        .dataa(chain[681]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w681));
    assign chain[682] = w681;
    (* keep = 1, preserve = 1 *) wire w682;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u682 (
        .dataa(chain[682]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w682));
    assign chain[683] = w682;
    (* keep = 1, preserve = 1 *) wire w683;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u683 (
        .dataa(chain[683]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w683));
    assign chain[684] = w683;
    (* keep = 1, preserve = 1 *) wire w684;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u684 (
        .dataa(chain[684]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w684));
    assign chain[685] = w684;
    (* keep = 1, preserve = 1 *) wire w685;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u685 (
        .dataa(chain[685]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w685));
    assign chain[686] = w685;
    (* keep = 1, preserve = 1 *) wire w686;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u686 (
        .dataa(chain[686]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w686));
    assign chain[687] = w686;
    (* keep = 1, preserve = 1 *) wire w687;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u687 (
        .dataa(chain[687]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w687));
    assign chain[688] = w687;
    (* keep = 1, preserve = 1 *) wire w688;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u688 (
        .dataa(chain[688]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w688));
    assign chain[689] = w688;
    (* keep = 1, preserve = 1 *) wire w689;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u689 (
        .dataa(chain[689]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w689));
    assign chain[690] = w689;
    (* keep = 1, preserve = 1 *) wire w690;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u690 (
        .dataa(chain[690]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w690));
    assign chain[691] = w690;
    (* keep = 1, preserve = 1 *) wire w691;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u691 (
        .dataa(chain[691]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w691));
    assign chain[692] = w691;
    (* keep = 1, preserve = 1 *) wire w692;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u692 (
        .dataa(chain[692]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w692));
    assign chain[693] = w692;
    (* keep = 1, preserve = 1 *) wire w693;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u693 (
        .dataa(chain[693]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w693));
    assign chain[694] = w693;
    (* keep = 1, preserve = 1 *) wire w694;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u694 (
        .dataa(chain[694]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w694));
    assign chain[695] = w694;
    (* keep = 1, preserve = 1 *) wire w695;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u695 (
        .dataa(chain[695]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w695));
    assign chain[696] = w695;
    (* keep = 1, preserve = 1 *) wire w696;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u696 (
        .dataa(chain[696]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w696));
    assign chain[697] = w696;
    (* keep = 1, preserve = 1 *) wire w697;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u697 (
        .dataa(chain[697]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w697));
    assign chain[698] = w697;
    (* keep = 1, preserve = 1 *) wire w698;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u698 (
        .dataa(chain[698]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w698));
    assign chain[699] = w698;
    (* keep = 1, preserve = 1 *) wire w699;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u699 (
        .dataa(chain[699]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w699));
    assign chain[700] = w699;
    (* keep = 1, preserve = 1 *) wire w700;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u700 (
        .dataa(chain[700]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w700));
    assign chain[701] = w700;
    (* keep = 1, preserve = 1 *) wire w701;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u701 (
        .dataa(chain[701]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w701));
    assign chain[702] = w701;
    (* keep = 1, preserve = 1 *) wire w702;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u702 (
        .dataa(chain[702]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w702));
    assign chain[703] = w702;
    (* keep = 1, preserve = 1 *) wire w703;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u703 (
        .dataa(chain[703]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w703));
    assign chain[704] = w703;
    (* keep = 1, preserve = 1 *) wire w704;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u704 (
        .dataa(chain[704]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w704));
    assign chain[705] = w704;
    (* keep = 1, preserve = 1 *) wire w705;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u705 (
        .dataa(chain[705]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w705));
    assign chain[706] = w705;
    (* keep = 1, preserve = 1 *) wire w706;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u706 (
        .dataa(chain[706]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w706));
    assign chain[707] = w706;
    (* keep = 1, preserve = 1 *) wire w707;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u707 (
        .dataa(chain[707]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w707));
    assign chain[708] = w707;
    (* keep = 1, preserve = 1 *) wire w708;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u708 (
        .dataa(chain[708]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w708));
    assign chain[709] = w708;
    (* keep = 1, preserve = 1 *) wire w709;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u709 (
        .dataa(chain[709]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w709));
    assign chain[710] = w709;
    (* keep = 1, preserve = 1 *) wire w710;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u710 (
        .dataa(chain[710]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w710));
    assign chain[711] = w710;
    (* keep = 1, preserve = 1 *) wire w711;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u711 (
        .dataa(chain[711]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w711));
    assign chain[712] = w711;
    (* keep = 1, preserve = 1 *) wire w712;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u712 (
        .dataa(chain[712]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w712));
    assign chain[713] = w712;
    (* keep = 1, preserve = 1 *) wire w713;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u713 (
        .dataa(chain[713]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w713));
    assign chain[714] = w713;
    (* keep = 1, preserve = 1 *) wire w714;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u714 (
        .dataa(chain[714]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w714));
    assign chain[715] = w714;
    (* keep = 1, preserve = 1 *) wire w715;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u715 (
        .dataa(chain[715]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w715));
    assign chain[716] = w715;
    (* keep = 1, preserve = 1 *) wire w716;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u716 (
        .dataa(chain[716]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w716));
    assign chain[717] = w716;
    (* keep = 1, preserve = 1 *) wire w717;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u717 (
        .dataa(chain[717]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w717));
    assign chain[718] = w717;
    (* keep = 1, preserve = 1 *) wire w718;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u718 (
        .dataa(chain[718]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w718));
    assign chain[719] = w718;
    (* keep = 1, preserve = 1 *) wire w719;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u719 (
        .dataa(chain[719]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w719));
    assign chain[720] = w719;
    (* keep = 1, preserve = 1 *) wire w720;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u720 (
        .dataa(chain[720]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w720));
    assign chain[721] = w720;
    (* keep = 1, preserve = 1 *) wire w721;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u721 (
        .dataa(chain[721]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w721));
    assign chain[722] = w721;
    (* keep = 1, preserve = 1 *) wire w722;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u722 (
        .dataa(chain[722]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w722));
    assign chain[723] = w722;
    (* keep = 1, preserve = 1 *) wire w723;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u723 (
        .dataa(chain[723]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w723));
    assign chain[724] = w723;
    (* keep = 1, preserve = 1 *) wire w724;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u724 (
        .dataa(chain[724]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w724));
    assign chain[725] = w724;
    (* keep = 1, preserve = 1 *) wire w725;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u725 (
        .dataa(chain[725]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w725));
    assign chain[726] = w725;
    (* keep = 1, preserve = 1 *) wire w726;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u726 (
        .dataa(chain[726]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w726));
    assign chain[727] = w726;
    (* keep = 1, preserve = 1 *) wire w727;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u727 (
        .dataa(chain[727]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w727));
    assign chain[728] = w727;
    (* keep = 1, preserve = 1 *) wire w728;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u728 (
        .dataa(chain[728]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w728));
    assign chain[729] = w728;
    (* keep = 1, preserve = 1 *) wire w729;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u729 (
        .dataa(chain[729]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w729));
    assign chain[730] = w729;
    (* keep = 1, preserve = 1 *) wire w730;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u730 (
        .dataa(chain[730]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w730));
    assign chain[731] = w730;
    (* keep = 1, preserve = 1 *) wire w731;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u731 (
        .dataa(chain[731]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w731));
    assign chain[732] = w731;
    (* keep = 1, preserve = 1 *) wire w732;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u732 (
        .dataa(chain[732]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w732));
    assign chain[733] = w732;
    (* keep = 1, preserve = 1 *) wire w733;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u733 (
        .dataa(chain[733]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w733));
    assign chain[734] = w733;
    (* keep = 1, preserve = 1 *) wire w734;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u734 (
        .dataa(chain[734]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w734));
    assign chain[735] = w734;
    (* keep = 1, preserve = 1 *) wire w735;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u735 (
        .dataa(chain[735]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w735));
    assign chain[736] = w735;
    (* keep = 1, preserve = 1 *) wire w736;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u736 (
        .dataa(chain[736]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w736));
    assign chain[737] = w736;
    (* keep = 1, preserve = 1 *) wire w737;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u737 (
        .dataa(chain[737]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w737));
    assign chain[738] = w737;
    (* keep = 1, preserve = 1 *) wire w738;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u738 (
        .dataa(chain[738]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w738));
    assign chain[739] = w738;
    (* keep = 1, preserve = 1 *) wire w739;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u739 (
        .dataa(chain[739]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w739));
    assign chain[740] = w739;
    (* keep = 1, preserve = 1 *) wire w740;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u740 (
        .dataa(chain[740]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w740));
    assign chain[741] = w740;
    (* keep = 1, preserve = 1 *) wire w741;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u741 (
        .dataa(chain[741]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w741));
    assign chain[742] = w741;
    (* keep = 1, preserve = 1 *) wire w742;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u742 (
        .dataa(chain[742]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w742));
    assign chain[743] = w742;
    (* keep = 1, preserve = 1 *) wire w743;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u743 (
        .dataa(chain[743]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w743));
    assign chain[744] = w743;
    (* keep = 1, preserve = 1 *) wire w744;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u744 (
        .dataa(chain[744]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w744));
    assign chain[745] = w744;
    (* keep = 1, preserve = 1 *) wire w745;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u745 (
        .dataa(chain[745]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w745));
    assign chain[746] = w745;
    (* keep = 1, preserve = 1 *) wire w746;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u746 (
        .dataa(chain[746]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w746));
    assign chain[747] = w746;
    (* keep = 1, preserve = 1 *) wire w747;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u747 (
        .dataa(chain[747]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w747));
    assign chain[748] = w747;
    (* keep = 1, preserve = 1 *) wire w748;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u748 (
        .dataa(chain[748]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w748));
    assign chain[749] = w748;
    (* keep = 1, preserve = 1 *) wire w749;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u749 (
        .dataa(chain[749]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w749));
    assign chain[750] = w749;
    (* keep = 1, preserve = 1 *) wire w750;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u750 (
        .dataa(chain[750]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w750));
    assign chain[751] = w750;
    (* keep = 1, preserve = 1 *) wire w751;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u751 (
        .dataa(chain[751]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w751));
    assign chain[752] = w751;
    (* keep = 1, preserve = 1 *) wire w752;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u752 (
        .dataa(chain[752]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w752));
    assign chain[753] = w752;
    (* keep = 1, preserve = 1 *) wire w753;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u753 (
        .dataa(chain[753]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w753));
    assign chain[754] = w753;
    (* keep = 1, preserve = 1 *) wire w754;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u754 (
        .dataa(chain[754]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w754));
    assign chain[755] = w754;
    (* keep = 1, preserve = 1 *) wire w755;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u755 (
        .dataa(chain[755]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w755));
    assign chain[756] = w755;
    (* keep = 1, preserve = 1 *) wire w756;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u756 (
        .dataa(chain[756]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w756));
    assign chain[757] = w756;
    (* keep = 1, preserve = 1 *) wire w757;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u757 (
        .dataa(chain[757]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w757));
    assign chain[758] = w757;
    (* keep = 1, preserve = 1 *) wire w758;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u758 (
        .dataa(chain[758]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w758));
    assign chain[759] = w758;
    (* keep = 1, preserve = 1 *) wire w759;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u759 (
        .dataa(chain[759]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w759));
    assign chain[760] = w759;
    (* keep = 1, preserve = 1 *) wire w760;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u760 (
        .dataa(chain[760]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w760));
    assign chain[761] = w760;
    (* keep = 1, preserve = 1 *) wire w761;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u761 (
        .dataa(chain[761]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w761));
    assign chain[762] = w761;
    (* keep = 1, preserve = 1 *) wire w762;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u762 (
        .dataa(chain[762]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w762));
    assign chain[763] = w762;
    (* keep = 1, preserve = 1 *) wire w763;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u763 (
        .dataa(chain[763]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w763));
    assign chain[764] = w763;
    (* keep = 1, preserve = 1 *) wire w764;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u764 (
        .dataa(chain[764]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w764));
    assign chain[765] = w764;
    (* keep = 1, preserve = 1 *) wire w765;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u765 (
        .dataa(chain[765]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w765));
    assign chain[766] = w765;
    (* keep = 1, preserve = 1 *) wire w766;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u766 (
        .dataa(chain[766]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w766));
    assign chain[767] = w766;
    (* keep = 1, preserve = 1 *) wire w767;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u767 (
        .dataa(chain[767]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w767));
    assign chain[768] = w767;
    (* keep = 1, preserve = 1 *) wire w768;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u768 (
        .dataa(chain[768]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w768));
    assign chain[769] = w768;
    (* keep = 1, preserve = 1 *) wire w769;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u769 (
        .dataa(chain[769]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w769));
    assign chain[770] = w769;
    (* keep = 1, preserve = 1 *) wire w770;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u770 (
        .dataa(chain[770]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w770));
    assign chain[771] = w770;
    (* keep = 1, preserve = 1 *) wire w771;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u771 (
        .dataa(chain[771]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w771));
    assign chain[772] = w771;
    (* keep = 1, preserve = 1 *) wire w772;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u772 (
        .dataa(chain[772]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w772));
    assign chain[773] = w772;
    (* keep = 1, preserve = 1 *) wire w773;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u773 (
        .dataa(chain[773]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w773));
    assign chain[774] = w773;
    (* keep = 1, preserve = 1 *) wire w774;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u774 (
        .dataa(chain[774]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w774));
    assign chain[775] = w774;
    (* keep = 1, preserve = 1 *) wire w775;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u775 (
        .dataa(chain[775]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w775));
    assign chain[776] = w775;
    (* keep = 1, preserve = 1 *) wire w776;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u776 (
        .dataa(chain[776]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w776));
    assign chain[777] = w776;
    (* keep = 1, preserve = 1 *) wire w777;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u777 (
        .dataa(chain[777]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w777));
    assign chain[778] = w777;
    (* keep = 1, preserve = 1 *) wire w778;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u778 (
        .dataa(chain[778]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w778));
    assign chain[779] = w778;
    (* keep = 1, preserve = 1 *) wire w779;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u779 (
        .dataa(chain[779]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w779));
    assign chain[780] = w779;
    (* keep = 1, preserve = 1 *) wire w780;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u780 (
        .dataa(chain[780]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w780));
    assign chain[781] = w780;
    (* keep = 1, preserve = 1 *) wire w781;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u781 (
        .dataa(chain[781]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w781));
    assign chain[782] = w781;
    (* keep = 1, preserve = 1 *) wire w782;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u782 (
        .dataa(chain[782]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w782));
    assign chain[783] = w782;
    (* keep = 1, preserve = 1 *) wire w783;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u783 (
        .dataa(chain[783]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w783));
    assign chain[784] = w783;
    (* keep = 1, preserve = 1 *) wire w784;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u784 (
        .dataa(chain[784]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w784));
    assign chain[785] = w784;
    (* keep = 1, preserve = 1 *) wire w785;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u785 (
        .dataa(chain[785]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w785));
    assign chain[786] = w785;
    (* keep = 1, preserve = 1 *) wire w786;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u786 (
        .dataa(chain[786]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w786));
    assign chain[787] = w786;
    (* keep = 1, preserve = 1 *) wire w787;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u787 (
        .dataa(chain[787]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w787));
    assign chain[788] = w787;
    (* keep = 1, preserve = 1 *) wire w788;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u788 (
        .dataa(chain[788]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w788));
    assign chain[789] = w788;
    (* keep = 1, preserve = 1 *) wire w789;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u789 (
        .dataa(chain[789]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w789));
    assign chain[790] = w789;
    (* keep = 1, preserve = 1 *) wire w790;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u790 (
        .dataa(chain[790]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w790));
    assign chain[791] = w790;
    (* keep = 1, preserve = 1 *) wire w791;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u791 (
        .dataa(chain[791]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w791));
    assign chain[792] = w791;
    (* keep = 1, preserve = 1 *) wire w792;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u792 (
        .dataa(chain[792]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w792));
    assign chain[793] = w792;
    (* keep = 1, preserve = 1 *) wire w793;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u793 (
        .dataa(chain[793]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w793));
    assign chain[794] = w793;
    (* keep = 1, preserve = 1 *) wire w794;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u794 (
        .dataa(chain[794]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w794));
    assign chain[795] = w794;
    (* keep = 1, preserve = 1 *) wire w795;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u795 (
        .dataa(chain[795]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w795));
    assign chain[796] = w795;
    (* keep = 1, preserve = 1 *) wire w796;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u796 (
        .dataa(chain[796]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w796));
    assign chain[797] = w796;
    (* keep = 1, preserve = 1 *) wire w797;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u797 (
        .dataa(chain[797]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w797));
    assign chain[798] = w797;
    (* keep = 1, preserve = 1 *) wire w798;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u798 (
        .dataa(chain[798]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w798));
    assign chain[799] = w798;
    (* keep = 1, preserve = 1 *) wire w799;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u799 (
        .dataa(chain[799]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w799));
    assign chain[800] = w799;
    (* keep = 1, preserve = 1 *) wire w800;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u800 (
        .dataa(chain[800]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w800));
    assign chain[801] = w800;
    (* keep = 1, preserve = 1 *) wire w801;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u801 (
        .dataa(chain[801]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w801));
    assign chain[802] = w801;
    (* keep = 1, preserve = 1 *) wire w802;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u802 (
        .dataa(chain[802]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w802));
    assign chain[803] = w802;
    (* keep = 1, preserve = 1 *) wire w803;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u803 (
        .dataa(chain[803]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w803));
    assign chain[804] = w803;
    (* keep = 1, preserve = 1 *) wire w804;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u804 (
        .dataa(chain[804]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w804));
    assign chain[805] = w804;
    (* keep = 1, preserve = 1 *) wire w805;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u805 (
        .dataa(chain[805]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w805));
    assign chain[806] = w805;
    (* keep = 1, preserve = 1 *) wire w806;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u806 (
        .dataa(chain[806]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w806));
    assign chain[807] = w806;
    (* keep = 1, preserve = 1 *) wire w807;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u807 (
        .dataa(chain[807]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w807));
    assign chain[808] = w807;
    (* keep = 1, preserve = 1 *) wire w808;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u808 (
        .dataa(chain[808]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w808));
    assign chain[809] = w808;
    (* keep = 1, preserve = 1 *) wire w809;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u809 (
        .dataa(chain[809]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w809));
    assign chain[810] = w809;
    (* keep = 1, preserve = 1 *) wire w810;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u810 (
        .dataa(chain[810]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w810));
    assign chain[811] = w810;
    (* keep = 1, preserve = 1 *) wire w811;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u811 (
        .dataa(chain[811]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w811));
    assign chain[812] = w811;
    (* keep = 1, preserve = 1 *) wire w812;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u812 (
        .dataa(chain[812]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w812));
    assign chain[813] = w812;
    (* keep = 1, preserve = 1 *) wire w813;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u813 (
        .dataa(chain[813]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w813));
    assign chain[814] = w813;
    (* keep = 1, preserve = 1 *) wire w814;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u814 (
        .dataa(chain[814]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w814));
    assign chain[815] = w814;
    (* keep = 1, preserve = 1 *) wire w815;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u815 (
        .dataa(chain[815]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w815));
    assign chain[816] = w815;
    (* keep = 1, preserve = 1 *) wire w816;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u816 (
        .dataa(chain[816]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w816));
    assign chain[817] = w816;
    (* keep = 1, preserve = 1 *) wire w817;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u817 (
        .dataa(chain[817]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w817));
    assign chain[818] = w817;
    (* keep = 1, preserve = 1 *) wire w818;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u818 (
        .dataa(chain[818]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w818));
    assign chain[819] = w818;
    (* keep = 1, preserve = 1 *) wire w819;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u819 (
        .dataa(chain[819]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w819));
    assign chain[820] = w819;
    (* keep = 1, preserve = 1 *) wire w820;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u820 (
        .dataa(chain[820]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w820));
    assign chain[821] = w820;
    (* keep = 1, preserve = 1 *) wire w821;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u821 (
        .dataa(chain[821]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w821));
    assign chain[822] = w821;
    (* keep = 1, preserve = 1 *) wire w822;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u822 (
        .dataa(chain[822]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w822));
    assign chain[823] = w822;
    (* keep = 1, preserve = 1 *) wire w823;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u823 (
        .dataa(chain[823]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w823));
    assign chain[824] = w823;
    (* keep = 1, preserve = 1 *) wire w824;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u824 (
        .dataa(chain[824]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w824));
    assign chain[825] = w824;
    (* keep = 1, preserve = 1 *) wire w825;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u825 (
        .dataa(chain[825]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w825));
    assign chain[826] = w825;
    (* keep = 1, preserve = 1 *) wire w826;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u826 (
        .dataa(chain[826]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w826));
    assign chain[827] = w826;
    (* keep = 1, preserve = 1 *) wire w827;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u827 (
        .dataa(chain[827]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w827));
    assign chain[828] = w827;
    (* keep = 1, preserve = 1 *) wire w828;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u828 (
        .dataa(chain[828]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w828));
    assign chain[829] = w828;
    (* keep = 1, preserve = 1 *) wire w829;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u829 (
        .dataa(chain[829]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w829));
    assign chain[830] = w829;
    (* keep = 1, preserve = 1 *) wire w830;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u830 (
        .dataa(chain[830]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w830));
    assign chain[831] = w830;
    (* keep = 1, preserve = 1 *) wire w831;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u831 (
        .dataa(chain[831]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w831));
    assign chain[832] = w831;
    (* keep = 1, preserve = 1 *) wire w832;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u832 (
        .dataa(chain[832]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w832));
    assign chain[833] = w832;
    (* keep = 1, preserve = 1 *) wire w833;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u833 (
        .dataa(chain[833]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w833));
    assign chain[834] = w833;
    (* keep = 1, preserve = 1 *) wire w834;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u834 (
        .dataa(chain[834]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w834));
    assign chain[835] = w834;
    (* keep = 1, preserve = 1 *) wire w835;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u835 (
        .dataa(chain[835]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w835));
    assign chain[836] = w835;
    (* keep = 1, preserve = 1 *) wire w836;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u836 (
        .dataa(chain[836]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w836));
    assign chain[837] = w836;
    (* keep = 1, preserve = 1 *) wire w837;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u837 (
        .dataa(chain[837]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w837));
    assign chain[838] = w837;
    (* keep = 1, preserve = 1 *) wire w838;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u838 (
        .dataa(chain[838]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w838));
    assign chain[839] = w838;
    (* keep = 1, preserve = 1 *) wire w839;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u839 (
        .dataa(chain[839]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w839));
    assign chain[840] = w839;
    (* keep = 1, preserve = 1 *) wire w840;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u840 (
        .dataa(chain[840]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w840));
    assign chain[841] = w840;
    (* keep = 1, preserve = 1 *) wire w841;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u841 (
        .dataa(chain[841]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w841));
    assign chain[842] = w841;
    (* keep = 1, preserve = 1 *) wire w842;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u842 (
        .dataa(chain[842]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w842));
    assign chain[843] = w842;
    (* keep = 1, preserve = 1 *) wire w843;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u843 (
        .dataa(chain[843]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w843));
    assign chain[844] = w843;
    (* keep = 1, preserve = 1 *) wire w844;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u844 (
        .dataa(chain[844]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w844));
    assign chain[845] = w844;
    (* keep = 1, preserve = 1 *) wire w845;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u845 (
        .dataa(chain[845]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w845));
    assign chain[846] = w845;
    (* keep = 1, preserve = 1 *) wire w846;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u846 (
        .dataa(chain[846]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w846));
    assign chain[847] = w846;
    (* keep = 1, preserve = 1 *) wire w847;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u847 (
        .dataa(chain[847]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w847));
    assign chain[848] = w847;
    (* keep = 1, preserve = 1 *) wire w848;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u848 (
        .dataa(chain[848]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w848));
    assign chain[849] = w848;
    (* keep = 1, preserve = 1 *) wire w849;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u849 (
        .dataa(chain[849]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w849));
    assign chain[850] = w849;
    (* keep = 1, preserve = 1 *) wire w850;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u850 (
        .dataa(chain[850]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w850));
    assign chain[851] = w850;
    (* keep = 1, preserve = 1 *) wire w851;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u851 (
        .dataa(chain[851]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w851));
    assign chain[852] = w851;
    (* keep = 1, preserve = 1 *) wire w852;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u852 (
        .dataa(chain[852]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w852));
    assign chain[853] = w852;
    (* keep = 1, preserve = 1 *) wire w853;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u853 (
        .dataa(chain[853]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w853));
    assign chain[854] = w853;
    (* keep = 1, preserve = 1 *) wire w854;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u854 (
        .dataa(chain[854]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w854));
    assign chain[855] = w854;
    (* keep = 1, preserve = 1 *) wire w855;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u855 (
        .dataa(chain[855]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w855));
    assign chain[856] = w855;
    (* keep = 1, preserve = 1 *) wire w856;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u856 (
        .dataa(chain[856]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w856));
    assign chain[857] = w856;
    (* keep = 1, preserve = 1 *) wire w857;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u857 (
        .dataa(chain[857]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w857));
    assign chain[858] = w857;
    (* keep = 1, preserve = 1 *) wire w858;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u858 (
        .dataa(chain[858]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w858));
    assign chain[859] = w858;
    (* keep = 1, preserve = 1 *) wire w859;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u859 (
        .dataa(chain[859]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w859));
    assign chain[860] = w859;
    (* keep = 1, preserve = 1 *) wire w860;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u860 (
        .dataa(chain[860]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w860));
    assign chain[861] = w860;
    (* keep = 1, preserve = 1 *) wire w861;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u861 (
        .dataa(chain[861]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w861));
    assign chain[862] = w861;
    (* keep = 1, preserve = 1 *) wire w862;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u862 (
        .dataa(chain[862]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w862));
    assign chain[863] = w862;
    (* keep = 1, preserve = 1 *) wire w863;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u863 (
        .dataa(chain[863]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w863));
    assign chain[864] = w863;
    (* keep = 1, preserve = 1 *) wire w864;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u864 (
        .dataa(chain[864]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w864));
    assign chain[865] = w864;
    (* keep = 1, preserve = 1 *) wire w865;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u865 (
        .dataa(chain[865]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w865));
    assign chain[866] = w865;
    (* keep = 1, preserve = 1 *) wire w866;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u866 (
        .dataa(chain[866]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w866));
    assign chain[867] = w866;
    (* keep = 1, preserve = 1 *) wire w867;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u867 (
        .dataa(chain[867]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w867));
    assign chain[868] = w867;
    (* keep = 1, preserve = 1 *) wire w868;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u868 (
        .dataa(chain[868]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w868));
    assign chain[869] = w868;
    (* keep = 1, preserve = 1 *) wire w869;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u869 (
        .dataa(chain[869]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w869));
    assign chain[870] = w869;
    (* keep = 1, preserve = 1 *) wire w870;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u870 (
        .dataa(chain[870]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w870));
    assign chain[871] = w870;
    (* keep = 1, preserve = 1 *) wire w871;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u871 (
        .dataa(chain[871]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w871));
    assign chain[872] = w871;
    (* keep = 1, preserve = 1 *) wire w872;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u872 (
        .dataa(chain[872]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w872));
    assign chain[873] = w872;
    (* keep = 1, preserve = 1 *) wire w873;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u873 (
        .dataa(chain[873]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w873));
    assign chain[874] = w873;
    (* keep = 1, preserve = 1 *) wire w874;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u874 (
        .dataa(chain[874]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w874));
    assign chain[875] = w874;
    (* keep = 1, preserve = 1 *) wire w875;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u875 (
        .dataa(chain[875]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w875));
    assign chain[876] = w875;
    (* keep = 1, preserve = 1 *) wire w876;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u876 (
        .dataa(chain[876]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w876));
    assign chain[877] = w876;
    (* keep = 1, preserve = 1 *) wire w877;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u877 (
        .dataa(chain[877]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w877));
    assign chain[878] = w877;
    (* keep = 1, preserve = 1 *) wire w878;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u878 (
        .dataa(chain[878]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w878));
    assign chain[879] = w878;
    (* keep = 1, preserve = 1 *) wire w879;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u879 (
        .dataa(chain[879]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w879));
    assign chain[880] = w879;
    (* keep = 1, preserve = 1 *) wire w880;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u880 (
        .dataa(chain[880]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w880));
    assign chain[881] = w880;
    (* keep = 1, preserve = 1 *) wire w881;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u881 (
        .dataa(chain[881]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w881));
    assign chain[882] = w881;
    (* keep = 1, preserve = 1 *) wire w882;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u882 (
        .dataa(chain[882]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w882));
    assign chain[883] = w882;
    (* keep = 1, preserve = 1 *) wire w883;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u883 (
        .dataa(chain[883]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w883));
    assign chain[884] = w883;
    (* keep = 1, preserve = 1 *) wire w884;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u884 (
        .dataa(chain[884]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w884));
    assign chain[885] = w884;
    (* keep = 1, preserve = 1 *) wire w885;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u885 (
        .dataa(chain[885]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w885));
    assign chain[886] = w885;
    (* keep = 1, preserve = 1 *) wire w886;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u886 (
        .dataa(chain[886]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w886));
    assign chain[887] = w886;
    (* keep = 1, preserve = 1 *) wire w887;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u887 (
        .dataa(chain[887]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w887));
    assign chain[888] = w887;
    (* keep = 1, preserve = 1 *) wire w888;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u888 (
        .dataa(chain[888]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w888));
    assign chain[889] = w888;
    (* keep = 1, preserve = 1 *) wire w889;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u889 (
        .dataa(chain[889]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w889));
    assign chain[890] = w889;
    (* keep = 1, preserve = 1 *) wire w890;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u890 (
        .dataa(chain[890]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w890));
    assign chain[891] = w890;
    (* keep = 1, preserve = 1 *) wire w891;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u891 (
        .dataa(chain[891]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w891));
    assign chain[892] = w891;
    (* keep = 1, preserve = 1 *) wire w892;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u892 (
        .dataa(chain[892]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w892));
    assign chain[893] = w892;
    (* keep = 1, preserve = 1 *) wire w893;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u893 (
        .dataa(chain[893]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w893));
    assign chain[894] = w893;
    (* keep = 1, preserve = 1 *) wire w894;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u894 (
        .dataa(chain[894]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w894));
    assign chain[895] = w894;
    (* keep = 1, preserve = 1 *) wire w895;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u895 (
        .dataa(chain[895]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w895));
    assign chain[896] = w895;
    (* keep = 1, preserve = 1 *) wire w896;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u896 (
        .dataa(chain[896]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w896));
    assign chain[897] = w896;
    (* keep = 1, preserve = 1 *) wire w897;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u897 (
        .dataa(chain[897]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w897));
    assign chain[898] = w897;
    (* keep = 1, preserve = 1 *) wire w898;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u898 (
        .dataa(chain[898]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w898));
    assign chain[899] = w898;
    (* keep = 1, preserve = 1 *) wire w899;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u899 (
        .dataa(chain[899]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w899));
    assign chain[900] = w899;
    (* keep = 1, preserve = 1 *) wire w900;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u900 (
        .dataa(chain[900]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w900));
    assign chain[901] = w900;
    (* keep = 1, preserve = 1 *) wire w901;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u901 (
        .dataa(chain[901]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w901));
    assign chain[902] = w901;
    (* keep = 1, preserve = 1 *) wire w902;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u902 (
        .dataa(chain[902]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w902));
    assign chain[903] = w902;
    (* keep = 1, preserve = 1 *) wire w903;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u903 (
        .dataa(chain[903]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w903));
    assign chain[904] = w903;
    (* keep = 1, preserve = 1 *) wire w904;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u904 (
        .dataa(chain[904]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w904));
    assign chain[905] = w904;
    (* keep = 1, preserve = 1 *) wire w905;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u905 (
        .dataa(chain[905]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w905));
    assign chain[906] = w905;
    (* keep = 1, preserve = 1 *) wire w906;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u906 (
        .dataa(chain[906]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w906));
    assign chain[907] = w906;
    (* keep = 1, preserve = 1 *) wire w907;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u907 (
        .dataa(chain[907]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w907));
    assign chain[908] = w907;
    (* keep = 1, preserve = 1 *) wire w908;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u908 (
        .dataa(chain[908]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w908));
    assign chain[909] = w908;
    (* keep = 1, preserve = 1 *) wire w909;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u909 (
        .dataa(chain[909]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w909));
    assign chain[910] = w909;
    (* keep = 1, preserve = 1 *) wire w910;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u910 (
        .dataa(chain[910]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w910));
    assign chain[911] = w910;
    (* keep = 1, preserve = 1 *) wire w911;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u911 (
        .dataa(chain[911]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w911));
    assign chain[912] = w911;
    (* keep = 1, preserve = 1 *) wire w912;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u912 (
        .dataa(chain[912]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w912));
    assign chain[913] = w912;
    (* keep = 1, preserve = 1 *) wire w913;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u913 (
        .dataa(chain[913]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w913));
    assign chain[914] = w913;
    (* keep = 1, preserve = 1 *) wire w914;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u914 (
        .dataa(chain[914]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w914));
    assign chain[915] = w914;
    (* keep = 1, preserve = 1 *) wire w915;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u915 (
        .dataa(chain[915]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w915));
    assign chain[916] = w915;
    (* keep = 1, preserve = 1 *) wire w916;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u916 (
        .dataa(chain[916]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w916));
    assign chain[917] = w916;
    (* keep = 1, preserve = 1 *) wire w917;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u917 (
        .dataa(chain[917]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w917));
    assign chain[918] = w917;
    (* keep = 1, preserve = 1 *) wire w918;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u918 (
        .dataa(chain[918]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w918));
    assign chain[919] = w918;
    (* keep = 1, preserve = 1 *) wire w919;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u919 (
        .dataa(chain[919]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w919));
    assign chain[920] = w919;
    (* keep = 1, preserve = 1 *) wire w920;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u920 (
        .dataa(chain[920]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w920));
    assign chain[921] = w920;
    (* keep = 1, preserve = 1 *) wire w921;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u921 (
        .dataa(chain[921]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w921));
    assign chain[922] = w921;
    (* keep = 1, preserve = 1 *) wire w922;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u922 (
        .dataa(chain[922]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w922));
    assign chain[923] = w922;
    (* keep = 1, preserve = 1 *) wire w923;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u923 (
        .dataa(chain[923]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w923));
    assign chain[924] = w923;
    (* keep = 1, preserve = 1 *) wire w924;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u924 (
        .dataa(chain[924]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w924));
    assign chain[925] = w924;
    (* keep = 1, preserve = 1 *) wire w925;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u925 (
        .dataa(chain[925]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w925));
    assign chain[926] = w925;
    (* keep = 1, preserve = 1 *) wire w926;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u926 (
        .dataa(chain[926]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w926));
    assign chain[927] = w926;
    (* keep = 1, preserve = 1 *) wire w927;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u927 (
        .dataa(chain[927]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w927));
    assign chain[928] = w927;
    (* keep = 1, preserve = 1 *) wire w928;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u928 (
        .dataa(chain[928]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w928));
    assign chain[929] = w928;
    (* keep = 1, preserve = 1 *) wire w929;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u929 (
        .dataa(chain[929]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w929));
    assign chain[930] = w929;
    (* keep = 1, preserve = 1 *) wire w930;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u930 (
        .dataa(chain[930]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w930));
    assign chain[931] = w930;
    (* keep = 1, preserve = 1 *) wire w931;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u931 (
        .dataa(chain[931]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w931));
    assign chain[932] = w931;
    (* keep = 1, preserve = 1 *) wire w932;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u932 (
        .dataa(chain[932]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w932));
    assign chain[933] = w932;
    (* keep = 1, preserve = 1 *) wire w933;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u933 (
        .dataa(chain[933]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w933));
    assign chain[934] = w933;
    (* keep = 1, preserve = 1 *) wire w934;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u934 (
        .dataa(chain[934]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w934));
    assign chain[935] = w934;
    (* keep = 1, preserve = 1 *) wire w935;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u935 (
        .dataa(chain[935]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w935));
    assign chain[936] = w935;
    (* keep = 1, preserve = 1 *) wire w936;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u936 (
        .dataa(chain[936]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w936));
    assign chain[937] = w936;
    (* keep = 1, preserve = 1 *) wire w937;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u937 (
        .dataa(chain[937]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w937));
    assign chain[938] = w937;
    (* keep = 1, preserve = 1 *) wire w938;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u938 (
        .dataa(chain[938]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w938));
    assign chain[939] = w938;
    (* keep = 1, preserve = 1 *) wire w939;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u939 (
        .dataa(chain[939]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w939));
    assign chain[940] = w939;
    (* keep = 1, preserve = 1 *) wire w940;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u940 (
        .dataa(chain[940]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w940));
    assign chain[941] = w940;
    (* keep = 1, preserve = 1 *) wire w941;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u941 (
        .dataa(chain[941]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w941));
    assign chain[942] = w941;
    (* keep = 1, preserve = 1 *) wire w942;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u942 (
        .dataa(chain[942]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w942));
    assign chain[943] = w942;
    (* keep = 1, preserve = 1 *) wire w943;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u943 (
        .dataa(chain[943]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w943));
    assign chain[944] = w943;
    (* keep = 1, preserve = 1 *) wire w944;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u944 (
        .dataa(chain[944]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w944));
    assign chain[945] = w944;
    (* keep = 1, preserve = 1 *) wire w945;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u945 (
        .dataa(chain[945]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w945));
    assign chain[946] = w945;
    (* keep = 1, preserve = 1 *) wire w946;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u946 (
        .dataa(chain[946]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w946));
    assign chain[947] = w946;
    (* keep = 1, preserve = 1 *) wire w947;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u947 (
        .dataa(chain[947]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w947));
    assign chain[948] = w947;
    (* keep = 1, preserve = 1 *) wire w948;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u948 (
        .dataa(chain[948]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w948));
    assign chain[949] = w948;
    (* keep = 1, preserve = 1 *) wire w949;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u949 (
        .dataa(chain[949]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w949));
    assign chain[950] = w949;
    (* keep = 1, preserve = 1 *) wire w950;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u950 (
        .dataa(chain[950]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w950));
    assign chain[951] = w950;
    (* keep = 1, preserve = 1 *) wire w951;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u951 (
        .dataa(chain[951]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w951));
    assign chain[952] = w951;
    (* keep = 1, preserve = 1 *) wire w952;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u952 (
        .dataa(chain[952]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w952));
    assign chain[953] = w952;
    (* keep = 1, preserve = 1 *) wire w953;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u953 (
        .dataa(chain[953]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w953));
    assign chain[954] = w953;
    (* keep = 1, preserve = 1 *) wire w954;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u954 (
        .dataa(chain[954]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w954));
    assign chain[955] = w954;
    (* keep = 1, preserve = 1 *) wire w955;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u955 (
        .dataa(chain[955]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w955));
    assign chain[956] = w955;
    (* keep = 1, preserve = 1 *) wire w956;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u956 (
        .dataa(chain[956]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w956));
    assign chain[957] = w956;
    (* keep = 1, preserve = 1 *) wire w957;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u957 (
        .dataa(chain[957]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w957));
    assign chain[958] = w957;
    (* keep = 1, preserve = 1 *) wire w958;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u958 (
        .dataa(chain[958]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w958));
    assign chain[959] = w958;
    (* keep = 1, preserve = 1 *) wire w959;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u959 (
        .dataa(chain[959]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w959));
    assign chain[960] = w959;
    (* keep = 1, preserve = 1 *) wire w960;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u960 (
        .dataa(chain[960]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w960));
    assign chain[961] = w960;
    (* keep = 1, preserve = 1 *) wire w961;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u961 (
        .dataa(chain[961]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w961));
    assign chain[962] = w961;
    (* keep = 1, preserve = 1 *) wire w962;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u962 (
        .dataa(chain[962]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w962));
    assign chain[963] = w962;
    (* keep = 1, preserve = 1 *) wire w963;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u963 (
        .dataa(chain[963]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w963));
    assign chain[964] = w963;
    (* keep = 1, preserve = 1 *) wire w964;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u964 (
        .dataa(chain[964]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w964));
    assign chain[965] = w964;
    (* keep = 1, preserve = 1 *) wire w965;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u965 (
        .dataa(chain[965]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w965));
    assign chain[966] = w965;
    (* keep = 1, preserve = 1 *) wire w966;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u966 (
        .dataa(chain[966]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w966));
    assign chain[967] = w966;
    (* keep = 1, preserve = 1 *) wire w967;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u967 (
        .dataa(chain[967]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w967));
    assign chain[968] = w967;
    (* keep = 1, preserve = 1 *) wire w968;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u968 (
        .dataa(chain[968]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w968));
    assign chain[969] = w968;
    (* keep = 1, preserve = 1 *) wire w969;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u969 (
        .dataa(chain[969]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w969));
    assign chain[970] = w969;
    (* keep = 1, preserve = 1 *) wire w970;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u970 (
        .dataa(chain[970]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w970));
    assign chain[971] = w970;
    (* keep = 1, preserve = 1 *) wire w971;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u971 (
        .dataa(chain[971]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w971));
    assign chain[972] = w971;
    (* keep = 1, preserve = 1 *) wire w972;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u972 (
        .dataa(chain[972]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w972));
    assign chain[973] = w972;
    (* keep = 1, preserve = 1 *) wire w973;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u973 (
        .dataa(chain[973]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w973));
    assign chain[974] = w973;
    (* keep = 1, preserve = 1 *) wire w974;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u974 (
        .dataa(chain[974]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w974));
    assign chain[975] = w974;
    (* keep = 1, preserve = 1 *) wire w975;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u975 (
        .dataa(chain[975]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w975));
    assign chain[976] = w975;
    (* keep = 1, preserve = 1 *) wire w976;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u976 (
        .dataa(chain[976]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w976));
    assign chain[977] = w976;
    (* keep = 1, preserve = 1 *) wire w977;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u977 (
        .dataa(chain[977]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w977));
    assign chain[978] = w977;
    (* keep = 1, preserve = 1 *) wire w978;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u978 (
        .dataa(chain[978]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w978));
    assign chain[979] = w978;
    (* keep = 1, preserve = 1 *) wire w979;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u979 (
        .dataa(chain[979]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w979));
    assign chain[980] = w979;
    (* keep = 1, preserve = 1 *) wire w980;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u980 (
        .dataa(chain[980]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w980));
    assign chain[981] = w980;
    (* keep = 1, preserve = 1 *) wire w981;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u981 (
        .dataa(chain[981]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w981));
    assign chain[982] = w981;
    (* keep = 1, preserve = 1 *) wire w982;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u982 (
        .dataa(chain[982]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w982));
    assign chain[983] = w982;
    (* keep = 1, preserve = 1 *) wire w983;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u983 (
        .dataa(chain[983]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w983));
    assign chain[984] = w983;
    (* keep = 1, preserve = 1 *) wire w984;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u984 (
        .dataa(chain[984]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w984));
    assign chain[985] = w984;
    (* keep = 1, preserve = 1 *) wire w985;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u985 (
        .dataa(chain[985]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w985));
    assign chain[986] = w985;
    (* keep = 1, preserve = 1 *) wire w986;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u986 (
        .dataa(chain[986]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w986));
    assign chain[987] = w986;
    (* keep = 1, preserve = 1 *) wire w987;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u987 (
        .dataa(chain[987]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w987));
    assign chain[988] = w987;
    (* keep = 1, preserve = 1 *) wire w988;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u988 (
        .dataa(chain[988]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w988));
    assign chain[989] = w988;
    (* keep = 1, preserve = 1 *) wire w989;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u989 (
        .dataa(chain[989]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w989));
    assign chain[990] = w989;
    (* keep = 1, preserve = 1 *) wire w990;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u990 (
        .dataa(chain[990]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w990));
    assign chain[991] = w990;
    (* keep = 1, preserve = 1 *) wire w991;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u991 (
        .dataa(chain[991]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w991));
    assign chain[992] = w991;
    (* keep = 1, preserve = 1 *) wire w992;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u992 (
        .dataa(chain[992]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w992));
    assign chain[993] = w992;
    (* keep = 1, preserve = 1 *) wire w993;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u993 (
        .dataa(chain[993]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w993));
    assign chain[994] = w993;
    (* keep = 1, preserve = 1 *) wire w994;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u994 (
        .dataa(chain[994]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w994));
    assign chain[995] = w994;
    (* keep = 1, preserve = 1 *) wire w995;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u995 (
        .dataa(chain[995]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w995));
    assign chain[996] = w995;
    (* keep = 1, preserve = 1 *) wire w996;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u996 (
        .dataa(chain[996]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w996));
    assign chain[997] = w996;
    (* keep = 1, preserve = 1 *) wire w997;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u997 (
        .dataa(chain[997]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w997));
    assign chain[998] = w997;
    (* keep = 1, preserve = 1 *) wire w998;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u998 (
        .dataa(chain[998]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w998));
    assign chain[999] = w998;
    (* keep = 1, preserve = 1 *) wire w999;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u999 (
        .dataa(chain[999]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w999));
    assign chain[1000] = w999;
    (* keep = 1, preserve = 1 *) wire w1000;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1000 (
        .dataa(chain[1000]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1000));
    assign chain[1001] = w1000;
    (* keep = 1, preserve = 1 *) wire w1001;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1001 (
        .dataa(chain[1001]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1001));
    assign chain[1002] = w1001;
    (* keep = 1, preserve = 1 *) wire w1002;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1002 (
        .dataa(chain[1002]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1002));
    assign chain[1003] = w1002;
    (* keep = 1, preserve = 1 *) wire w1003;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1003 (
        .dataa(chain[1003]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1003));
    assign chain[1004] = w1003;
    (* keep = 1, preserve = 1 *) wire w1004;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1004 (
        .dataa(chain[1004]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1004));
    assign chain[1005] = w1004;
    (* keep = 1, preserve = 1 *) wire w1005;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1005 (
        .dataa(chain[1005]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1005));
    assign chain[1006] = w1005;
    (* keep = 1, preserve = 1 *) wire w1006;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1006 (
        .dataa(chain[1006]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1006));
    assign chain[1007] = w1006;
    (* keep = 1, preserve = 1 *) wire w1007;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1007 (
        .dataa(chain[1007]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1007));
    assign chain[1008] = w1007;
    (* keep = 1, preserve = 1 *) wire w1008;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1008 (
        .dataa(chain[1008]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1008));
    assign chain[1009] = w1008;
    (* keep = 1, preserve = 1 *) wire w1009;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1009 (
        .dataa(chain[1009]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1009));
    assign chain[1010] = w1009;
    (* keep = 1, preserve = 1 *) wire w1010;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1010 (
        .dataa(chain[1010]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1010));
    assign chain[1011] = w1010;
    (* keep = 1, preserve = 1 *) wire w1011;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1011 (
        .dataa(chain[1011]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1011));
    assign chain[1012] = w1011;
    (* keep = 1, preserve = 1 *) wire w1012;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1012 (
        .dataa(chain[1012]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1012));
    assign chain[1013] = w1012;
    (* keep = 1, preserve = 1 *) wire w1013;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1013 (
        .dataa(chain[1013]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1013));
    assign chain[1014] = w1013;
    (* keep = 1, preserve = 1 *) wire w1014;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1014 (
        .dataa(chain[1014]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1014));
    assign chain[1015] = w1014;
    (* keep = 1, preserve = 1 *) wire w1015;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1015 (
        .dataa(chain[1015]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1015));
    assign chain[1016] = w1015;
    (* keep = 1, preserve = 1 *) wire w1016;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1016 (
        .dataa(chain[1016]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1016));
    assign chain[1017] = w1016;
    (* keep = 1, preserve = 1 *) wire w1017;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1017 (
        .dataa(chain[1017]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1017));
    assign chain[1018] = w1017;
    (* keep = 1, preserve = 1 *) wire w1018;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1018 (
        .dataa(chain[1018]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1018));
    assign chain[1019] = w1018;
    (* keep = 1, preserve = 1 *) wire w1019;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1019 (
        .dataa(chain[1019]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1019));
    assign chain[1020] = w1019;
    (* keep = 1, preserve = 1 *) wire w1020;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1020 (
        .dataa(chain[1020]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1020));
    assign chain[1021] = w1020;
    (* keep = 1, preserve = 1 *) wire w1021;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1021 (
        .dataa(chain[1021]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1021));
    assign chain[1022] = w1021;
    (* keep = 1, preserve = 1 *) wire w1022;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1022 (
        .dataa(chain[1022]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1022));
    assign chain[1023] = w1022;
    (* keep = 1, preserve = 1 *) wire w1023;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1023 (
        .dataa(chain[1023]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1023));
    assign chain[1024] = w1023;
    (* keep = 1, preserve = 1 *) wire w1024;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1024 (
        .dataa(chain[1024]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1024));
    assign chain[1025] = w1024;
    (* keep = 1, preserve = 1 *) wire w1025;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1025 (
        .dataa(chain[1025]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1025));
    assign chain[1026] = w1025;
    (* keep = 1, preserve = 1 *) wire w1026;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1026 (
        .dataa(chain[1026]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1026));
    assign chain[1027] = w1026;
    (* keep = 1, preserve = 1 *) wire w1027;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1027 (
        .dataa(chain[1027]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1027));
    assign chain[1028] = w1027;
    (* keep = 1, preserve = 1 *) wire w1028;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1028 (
        .dataa(chain[1028]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1028));
    assign chain[1029] = w1028;
    (* keep = 1, preserve = 1 *) wire w1029;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1029 (
        .dataa(chain[1029]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1029));
    assign chain[1030] = w1029;
    (* keep = 1, preserve = 1 *) wire w1030;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1030 (
        .dataa(chain[1030]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1030));
    assign chain[1031] = w1030;
    (* keep = 1, preserve = 1 *) wire w1031;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1031 (
        .dataa(chain[1031]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1031));
    assign chain[1032] = w1031;
    (* keep = 1, preserve = 1 *) wire w1032;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1032 (
        .dataa(chain[1032]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1032));
    assign chain[1033] = w1032;
    (* keep = 1, preserve = 1 *) wire w1033;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1033 (
        .dataa(chain[1033]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1033));
    assign chain[1034] = w1033;
    (* keep = 1, preserve = 1 *) wire w1034;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1034 (
        .dataa(chain[1034]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1034));
    assign chain[1035] = w1034;
    (* keep = 1, preserve = 1 *) wire w1035;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1035 (
        .dataa(chain[1035]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1035));
    assign chain[1036] = w1035;
    (* keep = 1, preserve = 1 *) wire w1036;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1036 (
        .dataa(chain[1036]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1036));
    assign chain[1037] = w1036;
    (* keep = 1, preserve = 1 *) wire w1037;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1037 (
        .dataa(chain[1037]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1037));
    assign chain[1038] = w1037;
    (* keep = 1, preserve = 1 *) wire w1038;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1038 (
        .dataa(chain[1038]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1038));
    assign chain[1039] = w1038;
    (* keep = 1, preserve = 1 *) wire w1039;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1039 (
        .dataa(chain[1039]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1039));
    assign chain[1040] = w1039;
    (* keep = 1, preserve = 1 *) wire w1040;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1040 (
        .dataa(chain[1040]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1040));
    assign chain[1041] = w1040;
    (* keep = 1, preserve = 1 *) wire w1041;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1041 (
        .dataa(chain[1041]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1041));
    assign chain[1042] = w1041;
    (* keep = 1, preserve = 1 *) wire w1042;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1042 (
        .dataa(chain[1042]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1042));
    assign chain[1043] = w1042;
    (* keep = 1, preserve = 1 *) wire w1043;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1043 (
        .dataa(chain[1043]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1043));
    assign chain[1044] = w1043;
    (* keep = 1, preserve = 1 *) wire w1044;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1044 (
        .dataa(chain[1044]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1044));
    assign chain[1045] = w1044;
    (* keep = 1, preserve = 1 *) wire w1045;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1045 (
        .dataa(chain[1045]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1045));
    assign chain[1046] = w1045;
    (* keep = 1, preserve = 1 *) wire w1046;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1046 (
        .dataa(chain[1046]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1046));
    assign chain[1047] = w1046;
    (* keep = 1, preserve = 1 *) wire w1047;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1047 (
        .dataa(chain[1047]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1047));
    assign chain[1048] = w1047;
    (* keep = 1, preserve = 1 *) wire w1048;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1048 (
        .dataa(chain[1048]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1048));
    assign chain[1049] = w1048;
    (* keep = 1, preserve = 1 *) wire w1049;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1049 (
        .dataa(chain[1049]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1049));
    assign chain[1050] = w1049;
    (* keep = 1, preserve = 1 *) wire w1050;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1050 (
        .dataa(chain[1050]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1050));
    assign chain[1051] = w1050;
    (* keep = 1, preserve = 1 *) wire w1051;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1051 (
        .dataa(chain[1051]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1051));
    assign chain[1052] = w1051;
    (* keep = 1, preserve = 1 *) wire w1052;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1052 (
        .dataa(chain[1052]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1052));
    assign chain[1053] = w1052;
    (* keep = 1, preserve = 1 *) wire w1053;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1053 (
        .dataa(chain[1053]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1053));
    assign chain[1054] = w1053;
    (* keep = 1, preserve = 1 *) wire w1054;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1054 (
        .dataa(chain[1054]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1054));
    assign chain[1055] = w1054;
    (* keep = 1, preserve = 1 *) wire w1055;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1055 (
        .dataa(chain[1055]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1055));
    assign chain[1056] = w1055;
    (* keep = 1, preserve = 1 *) wire w1056;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1056 (
        .dataa(chain[1056]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1056));
    assign chain[1057] = w1056;
    (* keep = 1, preserve = 1 *) wire w1057;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1057 (
        .dataa(chain[1057]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1057));
    assign chain[1058] = w1057;
    (* keep = 1, preserve = 1 *) wire w1058;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1058 (
        .dataa(chain[1058]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1058));
    assign chain[1059] = w1058;
    (* keep = 1, preserve = 1 *) wire w1059;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1059 (
        .dataa(chain[1059]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1059));
    assign chain[1060] = w1059;
    (* keep = 1, preserve = 1 *) wire w1060;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1060 (
        .dataa(chain[1060]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1060));
    assign chain[1061] = w1060;
    (* keep = 1, preserve = 1 *) wire w1061;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1061 (
        .dataa(chain[1061]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1061));
    assign chain[1062] = w1061;
    (* keep = 1, preserve = 1 *) wire w1062;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1062 (
        .dataa(chain[1062]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1062));
    assign chain[1063] = w1062;
    (* keep = 1, preserve = 1 *) wire w1063;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1063 (
        .dataa(chain[1063]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1063));
    assign chain[1064] = w1063;
    (* keep = 1, preserve = 1 *) wire w1064;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1064 (
        .dataa(chain[1064]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1064));
    assign chain[1065] = w1064;
    (* keep = 1, preserve = 1 *) wire w1065;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1065 (
        .dataa(chain[1065]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1065));
    assign chain[1066] = w1065;
    (* keep = 1, preserve = 1 *) wire w1066;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1066 (
        .dataa(chain[1066]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1066));
    assign chain[1067] = w1066;
    (* keep = 1, preserve = 1 *) wire w1067;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1067 (
        .dataa(chain[1067]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1067));
    assign chain[1068] = w1067;
    (* keep = 1, preserve = 1 *) wire w1068;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1068 (
        .dataa(chain[1068]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1068));
    assign chain[1069] = w1068;
    (* keep = 1, preserve = 1 *) wire w1069;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1069 (
        .dataa(chain[1069]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1069));
    assign chain[1070] = w1069;
    (* keep = 1, preserve = 1 *) wire w1070;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1070 (
        .dataa(chain[1070]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1070));
    assign chain[1071] = w1070;
    (* keep = 1, preserve = 1 *) wire w1071;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1071 (
        .dataa(chain[1071]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1071));
    assign chain[1072] = w1071;
    (* keep = 1, preserve = 1 *) wire w1072;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1072 (
        .dataa(chain[1072]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1072));
    assign chain[1073] = w1072;
    (* keep = 1, preserve = 1 *) wire w1073;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1073 (
        .dataa(chain[1073]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1073));
    assign chain[1074] = w1073;
    (* keep = 1, preserve = 1 *) wire w1074;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1074 (
        .dataa(chain[1074]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1074));
    assign chain[1075] = w1074;
    (* keep = 1, preserve = 1 *) wire w1075;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1075 (
        .dataa(chain[1075]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1075));
    assign chain[1076] = w1075;
    (* keep = 1, preserve = 1 *) wire w1076;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1076 (
        .dataa(chain[1076]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1076));
    assign chain[1077] = w1076;
    (* keep = 1, preserve = 1 *) wire w1077;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1077 (
        .dataa(chain[1077]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1077));
    assign chain[1078] = w1077;
    (* keep = 1, preserve = 1 *) wire w1078;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1078 (
        .dataa(chain[1078]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1078));
    assign chain[1079] = w1078;
    (* keep = 1, preserve = 1 *) wire w1079;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1079 (
        .dataa(chain[1079]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1079));
    assign chain[1080] = w1079;
    (* keep = 1, preserve = 1 *) wire w1080;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1080 (
        .dataa(chain[1080]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1080));
    assign chain[1081] = w1080;
    (* keep = 1, preserve = 1 *) wire w1081;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1081 (
        .dataa(chain[1081]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1081));
    assign chain[1082] = w1081;
    (* keep = 1, preserve = 1 *) wire w1082;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1082 (
        .dataa(chain[1082]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1082));
    assign chain[1083] = w1082;
    (* keep = 1, preserve = 1 *) wire w1083;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1083 (
        .dataa(chain[1083]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1083));
    assign chain[1084] = w1083;
    (* keep = 1, preserve = 1 *) wire w1084;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1084 (
        .dataa(chain[1084]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1084));
    assign chain[1085] = w1084;
    (* keep = 1, preserve = 1 *) wire w1085;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1085 (
        .dataa(chain[1085]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1085));
    assign chain[1086] = w1085;
    (* keep = 1, preserve = 1 *) wire w1086;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1086 (
        .dataa(chain[1086]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1086));
    assign chain[1087] = w1086;
    (* keep = 1, preserve = 1 *) wire w1087;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1087 (
        .dataa(chain[1087]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1087));
    assign chain[1088] = w1087;
    (* keep = 1, preserve = 1 *) wire w1088;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1088 (
        .dataa(chain[1088]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1088));
    assign chain[1089] = w1088;
    (* keep = 1, preserve = 1 *) wire w1089;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1089 (
        .dataa(chain[1089]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1089));
    assign chain[1090] = w1089;
    (* keep = 1, preserve = 1 *) wire w1090;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1090 (
        .dataa(chain[1090]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1090));
    assign chain[1091] = w1090;
    (* keep = 1, preserve = 1 *) wire w1091;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1091 (
        .dataa(chain[1091]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1091));
    assign chain[1092] = w1091;
    (* keep = 1, preserve = 1 *) wire w1092;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1092 (
        .dataa(chain[1092]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1092));
    assign chain[1093] = w1092;
    (* keep = 1, preserve = 1 *) wire w1093;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1093 (
        .dataa(chain[1093]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1093));
    assign chain[1094] = w1093;
    (* keep = 1, preserve = 1 *) wire w1094;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1094 (
        .dataa(chain[1094]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1094));
    assign chain[1095] = w1094;
    (* keep = 1, preserve = 1 *) wire w1095;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1095 (
        .dataa(chain[1095]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1095));
    assign chain[1096] = w1095;
    (* keep = 1, preserve = 1 *) wire w1096;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1096 (
        .dataa(chain[1096]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1096));
    assign chain[1097] = w1096;
    (* keep = 1, preserve = 1 *) wire w1097;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1097 (
        .dataa(chain[1097]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1097));
    assign chain[1098] = w1097;
    (* keep = 1, preserve = 1 *) wire w1098;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1098 (
        .dataa(chain[1098]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1098));
    assign chain[1099] = w1098;
    (* keep = 1, preserve = 1 *) wire w1099;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1099 (
        .dataa(chain[1099]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1099));
    assign chain[1100] = w1099;
    (* keep = 1, preserve = 1 *) wire w1100;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1100 (
        .dataa(chain[1100]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1100));
    assign chain[1101] = w1100;
    (* keep = 1, preserve = 1 *) wire w1101;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1101 (
        .dataa(chain[1101]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1101));
    assign chain[1102] = w1101;
    (* keep = 1, preserve = 1 *) wire w1102;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1102 (
        .dataa(chain[1102]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1102));
    assign chain[1103] = w1102;
    (* keep = 1, preserve = 1 *) wire w1103;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1103 (
        .dataa(chain[1103]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1103));
    assign chain[1104] = w1103;
    (* keep = 1, preserve = 1 *) wire w1104;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1104 (
        .dataa(chain[1104]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1104));
    assign chain[1105] = w1104;
    (* keep = 1, preserve = 1 *) wire w1105;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1105 (
        .dataa(chain[1105]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1105));
    assign chain[1106] = w1105;
    (* keep = 1, preserve = 1 *) wire w1106;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1106 (
        .dataa(chain[1106]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1106));
    assign chain[1107] = w1106;
    (* keep = 1, preserve = 1 *) wire w1107;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1107 (
        .dataa(chain[1107]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1107));
    assign chain[1108] = w1107;
    (* keep = 1, preserve = 1 *) wire w1108;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1108 (
        .dataa(chain[1108]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1108));
    assign chain[1109] = w1108;
    (* keep = 1, preserve = 1 *) wire w1109;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1109 (
        .dataa(chain[1109]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1109));
    assign chain[1110] = w1109;
    (* keep = 1, preserve = 1 *) wire w1110;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1110 (
        .dataa(chain[1110]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1110));
    assign chain[1111] = w1110;
    (* keep = 1, preserve = 1 *) wire w1111;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1111 (
        .dataa(chain[1111]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1111));
    assign chain[1112] = w1111;
    (* keep = 1, preserve = 1 *) wire w1112;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1112 (
        .dataa(chain[1112]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1112));
    assign chain[1113] = w1112;
    (* keep = 1, preserve = 1 *) wire w1113;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1113 (
        .dataa(chain[1113]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1113));
    assign chain[1114] = w1113;
    (* keep = 1, preserve = 1 *) wire w1114;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1114 (
        .dataa(chain[1114]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1114));
    assign chain[1115] = w1114;
    (* keep = 1, preserve = 1 *) wire w1115;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1115 (
        .dataa(chain[1115]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1115));
    assign chain[1116] = w1115;
    (* keep = 1, preserve = 1 *) wire w1116;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1116 (
        .dataa(chain[1116]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1116));
    assign chain[1117] = w1116;
    (* keep = 1, preserve = 1 *) wire w1117;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1117 (
        .dataa(chain[1117]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1117));
    assign chain[1118] = w1117;
    (* keep = 1, preserve = 1 *) wire w1118;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1118 (
        .dataa(chain[1118]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1118));
    assign chain[1119] = w1118;
    (* keep = 1, preserve = 1 *) wire w1119;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1119 (
        .dataa(chain[1119]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1119));
    assign chain[1120] = w1119;
    (* keep = 1, preserve = 1 *) wire w1120;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1120 (
        .dataa(chain[1120]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1120));
    assign chain[1121] = w1120;
    (* keep = 1, preserve = 1 *) wire w1121;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1121 (
        .dataa(chain[1121]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1121));
    assign chain[1122] = w1121;
    (* keep = 1, preserve = 1 *) wire w1122;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1122 (
        .dataa(chain[1122]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1122));
    assign chain[1123] = w1122;
    (* keep = 1, preserve = 1 *) wire w1123;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1123 (
        .dataa(chain[1123]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1123));
    assign chain[1124] = w1123;
    (* keep = 1, preserve = 1 *) wire w1124;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1124 (
        .dataa(chain[1124]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1124));
    assign chain[1125] = w1124;
    (* keep = 1, preserve = 1 *) wire w1125;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1125 (
        .dataa(chain[1125]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1125));
    assign chain[1126] = w1125;
    (* keep = 1, preserve = 1 *) wire w1126;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1126 (
        .dataa(chain[1126]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1126));
    assign chain[1127] = w1126;
    (* keep = 1, preserve = 1 *) wire w1127;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1127 (
        .dataa(chain[1127]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1127));
    assign chain[1128] = w1127;
    (* keep = 1, preserve = 1 *) wire w1128;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1128 (
        .dataa(chain[1128]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1128));
    assign chain[1129] = w1128;
    (* keep = 1, preserve = 1 *) wire w1129;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1129 (
        .dataa(chain[1129]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1129));
    assign chain[1130] = w1129;
    (* keep = 1, preserve = 1 *) wire w1130;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1130 (
        .dataa(chain[1130]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1130));
    assign chain[1131] = w1130;
    (* keep = 1, preserve = 1 *) wire w1131;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1131 (
        .dataa(chain[1131]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1131));
    assign chain[1132] = w1131;
    (* keep = 1, preserve = 1 *) wire w1132;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1132 (
        .dataa(chain[1132]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1132));
    assign chain[1133] = w1132;
    (* keep = 1, preserve = 1 *) wire w1133;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1133 (
        .dataa(chain[1133]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1133));
    assign chain[1134] = w1133;
    (* keep = 1, preserve = 1 *) wire w1134;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1134 (
        .dataa(chain[1134]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1134));
    assign chain[1135] = w1134;
    (* keep = 1, preserve = 1 *) wire w1135;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1135 (
        .dataa(chain[1135]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1135));
    assign chain[1136] = w1135;
    (* keep = 1, preserve = 1 *) wire w1136;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1136 (
        .dataa(chain[1136]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1136));
    assign chain[1137] = w1136;
    (* keep = 1, preserve = 1 *) wire w1137;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1137 (
        .dataa(chain[1137]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1137));
    assign chain[1138] = w1137;
    (* keep = 1, preserve = 1 *) wire w1138;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1138 (
        .dataa(chain[1138]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1138));
    assign chain[1139] = w1138;
    (* keep = 1, preserve = 1 *) wire w1139;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1139 (
        .dataa(chain[1139]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1139));
    assign chain[1140] = w1139;
    (* keep = 1, preserve = 1 *) wire w1140;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1140 (
        .dataa(chain[1140]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1140));
    assign chain[1141] = w1140;
    (* keep = 1, preserve = 1 *) wire w1141;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1141 (
        .dataa(chain[1141]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1141));
    assign chain[1142] = w1141;
    (* keep = 1, preserve = 1 *) wire w1142;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1142 (
        .dataa(chain[1142]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1142));
    assign chain[1143] = w1142;
    (* keep = 1, preserve = 1 *) wire w1143;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1143 (
        .dataa(chain[1143]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1143));
    assign chain[1144] = w1143;
    (* keep = 1, preserve = 1 *) wire w1144;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1144 (
        .dataa(chain[1144]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1144));
    assign chain[1145] = w1144;
    (* keep = 1, preserve = 1 *) wire w1145;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1145 (
        .dataa(chain[1145]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1145));
    assign chain[1146] = w1145;
    (* keep = 1, preserve = 1 *) wire w1146;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1146 (
        .dataa(chain[1146]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1146));
    assign chain[1147] = w1146;
    (* keep = 1, preserve = 1 *) wire w1147;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1147 (
        .dataa(chain[1147]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1147));
    assign chain[1148] = w1147;
    (* keep = 1, preserve = 1 *) wire w1148;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1148 (
        .dataa(chain[1148]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1148));
    assign chain[1149] = w1148;
    (* keep = 1, preserve = 1 *) wire w1149;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1149 (
        .dataa(chain[1149]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1149));
    assign chain[1150] = w1149;
    (* keep = 1, preserve = 1 *) wire w1150;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1150 (
        .dataa(chain[1150]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1150));
    assign chain[1151] = w1150;
    (* keep = 1, preserve = 1 *) wire w1151;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1151 (
        .dataa(chain[1151]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1151));
    assign chain[1152] = w1151;
    (* keep = 1, preserve = 1 *) wire w1152;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1152 (
        .dataa(chain[1152]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1152));
    assign chain[1153] = w1152;
    (* keep = 1, preserve = 1 *) wire w1153;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1153 (
        .dataa(chain[1153]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1153));
    assign chain[1154] = w1153;
    (* keep = 1, preserve = 1 *) wire w1154;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1154 (
        .dataa(chain[1154]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1154));
    assign chain[1155] = w1154;
    (* keep = 1, preserve = 1 *) wire w1155;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1155 (
        .dataa(chain[1155]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1155));
    assign chain[1156] = w1155;
    (* keep = 1, preserve = 1 *) wire w1156;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1156 (
        .dataa(chain[1156]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1156));
    assign chain[1157] = w1156;
    (* keep = 1, preserve = 1 *) wire w1157;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1157 (
        .dataa(chain[1157]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1157));
    assign chain[1158] = w1157;
    (* keep = 1, preserve = 1 *) wire w1158;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1158 (
        .dataa(chain[1158]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1158));
    assign chain[1159] = w1158;
    (* keep = 1, preserve = 1 *) wire w1159;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1159 (
        .dataa(chain[1159]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1159));
    assign chain[1160] = w1159;
    (* keep = 1, preserve = 1 *) wire w1160;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1160 (
        .dataa(chain[1160]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1160));
    assign chain[1161] = w1160;
    (* keep = 1, preserve = 1 *) wire w1161;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1161 (
        .dataa(chain[1161]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1161));
    assign chain[1162] = w1161;
    (* keep = 1, preserve = 1 *) wire w1162;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1162 (
        .dataa(chain[1162]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1162));
    assign chain[1163] = w1162;
    (* keep = 1, preserve = 1 *) wire w1163;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1163 (
        .dataa(chain[1163]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1163));
    assign chain[1164] = w1163;
    (* keep = 1, preserve = 1 *) wire w1164;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1164 (
        .dataa(chain[1164]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1164));
    assign chain[1165] = w1164;
    (* keep = 1, preserve = 1 *) wire w1165;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1165 (
        .dataa(chain[1165]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1165));
    assign chain[1166] = w1165;
    (* keep = 1, preserve = 1 *) wire w1166;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1166 (
        .dataa(chain[1166]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1166));
    assign chain[1167] = w1166;
    (* keep = 1, preserve = 1 *) wire w1167;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1167 (
        .dataa(chain[1167]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1167));
    assign chain[1168] = w1167;
    (* keep = 1, preserve = 1 *) wire w1168;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1168 (
        .dataa(chain[1168]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1168));
    assign chain[1169] = w1168;
    (* keep = 1, preserve = 1 *) wire w1169;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1169 (
        .dataa(chain[1169]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1169));
    assign chain[1170] = w1169;
    (* keep = 1, preserve = 1 *) wire w1170;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1170 (
        .dataa(chain[1170]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1170));
    assign chain[1171] = w1170;
    (* keep = 1, preserve = 1 *) wire w1171;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1171 (
        .dataa(chain[1171]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1171));
    assign chain[1172] = w1171;
    (* keep = 1, preserve = 1 *) wire w1172;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1172 (
        .dataa(chain[1172]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1172));
    assign chain[1173] = w1172;
    (* keep = 1, preserve = 1 *) wire w1173;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1173 (
        .dataa(chain[1173]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1173));
    assign chain[1174] = w1173;
    (* keep = 1, preserve = 1 *) wire w1174;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1174 (
        .dataa(chain[1174]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1174));
    assign chain[1175] = w1174;
    (* keep = 1, preserve = 1 *) wire w1175;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1175 (
        .dataa(chain[1175]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1175));
    assign chain[1176] = w1175;
    (* keep = 1, preserve = 1 *) wire w1176;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1176 (
        .dataa(chain[1176]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1176));
    assign chain[1177] = w1176;
    (* keep = 1, preserve = 1 *) wire w1177;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1177 (
        .dataa(chain[1177]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1177));
    assign chain[1178] = w1177;
    (* keep = 1, preserve = 1 *) wire w1178;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1178 (
        .dataa(chain[1178]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1178));
    assign chain[1179] = w1178;
    (* keep = 1, preserve = 1 *) wire w1179;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1179 (
        .dataa(chain[1179]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1179));
    assign chain[1180] = w1179;
    (* keep = 1, preserve = 1 *) wire w1180;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1180 (
        .dataa(chain[1180]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1180));
    assign chain[1181] = w1180;
    (* keep = 1, preserve = 1 *) wire w1181;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1181 (
        .dataa(chain[1181]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1181));
    assign chain[1182] = w1181;
    (* keep = 1, preserve = 1 *) wire w1182;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1182 (
        .dataa(chain[1182]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1182));
    assign chain[1183] = w1182;
    (* keep = 1, preserve = 1 *) wire w1183;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1183 (
        .dataa(chain[1183]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1183));
    assign chain[1184] = w1183;
    (* keep = 1, preserve = 1 *) wire w1184;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1184 (
        .dataa(chain[1184]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1184));
    assign chain[1185] = w1184;
    (* keep = 1, preserve = 1 *) wire w1185;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1185 (
        .dataa(chain[1185]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1185));
    assign chain[1186] = w1185;
    (* keep = 1, preserve = 1 *) wire w1186;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1186 (
        .dataa(chain[1186]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1186));
    assign chain[1187] = w1186;
    (* keep = 1, preserve = 1 *) wire w1187;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1187 (
        .dataa(chain[1187]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1187));
    assign chain[1188] = w1187;
    (* keep = 1, preserve = 1 *) wire w1188;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1188 (
        .dataa(chain[1188]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1188));
    assign chain[1189] = w1188;
    (* keep = 1, preserve = 1 *) wire w1189;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1189 (
        .dataa(chain[1189]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1189));
    assign chain[1190] = w1189;
    (* keep = 1, preserve = 1 *) wire w1190;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1190 (
        .dataa(chain[1190]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1190));
    assign chain[1191] = w1190;
    (* keep = 1, preserve = 1 *) wire w1191;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1191 (
        .dataa(chain[1191]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1191));
    assign chain[1192] = w1191;
    (* keep = 1, preserve = 1 *) wire w1192;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1192 (
        .dataa(chain[1192]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1192));
    assign chain[1193] = w1192;
    (* keep = 1, preserve = 1 *) wire w1193;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1193 (
        .dataa(chain[1193]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1193));
    assign chain[1194] = w1193;
    (* keep = 1, preserve = 1 *) wire w1194;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1194 (
        .dataa(chain[1194]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1194));
    assign chain[1195] = w1194;
    (* keep = 1, preserve = 1 *) wire w1195;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1195 (
        .dataa(chain[1195]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1195));
    assign chain[1196] = w1195;
    (* keep = 1, preserve = 1 *) wire w1196;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1196 (
        .dataa(chain[1196]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1196));
    assign chain[1197] = w1196;
    (* keep = 1, preserve = 1 *) wire w1197;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1197 (
        .dataa(chain[1197]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1197));
    assign chain[1198] = w1197;
    (* keep = 1, preserve = 1 *) wire w1198;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1198 (
        .dataa(chain[1198]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1198));
    assign chain[1199] = w1198;
    (* keep = 1, preserve = 1 *) wire w1199;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1199 (
        .dataa(chain[1199]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1199));
    assign chain[1200] = w1199;
    (* keep = 1, preserve = 1 *) wire w1200;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1200 (
        .dataa(chain[1200]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1200));
    assign chain[1201] = w1200;
    (* keep = 1, preserve = 1 *) wire w1201;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1201 (
        .dataa(chain[1201]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1201));
    assign chain[1202] = w1201;
    (* keep = 1, preserve = 1 *) wire w1202;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1202 (
        .dataa(chain[1202]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1202));
    assign chain[1203] = w1202;
    (* keep = 1, preserve = 1 *) wire w1203;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1203 (
        .dataa(chain[1203]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1203));
    assign chain[1204] = w1203;
    (* keep = 1, preserve = 1 *) wire w1204;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1204 (
        .dataa(chain[1204]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1204));
    assign chain[1205] = w1204;
    (* keep = 1, preserve = 1 *) wire w1205;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1205 (
        .dataa(chain[1205]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1205));
    assign chain[1206] = w1205;
    (* keep = 1, preserve = 1 *) wire w1206;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1206 (
        .dataa(chain[1206]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1206));
    assign chain[1207] = w1206;
    (* keep = 1, preserve = 1 *) wire w1207;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1207 (
        .dataa(chain[1207]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1207));
    assign chain[1208] = w1207;
    (* keep = 1, preserve = 1 *) wire w1208;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1208 (
        .dataa(chain[1208]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1208));
    assign chain[1209] = w1208;
    (* keep = 1, preserve = 1 *) wire w1209;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1209 (
        .dataa(chain[1209]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1209));
    assign chain[1210] = w1209;
    (* keep = 1, preserve = 1 *) wire w1210;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1210 (
        .dataa(chain[1210]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1210));
    assign chain[1211] = w1210;
    (* keep = 1, preserve = 1 *) wire w1211;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1211 (
        .dataa(chain[1211]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1211));
    assign chain[1212] = w1211;
    (* keep = 1, preserve = 1 *) wire w1212;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1212 (
        .dataa(chain[1212]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1212));
    assign chain[1213] = w1212;
    (* keep = 1, preserve = 1 *) wire w1213;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1213 (
        .dataa(chain[1213]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1213));
    assign chain[1214] = w1213;
    (* keep = 1, preserve = 1 *) wire w1214;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1214 (
        .dataa(chain[1214]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1214));
    assign chain[1215] = w1214;
    (* keep = 1, preserve = 1 *) wire w1215;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1215 (
        .dataa(chain[1215]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1215));
    assign chain[1216] = w1215;
    (* keep = 1, preserve = 1 *) wire w1216;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1216 (
        .dataa(chain[1216]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1216));
    assign chain[1217] = w1216;
    (* keep = 1, preserve = 1 *) wire w1217;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1217 (
        .dataa(chain[1217]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1217));
    assign chain[1218] = w1217;
    (* keep = 1, preserve = 1 *) wire w1218;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1218 (
        .dataa(chain[1218]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1218));
    assign chain[1219] = w1218;
    (* keep = 1, preserve = 1 *) wire w1219;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1219 (
        .dataa(chain[1219]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1219));
    assign chain[1220] = w1219;
    (* keep = 1, preserve = 1 *) wire w1220;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1220 (
        .dataa(chain[1220]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1220));
    assign chain[1221] = w1220;
    (* keep = 1, preserve = 1 *) wire w1221;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1221 (
        .dataa(chain[1221]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1221));
    assign chain[1222] = w1221;
    (* keep = 1, preserve = 1 *) wire w1222;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1222 (
        .dataa(chain[1222]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1222));
    assign chain[1223] = w1222;
    (* keep = 1, preserve = 1 *) wire w1223;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1223 (
        .dataa(chain[1223]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1223));
    assign chain[1224] = w1223;
    (* keep = 1, preserve = 1 *) wire w1224;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1224 (
        .dataa(chain[1224]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1224));
    assign chain[1225] = w1224;
    (* keep = 1, preserve = 1 *) wire w1225;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1225 (
        .dataa(chain[1225]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1225));
    assign chain[1226] = w1225;
    (* keep = 1, preserve = 1 *) wire w1226;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1226 (
        .dataa(chain[1226]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1226));
    assign chain[1227] = w1226;
    (* keep = 1, preserve = 1 *) wire w1227;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1227 (
        .dataa(chain[1227]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1227));
    assign chain[1228] = w1227;
    (* keep = 1, preserve = 1 *) wire w1228;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1228 (
        .dataa(chain[1228]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1228));
    assign chain[1229] = w1228;
    (* keep = 1, preserve = 1 *) wire w1229;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1229 (
        .dataa(chain[1229]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1229));
    assign chain[1230] = w1229;
    (* keep = 1, preserve = 1 *) wire w1230;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1230 (
        .dataa(chain[1230]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1230));
    assign chain[1231] = w1230;
    (* keep = 1, preserve = 1 *) wire w1231;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1231 (
        .dataa(chain[1231]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1231));
    assign chain[1232] = w1231;
    (* keep = 1, preserve = 1 *) wire w1232;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1232 (
        .dataa(chain[1232]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1232));
    assign chain[1233] = w1232;
    (* keep = 1, preserve = 1 *) wire w1233;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1233 (
        .dataa(chain[1233]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1233));
    assign chain[1234] = w1233;
    (* keep = 1, preserve = 1 *) wire w1234;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1234 (
        .dataa(chain[1234]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1234));
    assign chain[1235] = w1234;
    (* keep = 1, preserve = 1 *) wire w1235;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1235 (
        .dataa(chain[1235]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1235));
    assign chain[1236] = w1235;
    (* keep = 1, preserve = 1 *) wire w1236;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1236 (
        .dataa(chain[1236]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1236));
    assign chain[1237] = w1236;
    (* keep = 1, preserve = 1 *) wire w1237;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1237 (
        .dataa(chain[1237]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1237));
    assign chain[1238] = w1237;
    (* keep = 1, preserve = 1 *) wire w1238;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1238 (
        .dataa(chain[1238]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1238));
    assign chain[1239] = w1238;
    (* keep = 1, preserve = 1 *) wire w1239;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1239 (
        .dataa(chain[1239]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1239));
    assign chain[1240] = w1239;
    (* keep = 1, preserve = 1 *) wire w1240;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1240 (
        .dataa(chain[1240]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1240));
    assign chain[1241] = w1240;
    (* keep = 1, preserve = 1 *) wire w1241;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1241 (
        .dataa(chain[1241]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1241));
    assign chain[1242] = w1241;
    (* keep = 1, preserve = 1 *) wire w1242;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1242 (
        .dataa(chain[1242]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1242));
    assign chain[1243] = w1242;
    (* keep = 1, preserve = 1 *) wire w1243;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1243 (
        .dataa(chain[1243]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1243));
    assign chain[1244] = w1243;
    (* keep = 1, preserve = 1 *) wire w1244;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1244 (
        .dataa(chain[1244]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1244));
    assign chain[1245] = w1244;
    (* keep = 1, preserve = 1 *) wire w1245;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1245 (
        .dataa(chain[1245]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1245));
    assign chain[1246] = w1245;
    (* keep = 1, preserve = 1 *) wire w1246;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1246 (
        .dataa(chain[1246]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1246));
    assign chain[1247] = w1246;
    (* keep = 1, preserve = 1 *) wire w1247;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1247 (
        .dataa(chain[1247]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1247));
    assign chain[1248] = w1247;
    (* keep = 1, preserve = 1 *) wire w1248;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1248 (
        .dataa(chain[1248]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1248));
    assign chain[1249] = w1248;
    (* keep = 1, preserve = 1 *) wire w1249;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1249 (
        .dataa(chain[1249]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1249));
    assign chain[1250] = w1249;
    (* keep = 1, preserve = 1 *) wire w1250;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1250 (
        .dataa(chain[1250]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1250));
    assign chain[1251] = w1250;
    (* keep = 1, preserve = 1 *) wire w1251;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1251 (
        .dataa(chain[1251]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1251));
    assign chain[1252] = w1251;
    (* keep = 1, preserve = 1 *) wire w1252;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1252 (
        .dataa(chain[1252]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1252));
    assign chain[1253] = w1252;
    (* keep = 1, preserve = 1 *) wire w1253;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1253 (
        .dataa(chain[1253]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1253));
    assign chain[1254] = w1253;
    (* keep = 1, preserve = 1 *) wire w1254;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1254 (
        .dataa(chain[1254]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1254));
    assign chain[1255] = w1254;
    (* keep = 1, preserve = 1 *) wire w1255;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1255 (
        .dataa(chain[1255]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1255));
    assign chain[1256] = w1255;
    (* keep = 1, preserve = 1 *) wire w1256;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1256 (
        .dataa(chain[1256]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1256));
    assign chain[1257] = w1256;
    (* keep = 1, preserve = 1 *) wire w1257;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1257 (
        .dataa(chain[1257]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1257));
    assign chain[1258] = w1257;
    (* keep = 1, preserve = 1 *) wire w1258;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1258 (
        .dataa(chain[1258]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1258));
    assign chain[1259] = w1258;
    (* keep = 1, preserve = 1 *) wire w1259;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1259 (
        .dataa(chain[1259]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1259));
    assign chain[1260] = w1259;
    (* keep = 1, preserve = 1 *) wire w1260;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1260 (
        .dataa(chain[1260]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1260));
    assign chain[1261] = w1260;
    (* keep = 1, preserve = 1 *) wire w1261;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1261 (
        .dataa(chain[1261]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1261));
    assign chain[1262] = w1261;
    (* keep = 1, preserve = 1 *) wire w1262;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1262 (
        .dataa(chain[1262]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1262));
    assign chain[1263] = w1262;
    (* keep = 1, preserve = 1 *) wire w1263;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1263 (
        .dataa(chain[1263]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1263));
    assign chain[1264] = w1263;
    (* keep = 1, preserve = 1 *) wire w1264;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1264 (
        .dataa(chain[1264]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1264));
    assign chain[1265] = w1264;
    (* keep = 1, preserve = 1 *) wire w1265;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1265 (
        .dataa(chain[1265]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1265));
    assign chain[1266] = w1265;
    (* keep = 1, preserve = 1 *) wire w1266;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1266 (
        .dataa(chain[1266]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1266));
    assign chain[1267] = w1266;
    (* keep = 1, preserve = 1 *) wire w1267;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1267 (
        .dataa(chain[1267]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1267));
    assign chain[1268] = w1267;
    (* keep = 1, preserve = 1 *) wire w1268;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1268 (
        .dataa(chain[1268]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1268));
    assign chain[1269] = w1268;
    (* keep = 1, preserve = 1 *) wire w1269;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1269 (
        .dataa(chain[1269]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1269));
    assign chain[1270] = w1269;
    (* keep = 1, preserve = 1 *) wire w1270;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1270 (
        .dataa(chain[1270]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1270));
    assign chain[1271] = w1270;
    (* keep = 1, preserve = 1 *) wire w1271;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1271 (
        .dataa(chain[1271]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1271));
    assign chain[1272] = w1271;
    (* keep = 1, preserve = 1 *) wire w1272;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1272 (
        .dataa(chain[1272]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1272));
    assign chain[1273] = w1272;
    (* keep = 1, preserve = 1 *) wire w1273;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1273 (
        .dataa(chain[1273]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1273));
    assign chain[1274] = w1273;
    (* keep = 1, preserve = 1 *) wire w1274;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1274 (
        .dataa(chain[1274]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1274));
    assign chain[1275] = w1274;
    (* keep = 1, preserve = 1 *) wire w1275;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1275 (
        .dataa(chain[1275]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1275));
    assign chain[1276] = w1275;
    (* keep = 1, preserve = 1 *) wire w1276;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1276 (
        .dataa(chain[1276]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1276));
    assign chain[1277] = w1276;
    (* keep = 1, preserve = 1 *) wire w1277;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1277 (
        .dataa(chain[1277]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1277));
    assign chain[1278] = w1277;
    (* keep = 1, preserve = 1 *) wire w1278;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1278 (
        .dataa(chain[1278]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1278));
    assign chain[1279] = w1278;
    (* keep = 1, preserve = 1 *) wire w1279;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1279 (
        .dataa(chain[1279]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1279));
    assign chain[1280] = w1279;
    (* keep = 1, preserve = 1 *) wire w1280;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1280 (
        .dataa(chain[1280]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1280));
    assign chain[1281] = w1280;
    (* keep = 1, preserve = 1 *) wire w1281;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1281 (
        .dataa(chain[1281]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1281));
    assign chain[1282] = w1281;
    (* keep = 1, preserve = 1 *) wire w1282;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1282 (
        .dataa(chain[1282]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1282));
    assign chain[1283] = w1282;
    (* keep = 1, preserve = 1 *) wire w1283;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1283 (
        .dataa(chain[1283]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1283));
    assign chain[1284] = w1283;
    (* keep = 1, preserve = 1 *) wire w1284;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1284 (
        .dataa(chain[1284]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1284));
    assign chain[1285] = w1284;
    (* keep = 1, preserve = 1 *) wire w1285;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1285 (
        .dataa(chain[1285]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1285));
    assign chain[1286] = w1285;
    (* keep = 1, preserve = 1 *) wire w1286;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1286 (
        .dataa(chain[1286]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1286));
    assign chain[1287] = w1286;
    (* keep = 1, preserve = 1 *) wire w1287;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1287 (
        .dataa(chain[1287]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1287));
    assign chain[1288] = w1287;
    (* keep = 1, preserve = 1 *) wire w1288;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1288 (
        .dataa(chain[1288]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1288));
    assign chain[1289] = w1288;
    (* keep = 1, preserve = 1 *) wire w1289;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1289 (
        .dataa(chain[1289]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1289));
    assign chain[1290] = w1289;
    (* keep = 1, preserve = 1 *) wire w1290;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1290 (
        .dataa(chain[1290]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1290));
    assign chain[1291] = w1290;
    (* keep = 1, preserve = 1 *) wire w1291;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1291 (
        .dataa(chain[1291]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1291));
    assign chain[1292] = w1291;
    (* keep = 1, preserve = 1 *) wire w1292;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1292 (
        .dataa(chain[1292]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1292));
    assign chain[1293] = w1292;
    (* keep = 1, preserve = 1 *) wire w1293;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1293 (
        .dataa(chain[1293]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1293));
    assign chain[1294] = w1293;
    (* keep = 1, preserve = 1 *) wire w1294;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1294 (
        .dataa(chain[1294]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1294));
    assign chain[1295] = w1294;
    (* keep = 1, preserve = 1 *) wire w1295;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1295 (
        .dataa(chain[1295]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1295));
    assign chain[1296] = w1295;
    (* keep = 1, preserve = 1 *) wire w1296;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1296 (
        .dataa(chain[1296]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1296));
    assign chain[1297] = w1296;
    (* keep = 1, preserve = 1 *) wire w1297;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1297 (
        .dataa(chain[1297]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1297));
    assign chain[1298] = w1297;
    (* keep = 1, preserve = 1 *) wire w1298;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1298 (
        .dataa(chain[1298]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1298));
    assign chain[1299] = w1298;
    (* keep = 1, preserve = 1 *) wire w1299;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1299 (
        .dataa(chain[1299]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1299));
    assign chain[1300] = w1299;
    (* keep = 1, preserve = 1 *) wire w1300;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1300 (
        .dataa(chain[1300]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1300));
    assign chain[1301] = w1300;
    (* keep = 1, preserve = 1 *) wire w1301;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1301 (
        .dataa(chain[1301]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1301));
    assign chain[1302] = w1301;
    (* keep = 1, preserve = 1 *) wire w1302;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1302 (
        .dataa(chain[1302]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1302));
    assign chain[1303] = w1302;
    (* keep = 1, preserve = 1 *) wire w1303;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1303 (
        .dataa(chain[1303]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1303));
    assign chain[1304] = w1303;
    (* keep = 1, preserve = 1 *) wire w1304;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1304 (
        .dataa(chain[1304]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1304));
    assign chain[1305] = w1304;
    (* keep = 1, preserve = 1 *) wire w1305;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1305 (
        .dataa(chain[1305]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1305));
    assign chain[1306] = w1305;
    (* keep = 1, preserve = 1 *) wire w1306;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1306 (
        .dataa(chain[1306]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1306));
    assign chain[1307] = w1306;
    (* keep = 1, preserve = 1 *) wire w1307;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1307 (
        .dataa(chain[1307]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1307));
    assign chain[1308] = w1307;
    (* keep = 1, preserve = 1 *) wire w1308;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1308 (
        .dataa(chain[1308]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1308));
    assign chain[1309] = w1308;
    (* keep = 1, preserve = 1 *) wire w1309;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1309 (
        .dataa(chain[1309]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1309));
    assign chain[1310] = w1309;
    (* keep = 1, preserve = 1 *) wire w1310;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1310 (
        .dataa(chain[1310]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1310));
    assign chain[1311] = w1310;
    (* keep = 1, preserve = 1 *) wire w1311;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1311 (
        .dataa(chain[1311]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1311));
    assign chain[1312] = w1311;
    (* keep = 1, preserve = 1 *) wire w1312;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1312 (
        .dataa(chain[1312]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1312));
    assign chain[1313] = w1312;
    (* keep = 1, preserve = 1 *) wire w1313;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1313 (
        .dataa(chain[1313]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1313));
    assign chain[1314] = w1313;
    (* keep = 1, preserve = 1 *) wire w1314;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1314 (
        .dataa(chain[1314]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1314));
    assign chain[1315] = w1314;
    (* keep = 1, preserve = 1 *) wire w1315;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1315 (
        .dataa(chain[1315]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1315));
    assign chain[1316] = w1315;
    (* keep = 1, preserve = 1 *) wire w1316;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1316 (
        .dataa(chain[1316]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1316));
    assign chain[1317] = w1316;
    (* keep = 1, preserve = 1 *) wire w1317;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1317 (
        .dataa(chain[1317]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1317));
    assign chain[1318] = w1317;
    (* keep = 1, preserve = 1 *) wire w1318;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1318 (
        .dataa(chain[1318]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1318));
    assign chain[1319] = w1318;
    (* keep = 1, preserve = 1 *) wire w1319;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1319 (
        .dataa(chain[1319]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1319));
    assign chain[1320] = w1319;
    (* keep = 1, preserve = 1 *) wire w1320;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1320 (
        .dataa(chain[1320]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1320));
    assign chain[1321] = w1320;
    (* keep = 1, preserve = 1 *) wire w1321;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1321 (
        .dataa(chain[1321]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1321));
    assign chain[1322] = w1321;
    (* keep = 1, preserve = 1 *) wire w1322;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1322 (
        .dataa(chain[1322]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1322));
    assign chain[1323] = w1322;
    (* keep = 1, preserve = 1 *) wire w1323;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1323 (
        .dataa(chain[1323]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1323));
    assign chain[1324] = w1323;
    (* keep = 1, preserve = 1 *) wire w1324;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1324 (
        .dataa(chain[1324]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1324));
    assign chain[1325] = w1324;
    (* keep = 1, preserve = 1 *) wire w1325;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1325 (
        .dataa(chain[1325]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1325));
    assign chain[1326] = w1325;
    (* keep = 1, preserve = 1 *) wire w1326;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1326 (
        .dataa(chain[1326]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1326));
    assign chain[1327] = w1326;
    (* keep = 1, preserve = 1 *) wire w1327;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1327 (
        .dataa(chain[1327]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1327));
    assign chain[1328] = w1327;
    (* keep = 1, preserve = 1 *) wire w1328;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1328 (
        .dataa(chain[1328]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1328));
    assign chain[1329] = w1328;
    (* keep = 1, preserve = 1 *) wire w1329;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1329 (
        .dataa(chain[1329]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1329));
    assign chain[1330] = w1329;
    (* keep = 1, preserve = 1 *) wire w1330;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1330 (
        .dataa(chain[1330]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1330));
    assign chain[1331] = w1330;
    (* keep = 1, preserve = 1 *) wire w1331;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1331 (
        .dataa(chain[1331]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1331));
    assign chain[1332] = w1331;
    (* keep = 1, preserve = 1 *) wire w1332;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1332 (
        .dataa(chain[1332]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1332));
    assign chain[1333] = w1332;
    (* keep = 1, preserve = 1 *) wire w1333;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1333 (
        .dataa(chain[1333]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1333));
    assign chain[1334] = w1333;
    (* keep = 1, preserve = 1 *) wire w1334;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1334 (
        .dataa(chain[1334]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1334));
    assign chain[1335] = w1334;
    (* keep = 1, preserve = 1 *) wire w1335;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1335 (
        .dataa(chain[1335]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1335));
    assign chain[1336] = w1335;
    (* keep = 1, preserve = 1 *) wire w1336;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1336 (
        .dataa(chain[1336]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1336));
    assign chain[1337] = w1336;
    (* keep = 1, preserve = 1 *) wire w1337;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1337 (
        .dataa(chain[1337]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1337));
    assign chain[1338] = w1337;
    (* keep = 1, preserve = 1 *) wire w1338;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1338 (
        .dataa(chain[1338]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1338));
    assign chain[1339] = w1338;
    (* keep = 1, preserve = 1 *) wire w1339;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1339 (
        .dataa(chain[1339]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1339));
    assign chain[1340] = w1339;
    (* keep = 1, preserve = 1 *) wire w1340;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1340 (
        .dataa(chain[1340]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1340));
    assign chain[1341] = w1340;
    (* keep = 1, preserve = 1 *) wire w1341;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1341 (
        .dataa(chain[1341]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1341));
    assign chain[1342] = w1341;
    (* keep = 1, preserve = 1 *) wire w1342;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1342 (
        .dataa(chain[1342]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1342));
    assign chain[1343] = w1342;
    (* keep = 1, preserve = 1 *) wire w1343;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1343 (
        .dataa(chain[1343]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1343));
    assign chain[1344] = w1343;
    (* keep = 1, preserve = 1 *) wire w1344;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1344 (
        .dataa(chain[1344]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1344));
    assign chain[1345] = w1344;
    (* keep = 1, preserve = 1 *) wire w1345;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1345 (
        .dataa(chain[1345]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1345));
    assign chain[1346] = w1345;
    (* keep = 1, preserve = 1 *) wire w1346;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1346 (
        .dataa(chain[1346]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1346));
    assign chain[1347] = w1346;
    (* keep = 1, preserve = 1 *) wire w1347;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1347 (
        .dataa(chain[1347]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1347));
    assign chain[1348] = w1347;
    (* keep = 1, preserve = 1 *) wire w1348;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1348 (
        .dataa(chain[1348]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1348));
    assign chain[1349] = w1348;
    (* keep = 1, preserve = 1 *) wire w1349;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1349 (
        .dataa(chain[1349]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1349));
    assign chain[1350] = w1349;
    (* keep = 1, preserve = 1 *) wire w1350;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1350 (
        .dataa(chain[1350]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1350));
    assign chain[1351] = w1350;
    (* keep = 1, preserve = 1 *) wire w1351;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1351 (
        .dataa(chain[1351]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1351));
    assign chain[1352] = w1351;
    (* keep = 1, preserve = 1 *) wire w1352;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1352 (
        .dataa(chain[1352]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1352));
    assign chain[1353] = w1352;
    (* keep = 1, preserve = 1 *) wire w1353;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1353 (
        .dataa(chain[1353]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1353));
    assign chain[1354] = w1353;
    (* keep = 1, preserve = 1 *) wire w1354;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1354 (
        .dataa(chain[1354]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1354));
    assign chain[1355] = w1354;
    (* keep = 1, preserve = 1 *) wire w1355;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1355 (
        .dataa(chain[1355]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1355));
    assign chain[1356] = w1355;
    (* keep = 1, preserve = 1 *) wire w1356;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1356 (
        .dataa(chain[1356]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1356));
    assign chain[1357] = w1356;
    (* keep = 1, preserve = 1 *) wire w1357;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1357 (
        .dataa(chain[1357]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1357));
    assign chain[1358] = w1357;
    (* keep = 1, preserve = 1 *) wire w1358;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1358 (
        .dataa(chain[1358]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1358));
    assign chain[1359] = w1358;
    (* keep = 1, preserve = 1 *) wire w1359;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1359 (
        .dataa(chain[1359]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1359));
    assign chain[1360] = w1359;
    (* keep = 1, preserve = 1 *) wire w1360;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1360 (
        .dataa(chain[1360]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1360));
    assign chain[1361] = w1360;
    (* keep = 1, preserve = 1 *) wire w1361;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1361 (
        .dataa(chain[1361]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1361));
    assign chain[1362] = w1361;
    (* keep = 1, preserve = 1 *) wire w1362;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1362 (
        .dataa(chain[1362]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1362));
    assign chain[1363] = w1362;
    (* keep = 1, preserve = 1 *) wire w1363;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1363 (
        .dataa(chain[1363]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1363));
    assign chain[1364] = w1363;
    (* keep = 1, preserve = 1 *) wire w1364;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1364 (
        .dataa(chain[1364]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1364));
    assign chain[1365] = w1364;
    (* keep = 1, preserve = 1 *) wire w1365;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1365 (
        .dataa(chain[1365]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1365));
    assign chain[1366] = w1365;
    (* keep = 1, preserve = 1 *) wire w1366;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1366 (
        .dataa(chain[1366]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1366));
    assign chain[1367] = w1366;
    (* keep = 1, preserve = 1 *) wire w1367;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1367 (
        .dataa(chain[1367]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1367));
    assign chain[1368] = w1367;
    (* keep = 1, preserve = 1 *) wire w1368;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1368 (
        .dataa(chain[1368]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1368));
    assign chain[1369] = w1368;
    (* keep = 1, preserve = 1 *) wire w1369;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1369 (
        .dataa(chain[1369]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1369));
    assign chain[1370] = w1369;
    (* keep = 1, preserve = 1 *) wire w1370;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1370 (
        .dataa(chain[1370]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1370));
    assign chain[1371] = w1370;
    (* keep = 1, preserve = 1 *) wire w1371;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1371 (
        .dataa(chain[1371]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1371));
    assign chain[1372] = w1371;
    (* keep = 1, preserve = 1 *) wire w1372;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1372 (
        .dataa(chain[1372]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1372));
    assign chain[1373] = w1372;
    (* keep = 1, preserve = 1 *) wire w1373;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1373 (
        .dataa(chain[1373]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1373));
    assign chain[1374] = w1373;
    (* keep = 1, preserve = 1 *) wire w1374;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1374 (
        .dataa(chain[1374]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1374));
    assign chain[1375] = w1374;
    (* keep = 1, preserve = 1 *) wire w1375;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1375 (
        .dataa(chain[1375]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1375));
    assign chain[1376] = w1375;
    (* keep = 1, preserve = 1 *) wire w1376;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1376 (
        .dataa(chain[1376]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1376));
    assign chain[1377] = w1376;
    (* keep = 1, preserve = 1 *) wire w1377;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1377 (
        .dataa(chain[1377]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1377));
    assign chain[1378] = w1377;
    (* keep = 1, preserve = 1 *) wire w1378;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1378 (
        .dataa(chain[1378]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1378));
    assign chain[1379] = w1378;
    (* keep = 1, preserve = 1 *) wire w1379;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1379 (
        .dataa(chain[1379]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1379));
    assign chain[1380] = w1379;
    (* keep = 1, preserve = 1 *) wire w1380;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1380 (
        .dataa(chain[1380]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1380));
    assign chain[1381] = w1380;
    (* keep = 1, preserve = 1 *) wire w1381;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1381 (
        .dataa(chain[1381]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1381));
    assign chain[1382] = w1381;
    (* keep = 1, preserve = 1 *) wire w1382;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1382 (
        .dataa(chain[1382]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1382));
    assign chain[1383] = w1382;
    (* keep = 1, preserve = 1 *) wire w1383;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1383 (
        .dataa(chain[1383]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1383));
    assign chain[1384] = w1383;
    (* keep = 1, preserve = 1 *) wire w1384;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1384 (
        .dataa(chain[1384]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1384));
    assign chain[1385] = w1384;
    (* keep = 1, preserve = 1 *) wire w1385;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1385 (
        .dataa(chain[1385]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1385));
    assign chain[1386] = w1385;
    (* keep = 1, preserve = 1 *) wire w1386;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1386 (
        .dataa(chain[1386]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1386));
    assign chain[1387] = w1386;
    (* keep = 1, preserve = 1 *) wire w1387;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1387 (
        .dataa(chain[1387]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1387));
    assign chain[1388] = w1387;
    (* keep = 1, preserve = 1 *) wire w1388;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1388 (
        .dataa(chain[1388]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1388));
    assign chain[1389] = w1388;
    (* keep = 1, preserve = 1 *) wire w1389;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1389 (
        .dataa(chain[1389]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1389));
    assign chain[1390] = w1389;
    (* keep = 1, preserve = 1 *) wire w1390;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1390 (
        .dataa(chain[1390]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1390));
    assign chain[1391] = w1390;
    (* keep = 1, preserve = 1 *) wire w1391;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1391 (
        .dataa(chain[1391]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1391));
    assign chain[1392] = w1391;
    (* keep = 1, preserve = 1 *) wire w1392;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1392 (
        .dataa(chain[1392]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1392));
    assign chain[1393] = w1392;
    (* keep = 1, preserve = 1 *) wire w1393;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1393 (
        .dataa(chain[1393]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1393));
    assign chain[1394] = w1393;
    (* keep = 1, preserve = 1 *) wire w1394;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1394 (
        .dataa(chain[1394]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1394));
    assign chain[1395] = w1394;
    (* keep = 1, preserve = 1 *) wire w1395;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1395 (
        .dataa(chain[1395]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1395));
    assign chain[1396] = w1395;
    (* keep = 1, preserve = 1 *) wire w1396;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1396 (
        .dataa(chain[1396]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1396));
    assign chain[1397] = w1396;
    (* keep = 1, preserve = 1 *) wire w1397;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1397 (
        .dataa(chain[1397]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1397));
    assign chain[1398] = w1397;
    (* keep = 1, preserve = 1 *) wire w1398;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1398 (
        .dataa(chain[1398]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1398));
    assign chain[1399] = w1398;
    (* keep = 1, preserve = 1 *) wire w1399;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1399 (
        .dataa(chain[1399]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1399));
    assign chain[1400] = w1399;
    (* keep = 1, preserve = 1 *) wire w1400;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1400 (
        .dataa(chain[1400]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1400));
    assign chain[1401] = w1400;
    (* keep = 1, preserve = 1 *) wire w1401;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1401 (
        .dataa(chain[1401]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1401));
    assign chain[1402] = w1401;
    (* keep = 1, preserve = 1 *) wire w1402;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1402 (
        .dataa(chain[1402]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1402));
    assign chain[1403] = w1402;
    (* keep = 1, preserve = 1 *) wire w1403;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1403 (
        .dataa(chain[1403]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1403));
    assign chain[1404] = w1403;
    (* keep = 1, preserve = 1 *) wire w1404;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1404 (
        .dataa(chain[1404]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1404));
    assign chain[1405] = w1404;
    (* keep = 1, preserve = 1 *) wire w1405;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1405 (
        .dataa(chain[1405]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1405));
    assign chain[1406] = w1405;
    (* keep = 1, preserve = 1 *) wire w1406;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1406 (
        .dataa(chain[1406]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1406));
    assign chain[1407] = w1406;
    (* keep = 1, preserve = 1 *) wire w1407;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1407 (
        .dataa(chain[1407]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1407));
    assign chain[1408] = w1407;
    (* keep = 1, preserve = 1 *) wire w1408;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1408 (
        .dataa(chain[1408]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1408));
    assign chain[1409] = w1408;
    (* keep = 1, preserve = 1 *) wire w1409;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1409 (
        .dataa(chain[1409]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1409));
    assign chain[1410] = w1409;
    (* keep = 1, preserve = 1 *) wire w1410;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1410 (
        .dataa(chain[1410]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1410));
    assign chain[1411] = w1410;
    (* keep = 1, preserve = 1 *) wire w1411;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1411 (
        .dataa(chain[1411]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1411));
    assign chain[1412] = w1411;
    (* keep = 1, preserve = 1 *) wire w1412;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1412 (
        .dataa(chain[1412]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1412));
    assign chain[1413] = w1412;
    (* keep = 1, preserve = 1 *) wire w1413;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1413 (
        .dataa(chain[1413]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1413));
    assign chain[1414] = w1413;
    (* keep = 1, preserve = 1 *) wire w1414;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1414 (
        .dataa(chain[1414]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1414));
    assign chain[1415] = w1414;
    (* keep = 1, preserve = 1 *) wire w1415;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1415 (
        .dataa(chain[1415]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1415));
    assign chain[1416] = w1415;
    (* keep = 1, preserve = 1 *) wire w1416;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1416 (
        .dataa(chain[1416]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1416));
    assign chain[1417] = w1416;
    (* keep = 1, preserve = 1 *) wire w1417;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1417 (
        .dataa(chain[1417]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1417));
    assign chain[1418] = w1417;
    (* keep = 1, preserve = 1 *) wire w1418;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1418 (
        .dataa(chain[1418]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1418));
    assign chain[1419] = w1418;
    (* keep = 1, preserve = 1 *) wire w1419;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1419 (
        .dataa(chain[1419]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1419));
    assign chain[1420] = w1419;
    (* keep = 1, preserve = 1 *) wire w1420;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1420 (
        .dataa(chain[1420]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1420));
    assign chain[1421] = w1420;
    (* keep = 1, preserve = 1 *) wire w1421;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1421 (
        .dataa(chain[1421]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1421));
    assign chain[1422] = w1421;
    (* keep = 1, preserve = 1 *) wire w1422;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1422 (
        .dataa(chain[1422]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1422));
    assign chain[1423] = w1422;
    (* keep = 1, preserve = 1 *) wire w1423;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1423 (
        .dataa(chain[1423]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1423));
    assign chain[1424] = w1423;
    (* keep = 1, preserve = 1 *) wire w1424;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1424 (
        .dataa(chain[1424]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1424));
    assign chain[1425] = w1424;
    (* keep = 1, preserve = 1 *) wire w1425;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1425 (
        .dataa(chain[1425]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1425));
    assign chain[1426] = w1425;
    (* keep = 1, preserve = 1 *) wire w1426;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1426 (
        .dataa(chain[1426]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1426));
    assign chain[1427] = w1426;
    (* keep = 1, preserve = 1 *) wire w1427;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1427 (
        .dataa(chain[1427]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1427));
    assign chain[1428] = w1427;
    (* keep = 1, preserve = 1 *) wire w1428;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1428 (
        .dataa(chain[1428]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1428));
    assign chain[1429] = w1428;
    (* keep = 1, preserve = 1 *) wire w1429;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1429 (
        .dataa(chain[1429]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1429));
    assign chain[1430] = w1429;
    (* keep = 1, preserve = 1 *) wire w1430;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1430 (
        .dataa(chain[1430]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1430));
    assign chain[1431] = w1430;
    (* keep = 1, preserve = 1 *) wire w1431;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1431 (
        .dataa(chain[1431]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1431));
    assign chain[1432] = w1431;
    (* keep = 1, preserve = 1 *) wire w1432;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1432 (
        .dataa(chain[1432]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1432));
    assign chain[1433] = w1432;
    (* keep = 1, preserve = 1 *) wire w1433;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1433 (
        .dataa(chain[1433]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1433));
    assign chain[1434] = w1433;
    (* keep = 1, preserve = 1 *) wire w1434;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1434 (
        .dataa(chain[1434]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1434));
    assign chain[1435] = w1434;
    (* keep = 1, preserve = 1 *) wire w1435;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1435 (
        .dataa(chain[1435]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1435));
    assign chain[1436] = w1435;
    (* keep = 1, preserve = 1 *) wire w1436;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1436 (
        .dataa(chain[1436]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1436));
    assign chain[1437] = w1436;
    (* keep = 1, preserve = 1 *) wire w1437;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1437 (
        .dataa(chain[1437]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1437));
    assign chain[1438] = w1437;
    (* keep = 1, preserve = 1 *) wire w1438;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1438 (
        .dataa(chain[1438]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1438));
    assign chain[1439] = w1438;
    (* keep = 1, preserve = 1 *) wire w1439;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1439 (
        .dataa(chain[1439]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1439));
    assign chain[1440] = w1439;
    (* keep = 1, preserve = 1 *) wire w1440;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1440 (
        .dataa(chain[1440]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1440));
    assign chain[1441] = w1440;
    (* keep = 1, preserve = 1 *) wire w1441;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1441 (
        .dataa(chain[1441]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1441));
    assign chain[1442] = w1441;
    (* keep = 1, preserve = 1 *) wire w1442;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1442 (
        .dataa(chain[1442]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1442));
    assign chain[1443] = w1442;
    (* keep = 1, preserve = 1 *) wire w1443;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1443 (
        .dataa(chain[1443]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1443));
    assign chain[1444] = w1443;
    (* keep = 1, preserve = 1 *) wire w1444;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1444 (
        .dataa(chain[1444]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1444));
    assign chain[1445] = w1444;
    (* keep = 1, preserve = 1 *) wire w1445;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1445 (
        .dataa(chain[1445]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1445));
    assign chain[1446] = w1445;
    (* keep = 1, preserve = 1 *) wire w1446;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1446 (
        .dataa(chain[1446]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1446));
    assign chain[1447] = w1446;
    (* keep = 1, preserve = 1 *) wire w1447;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1447 (
        .dataa(chain[1447]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1447));
    assign chain[1448] = w1447;
    (* keep = 1, preserve = 1 *) wire w1448;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1448 (
        .dataa(chain[1448]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1448));
    assign chain[1449] = w1448;
    (* keep = 1, preserve = 1 *) wire w1449;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1449 (
        .dataa(chain[1449]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1449));
    assign chain[1450] = w1449;
    (* keep = 1, preserve = 1 *) wire w1450;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1450 (
        .dataa(chain[1450]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1450));
    assign chain[1451] = w1450;
    (* keep = 1, preserve = 1 *) wire w1451;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1451 (
        .dataa(chain[1451]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1451));
    assign chain[1452] = w1451;
    (* keep = 1, preserve = 1 *) wire w1452;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1452 (
        .dataa(chain[1452]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1452));
    assign chain[1453] = w1452;
    (* keep = 1, preserve = 1 *) wire w1453;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1453 (
        .dataa(chain[1453]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1453));
    assign chain[1454] = w1453;
    (* keep = 1, preserve = 1 *) wire w1454;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1454 (
        .dataa(chain[1454]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1454));
    assign chain[1455] = w1454;
    (* keep = 1, preserve = 1 *) wire w1455;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1455 (
        .dataa(chain[1455]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1455));
    assign chain[1456] = w1455;
    (* keep = 1, preserve = 1 *) wire w1456;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1456 (
        .dataa(chain[1456]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1456));
    assign chain[1457] = w1456;
    (* keep = 1, preserve = 1 *) wire w1457;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1457 (
        .dataa(chain[1457]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1457));
    assign chain[1458] = w1457;
    (* keep = 1, preserve = 1 *) wire w1458;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1458 (
        .dataa(chain[1458]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1458));
    assign chain[1459] = w1458;
    (* keep = 1, preserve = 1 *) wire w1459;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1459 (
        .dataa(chain[1459]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1459));
    assign chain[1460] = w1459;
    (* keep = 1, preserve = 1 *) wire w1460;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1460 (
        .dataa(chain[1460]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1460));
    assign chain[1461] = w1460;
    (* keep = 1, preserve = 1 *) wire w1461;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1461 (
        .dataa(chain[1461]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1461));
    assign chain[1462] = w1461;
    (* keep = 1, preserve = 1 *) wire w1462;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1462 (
        .dataa(chain[1462]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1462));
    assign chain[1463] = w1462;
    (* keep = 1, preserve = 1 *) wire w1463;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1463 (
        .dataa(chain[1463]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1463));
    assign chain[1464] = w1463;
    (* keep = 1, preserve = 1 *) wire w1464;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1464 (
        .dataa(chain[1464]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1464));
    assign chain[1465] = w1464;
    (* keep = 1, preserve = 1 *) wire w1465;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1465 (
        .dataa(chain[1465]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1465));
    assign chain[1466] = w1465;
    (* keep = 1, preserve = 1 *) wire w1466;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1466 (
        .dataa(chain[1466]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1466));
    assign chain[1467] = w1466;
    (* keep = 1, preserve = 1 *) wire w1467;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1467 (
        .dataa(chain[1467]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1467));
    assign chain[1468] = w1467;
    (* keep = 1, preserve = 1 *) wire w1468;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1468 (
        .dataa(chain[1468]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1468));
    assign chain[1469] = w1468;
    (* keep = 1, preserve = 1 *) wire w1469;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1469 (
        .dataa(chain[1469]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1469));
    assign chain[1470] = w1469;
    (* keep = 1, preserve = 1 *) wire w1470;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1470 (
        .dataa(chain[1470]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1470));
    assign chain[1471] = w1470;
    (* keep = 1, preserve = 1 *) wire w1471;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1471 (
        .dataa(chain[1471]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1471));
    assign chain[1472] = w1471;
    (* keep = 1, preserve = 1 *) wire w1472;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1472 (
        .dataa(chain[1472]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1472));
    assign chain[1473] = w1472;
    (* keep = 1, preserve = 1 *) wire w1473;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1473 (
        .dataa(chain[1473]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1473));
    assign chain[1474] = w1473;
    (* keep = 1, preserve = 1 *) wire w1474;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1474 (
        .dataa(chain[1474]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1474));
    assign chain[1475] = w1474;
    (* keep = 1, preserve = 1 *) wire w1475;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1475 (
        .dataa(chain[1475]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1475));
    assign chain[1476] = w1475;
    (* keep = 1, preserve = 1 *) wire w1476;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1476 (
        .dataa(chain[1476]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1476));
    assign chain[1477] = w1476;
    (* keep = 1, preserve = 1 *) wire w1477;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1477 (
        .dataa(chain[1477]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1477));
    assign chain[1478] = w1477;
    (* keep = 1, preserve = 1 *) wire w1478;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1478 (
        .dataa(chain[1478]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1478));
    assign chain[1479] = w1478;
    (* keep = 1, preserve = 1 *) wire w1479;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1479 (
        .dataa(chain[1479]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1479));
    assign chain[1480] = w1479;
    (* keep = 1, preserve = 1 *) wire w1480;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1480 (
        .dataa(chain[1480]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1480));
    assign chain[1481] = w1480;
    (* keep = 1, preserve = 1 *) wire w1481;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1481 (
        .dataa(chain[1481]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1481));
    assign chain[1482] = w1481;
    (* keep = 1, preserve = 1 *) wire w1482;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1482 (
        .dataa(chain[1482]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1482));
    assign chain[1483] = w1482;
    (* keep = 1, preserve = 1 *) wire w1483;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1483 (
        .dataa(chain[1483]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1483));
    assign chain[1484] = w1483;
    (* keep = 1, preserve = 1 *) wire w1484;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1484 (
        .dataa(chain[1484]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1484));
    assign chain[1485] = w1484;
    (* keep = 1, preserve = 1 *) wire w1485;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1485 (
        .dataa(chain[1485]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1485));
    assign chain[1486] = w1485;
    (* keep = 1, preserve = 1 *) wire w1486;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1486 (
        .dataa(chain[1486]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1486));
    assign chain[1487] = w1486;
    (* keep = 1, preserve = 1 *) wire w1487;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1487 (
        .dataa(chain[1487]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1487));
    assign chain[1488] = w1487;
    (* keep = 1, preserve = 1 *) wire w1488;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1488 (
        .dataa(chain[1488]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1488));
    assign chain[1489] = w1488;
    (* keep = 1, preserve = 1 *) wire w1489;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1489 (
        .dataa(chain[1489]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1489));
    assign chain[1490] = w1489;
    (* keep = 1, preserve = 1 *) wire w1490;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1490 (
        .dataa(chain[1490]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1490));
    assign chain[1491] = w1490;
    (* keep = 1, preserve = 1 *) wire w1491;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1491 (
        .dataa(chain[1491]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1491));
    assign chain[1492] = w1491;
    (* keep = 1, preserve = 1 *) wire w1492;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1492 (
        .dataa(chain[1492]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1492));
    assign chain[1493] = w1492;
    (* keep = 1, preserve = 1 *) wire w1493;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1493 (
        .dataa(chain[1493]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1493));
    assign chain[1494] = w1493;
    (* keep = 1, preserve = 1 *) wire w1494;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1494 (
        .dataa(chain[1494]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1494));
    assign chain[1495] = w1494;
    (* keep = 1, preserve = 1 *) wire w1495;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1495 (
        .dataa(chain[1495]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1495));
    assign chain[1496] = w1495;
    (* keep = 1, preserve = 1 *) wire w1496;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1496 (
        .dataa(chain[1496]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1496));
    assign chain[1497] = w1496;
    (* keep = 1, preserve = 1 *) wire w1497;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1497 (
        .dataa(chain[1497]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1497));
    assign chain[1498] = w1497;
    (* keep = 1, preserve = 1 *) wire w1498;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1498 (
        .dataa(chain[1498]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1498));
    assign chain[1499] = w1498;
    (* keep = 1, preserve = 1 *) wire w1499;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1499 (
        .dataa(chain[1499]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1499));
    assign chain[1500] = w1499;
    (* keep = 1, preserve = 1 *) wire w1500;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1500 (
        .dataa(chain[1500]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1500));
    assign chain[1501] = w1500;
    (* keep = 1, preserve = 1 *) wire w1501;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1501 (
        .dataa(chain[1501]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1501));
    assign chain[1502] = w1501;
    (* keep = 1, preserve = 1 *) wire w1502;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1502 (
        .dataa(chain[1502]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1502));
    assign chain[1503] = w1502;
    (* keep = 1, preserve = 1 *) wire w1503;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1503 (
        .dataa(chain[1503]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1503));
    assign chain[1504] = w1503;
    (* keep = 1, preserve = 1 *) wire w1504;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1504 (
        .dataa(chain[1504]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1504));
    assign chain[1505] = w1504;
    (* keep = 1, preserve = 1 *) wire w1505;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1505 (
        .dataa(chain[1505]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1505));
    assign chain[1506] = w1505;
    (* keep = 1, preserve = 1 *) wire w1506;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1506 (
        .dataa(chain[1506]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1506));
    assign chain[1507] = w1506;
    (* keep = 1, preserve = 1 *) wire w1507;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1507 (
        .dataa(chain[1507]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1507));
    assign chain[1508] = w1507;
    (* keep = 1, preserve = 1 *) wire w1508;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1508 (
        .dataa(chain[1508]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1508));
    assign chain[1509] = w1508;
    (* keep = 1, preserve = 1 *) wire w1509;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1509 (
        .dataa(chain[1509]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1509));
    assign chain[1510] = w1509;
    (* keep = 1, preserve = 1 *) wire w1510;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1510 (
        .dataa(chain[1510]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1510));
    assign chain[1511] = w1510;
    (* keep = 1, preserve = 1 *) wire w1511;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1511 (
        .dataa(chain[1511]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1511));
    assign chain[1512] = w1511;
    (* keep = 1, preserve = 1 *) wire w1512;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1512 (
        .dataa(chain[1512]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1512));
    assign chain[1513] = w1512;
    (* keep = 1, preserve = 1 *) wire w1513;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1513 (
        .dataa(chain[1513]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1513));
    assign chain[1514] = w1513;
    (* keep = 1, preserve = 1 *) wire w1514;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1514 (
        .dataa(chain[1514]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1514));
    assign chain[1515] = w1514;
    (* keep = 1, preserve = 1 *) wire w1515;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1515 (
        .dataa(chain[1515]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1515));
    assign chain[1516] = w1515;
    (* keep = 1, preserve = 1 *) wire w1516;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1516 (
        .dataa(chain[1516]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1516));
    assign chain[1517] = w1516;
    (* keep = 1, preserve = 1 *) wire w1517;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1517 (
        .dataa(chain[1517]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1517));
    assign chain[1518] = w1517;
    (* keep = 1, preserve = 1 *) wire w1518;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1518 (
        .dataa(chain[1518]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1518));
    assign chain[1519] = w1518;
    (* keep = 1, preserve = 1 *) wire w1519;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1519 (
        .dataa(chain[1519]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1519));
    assign chain[1520] = w1519;
    (* keep = 1, preserve = 1 *) wire w1520;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1520 (
        .dataa(chain[1520]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1520));
    assign chain[1521] = w1520;
    (* keep = 1, preserve = 1 *) wire w1521;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1521 (
        .dataa(chain[1521]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1521));
    assign chain[1522] = w1521;
    (* keep = 1, preserve = 1 *) wire w1522;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1522 (
        .dataa(chain[1522]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1522));
    assign chain[1523] = w1522;
    (* keep = 1, preserve = 1 *) wire w1523;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1523 (
        .dataa(chain[1523]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1523));
    assign chain[1524] = w1523;
    (* keep = 1, preserve = 1 *) wire w1524;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1524 (
        .dataa(chain[1524]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1524));
    assign chain[1525] = w1524;
    (* keep = 1, preserve = 1 *) wire w1525;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1525 (
        .dataa(chain[1525]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1525));
    assign chain[1526] = w1525;
    (* keep = 1, preserve = 1 *) wire w1526;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1526 (
        .dataa(chain[1526]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1526));
    assign chain[1527] = w1526;
    (* keep = 1, preserve = 1 *) wire w1527;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1527 (
        .dataa(chain[1527]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1527));
    assign chain[1528] = w1527;
    (* keep = 1, preserve = 1 *) wire w1528;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1528 (
        .dataa(chain[1528]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1528));
    assign chain[1529] = w1528;
    (* keep = 1, preserve = 1 *) wire w1529;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1529 (
        .dataa(chain[1529]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1529));
    assign chain[1530] = w1529;
    (* keep = 1, preserve = 1 *) wire w1530;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1530 (
        .dataa(chain[1530]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1530));
    assign chain[1531] = w1530;
    (* keep = 1, preserve = 1 *) wire w1531;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1531 (
        .dataa(chain[1531]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1531));
    assign chain[1532] = w1531;
    (* keep = 1, preserve = 1 *) wire w1532;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1532 (
        .dataa(chain[1532]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1532));
    assign chain[1533] = w1532;
    (* keep = 1, preserve = 1 *) wire w1533;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1533 (
        .dataa(chain[1533]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1533));
    assign chain[1534] = w1533;
    (* keep = 1, preserve = 1 *) wire w1534;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1534 (
        .dataa(chain[1534]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1534));
    assign chain[1535] = w1534;
    (* keep = 1, preserve = 1 *) wire w1535;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1535 (
        .dataa(chain[1535]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1535));
    assign chain[1536] = w1535;
    (* keep = 1, preserve = 1 *) wire w1536;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1536 (
        .dataa(chain[1536]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1536));
    assign chain[1537] = w1536;
    (* keep = 1, preserve = 1 *) wire w1537;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1537 (
        .dataa(chain[1537]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1537));
    assign chain[1538] = w1537;
    (* keep = 1, preserve = 1 *) wire w1538;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1538 (
        .dataa(chain[1538]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1538));
    assign chain[1539] = w1538;
    (* keep = 1, preserve = 1 *) wire w1539;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1539 (
        .dataa(chain[1539]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1539));
    assign chain[1540] = w1539;
    (* keep = 1, preserve = 1 *) wire w1540;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1540 (
        .dataa(chain[1540]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1540));
    assign chain[1541] = w1540;
    (* keep = 1, preserve = 1 *) wire w1541;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1541 (
        .dataa(chain[1541]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1541));
    assign chain[1542] = w1541;
    (* keep = 1, preserve = 1 *) wire w1542;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1542 (
        .dataa(chain[1542]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1542));
    assign chain[1543] = w1542;
    (* keep = 1, preserve = 1 *) wire w1543;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1543 (
        .dataa(chain[1543]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1543));
    assign chain[1544] = w1543;
    (* keep = 1, preserve = 1 *) wire w1544;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1544 (
        .dataa(chain[1544]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1544));
    assign chain[1545] = w1544;
    (* keep = 1, preserve = 1 *) wire w1545;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1545 (
        .dataa(chain[1545]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1545));
    assign chain[1546] = w1545;
    (* keep = 1, preserve = 1 *) wire w1546;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1546 (
        .dataa(chain[1546]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1546));
    assign chain[1547] = w1546;
    (* keep = 1, preserve = 1 *) wire w1547;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1547 (
        .dataa(chain[1547]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1547));
    assign chain[1548] = w1547;
    (* keep = 1, preserve = 1 *) wire w1548;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1548 (
        .dataa(chain[1548]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1548));
    assign chain[1549] = w1548;
    (* keep = 1, preserve = 1 *) wire w1549;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1549 (
        .dataa(chain[1549]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1549));
    assign chain[1550] = w1549;
    (* keep = 1, preserve = 1 *) wire w1550;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1550 (
        .dataa(chain[1550]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1550));
    assign chain[1551] = w1550;
    (* keep = 1, preserve = 1 *) wire w1551;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1551 (
        .dataa(chain[1551]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1551));
    assign chain[1552] = w1551;
    (* keep = 1, preserve = 1 *) wire w1552;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1552 (
        .dataa(chain[1552]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1552));
    assign chain[1553] = w1552;
    (* keep = 1, preserve = 1 *) wire w1553;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1553 (
        .dataa(chain[1553]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1553));
    assign chain[1554] = w1553;
    (* keep = 1, preserve = 1 *) wire w1554;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1554 (
        .dataa(chain[1554]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1554));
    assign chain[1555] = w1554;
    (* keep = 1, preserve = 1 *) wire w1555;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1555 (
        .dataa(chain[1555]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1555));
    assign chain[1556] = w1555;
    (* keep = 1, preserve = 1 *) wire w1556;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1556 (
        .dataa(chain[1556]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1556));
    assign chain[1557] = w1556;
    (* keep = 1, preserve = 1 *) wire w1557;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1557 (
        .dataa(chain[1557]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1557));
    assign chain[1558] = w1557;
    (* keep = 1, preserve = 1 *) wire w1558;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1558 (
        .dataa(chain[1558]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1558));
    assign chain[1559] = w1558;
    (* keep = 1, preserve = 1 *) wire w1559;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1559 (
        .dataa(chain[1559]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1559));
    assign chain[1560] = w1559;
    (* keep = 1, preserve = 1 *) wire w1560;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1560 (
        .dataa(chain[1560]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1560));
    assign chain[1561] = w1560;
    (* keep = 1, preserve = 1 *) wire w1561;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1561 (
        .dataa(chain[1561]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1561));
    assign chain[1562] = w1561;
    (* keep = 1, preserve = 1 *) wire w1562;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1562 (
        .dataa(chain[1562]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1562));
    assign chain[1563] = w1562;
    (* keep = 1, preserve = 1 *) wire w1563;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1563 (
        .dataa(chain[1563]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1563));
    assign chain[1564] = w1563;
    (* keep = 1, preserve = 1 *) wire w1564;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1564 (
        .dataa(chain[1564]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1564));
    assign chain[1565] = w1564;
    (* keep = 1, preserve = 1 *) wire w1565;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1565 (
        .dataa(chain[1565]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1565));
    assign chain[1566] = w1565;
    (* keep = 1, preserve = 1 *) wire w1566;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1566 (
        .dataa(chain[1566]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1566));
    assign chain[1567] = w1566;
    (* keep = 1, preserve = 1 *) wire w1567;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1567 (
        .dataa(chain[1567]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1567));
    assign chain[1568] = w1567;
    (* keep = 1, preserve = 1 *) wire w1568;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1568 (
        .dataa(chain[1568]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1568));
    assign chain[1569] = w1568;
    (* keep = 1, preserve = 1 *) wire w1569;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1569 (
        .dataa(chain[1569]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1569));
    assign chain[1570] = w1569;
    (* keep = 1, preserve = 1 *) wire w1570;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1570 (
        .dataa(chain[1570]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1570));
    assign chain[1571] = w1570;
    (* keep = 1, preserve = 1 *) wire w1571;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1571 (
        .dataa(chain[1571]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1571));
    assign chain[1572] = w1571;
    (* keep = 1, preserve = 1 *) wire w1572;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1572 (
        .dataa(chain[1572]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1572));
    assign chain[1573] = w1572;
    (* keep = 1, preserve = 1 *) wire w1573;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1573 (
        .dataa(chain[1573]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1573));
    assign chain[1574] = w1573;
    (* keep = 1, preserve = 1 *) wire w1574;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1574 (
        .dataa(chain[1574]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1574));
    assign chain[1575] = w1574;
    (* keep = 1, preserve = 1 *) wire w1575;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1575 (
        .dataa(chain[1575]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1575));
    assign chain[1576] = w1575;
    (* keep = 1, preserve = 1 *) wire w1576;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1576 (
        .dataa(chain[1576]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1576));
    assign chain[1577] = w1576;
    (* keep = 1, preserve = 1 *) wire w1577;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1577 (
        .dataa(chain[1577]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1577));
    assign chain[1578] = w1577;
    (* keep = 1, preserve = 1 *) wire w1578;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1578 (
        .dataa(chain[1578]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1578));
    assign chain[1579] = w1578;
    (* keep = 1, preserve = 1 *) wire w1579;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1579 (
        .dataa(chain[1579]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1579));
    assign chain[1580] = w1579;
    (* keep = 1, preserve = 1 *) wire w1580;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1580 (
        .dataa(chain[1580]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1580));
    assign chain[1581] = w1580;
    (* keep = 1, preserve = 1 *) wire w1581;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1581 (
        .dataa(chain[1581]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1581));
    assign chain[1582] = w1581;
    (* keep = 1, preserve = 1 *) wire w1582;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1582 (
        .dataa(chain[1582]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1582));
    assign chain[1583] = w1582;
    (* keep = 1, preserve = 1 *) wire w1583;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1583 (
        .dataa(chain[1583]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1583));
    assign chain[1584] = w1583;
    (* keep = 1, preserve = 1 *) wire w1584;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1584 (
        .dataa(chain[1584]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1584));
    assign chain[1585] = w1584;
    (* keep = 1, preserve = 1 *) wire w1585;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1585 (
        .dataa(chain[1585]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1585));
    assign chain[1586] = w1585;
    (* keep = 1, preserve = 1 *) wire w1586;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1586 (
        .dataa(chain[1586]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1586));
    assign chain[1587] = w1586;
    (* keep = 1, preserve = 1 *) wire w1587;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1587 (
        .dataa(chain[1587]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1587));
    assign chain[1588] = w1587;
    (* keep = 1, preserve = 1 *) wire w1588;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1588 (
        .dataa(chain[1588]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1588));
    assign chain[1589] = w1588;
    (* keep = 1, preserve = 1 *) wire w1589;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1589 (
        .dataa(chain[1589]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1589));
    assign chain[1590] = w1589;
    (* keep = 1, preserve = 1 *) wire w1590;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1590 (
        .dataa(chain[1590]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1590));
    assign chain[1591] = w1590;
    (* keep = 1, preserve = 1 *) wire w1591;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1591 (
        .dataa(chain[1591]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1591));
    assign chain[1592] = w1591;
    (* keep = 1, preserve = 1 *) wire w1592;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1592 (
        .dataa(chain[1592]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1592));
    assign chain[1593] = w1592;
    (* keep = 1, preserve = 1 *) wire w1593;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1593 (
        .dataa(chain[1593]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1593));
    assign chain[1594] = w1593;
    (* keep = 1, preserve = 1 *) wire w1594;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1594 (
        .dataa(chain[1594]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1594));
    assign chain[1595] = w1594;
    (* keep = 1, preserve = 1 *) wire w1595;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1595 (
        .dataa(chain[1595]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1595));
    assign chain[1596] = w1595;
    (* keep = 1, preserve = 1 *) wire w1596;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1596 (
        .dataa(chain[1596]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1596));
    assign chain[1597] = w1596;
    (* keep = 1, preserve = 1 *) wire w1597;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1597 (
        .dataa(chain[1597]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1597));
    assign chain[1598] = w1597;
    (* keep = 1, preserve = 1 *) wire w1598;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1598 (
        .dataa(chain[1598]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1598));
    assign chain[1599] = w1598;
    (* keep = 1, preserve = 1 *) wire w1599;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1599 (
        .dataa(chain[1599]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1599));
    assign chain[1600] = w1599;
    (* keep = 1, preserve = 1 *) wire w1600;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1600 (
        .dataa(chain[1600]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1600));
    assign chain[1601] = w1600;
    (* keep = 1, preserve = 1 *) wire w1601;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1601 (
        .dataa(chain[1601]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1601));
    assign chain[1602] = w1601;
    (* keep = 1, preserve = 1 *) wire w1602;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1602 (
        .dataa(chain[1602]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1602));
    assign chain[1603] = w1602;
    (* keep = 1, preserve = 1 *) wire w1603;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1603 (
        .dataa(chain[1603]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1603));
    assign chain[1604] = w1603;
    (* keep = 1, preserve = 1 *) wire w1604;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1604 (
        .dataa(chain[1604]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1604));
    assign chain[1605] = w1604;
    (* keep = 1, preserve = 1 *) wire w1605;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1605 (
        .dataa(chain[1605]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1605));
    assign chain[1606] = w1605;
    (* keep = 1, preserve = 1 *) wire w1606;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1606 (
        .dataa(chain[1606]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1606));
    assign chain[1607] = w1606;
    (* keep = 1, preserve = 1 *) wire w1607;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1607 (
        .dataa(chain[1607]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1607));
    assign chain[1608] = w1607;
    (* keep = 1, preserve = 1 *) wire w1608;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1608 (
        .dataa(chain[1608]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1608));
    assign chain[1609] = w1608;
    (* keep = 1, preserve = 1 *) wire w1609;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1609 (
        .dataa(chain[1609]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1609));
    assign chain[1610] = w1609;
    (* keep = 1, preserve = 1 *) wire w1610;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1610 (
        .dataa(chain[1610]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1610));
    assign chain[1611] = w1610;
    (* keep = 1, preserve = 1 *) wire w1611;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1611 (
        .dataa(chain[1611]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1611));
    assign chain[1612] = w1611;
    (* keep = 1, preserve = 1 *) wire w1612;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1612 (
        .dataa(chain[1612]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1612));
    assign chain[1613] = w1612;
    (* keep = 1, preserve = 1 *) wire w1613;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1613 (
        .dataa(chain[1613]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1613));
    assign chain[1614] = w1613;
    (* keep = 1, preserve = 1 *) wire w1614;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1614 (
        .dataa(chain[1614]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1614));
    assign chain[1615] = w1614;
    (* keep = 1, preserve = 1 *) wire w1615;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1615 (
        .dataa(chain[1615]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1615));
    assign chain[1616] = w1615;
    (* keep = 1, preserve = 1 *) wire w1616;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1616 (
        .dataa(chain[1616]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1616));
    assign chain[1617] = w1616;
    (* keep = 1, preserve = 1 *) wire w1617;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1617 (
        .dataa(chain[1617]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1617));
    assign chain[1618] = w1617;
    (* keep = 1, preserve = 1 *) wire w1618;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1618 (
        .dataa(chain[1618]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1618));
    assign chain[1619] = w1618;
    (* keep = 1, preserve = 1 *) wire w1619;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1619 (
        .dataa(chain[1619]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1619));
    assign chain[1620] = w1619;
    (* keep = 1, preserve = 1 *) wire w1620;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1620 (
        .dataa(chain[1620]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1620));
    assign chain[1621] = w1620;
    (* keep = 1, preserve = 1 *) wire w1621;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1621 (
        .dataa(chain[1621]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1621));
    assign chain[1622] = w1621;
    (* keep = 1, preserve = 1 *) wire w1622;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1622 (
        .dataa(chain[1622]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1622));
    assign chain[1623] = w1622;
    (* keep = 1, preserve = 1 *) wire w1623;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1623 (
        .dataa(chain[1623]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1623));
    assign chain[1624] = w1623;
    (* keep = 1, preserve = 1 *) wire w1624;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1624 (
        .dataa(chain[1624]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1624));
    assign chain[1625] = w1624;
    (* keep = 1, preserve = 1 *) wire w1625;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1625 (
        .dataa(chain[1625]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1625));
    assign chain[1626] = w1625;
    (* keep = 1, preserve = 1 *) wire w1626;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1626 (
        .dataa(chain[1626]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1626));
    assign chain[1627] = w1626;
    (* keep = 1, preserve = 1 *) wire w1627;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1627 (
        .dataa(chain[1627]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1627));
    assign chain[1628] = w1627;
    (* keep = 1, preserve = 1 *) wire w1628;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1628 (
        .dataa(chain[1628]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1628));
    assign chain[1629] = w1628;
    (* keep = 1, preserve = 1 *) wire w1629;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1629 (
        .dataa(chain[1629]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1629));
    assign chain[1630] = w1629;
    (* keep = 1, preserve = 1 *) wire w1630;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1630 (
        .dataa(chain[1630]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1630));
    assign chain[1631] = w1630;
    (* keep = 1, preserve = 1 *) wire w1631;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1631 (
        .dataa(chain[1631]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1631));
    assign chain[1632] = w1631;
    (* keep = 1, preserve = 1 *) wire w1632;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1632 (
        .dataa(chain[1632]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1632));
    assign chain[1633] = w1632;
    (* keep = 1, preserve = 1 *) wire w1633;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1633 (
        .dataa(chain[1633]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1633));
    assign chain[1634] = w1633;
    (* keep = 1, preserve = 1 *) wire w1634;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1634 (
        .dataa(chain[1634]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1634));
    assign chain[1635] = w1634;
    (* keep = 1, preserve = 1 *) wire w1635;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1635 (
        .dataa(chain[1635]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1635));
    assign chain[1636] = w1635;
    (* keep = 1, preserve = 1 *) wire w1636;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1636 (
        .dataa(chain[1636]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1636));
    assign chain[1637] = w1636;
    (* keep = 1, preserve = 1 *) wire w1637;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1637 (
        .dataa(chain[1637]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1637));
    assign chain[1638] = w1637;
    (* keep = 1, preserve = 1 *) wire w1638;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1638 (
        .dataa(chain[1638]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1638));
    assign chain[1639] = w1638;
    (* keep = 1, preserve = 1 *) wire w1639;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1639 (
        .dataa(chain[1639]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1639));
    assign chain[1640] = w1639;
    (* keep = 1, preserve = 1 *) wire w1640;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1640 (
        .dataa(chain[1640]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1640));
    assign chain[1641] = w1640;
    (* keep = 1, preserve = 1 *) wire w1641;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1641 (
        .dataa(chain[1641]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1641));
    assign chain[1642] = w1641;
    (* keep = 1, preserve = 1 *) wire w1642;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1642 (
        .dataa(chain[1642]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1642));
    assign chain[1643] = w1642;
    (* keep = 1, preserve = 1 *) wire w1643;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1643 (
        .dataa(chain[1643]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1643));
    assign chain[1644] = w1643;
    (* keep = 1, preserve = 1 *) wire w1644;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1644 (
        .dataa(chain[1644]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1644));
    assign chain[1645] = w1644;
    (* keep = 1, preserve = 1 *) wire w1645;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1645 (
        .dataa(chain[1645]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1645));
    assign chain[1646] = w1645;
    (* keep = 1, preserve = 1 *) wire w1646;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1646 (
        .dataa(chain[1646]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1646));
    assign chain[1647] = w1646;
    (* keep = 1, preserve = 1 *) wire w1647;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1647 (
        .dataa(chain[1647]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1647));
    assign chain[1648] = w1647;
    (* keep = 1, preserve = 1 *) wire w1648;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1648 (
        .dataa(chain[1648]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1648));
    assign chain[1649] = w1648;
    (* keep = 1, preserve = 1 *) wire w1649;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1649 (
        .dataa(chain[1649]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1649));
    assign chain[1650] = w1649;
    (* keep = 1, preserve = 1 *) wire w1650;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1650 (
        .dataa(chain[1650]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1650));
    assign chain[1651] = w1650;
    (* keep = 1, preserve = 1 *) wire w1651;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1651 (
        .dataa(chain[1651]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1651));
    assign chain[1652] = w1651;
    (* keep = 1, preserve = 1 *) wire w1652;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1652 (
        .dataa(chain[1652]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1652));
    assign chain[1653] = w1652;
    (* keep = 1, preserve = 1 *) wire w1653;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1653 (
        .dataa(chain[1653]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1653));
    assign chain[1654] = w1653;
    (* keep = 1, preserve = 1 *) wire w1654;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1654 (
        .dataa(chain[1654]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1654));
    assign chain[1655] = w1654;
    (* keep = 1, preserve = 1 *) wire w1655;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1655 (
        .dataa(chain[1655]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1655));
    assign chain[1656] = w1655;
    (* keep = 1, preserve = 1 *) wire w1656;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1656 (
        .dataa(chain[1656]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1656));
    assign chain[1657] = w1656;
    (* keep = 1, preserve = 1 *) wire w1657;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1657 (
        .dataa(chain[1657]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1657));
    assign chain[1658] = w1657;
    (* keep = 1, preserve = 1 *) wire w1658;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1658 (
        .dataa(chain[1658]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1658));
    assign chain[1659] = w1658;
    (* keep = 1, preserve = 1 *) wire w1659;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1659 (
        .dataa(chain[1659]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1659));
    assign chain[1660] = w1659;
    (* keep = 1, preserve = 1 *) wire w1660;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1660 (
        .dataa(chain[1660]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1660));
    assign chain[1661] = w1660;
    (* keep = 1, preserve = 1 *) wire w1661;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1661 (
        .dataa(chain[1661]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1661));
    assign chain[1662] = w1661;
    (* keep = 1, preserve = 1 *) wire w1662;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1662 (
        .dataa(chain[1662]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1662));
    assign chain[1663] = w1662;
    (* keep = 1, preserve = 1 *) wire w1663;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1663 (
        .dataa(chain[1663]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1663));
    assign chain[1664] = w1663;
    (* keep = 1, preserve = 1 *) wire w1664;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1664 (
        .dataa(chain[1664]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1664));
    assign chain[1665] = w1664;
    (* keep = 1, preserve = 1 *) wire w1665;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1665 (
        .dataa(chain[1665]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1665));
    assign chain[1666] = w1665;
    (* keep = 1, preserve = 1 *) wire w1666;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1666 (
        .dataa(chain[1666]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1666));
    assign chain[1667] = w1666;
    (* keep = 1, preserve = 1 *) wire w1667;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1667 (
        .dataa(chain[1667]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1667));
    assign chain[1668] = w1667;
    (* keep = 1, preserve = 1 *) wire w1668;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1668 (
        .dataa(chain[1668]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1668));
    assign chain[1669] = w1668;
    (* keep = 1, preserve = 1 *) wire w1669;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1669 (
        .dataa(chain[1669]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1669));
    assign chain[1670] = w1669;
    (* keep = 1, preserve = 1 *) wire w1670;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1670 (
        .dataa(chain[1670]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1670));
    assign chain[1671] = w1670;
    (* keep = 1, preserve = 1 *) wire w1671;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1671 (
        .dataa(chain[1671]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1671));
    assign chain[1672] = w1671;
    (* keep = 1, preserve = 1 *) wire w1672;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1672 (
        .dataa(chain[1672]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1672));
    assign chain[1673] = w1672;
    (* keep = 1, preserve = 1 *) wire w1673;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1673 (
        .dataa(chain[1673]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1673));
    assign chain[1674] = w1673;
    (* keep = 1, preserve = 1 *) wire w1674;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1674 (
        .dataa(chain[1674]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1674));
    assign chain[1675] = w1674;
    (* keep = 1, preserve = 1 *) wire w1675;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1675 (
        .dataa(chain[1675]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1675));
    assign chain[1676] = w1675;
    (* keep = 1, preserve = 1 *) wire w1676;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1676 (
        .dataa(chain[1676]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1676));
    assign chain[1677] = w1676;
    (* keep = 1, preserve = 1 *) wire w1677;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1677 (
        .dataa(chain[1677]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1677));
    assign chain[1678] = w1677;
    (* keep = 1, preserve = 1 *) wire w1678;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1678 (
        .dataa(chain[1678]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1678));
    assign chain[1679] = w1678;
    (* keep = 1, preserve = 1 *) wire w1679;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1679 (
        .dataa(chain[1679]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1679));
    assign chain[1680] = w1679;
    (* keep = 1, preserve = 1 *) wire w1680;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1680 (
        .dataa(chain[1680]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1680));
    assign chain[1681] = w1680;
    (* keep = 1, preserve = 1 *) wire w1681;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1681 (
        .dataa(chain[1681]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1681));
    assign chain[1682] = w1681;
    (* keep = 1, preserve = 1 *) wire w1682;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1682 (
        .dataa(chain[1682]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1682));
    assign chain[1683] = w1682;
    (* keep = 1, preserve = 1 *) wire w1683;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1683 (
        .dataa(chain[1683]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1683));
    assign chain[1684] = w1683;
    (* keep = 1, preserve = 1 *) wire w1684;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1684 (
        .dataa(chain[1684]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1684));
    assign chain[1685] = w1684;
    (* keep = 1, preserve = 1 *) wire w1685;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1685 (
        .dataa(chain[1685]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1685));
    assign chain[1686] = w1685;
    (* keep = 1, preserve = 1 *) wire w1686;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1686 (
        .dataa(chain[1686]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1686));
    assign chain[1687] = w1686;
    (* keep = 1, preserve = 1 *) wire w1687;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1687 (
        .dataa(chain[1687]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1687));
    assign chain[1688] = w1687;
    (* keep = 1, preserve = 1 *) wire w1688;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1688 (
        .dataa(chain[1688]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1688));
    assign chain[1689] = w1688;
    (* keep = 1, preserve = 1 *) wire w1689;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1689 (
        .dataa(chain[1689]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1689));
    assign chain[1690] = w1689;
    (* keep = 1, preserve = 1 *) wire w1690;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1690 (
        .dataa(chain[1690]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1690));
    assign chain[1691] = w1690;
    (* keep = 1, preserve = 1 *) wire w1691;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1691 (
        .dataa(chain[1691]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1691));
    assign chain[1692] = w1691;
    (* keep = 1, preserve = 1 *) wire w1692;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1692 (
        .dataa(chain[1692]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1692));
    assign chain[1693] = w1692;
    (* keep = 1, preserve = 1 *) wire w1693;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1693 (
        .dataa(chain[1693]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1693));
    assign chain[1694] = w1693;
    (* keep = 1, preserve = 1 *) wire w1694;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1694 (
        .dataa(chain[1694]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1694));
    assign chain[1695] = w1694;
    (* keep = 1, preserve = 1 *) wire w1695;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1695 (
        .dataa(chain[1695]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1695));
    assign chain[1696] = w1695;
    (* keep = 1, preserve = 1 *) wire w1696;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1696 (
        .dataa(chain[1696]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1696));
    assign chain[1697] = w1696;
    (* keep = 1, preserve = 1 *) wire w1697;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1697 (
        .dataa(chain[1697]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1697));
    assign chain[1698] = w1697;
    (* keep = 1, preserve = 1 *) wire w1698;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1698 (
        .dataa(chain[1698]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1698));
    assign chain[1699] = w1698;
    (* keep = 1, preserve = 1 *) wire w1699;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1699 (
        .dataa(chain[1699]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1699));
    assign chain[1700] = w1699;
    (* keep = 1, preserve = 1 *) wire w1700;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1700 (
        .dataa(chain[1700]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1700));
    assign chain[1701] = w1700;
    (* keep = 1, preserve = 1 *) wire w1701;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1701 (
        .dataa(chain[1701]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1701));
    assign chain[1702] = w1701;
    (* keep = 1, preserve = 1 *) wire w1702;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1702 (
        .dataa(chain[1702]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1702));
    assign chain[1703] = w1702;
    (* keep = 1, preserve = 1 *) wire w1703;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1703 (
        .dataa(chain[1703]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1703));
    assign chain[1704] = w1703;
    (* keep = 1, preserve = 1 *) wire w1704;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1704 (
        .dataa(chain[1704]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1704));
    assign chain[1705] = w1704;
    (* keep = 1, preserve = 1 *) wire w1705;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1705 (
        .dataa(chain[1705]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1705));
    assign chain[1706] = w1705;
    (* keep = 1, preserve = 1 *) wire w1706;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1706 (
        .dataa(chain[1706]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1706));
    assign chain[1707] = w1706;
    (* keep = 1, preserve = 1 *) wire w1707;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1707 (
        .dataa(chain[1707]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1707));
    assign chain[1708] = w1707;
    (* keep = 1, preserve = 1 *) wire w1708;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1708 (
        .dataa(chain[1708]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1708));
    assign chain[1709] = w1708;
    (* keep = 1, preserve = 1 *) wire w1709;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1709 (
        .dataa(chain[1709]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1709));
    assign chain[1710] = w1709;
    (* keep = 1, preserve = 1 *) wire w1710;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1710 (
        .dataa(chain[1710]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1710));
    assign chain[1711] = w1710;
    (* keep = 1, preserve = 1 *) wire w1711;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1711 (
        .dataa(chain[1711]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1711));
    assign chain[1712] = w1711;
    (* keep = 1, preserve = 1 *) wire w1712;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1712 (
        .dataa(chain[1712]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1712));
    assign chain[1713] = w1712;
    (* keep = 1, preserve = 1 *) wire w1713;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1713 (
        .dataa(chain[1713]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1713));
    assign chain[1714] = w1713;
    (* keep = 1, preserve = 1 *) wire w1714;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1714 (
        .dataa(chain[1714]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1714));
    assign chain[1715] = w1714;
    (* keep = 1, preserve = 1 *) wire w1715;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1715 (
        .dataa(chain[1715]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1715));
    assign chain[1716] = w1715;
    (* keep = 1, preserve = 1 *) wire w1716;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1716 (
        .dataa(chain[1716]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1716));
    assign chain[1717] = w1716;
    (* keep = 1, preserve = 1 *) wire w1717;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1717 (
        .dataa(chain[1717]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1717));
    assign chain[1718] = w1717;
    (* keep = 1, preserve = 1 *) wire w1718;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1718 (
        .dataa(chain[1718]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1718));
    assign chain[1719] = w1718;
    (* keep = 1, preserve = 1 *) wire w1719;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1719 (
        .dataa(chain[1719]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1719));
    assign chain[1720] = w1719;
    (* keep = 1, preserve = 1 *) wire w1720;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1720 (
        .dataa(chain[1720]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1720));
    assign chain[1721] = w1720;
    (* keep = 1, preserve = 1 *) wire w1721;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1721 (
        .dataa(chain[1721]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1721));
    assign chain[1722] = w1721;
    (* keep = 1, preserve = 1 *) wire w1722;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1722 (
        .dataa(chain[1722]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1722));
    assign chain[1723] = w1722;
    (* keep = 1, preserve = 1 *) wire w1723;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1723 (
        .dataa(chain[1723]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1723));
    assign chain[1724] = w1723;
    (* keep = 1, preserve = 1 *) wire w1724;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1724 (
        .dataa(chain[1724]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1724));
    assign chain[1725] = w1724;
    (* keep = 1, preserve = 1 *) wire w1725;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1725 (
        .dataa(chain[1725]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1725));
    assign chain[1726] = w1725;
    (* keep = 1, preserve = 1 *) wire w1726;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1726 (
        .dataa(chain[1726]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1726));
    assign chain[1727] = w1726;
    (* keep = 1, preserve = 1 *) wire w1727;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1727 (
        .dataa(chain[1727]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1727));
    assign chain[1728] = w1727;
    (* keep = 1, preserve = 1 *) wire w1728;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1728 (
        .dataa(chain[1728]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1728));
    assign chain[1729] = w1728;
    (* keep = 1, preserve = 1 *) wire w1729;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1729 (
        .dataa(chain[1729]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1729));
    assign chain[1730] = w1729;
    (* keep = 1, preserve = 1 *) wire w1730;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1730 (
        .dataa(chain[1730]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1730));
    assign chain[1731] = w1730;
    (* keep = 1, preserve = 1 *) wire w1731;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1731 (
        .dataa(chain[1731]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1731));
    assign chain[1732] = w1731;
    (* keep = 1, preserve = 1 *) wire w1732;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1732 (
        .dataa(chain[1732]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1732));
    assign chain[1733] = w1732;
    (* keep = 1, preserve = 1 *) wire w1733;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1733 (
        .dataa(chain[1733]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1733));
    assign chain[1734] = w1733;
    (* keep = 1, preserve = 1 *) wire w1734;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1734 (
        .dataa(chain[1734]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1734));
    assign chain[1735] = w1734;
    (* keep = 1, preserve = 1 *) wire w1735;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1735 (
        .dataa(chain[1735]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1735));
    assign chain[1736] = w1735;
    (* keep = 1, preserve = 1 *) wire w1736;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1736 (
        .dataa(chain[1736]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1736));
    assign chain[1737] = w1736;
    (* keep = 1, preserve = 1 *) wire w1737;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1737 (
        .dataa(chain[1737]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1737));
    assign chain[1738] = w1737;
    (* keep = 1, preserve = 1 *) wire w1738;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1738 (
        .dataa(chain[1738]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1738));
    assign chain[1739] = w1738;
    (* keep = 1, preserve = 1 *) wire w1739;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1739 (
        .dataa(chain[1739]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1739));
    assign chain[1740] = w1739;
    (* keep = 1, preserve = 1 *) wire w1740;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1740 (
        .dataa(chain[1740]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1740));
    assign chain[1741] = w1740;
    (* keep = 1, preserve = 1 *) wire w1741;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1741 (
        .dataa(chain[1741]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1741));
    assign chain[1742] = w1741;
    (* keep = 1, preserve = 1 *) wire w1742;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1742 (
        .dataa(chain[1742]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1742));
    assign chain[1743] = w1742;
    (* keep = 1, preserve = 1 *) wire w1743;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1743 (
        .dataa(chain[1743]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1743));
    assign chain[1744] = w1743;
    (* keep = 1, preserve = 1 *) wire w1744;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1744 (
        .dataa(chain[1744]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1744));
    assign chain[1745] = w1744;
    (* keep = 1, preserve = 1 *) wire w1745;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1745 (
        .dataa(chain[1745]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1745));
    assign chain[1746] = w1745;
    (* keep = 1, preserve = 1 *) wire w1746;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1746 (
        .dataa(chain[1746]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1746));
    assign chain[1747] = w1746;
    (* keep = 1, preserve = 1 *) wire w1747;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1747 (
        .dataa(chain[1747]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1747));
    assign chain[1748] = w1747;
    (* keep = 1, preserve = 1 *) wire w1748;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1748 (
        .dataa(chain[1748]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1748));
    assign chain[1749] = w1748;
    (* keep = 1, preserve = 1 *) wire w1749;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1749 (
        .dataa(chain[1749]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1749));
    assign chain[1750] = w1749;
    (* keep = 1, preserve = 1 *) wire w1750;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1750 (
        .dataa(chain[1750]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1750));
    assign chain[1751] = w1750;
    (* keep = 1, preserve = 1 *) wire w1751;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1751 (
        .dataa(chain[1751]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1751));
    assign chain[1752] = w1751;
    (* keep = 1, preserve = 1 *) wire w1752;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1752 (
        .dataa(chain[1752]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1752));
    assign chain[1753] = w1752;
    (* keep = 1, preserve = 1 *) wire w1753;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1753 (
        .dataa(chain[1753]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1753));
    assign chain[1754] = w1753;
    (* keep = 1, preserve = 1 *) wire w1754;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1754 (
        .dataa(chain[1754]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1754));
    assign chain[1755] = w1754;
    (* keep = 1, preserve = 1 *) wire w1755;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1755 (
        .dataa(chain[1755]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1755));
    assign chain[1756] = w1755;
    (* keep = 1, preserve = 1 *) wire w1756;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1756 (
        .dataa(chain[1756]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1756));
    assign chain[1757] = w1756;
    (* keep = 1, preserve = 1 *) wire w1757;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1757 (
        .dataa(chain[1757]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1757));
    assign chain[1758] = w1757;
    (* keep = 1, preserve = 1 *) wire w1758;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1758 (
        .dataa(chain[1758]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1758));
    assign chain[1759] = w1758;
    (* keep = 1, preserve = 1 *) wire w1759;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1759 (
        .dataa(chain[1759]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1759));
    assign chain[1760] = w1759;
    (* keep = 1, preserve = 1 *) wire w1760;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1760 (
        .dataa(chain[1760]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1760));
    assign chain[1761] = w1760;
    (* keep = 1, preserve = 1 *) wire w1761;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1761 (
        .dataa(chain[1761]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1761));
    assign chain[1762] = w1761;
    (* keep = 1, preserve = 1 *) wire w1762;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1762 (
        .dataa(chain[1762]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1762));
    assign chain[1763] = w1762;
    (* keep = 1, preserve = 1 *) wire w1763;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1763 (
        .dataa(chain[1763]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1763));
    assign chain[1764] = w1763;
    (* keep = 1, preserve = 1 *) wire w1764;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1764 (
        .dataa(chain[1764]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1764));
    assign chain[1765] = w1764;
    (* keep = 1, preserve = 1 *) wire w1765;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1765 (
        .dataa(chain[1765]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1765));
    assign chain[1766] = w1765;
    (* keep = 1, preserve = 1 *) wire w1766;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1766 (
        .dataa(chain[1766]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1766));
    assign chain[1767] = w1766;
    (* keep = 1, preserve = 1 *) wire w1767;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1767 (
        .dataa(chain[1767]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1767));
    assign chain[1768] = w1767;
    (* keep = 1, preserve = 1 *) wire w1768;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1768 (
        .dataa(chain[1768]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1768));
    assign chain[1769] = w1768;
    (* keep = 1, preserve = 1 *) wire w1769;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1769 (
        .dataa(chain[1769]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1769));
    assign chain[1770] = w1769;
    (* keep = 1, preserve = 1 *) wire w1770;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1770 (
        .dataa(chain[1770]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1770));
    assign chain[1771] = w1770;
    (* keep = 1, preserve = 1 *) wire w1771;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1771 (
        .dataa(chain[1771]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1771));
    assign chain[1772] = w1771;
    (* keep = 1, preserve = 1 *) wire w1772;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1772 (
        .dataa(chain[1772]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1772));
    assign chain[1773] = w1772;
    (* keep = 1, preserve = 1 *) wire w1773;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1773 (
        .dataa(chain[1773]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1773));
    assign chain[1774] = w1773;
    (* keep = 1, preserve = 1 *) wire w1774;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1774 (
        .dataa(chain[1774]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1774));
    assign chain[1775] = w1774;
    (* keep = 1, preserve = 1 *) wire w1775;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1775 (
        .dataa(chain[1775]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1775));
    assign chain[1776] = w1775;
    (* keep = 1, preserve = 1 *) wire w1776;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1776 (
        .dataa(chain[1776]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1776));
    assign chain[1777] = w1776;
    (* keep = 1, preserve = 1 *) wire w1777;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1777 (
        .dataa(chain[1777]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1777));
    assign chain[1778] = w1777;
    (* keep = 1, preserve = 1 *) wire w1778;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1778 (
        .dataa(chain[1778]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1778));
    assign chain[1779] = w1778;
    (* keep = 1, preserve = 1 *) wire w1779;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1779 (
        .dataa(chain[1779]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1779));
    assign chain[1780] = w1779;
    (* keep = 1, preserve = 1 *) wire w1780;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1780 (
        .dataa(chain[1780]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1780));
    assign chain[1781] = w1780;
    (* keep = 1, preserve = 1 *) wire w1781;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1781 (
        .dataa(chain[1781]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1781));
    assign chain[1782] = w1781;
    (* keep = 1, preserve = 1 *) wire w1782;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1782 (
        .dataa(chain[1782]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1782));
    assign chain[1783] = w1782;
    (* keep = 1, preserve = 1 *) wire w1783;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1783 (
        .dataa(chain[1783]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1783));
    assign chain[1784] = w1783;
    (* keep = 1, preserve = 1 *) wire w1784;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1784 (
        .dataa(chain[1784]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1784));
    assign chain[1785] = w1784;
    (* keep = 1, preserve = 1 *) wire w1785;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1785 (
        .dataa(chain[1785]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1785));
    assign chain[1786] = w1785;
    (* keep = 1, preserve = 1 *) wire w1786;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1786 (
        .dataa(chain[1786]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1786));
    assign chain[1787] = w1786;
    (* keep = 1, preserve = 1 *) wire w1787;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1787 (
        .dataa(chain[1787]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1787));
    assign chain[1788] = w1787;
    (* keep = 1, preserve = 1 *) wire w1788;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1788 (
        .dataa(chain[1788]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1788));
    assign chain[1789] = w1788;
    (* keep = 1, preserve = 1 *) wire w1789;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1789 (
        .dataa(chain[1789]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1789));
    assign chain[1790] = w1789;
    (* keep = 1, preserve = 1 *) wire w1790;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1790 (
        .dataa(chain[1790]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1790));
    assign chain[1791] = w1790;
    (* keep = 1, preserve = 1 *) wire w1791;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1791 (
        .dataa(chain[1791]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1791));
    assign chain[1792] = w1791;
    (* keep = 1, preserve = 1 *) wire w1792;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1792 (
        .dataa(chain[1792]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1792));
    assign chain[1793] = w1792;
    (* keep = 1, preserve = 1 *) wire w1793;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1793 (
        .dataa(chain[1793]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1793));
    assign chain[1794] = w1793;
    (* keep = 1, preserve = 1 *) wire w1794;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1794 (
        .dataa(chain[1794]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1794));
    assign chain[1795] = w1794;
    (* keep = 1, preserve = 1 *) wire w1795;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1795 (
        .dataa(chain[1795]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1795));
    assign chain[1796] = w1795;
    (* keep = 1, preserve = 1 *) wire w1796;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1796 (
        .dataa(chain[1796]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1796));
    assign chain[1797] = w1796;
    (* keep = 1, preserve = 1 *) wire w1797;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1797 (
        .dataa(chain[1797]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1797));
    assign chain[1798] = w1797;
    (* keep = 1, preserve = 1 *) wire w1798;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1798 (
        .dataa(chain[1798]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1798));
    assign chain[1799] = w1798;
    (* keep = 1, preserve = 1 *) wire w1799;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1799 (
        .dataa(chain[1799]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1799));
    assign chain[1800] = w1799;
    (* keep = 1, preserve = 1 *) wire w1800;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1800 (
        .dataa(chain[1800]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1800));
    assign chain[1801] = w1800;
    (* keep = 1, preserve = 1 *) wire w1801;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1801 (
        .dataa(chain[1801]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1801));
    assign chain[1802] = w1801;
    (* keep = 1, preserve = 1 *) wire w1802;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1802 (
        .dataa(chain[1802]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1802));
    assign chain[1803] = w1802;
    (* keep = 1, preserve = 1 *) wire w1803;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1803 (
        .dataa(chain[1803]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1803));
    assign chain[1804] = w1803;
    (* keep = 1, preserve = 1 *) wire w1804;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1804 (
        .dataa(chain[1804]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1804));
    assign chain[1805] = w1804;
    (* keep = 1, preserve = 1 *) wire w1805;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1805 (
        .dataa(chain[1805]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1805));
    assign chain[1806] = w1805;
    (* keep = 1, preserve = 1 *) wire w1806;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1806 (
        .dataa(chain[1806]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1806));
    assign chain[1807] = w1806;
    (* keep = 1, preserve = 1 *) wire w1807;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1807 (
        .dataa(chain[1807]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1807));
    assign chain[1808] = w1807;
    (* keep = 1, preserve = 1 *) wire w1808;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1808 (
        .dataa(chain[1808]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1808));
    assign chain[1809] = w1808;
    (* keep = 1, preserve = 1 *) wire w1809;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1809 (
        .dataa(chain[1809]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1809));
    assign chain[1810] = w1809;
    (* keep = 1, preserve = 1 *) wire w1810;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1810 (
        .dataa(chain[1810]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1810));
    assign chain[1811] = w1810;
    (* keep = 1, preserve = 1 *) wire w1811;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1811 (
        .dataa(chain[1811]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1811));
    assign chain[1812] = w1811;
    (* keep = 1, preserve = 1 *) wire w1812;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1812 (
        .dataa(chain[1812]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1812));
    assign chain[1813] = w1812;
    (* keep = 1, preserve = 1 *) wire w1813;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1813 (
        .dataa(chain[1813]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1813));
    assign chain[1814] = w1813;
    (* keep = 1, preserve = 1 *) wire w1814;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1814 (
        .dataa(chain[1814]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1814));
    assign chain[1815] = w1814;
    (* keep = 1, preserve = 1 *) wire w1815;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1815 (
        .dataa(chain[1815]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1815));
    assign chain[1816] = w1815;
    (* keep = 1, preserve = 1 *) wire w1816;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1816 (
        .dataa(chain[1816]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1816));
    assign chain[1817] = w1816;
    (* keep = 1, preserve = 1 *) wire w1817;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1817 (
        .dataa(chain[1817]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1817));
    assign chain[1818] = w1817;
    (* keep = 1, preserve = 1 *) wire w1818;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1818 (
        .dataa(chain[1818]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1818));
    assign chain[1819] = w1818;
    (* keep = 1, preserve = 1 *) wire w1819;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1819 (
        .dataa(chain[1819]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1819));
    assign chain[1820] = w1819;
    (* keep = 1, preserve = 1 *) wire w1820;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1820 (
        .dataa(chain[1820]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1820));
    assign chain[1821] = w1820;
    (* keep = 1, preserve = 1 *) wire w1821;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1821 (
        .dataa(chain[1821]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1821));
    assign chain[1822] = w1821;
    (* keep = 1, preserve = 1 *) wire w1822;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1822 (
        .dataa(chain[1822]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1822));
    assign chain[1823] = w1822;
    (* keep = 1, preserve = 1 *) wire w1823;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1823 (
        .dataa(chain[1823]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1823));
    assign chain[1824] = w1823;
    (* keep = 1, preserve = 1 *) wire w1824;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1824 (
        .dataa(chain[1824]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1824));
    assign chain[1825] = w1824;
    (* keep = 1, preserve = 1 *) wire w1825;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1825 (
        .dataa(chain[1825]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1825));
    assign chain[1826] = w1825;
    (* keep = 1, preserve = 1 *) wire w1826;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1826 (
        .dataa(chain[1826]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1826));
    assign chain[1827] = w1826;
    (* keep = 1, preserve = 1 *) wire w1827;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1827 (
        .dataa(chain[1827]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1827));
    assign chain[1828] = w1827;
    (* keep = 1, preserve = 1 *) wire w1828;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1828 (
        .dataa(chain[1828]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1828));
    assign chain[1829] = w1828;
    (* keep = 1, preserve = 1 *) wire w1829;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1829 (
        .dataa(chain[1829]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1829));
    assign chain[1830] = w1829;
    (* keep = 1, preserve = 1 *) wire w1830;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1830 (
        .dataa(chain[1830]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1830));
    assign chain[1831] = w1830;
    (* keep = 1, preserve = 1 *) wire w1831;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1831 (
        .dataa(chain[1831]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1831));
    assign chain[1832] = w1831;
    (* keep = 1, preserve = 1 *) wire w1832;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1832 (
        .dataa(chain[1832]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1832));
    assign chain[1833] = w1832;
    (* keep = 1, preserve = 1 *) wire w1833;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1833 (
        .dataa(chain[1833]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1833));
    assign chain[1834] = w1833;
    (* keep = 1, preserve = 1 *) wire w1834;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1834 (
        .dataa(chain[1834]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1834));
    assign chain[1835] = w1834;
    (* keep = 1, preserve = 1 *) wire w1835;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1835 (
        .dataa(chain[1835]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1835));
    assign chain[1836] = w1835;
    (* keep = 1, preserve = 1 *) wire w1836;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1836 (
        .dataa(chain[1836]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1836));
    assign chain[1837] = w1836;
    (* keep = 1, preserve = 1 *) wire w1837;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1837 (
        .dataa(chain[1837]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1837));
    assign chain[1838] = w1837;
    (* keep = 1, preserve = 1 *) wire w1838;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1838 (
        .dataa(chain[1838]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1838));
    assign chain[1839] = w1838;
    (* keep = 1, preserve = 1 *) wire w1839;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input("datac")) u1839 (
        .dataa(chain[1839]), .datab(1'b0), .datac(1'b0), .datad(1'b0),
        .cin(1'b0), .combout(w1839));
    assign chain[1840] = w1839;
    assign led = chain[1840];
endmodule
