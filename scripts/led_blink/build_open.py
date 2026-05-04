#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open-toolchain build: minimal LED heartbeat for AX301.

Pinned to coverage of the existing sigcache:
  - CLOCK = PIN_E1   (GCLK_PIN-mined)
  - LED   = PIN_G15  (OUTROUTE_G15-mined)

Forces nextpnr to place the LED-driving LE at X16Y4N0 (one of the
33 OUTROUTE_G15-capable slices) so np2fasm emits the OUTROUTE_G15
directive instead of skipping it as "missing".  Counter logic is
free to land anywhere in the 22 mined CE6 LAB columns; the formula
path handles intra-LAB and short cross-LAB routing.
"""
from pathlib import Path
import os, subprocess, sys

REPO = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "led_blink"
OUT_RBF = REPO / "tmp" / "led_blink_open.rbf"
LED_DRIVER_BEL = "SLICE_X4_Y4_N16"  # OUTROUTE_G15-mined slice OUTSIDE the
                                    # carry-chain region (LAB(4,18)+(4,17))
                                    # so prepack_carry never claims it.
                                    # The Verilog led_q buffer is bound here
                                    # by the pre-place hook (matches "led_q"
                                    # in cell name).  Without this, the LED
                                    # signal was driven by the chain-end DFF
                                    # cnt[23] at X4Y17N14 (UNMINED) → 0
                                    # OUTROUTE_G15 emitted → silicon stuck.


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
        # Source oss-cad-suite environment by reading exported PATH
        out = subprocess.check_output(
            ["bash", "-c", f"source {oss_env} && env"],
            text=True
        )
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    WORK.mkdir(parents=True, exist_ok=True)

    verilog = SCRIPT_DIR / "led_blink.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims   = REPO / "synth" / "prims.v"
    chipdb_py   = REPO / "results" / "chipdb_ep4ce6_nojb.py"
    chipdb_json = REPO / "results" / "chipdb_ep4ce6_data_nojb.json.gz"

    print("\n=== Step 1: Yosys synthesis ===", flush=True)
    yosys_json = WORK / "led_blink.json"
    # `alumacc` BEFORE the first techmap is required for $alu →
    # CE6_CARRY chain mapping; without it, $add falls through to
    # LUT4-ripple via simplemap+abc and the silicon-validated carry
    # codec doesn't fire.  See path_alpha_progress_2026_05_03_night.md.
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

    # --- Step 1b: Generate combined pre-place hook ---
    # Pre-place hook combines (a) carry-chain BEL pinning produced by
    # prepack_carry.compute_bel_map (avoids the chipdb/CE6_CARRY-vs-
    # GENERIC_SLICE wire-aliasing collision by selecting non-overlapping
    # N for DFFs; multi-LAB column descent for chains > 16 bits) with
    # (b) the existing IOB pin + LED-driver bindings.  We emit a single
    # --pre-place script because nextpnr-generic 0.10 resolves
    # NEXTPNR_BEL attributes during JSON read — before --pre-pack runs
    # — so the carry pins must be deferred to --pre-place.
    sys.path.insert(0, str(REPO / "fuzz"))
    from prepack_carry import compute_bel_map, emit_pre_place_hook  # type: ignore
    import json as _json
    yj_for_map = _json.loads(yosys_json.read_text())
    bel_map, prepack_warns = compute_bel_map(yj_for_map, mode="nextpnr")
    for w in prepack_warns:
        print(f"  prepack: {w}")
    print(f"  carry/DFF bel map: {len(bel_map)} entries")

    # Find the cell whose output drives the LED IOB input (a separate
    # registered buffer in the Verilog).  Yosys obliterates the user-
    # given `led_q` name during synthesis; we recover it by chasing the
    # LED$iob.I net back to its driving cell port.  Embedding the
    # resolved name into the pre-place hook lets us pin the buffer to a
    # known-mined OUTROUTE_G15 slice without depending on Yosys-preserved
    # names.
    led_driver_cell = None
    # In Yosys JSON the LED IOB isn't a cell yet — it's a top-module port.
    # Find the cell whose port (Q for DFF) drives the LED port net.  The
    # cell name in nextpnr after pack gets a `_DFFLC` suffix appended, so
    # we save both forms.
    top_mod = yj_for_map["modules"].get("led_blink") or next(
        m for m in yj_for_map["modules"].values() if m.get("cells"))
    led_port = top_mod.get("ports", {}).get("LED")
    cells = top_mod.get("cells", {})
    if led_port and led_port.get("bits"):
        led_bit = led_port["bits"][0]
        for name, c in cells.items():
            for port, conn in c.get("connections", {}).items():
                if isinstance(conn, list) and conn == [led_bit]:
                    if c.get("type") == "DFF" and port == "Q":
                        led_driver_cell = name
                        break
            if led_driver_cell:
                break
    # nextpnr-generic appends "_DFFLC" to DFF cells during pack; match
    # both raw and suffixed in the hook.
    led_driver_candidates = []
    if led_driver_cell:
        led_driver_candidates = [led_driver_cell, led_driver_cell + "_DFFLC"]
        print(f"  LED-driver cell (from JSON): {led_driver_cell!r} "
              f"(also try {led_driver_cell + '_DFFLC'!r})")
    else:
        print(f"  WARN: could not resolve LED driver cell — pre-place hook "
              f"will not bind LED_DRIVER_BEL")

    PIN_MAP = {
        "CLOCK$iob": "IOB_CLK_PIN_E1",
        "LED$iob":   "IOB_Q_PIN_G15",
    }
    extra_pin_lines = (
        f"\nPIN_MAP = {PIN_MAP!r}\n"
        f"LED_DRIVER_BEL = {LED_DRIVER_BEL!r}\n"
        f"LED_DRIVER_CANDIDATES = {led_driver_candidates!r}\n"
        "bound_io = 0\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first)\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], kv.second, npnr.STRENGTH_LOCKED)\n"
        "        bound_io += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "# Pin the LED-buffer LE (resolved from JSON in build_open.py — its\n"
        "# user-given `led_q` name is obliterated by Yosys, so we look up\n"
        "# the cell that drives LED$iob.I directly).  Pinning to a known-\n"
        "# mined OUTROUTE_G15 slice OUTSIDE the carry chain region\n"
        "# (X4Y4N16 by default) ensures np2fasm emits the OUTROUTE_G15\n"
        "# directive, fixing the silicon-stuck failure root cause.\n"
        "if LED_DRIVER_CANDIDATES:\n"
        "    bound_led = False\n"
        "    name_to_cell = {str(kv.first): kv.second for kv in ctx.cells}\n"
        "    for cand in LED_DRIVER_CANDIDATES:\n"
        "        cell = name_to_cell.get(cand)\n"
        "        if cell is None:\n"
        "            continue\n"
        "        if cell.bel:\n"
        "            print(f'  LED driver {cand} already bound to '\n"
        "                  f'{cell.bel} — skipping')\n"
        "            bound_led = True\n"
        "            break\n"
        "        try:\n"
        "            ctx.bindBel(LED_DRIVER_BEL, cell, npnr.STRENGTH_LOCKED)\n"
        "            print(f'  LED driver {cand} -> {LED_DRIVER_BEL}')\n"
        "            bound_led = True\n"
        "        except Exception as e:\n"
        "            print(f'  WARN: bind {cand} -> {LED_DRIVER_BEL}: {e}')\n"
        "        break\n"
        "    if not bound_led:\n"
        "        print(f'  WARN: none of {LED_DRIVER_CANDIDATES!r} found '\n"
        "              f'in ctx.cells — open RBF will likely have no '\n"
        "              f'OUTROUTE_G15 emitted')\n"
        "print(f'[pin_constraints] bound {bound_io}/{len(PIN_MAP)} IO cells')\n"
    )
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(emit_pre_place_hook(bel_map,
                                              extra_pin_lines=extra_pin_lines))
    print(f"  Generated combined pre-place hook "
          f"({len(bel_map)} carry/DFF + {len(PIN_MAP)} pin + LED driver)")

    # --- Step 1c: removed.  LED-driver placement is handled by the
    # prepack-emitted --pre-place hook (looks for a free GENERIC_SLICE
    # whose cell name contains "LED" after the carry chain has been
    # bound).  Pinning via JSON ``BEL`` attributes was retired because
    # nextpnr-generic 0.10 resolves NEXTPNR_BEL during JSON read —
    # before --pre-pack adds the chipdb bels — which crashes with
    # ``no bel named …``.

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

    # Silicon-hostile pattern guard (memory `d_i_silicon_failed_2026_05_04`):
    # cross-LAB ROUTE without sig-cache falls through to the formula path,
    # which emits cells at structurally wrong CRAM offsets (analogous to
    # the documented X=33 ROUTE formula failure).  These wrong cells
    # corrupt config-controller-validated cells → FPGA reset on flash
    # (NOT just functional incorrectness — the bitstream is rejected).
    # validate_safe_for_hardware does NOT detect this class.
    crosslab_misses = [w for w in warnings
                       if "no sig-cache (cross-LAB)" in w]
    if crosslab_misses:
        print(f"  REFUSE TO BUILD: {len(crosslab_misses)} cross-LAB ROUTE "
              f"sig-cache miss(es) — formula fallback is silicon-hostile "
              f"(causes FPGA config-controller reset on flash, "
              f"validated 2026-05-04).")
        for w in crosslab_misses:
            print(f"    {w}")
        print(f"  Mine the missing sig-cache entries via Quartus before "
              f"flashing, OR change placement so the route stays "
              f"intra-LAB (e.g., tap LED from a different chain bit).")
        sys.exit(1)

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
