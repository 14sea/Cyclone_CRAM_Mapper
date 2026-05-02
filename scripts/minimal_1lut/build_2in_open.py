#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build 2-input AND (KEY2 & KEY3 -> LED0) through the open toolchain,
matching Quartus loc_led placement at X6Y21N16.

Then diff against the Quartus loc_led gold to identify missing cells.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "minimal_2in_open"

sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(REPO / "synth"))


def run(cmd, cwd=None, env=None):
    print(f"  $ {' '.join(str(c) for c in cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None,
                       capture_output=True, text=True, errors="replace",
                       timeout=300, env=env)
    if r.returncode != 0:
        print(f"FAIL (rc={r.returncode})")
        if r.stdout:
            print(r.stdout[-3000:])
        if r.stderr:
            print(r.stderr[-3000:])
        sys.exit(1)
    return r


def get_oss_env():
    import os
    env = os.environ.copy()
    oss_env = Path.home() / "opt" / "oss-cad-suite" / "environment"
    if oss_env.exists():
        r = subprocess.run(
            ["bash", "-c", f"source {oss_env} && env"],
            capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                env[k] = v
    return env


def main():
    env = get_oss_env()
    WORK.mkdir(parents=True, exist_ok=True)

    verilog = SCRIPT_DIR / "passthrough_2in.v"
    techmap = REPO / "synth" / "ep4ce6_map.v"
    prims = REPO / "synth" / "prims.v"
    chipdb_py = REPO / "results" / "chipdb_ep4ce6.py"

    # --- Yosys ---
    print("=== Yosys ===")
    yosys_json = WORK / "design.json"
    yosys_script = f"""
read_verilog -lib {prims}
read_verilog {verilog}
hierarchy -check -top passthrough_2in
proc; opt -full; flatten; opt -full
techmap -map {techmap}; techmap; opt -fast
simplemap; abc -lut 4; clean
techmap -map {techmap}; opt_clean
simplemap t:$and t:$or t:$xor t:$xnor t:$not
techmap -map +/gate2lut.v -D LUT_WIDTH=4; clean
techmap -map {techmap}; opt_clean
delete t:$scopeinfo; clean; stat
write_json {yosys_json}
"""
    (WORK / "synth.ys").write_text(yosys_script)
    r = run(["yosys", "-s", str(WORK / "synth.ys")], cwd=WORK, env=env)
    # Show cell count
    for line in r.stdout.splitlines():
        if "cells" in line.lower() or "LUT" in line:
            print(f"  {line.strip()}")

    # --- Pin constraints: force LUT at X6Y21N16 ---
    PIN_MAP = {
        "KEY2$iob": "IOB_A_PIN_E16",
        "KEY3$iob": "IOB_B_PIN_M16",
        "LED0$iob": "IOB_Q_PIN_G15",
    }
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        "import nextpnrpy_generic as npnr\n"
        "PIN_MAP = " + repr(PIN_MAP) + "\n"
        "# Also force the LUT at X6Y21N16 (matching Quartus LCCOMB_X6_Y21_N8)\n"
        "LUT_BEL = 'SLICE_X6_Y21_N16'\n"
        "bound = 0\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first)\n"
        "    cell = kv.second\n"
        "    if name in PIN_MAP:\n"
        "        ctx.bindBel(PIN_MAP[name], cell, npnr.STRENGTH_LOCKED)\n"
        "        bound += 1\n"
        "        print(f'  pin {name} -> {PIN_MAP[name]}')\n"
        "    elif str(cell.type) in ('GENERIC_SLICE', 'LUT') and 'GND' not in name and 'VCC' not in name:\n"
        "        try:\n"
        "            ctx.bindBel(LUT_BEL, cell, npnr.STRENGTH_LOCKED)\n"
        "            bound += 1\n"
        "            print(f'  lut {name} -> {LUT_BEL}')\n"
        "        except Exception as e:\n"
        "            print(f'  WARN: cant bind {name} to {LUT_BEL}: {e}')\n"
        "print(f'[pin_constraints] bound {bound} cells')\n"
    )

    # --- nextpnr ---
    print("\n=== nextpnr ===")
    placed_json = WORK / "design_placed.json"
    r = run([
        "nextpnr-generic",
        "--json", str(yosys_json),
        "--pre-pack", str(chipdb_py),
        "--pre-place", str(pin_script),
        "--router", "router2",
        "--write", str(placed_json),
    ], cwd=WORK, env=env)
    for line in (r.stdout + r.stderr).splitlines():
        ll = line.lower()
        if any(k in ll for k in ["error", "warning", "placed", "routed",
                                   "info: program", "pin ", "lut "]):
            print(f"  {line}")

    # --- np2fasm ---
    print("\n=== np2fasm ===")
    from np2fasm import convert
    routed = json.loads(placed_json.read_text())
    fasm_lines, warnings = convert(routed, baseline="pure")
    fasm_text = "\n".join(fasm_lines) + "\n"
    fasm_path = WORK / "design.fasm"
    fasm_path.write_text(fasm_text)

    print(f"  FASM ({len(fasm_lines)} lines):")
    for l in fasm_lines:
        print(f"    {l}")
    if warnings:
        for w in warnings[:10]:
            print(f"  WARN: {w}")

    # Show placed bels
    for mod in routed.get("modules", {}).values():
        for cn, cc in mod.get("cells", {}).items():
            bel = cc.get("attributes", {}).get("NEXTPNR_BEL", "")
            if bel:
                print(f"  cell {cn}: bel={bel}")

    # --- fasm2rbf ---
    print("\n=== fasm2rbf ===")
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen
    base = make_pure_zero_rbf()
    open_rbf = bitgen(fasm_text, base, lenient=False)
    out_rbf = WORK / "design.rbf"
    out_rbf.write_bytes(open_rbf)
    print(f"  RBF: {len(open_rbf)} bytes -> {out_rbf}")

    # --- Diff against Quartus loc_led gold ---
    gold_rbf_path = REPO / "tmp" / "mine_outroute_loc" / "loc_led" / "loc_led.rbf"
    if not gold_rbf_path.exists():
        print("\n  Quartus gold not found — run mine_outroute_loc.py first")
        return

    gold = gold_rbf_path.read_bytes()
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()

    # Count byte diffs
    diff_bytes = sum(1 for a, b in zip(gold, open_rbf) if a != b)
    print(f"\n=== Open vs Quartus gold: {diff_bytes} differing bytes ===")

    # Cell-level diff
    missing = []  # in gold but not in open
    extra = []    # in open but not in gold
    for off in range(32, min(len(gold), len(open_rbf))):
        if off >= 367952:
            break
        if (off - 32) % 210 >= 208:
            continue
        g = gold[off]
        o = open_rbf[off]
        if g != o:
            xor = g ^ o
            for bp in range(8):
                if xor & (1 << bp):
                    in_gold = bool(g & (1 << bp))
                    in_open = bool(o & (1 << bp))
                    in_nv = bool(nv[off] & (1 << bp))
                    # "missing" = gold has it flipped from nv, open doesn't
                    gold_flipped = (in_gold != in_nv)
                    open_flipped = (in_open != in_nv)
                    if gold_flipped and not open_flipped:
                        missing.append((off, bp))
                    elif open_flipped and not gold_flipped:
                        extra.append((off, bp))
                    else:
                        # Both flipped from nv but differently — edge case
                        missing.append((off, bp))

    def classify(cells):
        h = [c for c in cells if c[0] < 32 + 25 * 210]
        d = [c for c in cells if 32 + 25 * 210 <= c[0] < 32 + 1692 * 210]
        b = [c for c in cells if 32 + 1692 * 210 <= c[0]]
        return h, d, b

    mh, md, mb = classify(missing)
    eh, ed, eb = classify(extra)
    print(f"  Missing from open (in gold): {len(missing)} cells "
          f"(hdr={len(mh)}, data={len(md)}, block={len(mb)})")
    print(f"  Extra in open (not in gold): {len(extra)} cells "
          f"(hdr={len(eh)}, data={len(ed)}, block={len(eb)})")

    if missing:
        print(f"\n  Missing cells (these are the output routing gap):")
        for off, bp in missing:
            frame = (off - 32) // 210
            pos = (off - 32) % 210
            band = "hdr" if frame < 25 else ("data" if frame < 1692 else "block")
            print(f"    ({off}, {bp})  frame={frame} pos={pos} band={band}")

    if extra:
        print(f"\n  Extra cells (open has these but gold doesn't):")
        for off, bp in extra[:30]:
            frame = (off - 32) // 210
            pos = (off - 32) % 210
            band = "hdr" if frame < 25 else ("data" if frame < 1692 else "block")
            print(f"    ({off}, {bp})  frame={frame} pos={pos} band={band}")
        if len(extra) > 30:
            print(f"    ... and {len(extra) - 30} more")

    # --- Create patched RBF with missing cells applied ---
    print(f"\n=== Creating patched RBF ===")
    patched = bytearray(open_rbf)
    for off, bp in missing:
        patched[off] ^= (1 << bp)

    # Re-patch CRC
    from bitstream import patch_rbf_crc
    patched = patch_rbf_crc(bytes(patched))

    patch_rbf_path = WORK / "design_patched.rbf"
    Path(patch_rbf_path).write_bytes(patched)

    # Verify patch matches gold
    patch_diff = sum(1 for a, b in zip(gold, patched) if a != b)
    print(f"  Patched vs gold: {patch_diff} differing bytes")

    # Save missing cells for output_route directive development
    result = {
        "missing_cells": missing,
        "extra_cells": extra,
        "src_bel": "X6Y21N16",
        "pin": "G15",
        "note": "missing = output routing + LUT port diff; extra = IOB/input routing differences",
    }
    (WORK / "diff_analysis.json").write_text(json.dumps(result, indent=2))

    print(f"\n  Open toolchain RBF: {out_rbf}")
    print(f"  Patched RBF:        {patch_rbf_path}")
    print(f"  Quartus gold:       {gold_rbf_path}")
    print(f"\n  Flash gold:    openFPGALoader -c usb-blaster {gold_rbf_path}")
    print(f"  Flash patched: openFPGALoader -c usb-blaster {patch_rbf_path}")


if __name__ == "__main__":
    main()
