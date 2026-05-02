#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain clone of x33_probe2 (Quartus silicon-validated 2026-05-04).

Quartus probe2: 1-LE E16(in)+E1(clk)+G15(out), FAST_OUTPUT_REGISTER OFF.
Quartus places at X=32+X=33; LED0 follows KEY2 inverted on AX301.

Open-toolchain plan:
  * Force placement at X33Y4N4 via --pre-place hook + STAGE_A BEL pin
  * Standard np2fasm emission (LAB_CLK_SEL_LE / LUT / etc.)
  * Append 29-cell OUTROUTE_G15 X=33 seed as raw BIT directives (since
    output_route_sigcache.json has no X33Y4 entry yet)
  * fasm2rbf → byte-diff vs Quartus probe2.rbf to measure residual gap
"""
from pathlib import Path
import os, subprocess, sys, json, hashlib

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "probe2_open"
OUT_RBF = REPO / "tmp" / "probe2_open.rbf"
QUARTUS_REF = REPO / "results" / "rbf" / "x33_probe2_silicon_validated.rbf"
SEED_PATH = REPO / "results" / "cross_lab_gap" / "diffs" / "x33_outroute_g15_seed.json"

STAGE_A_BEL = os.environ.get("STAGE_A", "SLICE_X33_Y4_N4")


def run(cmd, **kw):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        print("STDOUT:", r.stdout)
        print("STDERR:", r.stderr)
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

    # probe2 Verilog: 1-LE E16->DFF->G15
    verilog = WORK / "probe2.v"
    verilog.write_text("""\
module top(input wire clk, input wire key2, output reg led0);
    always @(posedge clk) led0 <= key2;
endmodule
""")
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb_x33.py"

    print("\n=== Step 1: Yosys ===", flush=True)
    yosys_json = WORK / "probe2.json"
    yosys_script = f"""
