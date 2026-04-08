# SPDX-License-Identifier: GPL-3.0-or-later
"""Compile 4 DFF-mode corpora (base/sclr/sload/aload) in background.

Produces under results/rbf/:
  ffmode_base.rbf   - plain D FF (no ctrl)
  ffmode_sclr.rbf   - D FF with synchronous clear
  ffmode_sload.rbf  - D FF with synchronous load
  ffmode_aload.rbf  - D FF with asynchronous load

Then XOR-diffs each against ffmode_base and prints the majority-vote cell
table (same methodology as FFCodec _FF_ARST_CELLS / _FF_ENA_CELLS).
"""
import os, sys, shutil, subprocess
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
REPO = HERE.parent
RBF_DIR = REPO / "results" / "rbf"

VARIANTS = {
    "base": """module fuzz_top(input CLK, input D, output reg Q);
always @(posedge CLK) Q <= D;
endmodule
""",
    "sclr": """module fuzz_top(input CLK, input D, input SCLR, output reg Q);
always @(posedge CLK) if (SCLR) Q <= 1'b0; else Q <= D;
endmodule
""",
    "sload": """module fuzz_top(input CLK, input D, input SL, input SLD, output reg Q);
always @(posedge CLK) if (SL) Q <= SLD; else Q <= D;
endmodule
""",
    "aload": """module fuzz_top(input CLK, input D, input AL, input ALD, output reg Q);
always @(posedge CLK or posedge AL) if (AL) Q <= ALD; else Q <= D;
endmodule
""",
}


def build(name, verilog):
    out_rbf = RBF_DIR / f"ffmode_{name}.rbf"
    if out_rbf.exists():
        print(f"skip {name} (exists)")
        return out_rbf
    work = REPO / "work" / f"ffmode_{name}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(verilog)
    # minimal QSF with no pin lock — let Quartus place
    qsf = """set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name FITTER_EFFORT "Standard Fit"
set_global_assignment -name OPTIMIZATION_MODE "Aggressive Area"
set_location_assignment LCFF_X10_Y10_N1 -to "Q"
set_location_assignment LCFF_X10_Y10_N1 -to "Q~reg0"
"""
    (work / "fuzz_top.qsf").write_text(qsf)
    (work / "fuzz_top.qpf").write_text("PROJECT_REVISION = \"fuzz_top\"\n")
    for step in ("map", "fit", "asm"):
        r = subprocess.run(
            [f"quartus_{step}", "fuzz_top"],
            cwd=work, capture_output=True, text=True, errors="replace")
        if r.returncode != 0:
            print(f"[{name}] {step} FAILED:\n{r.stdout[-500:]}")
            return None
    r = subprocess.run(
        ["quartus_cpf", "-c", "-o", "bitstream_compression=off",
         "fuzz_top.sof", f"ffmode_{name}.rbf"],
        cwd=work, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        print(f"[{name}] cpf FAILED")
        return None
    shutil.copy(work / f"ffmode_{name}.rbf", out_rbf)
    print(f"built {out_rbf.name}")
    return out_rbf


def diff_analyze(base, variant, label):
    b = base.read_bytes()
    v = variant.read_bytes()
    cells = []
    for i in range(len(b)):
        d = b[i] ^ v[i]
        if d:
            for bp in range(8):
                if d & (1 << bp):
                    cells.append((i, bp))
    print(f"\n=== {label} vs base: {len(cells)} cell diffs ===")
    # Group by rel position (use COLUMN_BASE)
    from config import COLUMN_BASE
    from collections import defaultdict
    by_rel = defaultdict(list)
    for off, bp in cells:
        for x in sorted(COLUMN_BASE):
            cs = COLUMN_BASE[x] - 136
            rel = off - cs
            if 0 <= rel < 7350:
                by_rel[(rel, bp)].append(x)
                break
    # majority = cells that show up in >=50% of the columns they theoretically cover
    uni = [(rel, bp, cols) for (rel, bp), cols in by_rel.items() if len(cols) >= 2]
    uni.sort()
    print(f"  cells appearing in ≥2 LAB cols: {len(uni)}")
    for rel, bp, cols in uni[:20]:
        print(f"    rel={rel:5d} bp={bp}  cols={cols}")
    return uni


def main():
    RBF_DIR.mkdir(parents=True, exist_ok=True)
    builds = {}
    for name, v in VARIANTS.items():
        r = build(name, v)
        if r: builds[name] = r
    if "base" not in builds:
        print("base build failed, abort")
        return 1
    base = builds["base"]
    for name in ("sclr", "sload", "aload"):
        if name in builds:
            diff_analyze(base, builds[name], name)
    return 0

if __name__ == "__main__":
    sys.exit(main())
