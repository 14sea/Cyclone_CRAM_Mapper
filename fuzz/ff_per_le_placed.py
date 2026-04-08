# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-LE arst bit address model mining via forced placement.

For each target (x, y, n), compile two designs:
  plain: LCCOMB at (x,y,n) drives a plain D FF (packed into same LE)
  arst:  same, but FF uses async reset
CRC-normalize both, XOR-diff, subtract the 70-cell "any-arst" global common
set, and the survivor cell is this LE's per-LE arst bit.

Output: results/ff_per_le_placed.json
        {"(x,y,n)": [[off,bp],...], ...}
"""
import os, sys, shutil, subprocess, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

HERE = Path(os.path.dirname(os.path.abspath(__file__)))
REPO = HERE.parent
RBF_DIR = REPO / "results" / "rbf" / "ff_per_le_placed"
WORK_ROOT = REPO / "work_ff_per_le_placed"
OUT_JSON = REPO / "results" / "ff_per_le_placed.json"

sys.path.insert(0, str(HERE))
from bitstream import patch_rbf_crc  # noqa: E402

# LAB_X with varied Y and N — start with one LAB column, sweep Y+N
TARGETS = []
for y in (4, 7, 10, 13, 16, 19):
    for n in (0, 2, 6, 10, 14):
        TARGETS.append((10, y, n))
# add a couple other columns to check column-independence later
for x in (4, 16, 22, 28):
    TARGETS.append((x, 10, 0))


def gen_verilog(arst: bool) -> str:
    ff = ("always @(posedge CLK or posedge R) if (R) Q <= 1'b0; else Q <= d;"
          if arst else
          "always @(posedge CLK) Q <= d;")
    return f"""module fuzz_top(input CLK, input R, input A, input B, output reg Q);
wire d;
cycloneive_lcell_comb #(.lut_mask(16'h8888), .sum_lutc_input("datac"), .dont_touch("on")) lut_inst(
  .dataa(A), .datab(B), .datac(1'b0), .datad(1'b1), .combout(d));
{ff}
endmodule
"""


def gen_qsf(x, y, n) -> str:
    return f"""set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name SEED 1
set_location_assignment PIN_E1 -to CLK
set_location_assignment PIN_E15 -to R
set_location_assignment PIN_E16 -to A
set_location_assignment PIN_M16 -to B
set_location_assignment PIN_G15 -to Q
set_location_assignment LCCOMB_X{x}_Y{y}_N{n} -to "lut_inst"
"""


def build_one(args):
    x, y, n, arst = args
    tag = f"x{x}_y{y}_n{n}_{'arst' if arst else 'plain'}"
    out_rbf = RBF_DIR / f"{tag}.rbf"
    if out_rbf.exists():
        return tag, "exists"
    work = WORK_ROOT / tag
    if work.exists(): shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(gen_verilog(arst))
    (work / "fuzz_top.qsf").write_text(gen_qsf(x, y, n))
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
    shutil.rmtree(work, ignore_errors=True)
    return tag, "ok"


def analyze():
    # Load the 70-cell "any arst" common set from ff_per_le mine
    # (we derive it freshly here to avoid stale JSON dependencies)
    base_plain = patch_rbf_crc(open(RBF_DIR.parent / "ff_per_le" / "base.rbf", "rb").read())
    anyarst = None
    for k in range(8):
        p = RBF_DIR.parent / "ff_per_le" / f"arst_k{k}.rbf"
        if not p.exists(): continue
        d = patch_rbf_crc(open(p, "rb").read())
        cells = set()
        for i in range(len(d)):
            x = d[i] ^ base_plain[i]
            if x:
                for bp in range(8):
                    if x & (1 << bp):
                        cells.add((i, bp))
        anyarst = cells if anyarst is None else (anyarst & cells)
    anyarst = anyarst or set()
    print(f"any-arst common set: {len(anyarst)} cells")

    results = {}
    for (x, y, n) in TARGETS:
        pt = RBF_DIR / f"x{x}_y{y}_n{n}_plain.rbf"
        at = RBF_DIR / f"x{x}_y{y}_n{n}_arst.rbf"
        if not (pt.exists() and at.exists()):
            continue
        p = patch_rbf_crc(open(pt, "rb").read())
        a = patch_rbf_crc(open(at, "rb").read())
        cells = []
        for i in range(len(p)):
            xd = p[i] ^ a[i]
            if xd:
                for bp in range(8):
                    if xd & (1 << bp):
                        if (i, bp) not in anyarst:
                            cells.append([i, bp])
        # keep only frame-84 cells (bp=2), report fp
        frame84 = [(off, bp) for off, bp in cells
                   if bp == 2 and 32 + 84*210 <= off < 32 + 85*210]
        results[f"{x},{y},{n}"] = {
            "all_per_le": cells,
            "frame84_bp2": frame84,
            "fp": [off - (32 + 84*210) for off, bp in frame84],
        }
        print(f"({x},{y},{n}): {len(cells)} per-LE cells, frame84: {frame84}")
    OUT_JSON.write_text(json.dumps(results, indent=2))
    print(f"wrote {OUT_JSON}")


def main():
    RBF_DIR.mkdir(parents=True, exist_ok=True)
    WORK_ROOT.mkdir(parents=True, exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        analyze(); return
    jobs = []
    for (x, y, n) in TARGETS:
        jobs.append((x, y, n, False))
        jobs.append((x, y, n, True))
    print(f"queueing {len(jobs)} compiles ({len(TARGETS)} placements)")
    with ProcessPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
        futs = {ex.submit(build_one, j): j for j in jobs}
        for f in as_completed(futs):
            tag, status = f.result()
            print(f"  {tag:30s} {status}", flush=True)
    print("compiles done, analyzing...")
    analyze()


if __name__ == "__main__":
    main()
