# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-LE FF mode bit mining (layer 2 of the three-layer FF model).

Compile a design with N=8 parallel D FFs wired to 8 different output
pins. Two families of variants:
  base:     all 8 FFs plain D flip-flops
  arst_k:   FF k uses async reset, the rest stay plain (k=0..7)

The diff (base vs arst_k) minus the 61 layer-1 global arst bits
should be the LE-local mode cell for whichever LE Quartus placed
FF k into. Quartus's placement must stay mostly stable between
variants so 7/8 of the FFs stay in the same LEs — we bet on that
for a trivial design and verify by looking at the fit report LOCs.

Output:
  results/ff_per_le.json — {le_xyn: [(off,bp),...], ...}
  results/rbf/ff_per_le/*.rbf
"""
import os, sys, shutil, subprocess, re, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HERE = Path(os.path.dirname(os.path.abspath(__file__)))
REPO = HERE.parent
RBF_DIR = REPO / "results" / "rbf" / "ff_per_le"
WORK_ROOT = REPO / "work_ff_per_le"

Q_PINS = ["PIN_G15", "PIN_A2", "PIN_B1", "PIN_D3",
          "PIN_F2", "PIN_J1", "PIN_L1", "PIN_N1"]
N_FFS = len(Q_PINS)


def gen_verilog(arst_index):
    """arst_index=-1 → base (all plain); 0..N-1 → FF k has arst.

    D inputs are internally generated from CLK via a shift register so
    Quartus can't prune the FFs, avoiding extra I/O pin pressure.
    """
    lines = [
        f"module fuzz_top(input CLK, input R, output reg [{N_FFS-1}:0] Q);",
        f"reg [{N_FFS-1}:0] seed_r = 0;",
        "always @(posedge CLK) seed_r <= {seed_r[%d:0], ~seed_r[%d]};" % (N_FFS-2, N_FFS-1),
    ]
    for k in range(N_FFS):
        if k == arst_index:
            lines.append(f"always @(posedge CLK or posedge R) if (R) Q[{k}] <= 1'b0; else Q[{k}] <= seed_r[{k}];")
        else:
            lines.append(f"always @(posedge CLK) Q[{k}] <= seed_r[{k}];")
    lines.append("endmodule")
    return "\n".join(lines) + "\n"


def gen_qsf():
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name SEED 1",
        "set_location_assignment PIN_E1 -to CLK",
        "set_location_assignment PIN_E15 -to R",
    ]
    for k in range(N_FFS):
        lines.append(f"set_location_assignment {Q_PINS[k]} -to Q[{k}]")
    return "\n".join(lines) + "\n"


def build_one(args):
    tag, arst_idx = args
    out_rbf = RBF_DIR / f"{tag}.rbf"
    fit_rpt = RBF_DIR / f"{tag}.fit.rpt"
    if out_rbf.exists() and fit_rpt.exists():
        return tag, "exists"
    work = WORK_ROOT / tag
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(gen_verilog(arst_idx))
    (work / "fuzz_top.qsf").write_text(gen_qsf())
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
    if r.returncode != 0:
        return tag, "cpf_fail"
    shutil.copy(work / f"{tag}.rbf", out_rbf)
    rpt = work / "fuzz_top.fit.rpt"
    if rpt.exists():
        shutil.copy(rpt, fit_rpt)
    shutil.rmtree(work, ignore_errors=True)
    return tag, "ok"


def main():
    RBF_DIR.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    jobs = [("base", -1)] + [(f"arst_k{k}", k) for k in range(N_FFS)]
    print(f"queueing {len(jobs)} compiles")
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
        futs = {ex.submit(build_one, j): j for j in jobs}
        for f in as_completed(futs):
            tag, status = f.result()
            print(f"  {tag:12s} {status}", flush=True)
    print("done")


if __name__ == "__main__":
    main()
