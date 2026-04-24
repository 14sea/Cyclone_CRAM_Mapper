# SPDX-License-Identifier: GPL-3.0-or-later
"""Quartus-gold M9K_MODE mining — replaces the `inferred_goldintersect`
buckets (which were proven site-invariant fabric-safe overlays rather
than real mode cells — see memory `m9k_mode_gi_bucket_not_quartus_encoding.md`).

Per (width, depth) we build:
  * a matched baseline (same pinout, NO M9K, trivial passthrough)
  * N variants that share the SAME pinout + SAME M9K LOC (altsyncram `u`),
    but vary the INIT pattern and read-pipe depth

Per-variant mode cells =
    block_band(variant_i.rbf ⊕ matched_baseline.rbf)

Site-fixed (X15, Y10, N0), mode-invariant cells =
    intersection over all variants

These land in `results/m9k_mode_bits.json`
   → X15_Y10_N0_{W}x{D}.cells_by_template['quartus_gold']

Usage:
    python3 scripts/m9k_mode_quartus_gold_mine.py --width 4 --depth 2048
    python3 scripts/m9k_mode_quartus_gold_mine.py --all --workers 3
    python3 scripts/m9k_mode_quartus_gold_mine.py --only-analyze --all
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from compile import setup_project, compile_full, generate_rbf

PREAMBLE = 32
FRAME = 210
DATA_PER_FRAME = 208
BLOCK_FRAME_LO = 1692
BLOCK_FRAME_HI = 1738

WORK_ROOT = ROOT / "tmp" / "m9k_mode_quartus_gold"
RESULTS_PATH = ROOT / "results" / "m9k_mode_bits.json"

DEFAULT_SITE_X = 15
DEFAULT_SITE_Y = 10
DEFAULT_SITE_N = 0
# Populated by main() from --site; used by _qsf_variant / _mine_one.
SITE_X = DEFAULT_SITE_X
SITE_Y = DEFAULT_SITE_Y
SITE_N = DEFAULT_SITE_N

TARGET_COMBOS = [
    (4, 2048),
    (9, 512),
    (18, 512),
    (9, 1024),
    (36, 256),
]

PIN_POOL = [
    "PIN_E15", "PIN_E16", "PIN_M16", "PIN_M15",
    "PIN_A8",  "PIN_A11", "PIN_A14", "PIN_B14",
    "PIN_T2",  "PIN_T8",  "PIN_R1",  "PIN_R5",
    "PIN_R9",  "PIN_R13", "PIN_R16", "PIN_P1",
    "PIN_P9",  "PIN_P15", "PIN_T13",
    "PIN_F15", "PIN_B16", "PIN_G16", "PIN_K15",
    "PIN_K16", "PIN_L15", "PIN_L16", "PIN_N16",
    "PIN_D16", "PIN_D15", "PIN_C15", "PIN_C16",
    "PIN_F14", "PIN_F16", "PIN_J14", "PIN_J15",
    "PIN_J16", "PIN_T3",  "PIN_T7",  "PIN_T12",
    "PIN_T15", "PIN_P3",  "PIN_P11", "PIN_P16",
    "PIN_N2",  "PIN_N14",
]


def _addr_bits(depth: int) -> int:
    return max(1, int(math.ceil(math.log2(depth))))


def _fold_width(width: int) -> int:
    # Cap external bus at 9 pins; wider M9K modes XOR-fold internally.
    return min(width, 9)


def _port_signals(width: int, depth: int) -> list[str]:
    addr_bits = _addr_bits(depth)
    ew = _fold_width(width)
    sigs = ["CLK", "WE"]
    sigs += [f"ADDR{i}" for i in range(addr_bits)]
    sigs += [f"DIN{i}" for i in range(ew)]
    sigs += [f"DOUT{i}" for i in range(ew)]
    return sigs


def _pin_map(width: int, depth: int) -> dict[str, str]:
    sigs = _port_signals(width, depth)
    if len(sigs) > 1 + len(PIN_POOL):
        raise ValueError(f"{width}x{depth}: {len(sigs)} signals > pin budget")
    pins: dict[str, str] = {"CLK": "PIN_E1"}
    remain = [p for p in PIN_POOL]
    for s in sigs:
        if s == "CLK":
            continue
        pins[s] = remain.pop(0)
    return pins


def _port_decl(width: int, depth: int) -> str:
    parts: list[str] = []
    for s in _port_signals(width, depth):
        if s.startswith("DOUT"):
            parts.append(f"output {s}")
        else:
            parts.append(f"input {s}")
    return ",\n    ".join(parts)


def _qsf_common(project: str, width: int, depth: int) -> list[str]:
    lines = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        "set_global_assignment -name DEVICE EP4CE6F17C8",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
    ]
    for sig, pin in _pin_map(width, depth).items():
        lines.append(f"set_location_assignment {pin} -to {sig}")
    return lines


def _qsf_variant(project: str, width: int, depth: int) -> str:
    lines = _qsf_common(project, width, depth)
    # altsyncram instance `u`; LOC pins it to the M9K block site.
    lines.append(
        f'set_location_assignment M9K_X{SITE_X}_Y{SITE_Y}_N{SITE_N} -to "u"'
    )
    return "\n".join(lines) + "\n"


def _qsf_baseline(project: str, width: int, depth: int) -> str:
    return "\n".join(_qsf_common(project, width, depth)) + "\n"


def _init_mif(width: int, depth: int, variant: int) -> str:
    mask = (1 << width) - 1
    lines = [
        f"DEPTH = {depth};",
        f"WIDTH = {width};",
        "ADDRESS_RADIX = HEX;",
        "DATA_RADIX = HEX;",
        "CONTENT BEGIN",
    ]
    nibbles = (width + 3) // 4
    addr_nibbles = max(1, (_addr_bits(depth) + 3) // 4)
    for i in range(depth):
        if variant == 0:
            v = i & mask
        elif variant == 1:
            v = (~i) & mask
        else:
            v = (i ^ 0x5A5A5A5A) & mask
        lines.append(f"  {i:0{addr_nibbles}X} : {v:0{nibbles}X};")
    lines.append("END;")
    return "\n".join(lines) + "\n"


def _verilog_variant(width: int, depth: int, variant: int) -> str:
    """altsyncram template with instance name `u` (for LOC stability)."""
    addr_bits = _addr_bits(depth)
    ew = _fold_width(width)

    addr_bus = ", ".join(f"ADDR{i}" for i in range(addr_bits - 1, -1, -1))
    if width <= ew:
        din_bus = ", ".join(f"DIN{i}" for i in range(width - 1, -1, -1))
        din_expr = f"{{{din_bus}}}"
        dout_assign = ", ".join(f"DOUT{i}" for i in range(width - 1, -1, -1))
        dout_stmt = f"    assign {{{dout_assign}}} = dout_r;"
    else:
        reps = (width + ew - 1) // ew
        din_parts = ", ".join(f"DIN{i}" for i in range(ew - 1, -1, -1))
        repl = f"{{{reps}{{{{{din_parts}}}}}}}"
        if reps * ew > width:
            repl += f"[{width - 1}:0]"
        din_expr = repl
        fold_parts = []
        for i in range(0, width, ew):
            hi = min(i + ew - 1, width - 1)
            if hi - i + 1 == ew:
                fold_parts.append(f"dout_r[{hi}:{i}]")
            else:
                fold_parts.append(
                    f"{{{ew - (hi - i + 1)}'b0, dout_r[{hi}:{i}]}}"
                )
        xor_expr = " ^ ".join(fold_parts)
        dout_assign = ", ".join(f"DOUT{i}" for i in range(ew - 1, -1, -1))
        dout_stmt = f"    assign {{{dout_assign}}} = {xor_expr};"

    # Variant 2 inserts an extra pipeline stage after dout_r
    extra_pipe = ""
    if variant == 2:
        extra_pipe = f"""
    reg [{width-1}:0] dout_q;
    always @(posedge CLK) dout_q <= dout_r;
