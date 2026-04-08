# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase C: chain every newly-discovered CE6-hidden LE on this die."""
LES = []
# X=5,9: Y in {2..11, 17..21} (skip 12..16 M9K gap)
for x in (5, 9):
    for y in list(range(2, 12)) + list(range(17, 22)):
        for n in range(0, 32, 2):
            LES.append((x, y, n))
# X=14,30,32,33: full Y in [2..21]
for x in (14, 30, 32, 33):
    for y in range(2, 22):
        for n in range(0, 32, 2):
            LES.append((x, y, n))
# Y=15 row at normal X (those X=14,30,32,33 already covered above)
for x in (10, 16, 21, 25, 31):
    for n in range(0, 32, 2):
        LES.append((x, 15, n))

v = ["module jbscan(input k1, input k2, output led);"]
v.append(f"    wire [{len(LES)}:0] chain /* synthesis keep */;")
v.append("    assign chain[0] = k1 ^ k2;")
for i, (x, y, n) in enumerate(LES):
    v.append(f"    (* keep = 1, preserve = 1 *) wire w{i};")
    v.append(f"    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .sum_lutc_input(\"datac\")) u{i} (")
    v.append(f"        .dataa(chain[{i}]), .datab(1'b0), .datac(1'b0), .datad(1'b0),")
    v.append(f"        .cin(1'b0), .combout(w{i}));")
    v.append(f"    assign chain[{i+1}] = w{i};")
v.append(f"    assign led = chain[{len(LES)}];")
v.append("endmodule")
open("jbscan.v", "w").write("\n".join(v) + "\n")

q = [
    'set_global_assignment -name FAMILY "Cyclone IV E"',
    "set_global_assignment -name DEVICE EP4CE10F17C8",
    "set_global_assignment -name TOP_LEVEL_ENTITY jbscan",
    "set_global_assignment -name VERILOG_FILE jbscan.v",
    "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
    "set_location_assignment PIN_E15 -to k1",
    "set_location_assignment PIN_E16 -to k2",
    "set_location_assignment PIN_G15 -to led",
    "set_global_assignment -name GENERATE_RBF_FILE ON",
]
for i, (x, y, n) in enumerate(LES):
    q.append(f'set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "u{i}"')
open("jbscan.qsf", "w").write("\n".join(q) + "\n")
print(f"Phase C: {len(LES)} LEs across 6 hidden cols + Y=15 row")
