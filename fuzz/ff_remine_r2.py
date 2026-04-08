# SPDX-License-Identifier: GPL-3.0-or-later
"""FF re-mine round 2: vary Q pin to relocate FF across the die.

Round 1 (ff_remine.py) used fixed Q=PIN_G15 + 8 seeds → found 76/93 cells
but placement was identical across seeds, so we couldn't separate global
FF-feature bits from placement-specific routing. Round 2 varies the output
pin to force Quartus to put the FF in different LABs; the cells that
appear in EVERY placement are truly global (device-level FF enables),
while cells that move are placement-specific.
"""
import os, sys, shutil, subprocess
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = Path(os.path.dirname(os.path.abspath(__file__)))
REPO = HERE.parent
RBF_DIR = REPO / "results" / "rbf" / "ff_remine_r2"
WORK_ROOT = REPO / "work_ff_remine_r2"

# 10 Q pins spread across the die package (valid EP4CE6F17C8 user I/O)
Q_PINS = [
    "PIN_G15",  # LED0
    "PIN_A2", "PIN_B1", "PIN_D3", "PIN_F2",
    "PIN_J1", "PIN_L1", "PIN_N1", "PIN_P16", "PIN_T9",
]

VARIANTS = {
    "base": "module fuzz_top(input CLK,input D,output reg Q); always @(posedge CLK) Q<=D; endmodule\n",
    "arst": "module fuzz_top(input CLK,input D,input R,output reg Q); always @(posedge CLK or posedge R) if(R) Q<=1'b0; else Q<=D; endmodule\n",
    "ena":  "module fuzz_top(input CLK,input D,input E,output reg Q); always @(posedge CLK) if(E) Q<=D; endmodule\n",
}

QSF_TMPL = """set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_location_assignment PIN_E1 -to CLK
set_location_assignment PIN_M2 -to D
set_location_assignment {qpin} -to Q
{extra}
"""


def build_one(args):
    name, pin_idx, verilog = args
    tag = f"{name}_p{pin_idx}"
    out_rbf = RBF_DIR / f"{tag}.rbf"
    if out_rbf.exists():
        return tag, "exists"
    work = WORK_ROOT / tag
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(verilog)
    extra = ""
    if name == "arst": extra = 'set_location_assignment PIN_E15 -to R\n'
    elif name == "ena": extra = 'set_location_assignment PIN_E15 -to E\n'
    (work / "fuzz_top.qsf").write_text(QSF_TMPL.format(qpin=Q_PINS[pin_idx], extra=extra))
    (work / "fuzz_top.qpf").write_text('PROJECT_REVISION = "fuzz_top"\n')
    for step in ("map", "fit", "asm"):
        r = subprocess.run([f"quartus_{step}", "fuzz_top"], cwd=work,
                           capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            return tag, f"{step}_fail"
    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         "fuzz_top.sof", f"{tag}.rbf"],
        cwd=work, capture_output=True, text=True, errors="replace")
    if r.returncode != 0: return tag, "cpf_fail"
    shutil.copy(work / f"{tag}.rbf", out_rbf)
    shutil.rmtree(work, ignore_errors=True)
    return tag, "ok"


def main():
    RBF_DIR.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    jobs = [(name, i, v) for name, v in VARIANTS.items() for i in range(len(Q_PINS))]
    print(f"queueing {len(jobs)} compiles")
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
        futs = {ex.submit(build_one, j): j for j in jobs}
        for f in as_completed(futs):
            tag, status = f.result()
            print(f"  {tag:12s} {status}")
    print("r2 compiles done")

if __name__ == "__main__":
    main()
