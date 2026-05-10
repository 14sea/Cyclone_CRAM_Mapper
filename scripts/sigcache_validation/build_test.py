#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build for sigcache silicon validation.

Pins LE_A to SLICE_X4_Y4_N0 and LE_B to SLICE_X4_Y2_N0, forcing the
test to traverse sigcache entry `4,4,0->4,2,0,dataa`.  np2fasm should
emit a ROUTE directive matching that key.

Usage:  python3 scripts/sigcache_validation/build_test.py
Output: tmp/sigcache_test/test_4_4_0_to_4_2_0_dataa.rbf
"""
from pathlib import Path
import os, subprocess, sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "sigcache_test"
OUT_RBF = WORK / "test_4_4_0_to_4_21_0_dataa.rbf"

LE_A_BEL = "SLICE_X4_Y4_N0"
LE_B_BEL = "SLICE_X4_Y21_N0"


def run(cmd, **kw):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("STDOUT:", r.stdout[-2000:])
        print("STDERR:", r.stderr[-2000:])
        raise RuntimeError(f"command failed: {cmd[0]}")
    return r


def main():
    env = os.environ.copy()
    oss_env = Path.home() / "opt" / "oss-cad-suite" / "environment"
    if oss_env.exists():
        out = subprocess.check_output(
            ["bash", "-c", f"source {oss_env} && env"], text=True
        )
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    WORK.mkdir(parents=True, exist_ok=True)

    verilog = SCRIPT_DIR / "test_2lut_clocked.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data_nojb.json.gz"

    print("\n=== Step 1: Yosys ===", flush=True)
    yosys_json = WORK / "test.json"
    yosys_script = f"""
read_verilog -lib {prims}
read_verilog {verilog}
hierarchy -check -top fuzz_top
proc
async2sync
opt -full
flatten
opt -full
techmap -map {techmap}
techmap
opt -fast
dffunmap -ce-only
dffunmap -srst-only
simplemap
abc -lut 4
clean
techmap -map {techmap}
opt_clean
simplemap t:$and t:$or t:$xor t:$xnor t:$not
techmap -map +/gate2lut.v -D LUT_WIDTH=4
clean
techmap -map {techmap}
opt_clean
delete t:$scopeinfo
clean
stat
write_json {yosys_json}
"""
    yosys_ys = WORK / "synth.ys"
    yosys_ys.write_text(yosys_script)
    r = run(["yosys", "-s", str(yosys_ys)], cwd=WORK, env=env)
    print(r.stdout[-1200:])

    print("\n=== Step 2: nextpnr (BEL-pinned) ===", flush=True)
    placed_json = WORK / "test_placed.json"

    # Pre-place hook: pin LE_A and LE_B to specific SLICEs.
    # We discover the cell names from the JSON dynamically — Yosys
    # produces names based on the keep'd wire names.
    pre_place = f"""
import nextpnrpy_generic as npnr  # type: ignore

PIN_MAP = {{
    "CLK$iob": "IOB_CLK_PIN_E1",
    "Q$iob":   "IOB_Q_PIN_G15",
    "A$iob":   "IOB_A_PIN_E16",
    "B$iob":   "IOB_B_PIN_M16",
}}

bound = 0
for kv in ctx.cells:
    name = str(kv.first)
    if name in PIN_MAP:
        ctx.bindBel(PIN_MAP[name], kv.second, npnr.STRENGTH_LOCKED)
        bound += 1
        print(f"  pin {{name}} -> {{PIN_MAP[name]}}")

# List all GENERIC_SLICE cells for debugging
print("[debug] GENERIC_SLICE cells in design:")
for kv in ctx.cells:
    name = str(kv.first)
    cell = kv.second
    if str(cell.type) == "GENERIC_SLICE":
        print(f"    {{name}} bound? {{cell.bel is not None}}")

le_a_bel = "{LE_A_BEL}"
le_b_bel = "{LE_B_BEL}"
le_a_bound = False
le_b_bound = False
for kv in ctx.cells:
    name = str(kv.first)
    cell = kv.second
    if cell.bel:
        continue
    if str(cell.type) != "GENERIC_SLICE":
        continue
    nlower = name.lower()
    if not le_a_bound and "le_a" in nlower:
        try:
            ctx.bindBel(le_a_bel, cell, npnr.STRENGTH_LOCKED)
            le_a_bound = True
            print(f"  LE_A {{name}} -> {{le_a_bel}}")
        except Exception as e:
            print(f"  WARN: LE_A bind: {{e}}")
        continue
    if not le_b_bound and "le_b" in nlower:
        try:
            ctx.bindBel(le_b_bel, cell, npnr.STRENGTH_LOCKED)
            le_b_bound = True
            print(f"  LE_B {{name}} -> {{le_b_bel}}")
        except Exception as e:
            print(f"  WARN: LE_B bind: {{e}}")
        continue

print(f"[pin_constraints] bound {{bound}}/{{len(PIN_MAP)}} IO + LE_A={{le_a_bound}} LE_B={{le_b_bound}}")
"""
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(pre_place)

    nextpnr_cmd = [
        "nextpnr-generic",
        "--json", str(yosys_json),
        "--pre-pack", str(chipdb_py),
        "--pre-place", str(pin_script),
        "--router", "router2",
        "--write", str(placed_json),
    ]
    r = run(nextpnr_cmd, cwd=WORK, env=env)
    print(r.stdout[-2000:])
    print("STDERR-tail:", r.stderr[-1500:])

    print("\n=== Step 3: np2fasm ===", flush=True)
    fasm = WORK / "test.fasm"
    np_cmd = ["python3", str(REPO / "synth" / "np2fasm.py"),
              str(placed_json), str(fasm)]
    r = run(np_cmd, cwd=WORK, env=env)
    print(r.stdout[-1500:])
    # check fasm contents for our route
    fasm_text = fasm.read_text()
    has_route = "ROUTE X4Y4N0 -> X4Y21N0.dataa" in fasm_text
    print(f"\n  ROUTE X4Y4N0 -> X4Y21N0.dataa present in FASM? {has_route}")
    cross_lab_warns = [l for l in r.stdout.splitlines() + r.stderr.splitlines()
                       if "no sig-cache (cross-LAB)" in l]
    if cross_lab_warns:
        print(f"  WARN: {len(cross_lab_warns)} cross-LAB miss warnings")
        for w in cross_lab_warns[:5]:
            print(f"    {w}")

    print("\n=== Step 4: fasm2rbf ===", flush=True)
    base_rbf = REPO / "results" / "rbf" / "nv_zero_global.rbf"
    fr_cmd = ["python3", str(REPO / "fuzz" / "fasm2rbf.py"),
              str(fasm), str(base_rbf), str(OUT_RBF)]
    r = run(fr_cmd, cwd=WORK, env=env)
    print(r.stdout[-1500:])

    if not OUT_RBF.exists() or OUT_RBF.stat().st_size != 368011:
        print(f"ERROR: bad RBF output")
        sys.exit(1)
    print(f"\nFinal RBF: {OUT_RBF}")
    import hashlib
    print(f"  md5: {hashlib.md5(OUT_RBF.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
