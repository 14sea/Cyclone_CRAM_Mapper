#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build of cross_lab.v using the X=33-enabled chipdb sidecar.

Variant of build_cross_lab.py that swaps in chipdb_ep4ce6_nojb_x33 (CE6
whitelist + X=33 only) and lets nextpnr place freely (no Stage_B BEL pin).

Goal: see whether nextpnr can route IOB E16/M16/G15 through X=33 LABs,
matching Quartus's natural single-LAB pack at X=33.  If the routing
fails, that empirically confirms IOB->X=33 + X=33->G15 sig-cache mining
is required before this attack vector can close the silicon gap.
"""
from pathlib import Path
import os, subprocess, sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "cross_lab_open_x33"
OUT_RBF = REPO / "tmp" / "cross_lab_open_x33.rbf"


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

    verilog = SCRIPT_DIR / "cross_lab.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb_x33.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data_nojb_x33.json.gz"
    if not chipdb_py.exists() or not chipdb_json.exists():
        raise SystemExit("chipdb_ep4ce6_nojb_x33 not found; run "
                         "fuzz/chipdb_gen.py --no-jailbreak --add-jailbreak-x 33 "
                         "--out-tag nojb_x33")

    print("\n=== Step 1: Yosys ===", flush=True)
    yosys_json = WORK / "cross_lab.json"
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
    print(r.stdout[-800:])

    # IOB pinning only — let nextpnr place LEs freely.
    print("\n=== Step 1b: pre-place hook (IOB pins only) ===", flush=True)
    PIN_MAP = {
        "clk$iob":  "IOB_CLK_PIN_E1",
        "key2$iob": "IOB_A_PIN_E16",
        "key3$iob": "IOB_B_PIN_M16",
        "led0$iob": "IOB_Q_PIN_G15",
    }
    pin_script = WORK / "pin_constraints.py"
    # Both LEs forced into a single LAB at X=33 (Quartus-pack mimic).
    # X33Y4 has N=0,N=2,N=4,N=6 mined in clk_lab_sel_per_le; pick N=4/N=6
    # which both have specific buckets, avoiding hard-error on LAB_CLK_SEL_LE.
    STAGE_A_BEL = os.environ.get("STAGE_A", "SLICE_X33_Y4_N4")
    STAGE_B_BEL = os.environ.get("STAGE_B", "SLICE_X33_Y4_N6")
    force_x33 = os.environ.get("FORCE_X33", "1") == "1"
    pin_script.write_text(
        f"import nextpnrpy_generic as npnr\n"
        f"PIN_MAP = {PIN_MAP!r}\n"
        f"FORCE_X33 = {force_x33}\n"
        f"STAGE_A_BEL = {STAGE_A_BEL!r}\n"
        f"STAGE_B_BEL = {STAGE_B_BEL!r}\n"
        "bound = 0\n"
        "led_iob = None\n"
        "slice_cells = []\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first); cell = kv.second\n"
        "    ctype = str(cell.type)\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], cell, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "        if name == 'led0$iob':\n"
        "            led_iob = cell\n"
        "        continue\n"
        "    if ctype != 'GENERIC_SLICE' or '$PACKER' in name:\n"
        "        continue\n"
        "    slice_cells.append((name, cell))\n"
        "if FORCE_X33:\n"
        "    led_drive_net = None\n"
        "    if led_iob is not None and 'I' in led_iob.ports:\n"
        "        pinfo = led_iob.ports['I']\n"
        "        if pinfo.net is not None:\n"
        "            led_drive_net = str(pinfo.net.name)\n"
        "    stage_b_cell = None\n"
        "    stage_a_candidates = []\n"
        "    for name, cell in slice_cells:\n"
        "        qnet = None\n"
        "        if 'Q' in cell.ports and cell.ports['Q'].net is not None:\n"
        "            qnet = str(cell.ports['Q'].net.name)\n"
        "        if qnet is not None and qnet == led_drive_net:\n"
        "            stage_b_cell = (name, cell)\n"
        "        else:\n"
        "            stage_a_candidates.append((name, cell))\n"
        "    if stage_b_cell is not None:\n"
        "        ctx.bindBel(STAGE_B_BEL, stage_b_cell[1], npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  Stage B {stage_b_cell[0]} -> {STAGE_B_BEL}')\n"
        "    for name, cell in stage_a_candidates:\n"
        "        try:\n"
        "            ctx.bindBel(STAGE_A_BEL, cell, npnr.STRENGTH_LOCKED)\n"
        "            bound += 1\n"
        "            print(f'  Stage A {name} -> {STAGE_A_BEL}')\n"
        "            break\n"
        "        except Exception as e:\n"
        "            print(f'  WARN: bind {name}: {e}')\n"
        "print(f'[pin_constraints] bound {bound} cells')\n"
    )

    print("\n=== Step 2: nextpnr ===", flush=True)
    placed_json = WORK / "cross_lab_placed.json"
    nextpnr_cmd = [
        "nextpnr-generic",
        "--json", str(yosys_json),
        "--pre-pack", str(chipdb_py),
        "--pre-place", str(pin_script),
        "--router", "router2",
        "--write", str(placed_json),
    ]
    try:
        r = run(nextpnr_cmd, cwd=WORK, env=env)
    except RuntimeError:
        print("\n[npnr-failed] Routing failure expected — IOB↔X=33 pips not "
              "modelled in nojb_x33 chipdb.")
        sys.exit(2)
    placement_summary = []
    for line in (r.stdout + r.stderr).splitlines():
        ll = line.lower()
        if any(k in ll for k in ["error", "warning", "utilisation",
                                  "placed", "routed", "slack", "pin",
                                  "stage", "slice_x"]):
            print(f"  {line}")
            placement_summary.append(line)
    # Read placed JSON to print final SLICE locations
    import json as _json
    placed = _json.loads(placed_json.read_text())
    print("\n=== Placed SLICE locations ===")
    for cn, cd in placed.get("modules", {}).get("top", {}).get(
            "cells", {}).items():
        attrs = cd.get("attributes", {})
        if cd.get("type") == "GENERIC_SLICE" and "NEXTPNR_BEL" in attrs:
            print(f"  {cn}: {attrs['NEXTPNR_BEL']}")

    print("\n=== Step 3: np2fasm ===", flush=True)
    sys.path.insert(0, str(REPO / "synth"))
    sys.path.insert(0, str(REPO / "fuzz"))
    from np2fasm import convert
    routed_data = _json.loads(placed_json.read_text())
    # baseline="nv" — X=33 LUT codec assumes the working buffer is at
    # nv_zero_global state when phase 2 runs.  NV_BASELINE_PACK has
    # 3350 missing cells (incomplete coverage of pure→nv delta) which
    # break the XOR-flip semantics for X=33's per-nibble cells.
    fasm_lines, warnings = convert(routed_data, baseline="nv")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path = WORK / "cross_lab.fasm"
    fasm_path.write_text(fasm_text)
    print(f"  FASM: {len(fasm_lines)} lines -> {fasm_path}")
    for w in warnings:
        print(f"  W: {w}")

    print("\n=== Step 4: fasm2rbf ===", flush=True)
    from fasm2rbf import bitgen
    base_rbf = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    result_rbf = bitgen(fasm_text, base_rbf, lenient=False)
    OUT_RBF.write_bytes(result_rbf)
    import hashlib
    print(f"  RBF: {len(result_rbf)} bytes -> {OUT_RBF}")
    print(f"  md5: {hashlib.md5(result_rbf).hexdigest()}")

    print("\n=== Step 5: SAFETY ===", flush=True)
    from bitstream import RouteCodec
    NV = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    try:
        RouteCodec().validate_safe_for_hardware(result_rbf, NV)
        print("  SAFE")
    except Exception as e:
        print(f"  UNSAFE: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
