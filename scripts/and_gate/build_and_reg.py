#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build of the registered AND gate at X16Y4N0.

Mirror of scripts/led_blink/build_open.py for the silicon-validated
non-arith reference design (HW-validated 2026-04-21):
  reg q; always @(posedge clk) q <= key2 & key3;

Pinned to:
  CLK   = PIN_E1   (GCLK_PIN-mined)
  KEY2  = PIN_E16
  KEY3  = PIN_M16
  LED0  = PIN_G15  (OUTROUTE_G15-mined; X16Y4N0 is one of 33 mined slices)

Byte-identity target: tmp/e2e_test/and_gate_reg_open.rbf
  md5 = f0eed1b2ae852214f70dea8020eede13
which is silicon-validated against Quartus gold (memory:
pipeline_test_e2e_status.md, 2026-04-21).
"""
from pathlib import Path
import os, subprocess, sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "and_gate_open"
OUT_RBF = REPO / "tmp" / "and_gate_reg_open_today.rbf"
LED_DRIVER_BEL = "SLICE_X16_Y4_N0"


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

    verilog = SCRIPT_DIR / "and_gate_reg.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data_nojb.json.gz"

    print("\n=== Step 1: Yosys ===", flush=True)
    yosys_json = WORK / "and_reg.json"
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

    print("\n=== Step 1b: pre-place hook ===", flush=True)
    PIN_MAP = {
        "clk$iob":  "IOB_CLK_PIN_E1",
        "key2$iob": "IOB_A_PIN_E16",
        "key3$iob": "IOB_B_PIN_M16",
        "led0$iob": "IOB_Q_PIN_G15",
    }
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        f"import nextpnrpy_generic as npnr\n"
        f"PIN_MAP = {PIN_MAP!r}\n"
        f"LED_DRIVER_BEL = {LED_DRIVER_BEL!r}\n"
        "bound = 0\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first); cell = kv.second\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], cell, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "    elif str(cell.type) == 'GENERIC_SLICE' and '$PACKER' not in name:\n"
        "        try:\n"
        "            ctx.bindBel(LED_DRIVER_BEL, cell, npnr.STRENGTH_LOCKED)\n"
        "            bound += 1\n"
        "            print(f'  slice {name} -> {LED_DRIVER_BEL}')\n"
        "        except Exception as e:\n"
        "            print(f'  WARN: bind {name}: {e}')\n"
        "print(f'[pin_constraints] bound {bound} cells')\n"
    )

    print("\n=== Step 2: nextpnr ===", flush=True)
    placed_json = WORK / "and_reg_placed.json"
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
                                  "placed", "routed", "slack", "pin"]):
            print(f"  {line}")

    print("\n=== Step 3: np2fasm ===", flush=True)
    sys.path.insert(0, str(REPO / "synth"))
    sys.path.insert(0, str(REPO / "fuzz"))
    import json as _json
    from np2fasm import convert
    routed_data = _json.loads(placed_json.read_text())
    fasm_lines, warnings = convert(routed_data, baseline="pure")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path = WORK / "and_reg.fasm"
    fasm_path.write_text(fasm_text)
    print(f"  FASM: {len(fasm_lines)} lines -> {fasm_path}")
    for w in warnings:
        print(f"  W: {w}")

    print("\n=== Step 4: fasm2rbf ===", flush=True)
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen
    base_rbf = make_pure_zero_rbf()
    result_rbf = bitgen(fasm_text, base_rbf, lenient=False)
    OUT_RBF.write_bytes(result_rbf)
    print(f"  RBF: {len(result_rbf)} bytes -> {OUT_RBF}")

    print("\n=== Step 5: byte-identity check ===", flush=True)
    ref_path = REPO / "tmp" / "e2e_test" / "and_gate_reg_open.rbf"
    if ref_path.exists():
        import hashlib
        ref = ref_path.read_bytes()
        diffs = [i for i in range(len(result_rbf)) if result_rbf[i] != ref[i]]
        print(f"  md5 today : {hashlib.md5(result_rbf).hexdigest()}")
        print(f"  md5 ref   : {hashlib.md5(ref).hexdigest()}")
        print(f"  byte diffs: {len(diffs)}")
        if diffs:
            print(f"  first 16 offsets: {diffs[:16]}")

    print("\n=== Step 6: SAFETY ===", flush=True)
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
