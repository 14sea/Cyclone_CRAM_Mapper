# SPDX-License-Identifier: GPL-3.0-or-later
"""Re-mine FF arst/ena cells against CRC-normalized baselines.

Strategy: compile N variants of (base/arst/ena) where Quartus placement
is nudged by varying the SEED assignment. After patch_rbf_crc, take
majority vote across variants — cells that appear in the arst diff but
NOT the base diff for >=50% of seeds are real arst bits. Fitter noise
averages out; real structural bits survive.

Runs quartus_map/fit/asm/cpf serially per variant (Quartus Lite is
single-threaded per project), but variants are independent and run in
a parallel pool.
"""
import os, sys, shutil, subprocess, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
REPO = HERE.parent
RBF_DIR = REPO / "results" / "rbf" / "ff_remine"
WORK_ROOT = REPO / "work_ff_remine"

SEEDS = list(range(1, 9))  # 8 seeds per variant

VARIANTS = {
    "base": """module fuzz_top(input CLK, input D, output reg Q);
always @(posedge CLK) Q <= D;
endmodule
""",
    "arst": """module fuzz_top(input CLK, input D, input R, output reg Q);
always @(posedge CLK or posedge R) if (R) Q <= 1'b0; else Q <= D;
endmodule
""",
    "ena": """module fuzz_top(input CLK, input D, input E, output reg Q);
always @(posedge CLK) if (E) Q <= D;
endmodule
""",
}

QSF_TMPL = """set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name SEED {seed}
set_location_assignment PIN_E1 -to CLK
set_location_assignment PIN_M2 -to D
set_location_assignment PIN_G15 -to Q
{extra}
"""


def build_one(args):
    name, seed, verilog = args
    tag = f"{name}_s{seed}"
    out_rbf = RBF_DIR / f"{tag}.rbf"
    if out_rbf.exists():
        return tag, "exists"
    work = WORK_ROOT / tag
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(verilog)
    extra = ""
    if name == "arst":
        extra = 'set_location_assignment PIN_E15 -to R\n'
    elif name == "ena":
        extra = 'set_location_assignment PIN_E15 -to E\n'
    (work / "fuzz_top.qsf").write_text(QSF_TMPL.format(seed=seed, extra=extra))
    (work / "fuzz_top.qpf").write_text('PROJECT_REVISION = "fuzz_top"\n')
    for step in ("map", "fit", "asm"):
        r = subprocess.run(
            [f"quartus_{step}", "fuzz_top"],
            cwd=work, capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            return tag, f"{step}_fail"
    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         "fuzz_top.sof", f"{tag}.rbf"],
        cwd=work, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        return tag, "cpf_fail"
    shutil.copy(work / f"{tag}.rbf", out_rbf)
    shutil.rmtree(work, ignore_errors=True)
    return tag, "ok"


def main():
    RBF_DIR.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    jobs = [(name, s, v) for name, v in VARIANTS.items() for s in SEEDS]
    print(f"queueing {len(jobs)} compiles across {os.cpu_count()} workers")
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
        futs = {ex.submit(build_one, j): j for j in jobs}
        for f in as_completed(futs):
            tag, status = f.result()
            print(f"  {tag:15s} {status}")
    print("all compiles done")

if __name__ == "__main__":
    main()