read_verilog -lib {prims}
read_verilog {verilog}
hierarchy -check -top top
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
delete t:$scopeinfo
clean
stat
write_json {yosys_json}
"""
    yosys_ys = WORK / "synth.ys"
    yosys_ys.write_text(yosys_script)
    r = run(["yosys", "-s", str(yosys_ys)], cwd=WORK, env=env)
    print(r.stdout[-300:])

    print("\n=== Step 1b: pre-place hook (force X33Y4N4) ===", flush=True)
    PIN_MAP = {
        "clk$iob":  "IOB_CLK_PIN_E1",
        "key2$iob": "IOB_A_PIN_E16",
        "led0$iob": "IOB_Q_PIN_G15",
    }
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        f"import nextpnrpy_generic as npnr\n"
        f"PIN_MAP = {PIN_MAP!r}\n"
        f"STAGE_A_BEL = {STAGE_A_BEL!r}\n"
        "bound = 0\n"
        "le_cells = []\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first); cell = kv.second\n"
        "    ctype = str(cell.type)\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], cell, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "        continue\n"
        "    if ctype != 'GENERIC_SLICE' or '$PACKER' in name:\n"
        "        continue\n"
        "    le_cells.append((name, cell))\n"
        "for name, cell in le_cells:\n"
        "    try:\n"
        "        ctx.bindBel(STAGE_A_BEL, cell, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  LE {name} -> {STAGE_A_BEL}')\n"
        "        break\n"
        "    except Exception as e:\n"
        "        print(f'  WARN: bind {name}: {e}')\n"
        "print(f'[pin_constraints] bound {bound} cells')\n"
    )

    print("\n=== Step 2: nextpnr ===", flush=True)
    placed_json = WORK / "probe2_placed.json"
    nextpnr_cmd = [
        "nextpnr-generic",
        "--json", str(yosys_json),
        "--pre-pack", str(chipdb_py),
        "--pre-place", str(pin_script),
        "--router", "router2",
        "--write", str(placed_json),
    ]
    r = run(nextpnr_cmd, cwd=WORK, env=env)
    for line in (r.stdout + r.stderr).splitlines():
        ll = line.lower()
        if any(k in ll for k in ["error", "warning", "utilisation",
                                  "placed", "routed", "pin", "slice_x"]):
            print(f"  {line}")

    print("\n=== Step 3: np2fasm (baseline=nv) ===", flush=True)
    sys.path.insert(0, str(REPO / "synth"))
    sys.path.insert(0, str(REPO / "fuzz"))
    from np2fasm import convert
    routed_data = json.loads(placed_json.read_text())
    # baseline=nv: use nv_zero_global.rbf as base, skip NV_BASELINE_PACK directive
    # (which has not been silicon-validated as equivalent to nv_zero_global,
    # per CLAUDE.md "HW flash equivalence not yet confirmed")
    fasm_lines, warnings = convert(routed_data, baseline="nv")
    print(f"  np2fasm output: {len(fasm_lines)} FASM lines, {len(warnings)} warnings")
    for w in warnings:
        print(f"  W: {w}")

    # OUTROUTE_G15 X33Y4N4 is now registered in output_route_sigcache.json
    # (provisional entry, 29-cell seed) — np2fasm should have emitted both
    # OUTROUTE_G15 + IOB_PAD_NV.  No raw BIT seed needed.
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path = WORK / "probe2.fasm"
    fasm_path.write_text(fasm_text)

    print("\n=== Step 4: fasm2rbf (base=nv_zero_global) ===", flush=True)
    from fasm2rbf import bitgen
    base_rbf = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    result_rbf = bitgen(fasm_text, base_rbf, lenient=True)  # lenient: skip-not-found
    OUT_RBF.write_bytes(result_rbf)
    print(f"  RBF: {len(result_rbf)} bytes -> {OUT_RBF}")
    md5_open = hashlib.md5(result_rbf).hexdigest()
    print(f"  md5(open): {md5_open}")

    print("\n=== Step 5: byte-diff vs Quartus probe2 ===", flush=True)
    if not QUARTUS_REF.exists():
        print(f"  Quartus reference not found: {QUARTUS_REF}")
        sys.exit(1)
    quartus = QUARTUS_REF.read_bytes()
    md5_q = hashlib.md5(quartus).hexdigest()
    print(f"  md5(Quartus probe2): {md5_q}")
    if md5_open == md5_q:
        print("  *** BYTE-IDENTICAL — open toolchain matches Quartus probe2 ***")
        return
    diff_bits = sum(bin(a ^ b).count("1") for a, b in zip(result_rbf, quartus))
    diff_bytes = sum(1 for a, b in zip(result_rbf, quartus) if a != b)
    print(f"  diff: {diff_bits} bits across {diff_bytes} bytes")

    # Region-level breakdown
    NV = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    # Use extract_gap-style classifier
    diff_cells = []
    for off in range(len(result_rbf)):
        d = result_rbf[off] ^ quartus[off]
        if d:
            for bp in range(8):
                if d & (1 << bp):
                    diff_cells.append((off, bp))

    def region(off):
        if off < 32:
            return "preamble"
        if (off - 32) < 5200:
            return "header"
        if off > len(result_rbf) - 59:
            return "postamble"
        if (off - 32) % 210 >= 208:
            return "crc"
        return "fabric"

    from collections import Counter
    rc = Counter(region(off) for off, _ in diff_cells)
    print(f"  by region: {dict(rc)}")

    # Save the gap
    gap_out = REPO / "tmp" / "probe2_open_gap.json"
    gap_out.write_text(json.dumps({
        "open_md5": md5_open,
        "quartus_md5": md5_q,
        "diff_bits": diff_bits,
        "diff_bytes": diff_bytes,
        "by_region": dict(rc),
        "cells": diff_cells,
    }, indent=2))
    print(f"  wrote {gap_out}")

    print("\n=== Step 6: SAFETY (validate before flash) ===", flush=True)
    from bitstream import RouteCodec
    try:
        RouteCodec().validate_safe_for_hardware(result_rbf, NV)
        print("  SAFE — flash with:")
        print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader -c usb-blaster {OUT_RBF}")
    except Exception as e:
        print(f"  UNSAFE: {e}")


if __name__ == "__main__":
    main()