"""
        if width <= ew:
            dout_stmt = f"    assign {{{', '.join(f'DOUT{i}' for i in range(width-1,-1,-1))}}} = dout_q;"
        else:
            fold_parts = []
            for i in range(0, width, ew):
                hi = min(i + ew - 1, width - 1)
                if hi - i + 1 == ew:
                    fold_parts.append(f"dout_q[{hi}:{i}]")
                else:
                    fold_parts.append(
                        f"{{{ew - (hi - i + 1)}'b0, dout_q[{hi}:{i}]}}"
                    )
            xor_expr = " ^ ".join(fold_parts)
            dout_assign = ", ".join(f"DOUT{i}" for i in range(ew - 1, -1, -1))
            dout_stmt = f"    assign {{{dout_assign}}} = {xor_expr};"

    return f"""\
// Auto-generated altsyncram template variant v{variant} ({width},{depth}).
module fuzz_top(
    {_port_decl(width, depth)}
);
    wire [{addr_bits-1}:0] addr = {{{addr_bus}}};
    wire [{width-1}:0]     din  = {din_expr};
    wire [{width-1}:0]     dout;
    reg  [{width-1}:0]     dout_r;
    always @(posedge CLK) dout_r <= dout;
{dout_stmt}
{extra_pipe}

    altsyncram #(
        .operation_mode("SINGLE_PORT"),
        .width_a({width}), .widthad_a({addr_bits}), .numwords_a({depth}),
        .lpm_type("altsyncram"),
        .ram_block_type("M9K"),
        .outdata_reg_a("UNREGISTERED"),
        .read_during_write_mode_port_a("OLD_DATA"),
        .read_during_write_mode_mixed_ports("DONT_CARE"),
        .indata_reg_b("CLOCK1"),
        .wrcontrol_wraddress_reg_b("CLOCK1"),
        .rdcontrol_reg_b("CLOCK1"),
        .address_reg_b("CLOCK1"),
        .outdata_reg_b("UNREGISTERED"),
        .byteena_reg_b("CLOCK1"),
        .clock_enable_input_a("NORMAL"),
        .clock_enable_output_a("NORMAL"),
        .init_file("mem_init.mif"),
        .intended_device_family("Cyclone IV E")
    ) u (
        .clock0(CLK), .address_a(addr), .data_a(din),
        .wren_a(WE), .q_a(dout),
        .aclr0(1'b0), .aclr1(1'b0),
        .addressstall_a(1'b0), .addressstall_b(1'b0),
        .byteena_a(1'b1), .byteena_b(1'b1),
        .address_b({{{addr_bits}{{1'b0}}}}), .data_b({{{width}{{1'b0}}}}),
        .clock1(1'b1), .clocken0(1'b1), .clocken1(1'b1),
        .clocken2(1'b1), .clocken3(1'b1), .eccstatus(),
        .q_b(), .rden_a(1'b1), .rden_b(1'b1), .wren_b(1'b0)
    );
endmodule
"""


def _verilog_baseline(width: int, depth: int) -> str:
    ew = _fold_width(width)
    addr_bits = _addr_bits(depth)
    lines = []
    for i in range(ew):
        srcs = ["CLK", "WE", f"ADDR{i % addr_bits}", f"DIN{i % ew}"]
        lines.append(f"    assign DOUT{i} = " + " ^ ".join(srcs) + ";")
    body = "\n".join(lines)
    return f"""\
// Auto-generated baseline (no M9K) matched pinout for ({width},{depth}).
module fuzz_top(
    {_port_decl(width, depth)}
);
{body}
endmodule
"""


def _block_band_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    if len(a) != len(b):
        raise ValueError(f"length mismatch {len(a)} vs {len(b)}")
    out: set[tuple[int, int]] = set()
    lo = PREAMBLE + BLOCK_FRAME_LO * FRAME
    hi = PREAMBLE + (BLOCK_FRAME_HI + 1) * FRAME
    for off in range(lo, hi):
        if (off - PREAMBLE) % FRAME >= DATA_PER_FRAME:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bit in range(8):
            if x & (1 << bit):
                out.add((off, bit))
    return out


def _build_one(args) -> tuple[str, str | None, str]:
    project, proj_work, verilog, qsf, mif_text = args
    proj_dir = setup_project(project, verilog, qsf, str(proj_work))
    if mif_text is not None:
        (Path(proj_dir) / "mem_init.mif").write_text(mif_text)
    ok, el, err = compile_full(project, proj_dir, timeout=300)
    if not ok:
        return project, None, f"{err} ({el:.1f}s)"
    rbf = generate_rbf(project, proj_dir,
                       os.path.join(proj_work, f"{project}.rbf"))
    if rbf is None:
        return project, None, "RBF generation failed"
    return project, rbf, ""


def _mine_one(width: int, depth: int, n_variants: int,
              workers: int, only_analyze: bool) -> dict:
    combo_tag = f"{width}x{depth}"
    work = WORK_ROOT / combo_tag
    work.mkdir(parents=True, exist_ok=True)

    print(f"\n=== mining ({width},{depth}) @ X{SITE_X}_Y{SITE_Y}_N{SITE_N} ===")
    baseline_proj = f"m9k_mode_gold_{combo_tag}_baseline"
    variant_projs = [f"m9k_mode_gold_{combo_tag}_v{i}" for i in range(n_variants)]

    jobs = []
    jobs.append((baseline_proj, work, _verilog_baseline(width, depth),
                 _qsf_baseline(baseline_proj, width, depth), None))
    for i, p in enumerate(variant_projs):
        jobs.append((p, work, _verilog_variant(width, depth, i),
                     _qsf_variant(p, width, depth),
                     _init_mif(width, depth, i)))

    if not only_analyze:
        print(f"[mine] building {len(jobs)} specimens (workers={workers})",
              flush=True)
        with mp.Pool(processes=max(1, workers)) as pool:
            results = list(pool.imap_unordered(_build_one, jobs))
        for proj, rbf, err in results:
            if rbf is None:
                print(f"  FAIL {proj}: {err}")
            else:
                print(f"  OK   {proj} -> {Path(rbf).name}")
        fails = [r for r in results if r[1] is None]
        if fails:
            return {"width": width, "depth": depth, "error": "build_failures",
                    "fails": [r[0] for r in fails]}

    def _rbf_for(proj: str) -> Path:
        return work / f"{proj}.rbf"

    bl_path = _rbf_for(baseline_proj)
    if not bl_path.exists():
        return {"width": width, "depth": depth,
                "error": f"baseline RBF missing: {bl_path}"}
    bl_bytes = bl_path.read_bytes()
    per_variant: list[set[tuple[int, int]]] = []
    per_variant_size: list[int] = []
    for p in variant_projs:
        vp = _rbf_for(p)
        if not vp.exists():
            print(f"  SKIP {p}: RBF missing")
            continue
        v = vp.read_bytes()
        cells = _block_band_cells(bl_bytes, v)
        per_variant.append(cells)
        per_variant_size.append(len(cells))
        print(f"  {p}: {len(cells)} block-band cells vs matched baseline")

    if not per_variant:
        return {"width": width, "depth": depth, "error": "no variants built"}

    gold_cells = set.intersection(*per_variant)
    print(f"[mine] intersection across {len(per_variant)} builds: "
          f"{len(gold_cells)} cells  (sizes={per_variant_size})")

    if RESULTS_PATH.exists():
        mode_bits = json.loads(RESULTS_PATH.read_text())
    else:
        mode_bits = {}
    key = f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}_{combo_tag}"
    entry = mode_bits.get(key, {
        "site": f"X{SITE_X}_Y{SITE_Y}_N{SITE_N}",
        "width": width,
        "depth": depth,
    })
    cbt = entry.get("cells_by_template", {})
    cbt["quartus_gold"] = sorted(gold_cells)
    entry["cells_by_template"] = cbt
    # Preserve legacy gi / inferred / altsyncram buckets if this is a
    # first-time entry at (X15, Y10) for this (w, d); copy them from
    # any sibling site with the same geometry so downstream loaders
    # (tests, fasm2rbf fallback path) keep working.
    suffix = f"_{combo_tag}"
    for sibling_key, sibling_entry in mode_bits.items():
        if sibling_key == key or not sibling_key.endswith(suffix):
            continue
        sibling_cbt = sibling_entry.get("cells_by_template", {})
        for bucket in ("altsyncram", "inferred", "inferred_goldintersect"):
            if bucket in sibling_cbt and bucket not in cbt:
                cbt[bucket] = list(sibling_cbt[bucket])
        if "cells" in sibling_entry and "cells" not in entry:
            entry["cells"] = list(sibling_entry["cells"])
        break
    entry["quartus_gold_source"] = {
        "date": time.strftime("%Y-%m-%d"),
        "script": "scripts/m9k_mode_quartus_gold_mine.py",
        "n_variants": len(per_variant),
        "variant_sizes": per_variant_size,
        "variants": variant_projs,
        "baseline_proj": baseline_proj,
        "note": f"Site-specific X{SITE_X}_Y{SITE_Y}_N{SITE_N}, "
                f"mode-invariant under INIT/WE/read-pipe variation.",
    }
    mode_bits[key] = entry

    tmp = str(RESULTS_PATH) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(mode_bits, f, indent=2, default=list)
    os.replace(tmp, str(RESULTS_PATH))
    print(f"[mine] merged quartus_gold ({len(gold_cells)} cells) into {key}")

    return {"width": width, "depth": depth,
            "n_variants": len(per_variant),
            "variant_sizes": per_variant_size,
            "gold_cells": len(gold_cells),
            "key": key}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int)
    ap.add_argument("--depth", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only-analyze", action="store_true")
    ap.add_argument("--site", default=f"{DEFAULT_SITE_X},{DEFAULT_SITE_Y},{DEFAULT_SITE_N}",
                    help="M9K site as X,Y,N (default 15,10,0). Real Quartus "
                         "mode cells shift per Y within an M9K column — mine "
                         "each site that np2fasm expects to emit for.")
    args = ap.parse_args()

    global SITE_X, SITE_Y, SITE_N
    try:
        SITE_X, SITE_Y, SITE_N = (int(s) for s in args.site.split(","))
    except ValueError:
        ap.error(f"--site must be X,Y,N; got {args.site!r}")
        return 1

    if args.all:
        combos = TARGET_COMBOS
    elif args.width and args.depth:
        combos = [(args.width, args.depth)]
    else:
        ap.error("specify --width W --depth D or --all")
        return 1

    summary = []
    for w, d in combos:
        summary.append(_mine_one(w, d, args.variants, args.workers,
                                 args.only_analyze))

    print("\n=== summary ===")
    for r in summary:
        if "error" in r:
            print(f"  ({r['width']},{r['depth']}): ERROR {r['error']}")
        else:
            print(f"  ({r['width']},{r['depth']}): "
                  f"gold={r['gold_cells']} from {r['n_variants']} builds; "
                  f"sizes={r['variant_sizes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
