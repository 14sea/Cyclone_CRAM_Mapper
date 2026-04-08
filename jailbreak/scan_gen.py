# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate Phase A jailbreak scanner: identity chain through all 40
forbidden LEs (X in {32,33}, Y in 2..21, N=0). Each lcell passes its
dataa through unchanged (lut_mask=0xAAAA). Healthy chain -> LED = K1^K2.
Any dead/stuck cell breaks parity."""
LES = [(x, y, n) for x in (32, 33) for y in range(2, 22) for n in range(0, 32, 2)]

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
open("jbscan.qpf", "w").write('PROJECT_REVISION = "jbscan"\n')
print(f"generated jbscan: {len(LES)} LEs, file=jbscan.v/qsf")
