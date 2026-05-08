#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""β' Step 2 — mine intra-LAB ROUTE 4,17,14 -> 4,17,16,dataa.

Source LE is the chain-end (Q_N=7 = LCCOMB_X4_Y17_N7) of a W=24 carry
chain at LAB(4,17).  Q_N=7 is chain-only — Quartus rejects standalone
LCCOMB placement there — so the standard two-LUT factory pattern
(`scripts/sigcache_remine/mine_x4_cross_lab_route.py`) cannot mine this
edge.  This miner uses chain-context: places the full W=24 chain pinned
at LAB(4,18)+(4,17) Q_N=0..7, plus a buffer LE pinned at Q_N=8
(LCCOMB_X4_Y17_N8 = sigcache our_n=16) reading the chain-end via dataa
through a pass-through LUT (lut_mask=0xAAAA).

Pair-delta isolates the cnt_top → buffer.dataa intra-LAB LI MUX cells:

  D_with: chain + buffer with buf_lut.dataa = cnt[chain_end_Q]
  D_idle: chain + buffer with buf_lut.dataa = 1'b0 (constant; no route)

Both share: chain LEs, IOB_IN E1 (CLK), IOB_OUT F15, buffer LE position,
buffer LUT mask 0xAAAA, cnt register topology.  Diff captures the LI
MUX activation cells unique to D_with's cnt_top → buffer.dataa edge.

Output: results/route_cells_full.json gains key
        '4,17,14->4,17,16,dataa' (or whatever the bit-23 chain end
        FF resolves to in our_n convention).  Sidecar
        results/intralab_route_x4y17_to_n16_mining.json with diagnostics.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "intralab_route_x4y17"
QUARTUS = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

ROUTE_CELLS_FULL = REPO / "results" / "route_cells_full.json"
NV_ROUTE_CELLS = REPO / "results" / "nv_route_cells.json"
SIDECAR = REPO / "results" / "intralab_route_x4y17_to_n16_mining.json"
NV_ZERO = REPO / "results" / "rbf" / "nv_zero_global.rbf"

# Sigcache convention (CORRECTED 2026-05-08): our_n = chipdb SLICE bel N
# = Quartus LCCOMB N = 2 × LE_index.  np2fasm emits OUTROUTE_G15 X{x}Y{y}N{sn}
# where sn is the chipdb SLICE bel N (in {0,2,...,30}).
# src = chain end at LE_7 = LCCOMB_X4_Y17_N14 + FF_X4_Y17_N15 → our_n=14
# dst = buffer  at LE_8 = LCCOMB_X4_Y17_N16                  → our_n=16
# (The earlier `our_n / 2 = Quartus_N` comment was wrong: it conflated
# Quartus LCCOMB N (0,2,...,30) with the LE index 0..15.)
SRC_KEY = (4, 17, 14)
DST_KEY = (4, 17, 16, "dataa")


def run(cmd, cwd, timeout=300):
    env = os.environ.copy()
    env["PATH"] = str(QUARTUS) + ":" + env["PATH"]
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True,
                          errors="replace", timeout=timeout, env=env)


def build(name: str, verilog: str, qsf_extra: str) -> bytes | None:
    bdir = WORK / name
    for sub in ("db", "incremental_db", "output_files"):
        p = bdir / sub
        if p.exists():
            shutil.rmtree(p)
    bdir.mkdir(parents=True, exist_ok=True)

    (bdir / f"{name}.v").write_text(verilog)
    qsf = f"""\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY {name}
set_global_assignment -name VERILOG_FILE {name}.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name SEED 1
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name RESERVE_ALL_UNUSED_PINS_WEAK_PULLUP "AS INPUT TRI-STATED WITH WEAK PULL-UP"
set_global_assignment -name CYCLONEII_RESERVE_NCEO_AFTER_CONFIGURATION "USE AS REGULAR IO"
{qsf_extra}
"""
    (bdir / f"{name}.qsf").write_text(qsf)
    (bdir / f"{name}.qpf").write_text(f'PROJECT_REVISION = "{name}"\n')

    print(f"\n--- Building {name} ---", flush=True)
    for step in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = run([step, "--read_settings_files=on",
                 "--write_settings_files=off", name], cwd=bdir)
        if r.returncode != 0:
            print(f"  FAIL {step} (rc={r.returncode})")
            print(r.stdout[-2500:])
            return None

    fit_rpt = bdir / "output_files" / f"{name}.fit.rpt"
    if fit_rpt.exists():
        text = fit_rpt.read_text(errors="replace")
        chain_locs = []
        for line in text.splitlines():
            if "X4_Y17" in line and ("LCCOMB" in line or "FF_" in line):
                chain_locs.append(line.strip()[:200])
        if chain_locs:
            print(f"  X4Y17 placements:")
            for line in chain_locs[:6]:
                print(f"    {line}")

    sof = bdir / "output_files" / f"{name}.sof"
    rbf = bdir / f"{name}.rbf"
    r = run([str(QUARTUS / "quartus_cpf"), "-c", "-o",
             "bitstream_compression=off", str(sof), str(rbf)], cwd=bdir)
    if r.returncode != 0:
        print(f"  cpf FAIL")
        return None
    return rbf.read_bytes()


