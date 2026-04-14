#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate counter + identity design pairs for arith N-slot sweep."""
import os, sys

TEMPLATE_V_COUNTER = '''// {name}: {w}-bit counter at LAB({lx},{ly}) N=[{n_list}]
module top(input wire CLK, output wire LED);
    reg [{w_1}:0] Q;
    always @(posedge CLK) Q <= Q + 1'b1;
    assign LED = Q[{w_1}];
endmodule
'''

TEMPLATE_V_IDENTITY = '''// {name}: {w}-bit identity at LAB({lx},{ly}) N=[{n_list}]
module top(input wire CLK, output wire LED);
    (* noprune *) reg [{w_1}:0] Q;
    always @(posedge CLK) Q <= Q;
    assign LED = Q[{w_1}];
endmodule
'''

QSF_HEADER = '''set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY top
set_global_assignment -name VERILOG_FILE top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name AUTO_SHIFT_REGISTER_RECOGNITION OFF
set_global_assignment -name ALLOW_REGISTER_RETIMING OFF
set_global_assignment -name SYNTH_TIMING_DRIVEN_SYNTHESIS OFF
set_global_assignment -name FITTER_EFFORT "STANDARD FIT"
set_location_assignment PIN_E1 -to CLK
set_location_assignment PIN_G15 -to LED
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to CLK
set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to LED
'''

def gen_pair(base_dir, name, lx, ly, n_start_ff, w, *, identity=False):
    """n_start_ff: FF slot start (1 = LE0, 17 = LE8). w: number of bits."""
    d = os.path.join(base_dir, name)
    os.makedirs(d, exist_ok=True)
    n_slots = list(range(n_start_ff, n_start_ff + 2*w, 2))
    ctx = dict(name=name, w=w, w_1=w-1, lx=lx, ly=ly,
               n_list=",".join(str(n) for n in n_slots))
    vtxt = (TEMPLATE_V_IDENTITY if identity else TEMPLATE_V_COUNTER).format(**ctx)
    with open(os.path.join(d, "top.v"), "w") as f:
        f.write(vtxt)
    qsf = QSF_HEADER
    for i, n in enumerate(n_slots):
        qsf += f'set_location_assignment FF_X{lx}_Y{ly}_N{n}  -to "Q[{i}]~reg0"\n'
    with open(os.path.join(d, "top.qsf"), "w") as f:
        f.write(qsf)
    with open(os.path.join(d, "top.qpf"), "w") as f:
        f.write('PROJECT_REVISION = "top"\n')
    return d

# New configs to build (have: c8 lower, c8 upper, c16, c24, identity for each)
# Widths 2..7 lower half (N starting at 1), widths 2..7 upper half (N starting at 17)
CONFIGS = []
for w in range(2, 9):  # include width 8 for canonical c8_lo/c8_up at (4,18)
    CONFIGS.append((f"c{w}_lo", "counter", 4, 18, 1, w))
    CONFIGS.append((f"i{w}_lo", "identity", 4, 18, 1, w))
    CONFIGS.append((f"c{w}_up", "counter", 4, 18, 17, w))
    CONFIGS.append((f"i{w}_up", "identity", 4, 18, 17, w))

BASE = "tmp/arith_sweep"  # relative to repo root (gitignored scratch dir)
for tag, kind, lx, ly, nst, w in CONFIGS:
    gen_pair(BASE, tag, lx, ly, nst, w, identity=(kind == "identity"))
print(f"generated {len(CONFIGS)} design dirs under {BASE}")
for tag, kind, lx, ly, nst, w in CONFIGS:
    print(f"  {tag}: {kind} w={w} ({lx},{ly}) N=[{nst}..{nst+2*w-2}]")
