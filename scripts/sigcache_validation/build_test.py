#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build for sigcache silicon validation.

Pins LE_A to SLICE_X4_Y4_N0 and LE_B to SLICE_X4_Y21_N0, forcing the
test to traverse sigcache entry `4,4,0->4,21,0,dataa`.  np2fasm should
emit a ROUTE directive matching that key.

LE_A defaults to symmetric LUT mask 0x6996 (XOR4) so the σ⁻¹ input-
axis canonicalization ambiguity at X4Y4N0 (Pitfall #16) does not
interfere with γ Bug #1 strip-fix validation.  Y=21 is σ⁻¹-clean for
LE_B.

For P5+ canon-2input validation, override with `--le-a-mask 0x4444`
+ `--canon-2input unique` (or `absolute`).  build_test will generate
a per-build Verilog copy in WORK with the requested LE_A INIT and pass
the matching `--canon-2input-{aware,unique-aware}` flag to np2fasm.

Usage:
  python3 scripts/sigcache_validation/build_test.py
  python3 scripts/sigcache_validation/build_test.py --le-a-mask 0x4444 \\
      --canon-2input unique

Output: tmp/sigcache_test/test_4_4_0_to_4_21_0_dataa.rbf
"""
import argparse
from pathlib import Path
import os, re, subprocess, sys

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
    ap = argparse.ArgumentParser()
    ap.add_argument("--le-a-mask", default="0x6996",
                    help="LE_A LUT INIT mask (hex, e.g. 0x6996 default, "
                         "0x4444 for !A&B canon_naandb).  When != 0x6996, "
                         "build_test writes a per-build Verilog copy in "
                         "WORK with the requested mask substituted.")
    ap.add_argument("--canon-2input", choices=("none", "absolute", "unique"),
                    default="none",
                    help="Forward `--canon-2input-aware` or "
                         "`--canon-2input-unique-aware` to np2fasm.  "
                         "Use `unique` for cross-LAB validation of the "
                         "P5c wire4-baseline-subtracted table; `absolute` "
                         "preserves the P2 single-LE silicon-validated "
                         "path.  Default `none` for symmetric-mask builds.")
    args = ap.parse_args()

    le_a_mask = int(args.le_a_mask, 16) & 0xFFFF
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

    src_verilog = SCRIPT_DIR / "test_2lut_clocked.v"
    if le_a_mask == 0x6996:
        verilog = src_verilog
    else:
        # Generate per-build copy with overridden LE_A INIT.  Keep the
        # on-disk source at the conservative symmetric default; this
        # override path makes asymmetric-mask builds fully reproducible
        # from CLI without an uncommitted Verilog edit.
        text = src_verilog.read_text()
        new_text = re.sub(
            r"(LUT\s+#\(\.K\(4\),\s*\.INIT\(16'h)6996(\)\)\s+le_a)",
            lambda m: f"{m.group(1)}{le_a_mask:04X}{m.group(2)}",
            text, count=1)
        if new_text == text:
            print(f"FAIL: could not substitute LE_A INIT in source Verilog",
                  file=sys.stderr)
            sys.exit(1)
        verilog = WORK / "test_2lut_clocked_override.v"
        verilog.write_text(new_text)
        print(f"  wrote LE_A INIT=0x{le_a_mask:04X} override → {verilog.name}")
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
    np_cmd = ["python3", str(REPO / "synth" / "np2fasm.py")]
    if args.canon_2input == "absolute":
        np_cmd.append("--canon-2input-aware")
    elif args.canon_2input == "unique":
        np_cmd.append("--canon-2input-unique-aware")
    np_cmd += [str(placed_json), str(fasm)]
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