def diff_cells(a: bytes, b: bytes) -> list[tuple[int, int]]:
    cells = []
    for off in range(32, min(len(a), len(b))):
        if off >= 367952:
            break
        frame = (off - 32) // 210
        pos = (off - 32) % 210
        if frame >= 25 and pos >= 208:  # CRC bytes (data frames only)
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.append((off, bp))
    return cells


def main():
    WORK.mkdir(parents=True, exist_ok=True)

    # W=24 chain at LAB(4,18) LE_0..15 (cnt[0..15]) + LAB(4,17) LE_0..7 (cnt[16..23]).
    # cnt[23] FF lands at FF_X4_Y17_N15 (chain auto-cascade); LCCOMB at LCCOMB_N14 (LE_7).
    # Buffer LE at LCCOMB_X4_Y17_N16 (LE_8) with pass-through LUT.
    # Convention (FIXED 2026-05-08): chipdb SLICE_N = Quartus LCCOMB_N = 2 × LE_index.
    #
    # Both designs pin the chain identically (24 FFs explicit at LAB(4,18) +
    # FFs at LAB(4,17) Q_N=0..6; cnt[23] auto-cascade).  Buffer LE pinned at
    # Q_N=8 in both.  Only difference: D_with passes cnt[23] to buffer.dataa;
    # D_idle ties buffer.dataa = 1'b0.
    #
    # Output side: F15 driven by buffer.combout in BOTH (so IOB_OUT cells
    # cancel).  G15 = const 0 in BOTH (so IOB_OUT G15 cells cancel).
    chain_pin_lab418 = "\n".join(
        f'set_location_assignment FF_X4_Y18_N{2*k+1}  -to "cnt[{k}]"'
        for k in range(16)
    )
    chain_pin_lab417 = "\n".join(
        f'set_location_assignment FF_X4_Y17_N{2*k+1}  -to "cnt[{16+k}]"'
        for k in range(7)  # cnt[16..22]; cnt[23] auto-cascade
    )

    qsf_common = f"""\
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_G15 -to LED0
set_location_assignment PIN_F15 -to LED_SEC
{chain_pin_lab418}
{chain_pin_lab417}
set_location_assignment LCCOMB_X4_Y17_N16 -to "buf_lut"
"""

    v_with = """\
module mine_with (input CLK, output LED0, output LED_SEC);
    (* keep = "true" *) reg [23:0] cnt = 24'h000000;
    always @(posedge CLK) cnt <= cnt + 24'd1;

    wire buf_out;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .dont_touch("on")) buf_lut (
        .dataa(cnt[23]),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(buf_out)
    );

    assign LED0    = 1'b0;
    assign LED_SEC = buf_out;
endmodule
"""

    v_idle = """\
module mine_idle (input CLK, output LED0, output LED_SEC);
    (* keep = "true" *) reg [23:0] cnt = 24'h000000;
    always @(posedge CLK) cnt <= cnt + 24'd1;

    wire buf_out;
    cycloneive_lcell_comb #(.lut_mask(16'hAAAA), .dont_touch("on")) buf_lut (
        .dataa(1'b0),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(buf_out)
    );

    // Force buf_lut to retain by also touching cnt elsewhere
    assign LED0    = cnt[0];     // pull cnt into the design (chain not trimmed)
    assign LED_SEC = buf_out;    // F15 driven from buf_lut (combout retained)
endmodule
"""

    nv = NV_ZERO.read_bytes()
    assert len(nv) == 368011

    rbf_with = build("mine_with", v_with, qsf_common)
    rbf_idle = build("mine_idle", v_idle, qsf_common)

    if rbf_with is None or rbf_idle is None:
        print("\nBUILD FAILED — see logs above")
        sys.exit(1)

    print("\n=== Pair-delta analysis ===")
    cells_with_vs_nv = diff_cells(rbf_with, nv)
    cells_idle_vs_nv = diff_cells(rbf_idle, nv)
    cells_with_vs_idle = diff_cells(rbf_with, rbf_idle)
    print(f"  with vs nv_zero: {len(cells_with_vs_nv)} cells")
    print(f"  idle vs nv_zero: {len(cells_idle_vs_nv)} cells")
    print(f"  with vs idle    : {len(cells_with_vs_idle)} cells (= candidate intra-LAB ROUTE)")

    def classify(cells):
        hdr = [c for c in cells if c[0] < 32 + 25 * 210]
        block = [c for c in cells if c[0] >= 32 + 1692 * 210]
        data = [c for c in cells if 32 + 25 * 210 <= c[0] < 32 + 1692 * 210]
        return hdr, data, block

    print()
    for name, cells in [
        ("with vs nv", cells_with_vs_nv),
        ("idle vs nv", cells_idle_vs_nv),
        ("with - idle", cells_with_vs_idle),
    ]:
        hdr, data, block = classify(cells)
        print(f"  {name:14}: total={len(cells):>5}  hdr={len(hdr):>3}  data={len(data):>4}  block={len(block):>3}")

    new_cells = sorted(set(cells_with_vs_idle))
    key = f"{SRC_KEY[0]},{SRC_KEY[1]},{SRC_KEY[2]}->{DST_KEY[0]},{DST_KEY[1]},{DST_KEY[2]},{DST_KEY[3]}"

    # Compare against neighboring intra-LAB entries for sanity
    sigcache = json.loads(ROUTE_CELLS_FULL.read_text())
    intra_lab_lens = []
    for k, v in sigcache.items():
        # parse "sx,sy,sn->dx,dy,dn,port"
        try:
            src_part, rest = k.split("->")
            sx, sy, sn = [int(x) for x in src_part.split(",")]
            parts = rest.rsplit(",", 1)
            dx, dy, dn = [int(x) for x in parts[0].split(",")]
            if sx == dx and sy == dy:
                intra_lab_lens.append(len(v))
        except Exception:
            pass
    intra_lab_lens.sort()
    if intra_lab_lens:
        med = intra_lab_lens[len(intra_lab_lens) // 2]
        p10 = intra_lab_lens[len(intra_lab_lens) // 10]
        p90 = intra_lab_lens[(9 * len(intra_lab_lens)) // 10]
        print(f"\n  intra-LAB sigcache reference (N={len(intra_lab_lens)}):"
              f" p10={p10}  median={med}  p90={p90}")
        print(f"  new entry size: {len(new_cells)} cells")

    # Sidecar
    sidecar = {
        "description": "β' Step 2 chain-context mining for intra-LAB ROUTE 4,17,14 -> 4,17,16,dataa",
        "method": "W=24 chain at LAB(4,18)+(4,17); buffer LE @ LCCOMB_X4_Y17_N8; mine_with vs mine_idle pair-delta isolates cnt[23] → buf_lut.dataa LI MUX",
        "src": list(SRC_KEY),
        "dst": list(DST_KEY),
        "key": key,
        "with_vs_nv_count": len(cells_with_vs_nv),
        "idle_vs_nv_count": len(cells_idle_vs_nv),
        "with_vs_idle_count": len(cells_with_vs_idle),
        "cells": [list(c) for c in new_cells],
        "intra_lab_reference": {
            "n": len(intra_lab_lens),
            "p10": intra_lab_lens[len(intra_lab_lens) // 10] if intra_lab_lens else None,
            "median": intra_lab_lens[len(intra_lab_lens) // 2] if intra_lab_lens else None,
            "p90": intra_lab_lens[(9 * len(intra_lab_lens)) // 10] if intra_lab_lens else None,
        },
    }
    SIDECAR.write_text(json.dumps(sidecar, indent=2))
    print(f"\n  Sidecar: {SIDECAR}")

    # Sanity gate before sigcache write — use loose bounds (intra-LAB ROUTE
    # cell counts span a wide range; other entries go from 50-200ish).
    if len(new_cells) < 30 or len(new_cells) > 400:
        print(f"\n  WARNING: new entry has {len(new_cells)} cells — out of"
              f" expected 30..400 range.  NOT auto-updating sigcache;"
              f" review sidecar before manual merge.")
        return

    print(f"\n=== Updating sigcache: {key!r} = {len(new_cells)} cells ===")

    # Write nv_route_cells.json (canonical source for the merger).
    if NV_ROUTE_CELLS.exists():
        nv_sigs = json.loads(NV_ROUTE_CELLS.read_text())
    else:
        nv_sigs = {}
    if key in nv_sigs:
        print(f"  WARN: nv_route_cells.json already has key {key!r} "
              f"({len(nv_sigs[key])} cells) — overwriting.")
    nv_sigs[key] = [list(c) for c in new_cells]
    tmp = NV_ROUTE_CELLS.with_suffix(NV_ROUTE_CELLS.suffix + ".tmp")
    tmp.write_text(json.dumps(nv_sigs))
    os.replace(tmp, NV_ROUTE_CELLS)
    print(f"  wrote → {NV_ROUTE_CELLS.relative_to(REPO)} "
          f"(now {len(nv_sigs)} entries)")

    # Patch route_cells_full.json directly so the entry takes effect now.
    if key in sigcache:
        print(f"  WARN: route_cells_full.json already has key {key!r} "
              f"({len(sigcache[key])} cells) — overwriting.")
    sigcache[key] = [list(c) for c in new_cells]
    tmp = ROUTE_CELLS_FULL.with_suffix(ROUTE_CELLS_FULL.suffix + ".tmp")
    tmp.write_text(json.dumps(sigcache))
    os.replace(tmp, ROUTE_CELLS_FULL)
    print(f"  wrote → {ROUTE_CELLS_FULL.relative_to(REPO)} "
          f"(now {len(sigcache)} entries)")


if __name__ == "__main__":
    main()
