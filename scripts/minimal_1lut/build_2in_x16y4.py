#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Open toolchain build at X16Y4N0 — 方案B test.

Yosys→nextpnr→np2fasm→fasm2rbf, then diff against Quartus gold (nv_full).
Goal: identify exactly which cells are missing from the open toolchain.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
WORK = REPO / "tmp" / "build_2in_x16y4"

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
    run(["yosys", "-s", str(WORK / "synth.ys")], cwd=WORK, env=env)

    # --- Pin constraints: force LUT at SLICE_X16_Y4_N0 ---
    PIN_MAP = {
        "KEY2$iob": "IOB_A_PIN_E16",
        "KEY3$iob": "IOB_B_PIN_M16",
        "LED0$iob": "IOB_Q_PIN_G15",
    }
    LUT_BEL = "SLICE_X16_Y4_N0"
    pin_script = WORK / "pin_constraints.py"
    pin_script.write_text(
        "import nextpnrpy_generic as npnr\n"
        "PIN_MAP = " + repr(PIN_MAP) + "\n"
        "LUT_BEL = " + repr(LUT_BEL) + "\n"
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

    # --- fasm2rbf ---
    print("\n=== fasm2rbf ===")
    from pure_zero_rbf import make_pure_zero_rbf
    from fasm2rbf import bitgen
    from bitstream import patch_rbf_crc
    base = make_pure_zero_rbf()
    open_rbf = bitgen(fasm_text, base, lenient=True)
    open_rbf = patch_rbf_crc(open_rbf)
    out_rbf = WORK / "design.rbf"
    Path(out_rbf).write_bytes(open_rbf)
    print(f"  RBF: {len(open_rbf)} bytes -> {out_rbf}")

    # --- Diff against Quartus gold ---
    gold_path = REPO / "tmp" / "mine_outroute_nv" / "nv_full" / "nv_full.rbf"
    if not gold_path.exists():
        print("\n  Gold not found — run mine_outroute_nv.py first")
        return

    gold = gold_path.read_bytes()
    nv = (REPO / "results" / "rbf" / "nv_zero_global.rbf").read_bytes()

    diff_bytes = sum(1 for a, b in zip(gold, open_rbf) if a != b)
    print(f"\n=== Open vs Gold: {diff_bytes} differing bytes ===")

    # Cell-level diff
    missing = []
    extra = []
    for off in range(32, min(len(gold), len(open_rbf))):
        if off >= 367952:
            break
        # DON'T skip pos 208-209 for header frames!
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        if frame >= 25 and pos >= 208:
            continue  # CRC for data frames only
        g = gold[off]
        o = open_rbf[off]
        if g != o:
            xor = g ^ o
            for bp in range(8):
                if xor & (1 << bp):
                    in_gold = bool(g & (1 << bp))
                    in_open = bool(o & (1 << bp))
                    in_nv = bool(nv[off] & (1 << bp))
                    gold_flipped = (in_gold != in_nv)
                    open_flipped = (in_open != in_nv)
                    if gold_flipped and not open_flipped:
                        missing.append((off, bp))
                    elif open_flipped and not gold_flipped:
                        extra.append((off, bp))
                    else:
                        missing.append((off, bp))

    def cls(cells):
        h = [c for c in cells if c[0] < 32 + 25 * 210]
        d = [c for c in cells if 32 + 25 * 210 <= c[0] < 32 + 1692 * 210]
        b = [c for c in cells if 32 + 1692 * 210 <= c[0]]
        return h, d, b

    mh, md, mb = cls(missing)
    eh, ed, eb = cls(extra)
    print(f"  Missing (in gold, not open): {len(missing)} "
          f"(hdr={len(mh)}, data={len(md)}, block={len(mb)})")
    print(f"  Extra (in open, not gold):   {len(extra)} "
          f"(hdr={len(eh)}, data={len(ed)}, block={len(eb)})")

    if missing:
        print(f"\n  Missing cells:")
        for off, bp in missing[:50]:
            frame = (off - 32) // 210
            pos = (off - 32) % 210
            band = "hdr" if frame < 25 else ("data" if frame < 1692 else "block")
            print(f"    ({off}, {bp})  frame={frame} pos={pos} band={band}")
        if len(missing) > 50:
            print(f"    ... and {len(missing) - 50} more")

    if extra:
        print(f"\n  Extra cells:")
        for off, bp in extra[:30]:
            frame = (off - 32) // 210
            pos = (off - 32) % 210
            band = "hdr" if frame < 25 else ("data" if frame < 1692 else "block")
            print(f"    ({off}, {bp})  frame={frame} pos={pos} band={band}")
        if len(extra) > 30:
            print(f"    ... and {len(extra) - 30} more")

    # Save analysis
    analysis = {
        "missing_cells": missing,
        "extra_cells": extra,
        "diff_bytes": diff_bytes,
        "fasm_lines": len(fasm_lines),
        "loc": "X16Y4N0",
    }
    (WORK / "gap_analysis.json").write_text(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
