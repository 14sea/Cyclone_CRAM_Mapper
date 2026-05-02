#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build of a 2-stage cross-LAB register cascade.

Stage A (q1)  : SLICE_X16_Y8_N0  -- AND-LUT + DFF, dataa=key2, datab=key3
Stage B (led0): SLICE_X16_Y4_N0  -- buffer-LUT + DFF, dataa=q1, drives G15

Inter-LAB route X16Y8N0 -> X16Y4N0.dataa exercises the plain-route
sig-cache path (results/route_cells_full.json) that the arith pipeline
bypasses.  Same-column adjacent LAB is the simplest cross-LAB topology
with full 4-port mined coverage.

First-run output is silicon-validated by AX301 flash; resulting md5 then
serves as byte-identity anchor for future regression.
"""
from pathlib import Path
import os, subprocess, sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "cross_lab_open"
OUT_RBF = REPO / "tmp" / "cross_lab_open.rbf"

STAGE_A_BEL = "SLICE_X16_Y4_N0"
STAGE_B_BEL = "SLICE_X16_Y14_N0"


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
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data_nojb.json.gz"

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

    print("\n=== Step 1b: pre-place hook (connectivity-based Stage-B ID) ===", flush=True)
    PIN_MAP = {
        "clk$iob":  "IOB_CLK_PIN_E1",
        "key2$iob": "IOB_A_PIN_E16",
        "key3$iob": "IOB_B_PIN_M16",
        "led0$iob": "IOB_Q_PIN_G15",
    }
    # Stage B = the GENERIC_SLICE whose Q port shares a net with
    # led0$iob.I.  Cell names get rewritten by ABC LUT mapping, but
    # net connectivity is stable through pack.
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        f"import nextpnrpy_generic as npnr\n"
        f"PIN_MAP = {PIN_MAP!r}\n"
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
        "led_drive_net = None\n"
        "if led_iob is not None and 'I' in led_iob.ports:\n"
        "    pinfo = led_iob.ports['I']\n"
        "    if pinfo.net is not None:\n"
        "        led_drive_net = str(pinfo.net.name)\n"
        "        print(f'  led0$iob.I net = {led_drive_net}')\n"
        "stage_b_cell = None\n"
        "stage_a_candidates = []\n"
        "for name, cell in slice_cells:\n"
        "    qnet = None\n"
        "    if 'Q' in cell.ports and cell.ports['Q'].net is not None:\n"
        "        qnet = str(cell.ports['Q'].net.name)\n"
        "    if qnet is not None and qnet == led_drive_net:\n"
        "        stage_b_cell = (name, cell)\n"
        "    else:\n"
        "        stage_a_candidates.append((name, cell))\n"
        "if stage_b_cell is not None:\n"
        "    ctx.bindBel(STAGE_B_BEL, stage_b_cell[1], npnr.STRENGTH_LOCKED)\n"
        "    bound += 1\n"
        "    print(f'  Stage B {stage_b_cell[0]} -> {STAGE_B_BEL}')\n"
        "else:\n"
        "    print('  WARN: Stage B not identified by Q-net match')\n"
        "for name, cell in stage_a_candidates:\n"
        "    try:\n"
        "        ctx.bindBel(STAGE_A_BEL, cell, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  Stage A {name} -> {STAGE_A_BEL}')\n"
        "        break\n"
        "    except Exception as e:\n"
        "        print(f'  WARN: bind {name}: {e}')\n"
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
    r = run(nextpnr_cmd, cwd=WORK, env=env)
    for line in (r.stdout + r.stderr).splitlines():
        ll = line.lower()
        if any(k in ll for k in ["error", "warning", "utilisation",
                                  "placed", "routed", "slack", "pin",
                                  "stage"]):
            print(f"  {line}")

    print("\n=== Step 3: np2fasm ===", flush=True)
    sys.path.insert(0, str(REPO / "synth"))
    sys.path.insert(0, str(REPO / "fuzz"))
    import json as _json
    from np2fasm import convert
    routed_data = _json.loads(placed_json.read_text())
    fasm_lines, warnings = convert(routed_data, baseline="pure")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path = WORK / "cross_lab.fasm"
    fasm_path.write_text(fasm_text)
    print(f"  FASM: {len(fasm_lines)} lines -> {fasm_path}")
    for w in warnings:
        print(f"  W: {w}")
    print("---")
    for line in fasm_lines:
        print(f"  {line}")
    print("---")

    print("\n=== Step 4: fasm2rbf ===", flush=True)
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen
    base_rbf = make_pure_zero_rbf()
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
        print("  SAFE -- flash with:")
        print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader "
              f"-c usb-blaster {OUT_RBF}")
    except Exception as e:
        print(f"  UNSAFE: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
