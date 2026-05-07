#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build: 24-bit LED heartbeat for AX301 — BLOCKED on
OUTROUTE_G15 X4Y17N14 mining (Path B not yet silicon-closed).

Two mining attempts (v1 swap + v6 buf_reg) silicon-FAILED 2026-05-07:
both produced bounded cell sets that passed validate_safe_for_hardware
but the resulting RBF flashed clean to AX301 with LED stuck ON (cnt[23]
→ G15 connection didn't form).  See memo
`path_b_v1_v6_silicon_failed_2026_05_07`.

Hypothesis: the chain-end LE (LCCOMB_X4_Y17_N14) has a structurally
different output topology than middle-chain LEs (the chain terminator
may use the cout pin or a special output mux that diff-based mining
doesn't isolate cleanly).  Future investigation needs domain knowledge
about Cyclone IV E chain-terminator output muxing or differential
silicon probing.

This script is kept (with led_blink24.v + the mining tool at
scripts/path_b_chain_mining/) so future sessions can iterate without
rebuilding the scaffolding.  Currently np2fasm warns
"no output route: SLICE X4Y17N14 -> PIN_G15" and the resulting RBF
will silicon-fail at G15.
"""
from pathlib import Path
import os, subprocess, sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "led_blink24"
OUT_RBF = REPO / "tmp" / "led_blink_open24.rbf"
LED_DRIVER_BEL = "SLICE_X4_Y17_N14"  # chain end for W=24; the newly-mined
                                     # OUTROUTE_G15 entry from Path B.


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
            ["bash", "-c", f"source {oss_env} && env"],
            text=True
        )
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    WORK.mkdir(parents=True, exist_ok=True)

    verilog = SCRIPT_DIR / "led_blink24.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data_nojb.json.gz"

    print("\n=== Step 1: Yosys synthesis ===", flush=True)
    yosys_json = WORK / "led_blink.json"
    yosys_script = f"""
read_verilog -lib {prims}
read_verilog {verilog}
hierarchy -check -top led_blink
proc
async2sync
opt -full
alumacc
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

    sys.path.insert(0, str(REPO / "fuzz"))
    from prepack_carry import compute_bel_map, emit_pre_place_hook  # type: ignore
    import json as _json
    yj_for_map = _json.loads(yosys_json.read_text())
    bel_map, prepack_warns = compute_bel_map(yj_for_map, mode="nextpnr")
    for w in prepack_warns:
        print(f"  prepack: {w}")
    print(f"  carry/DFF bel map: {len(bel_map)} entries")

    PIN_MAP = {
        "CLOCK$iob": "IOB_CLK_PIN_E1",
        "LED$iob":   "IOB_Q_PIN_G15",
    }
    extra_pin_lines = (
        f"\nPIN_MAP = {PIN_MAP!r}\n"
        f"LED_DRIVER_BEL = {LED_DRIVER_BEL!r}\n"
        "bound_io = 0\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first)\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], kv.second, npnr.STRENGTH_LOCKED)\n"
        "        bound_io += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "print(f'[pin_constraints] bound {bound_io}/{len(PIN_MAP)} IO cells')\n"
    )
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(emit_pre_place_hook(bel_map,
                                              extra_pin_lines=extra_pin_lines))
    print(f"  Generated combined pre-place hook "
          f"({len(bel_map)} carry/DFF + {len(PIN_MAP)} pin)")

    print("\n=== Step 2: nextpnr placement + routing ===", flush=True)
    if not chipdb_json.exists():
        print(f"ERROR: {chipdb_json} not found. Run:\n"
              f"  python3 fuzz/chipdb_gen.py --no-jailbreak --out-tag nojb")
        sys.exit(1)
    placed_json = WORK / "led_blink_placed.json"
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
                                   "cells", "bels", "placed",
                                   "routed", "slack", "info: program",
                                   "info: device", "led driver",
                                   "pin"]):
            print(f"  {line}")

    print("\n=== Step 3: np2fasm ===", flush=True)
    sys.path.insert(0, str(REPO / "synth"))
    sys.path.insert(0, str(REPO / "fuzz"))
    import json as _json
    from np2fasm import convert
    routed_data = _json.loads(placed_json.read_text())
    fasm_lines, warnings = convert(routed_data, baseline="pure")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path = WORK / "led_blink.fasm"
    fasm_path.write_text(fasm_text)
    print(f"  FASM: {len(fasm_lines)} lines -> {fasm_path}")
    if warnings:
        print(f"  Warnings: {len(warnings)}")
        for w in warnings[:30]:
            print(f"    {w}")
        # Check for cross-LAB ROUTE warnings (Pitfall #12)
        cross_lab_warns = [w for w in warnings if "no sig-cache (cross-LAB)" in w]
        if cross_lab_warns:
            print(f"\n  REFUSING TO BUILD: {len(cross_lab_warns)} cross-LAB ROUTE warning(s).")
            print("  These would emit cells at structurally wrong CRAM offsets")
            print("  (Pitfall #12, silicon-hostile).  Mine the missing sigcache")
            print("  entries first.")
            sys.exit(2)

    print("\n=== Step 4: fasm2rbf ===", flush=True)
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen
    base_rbf = make_pure_zero_rbf()
    result_rbf = bitgen(fasm_text, base_rbf, lenient=False)
    OUT_RBF.write_bytes(result_rbf)
    print(f"  RBF: {len(result_rbf)} bytes -> {OUT_RBF}")

    print("\n=== Step 5: validate_safe_for_hardware ===", flush=True)
    from bitstream import RouteCodec
    NV = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()
    try:
        RouteCodec().validate_safe_for_hardware(result_rbf, NV)
        print("  SAFE — flash with:")
        print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader "
              f"-c usb-blaster {OUT_RBF}")
    except Exception as e:
        print("  UNSAFE:")
        print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
