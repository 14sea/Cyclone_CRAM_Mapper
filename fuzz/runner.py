#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Orchestrate EP4CE6 bitstream fuzzing campaigns.

Usage:
    python runner.py baseline          -- Generate baseline (empty) RBF
    python runner.py discover_node     -- Find synthesized LUT node name
    python runner.py lut_single X Y N  -- Fuzz 16 minterms at one LE
    python runner.py lut_verify X Y N  -- Verify with common logic functions
    python runner.py lut_lab X Y       -- Fuzz all 16 LEs in one LAB
    python runner.py grid_scan         -- Scan one LUT function across all LABs
"""

import argparse
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import time

from config import (
    QUARTUS_BIN, WORK_DIR, RBF_DIR, RESULTS_DIR,
    LAB_X, LAB_Y, LE_N,
    MINTERM_EXPRESSIONS, LOGIC_FUNCTIONS, FUZZ_PINS, ROUTE_FUZZ_PINS,
    INVALID_LABS,
)
from verilog_gen import (
    gen_lut4, gen_lut4_primitive, gen_empty,
    gen_two_luts_primitive, gen_two_luts_single_input, gen_two_luts_pinned_clocked,
    gen_two_luts_single_input_clocked,
    gen_single_lut_primitive_extra_inputs,
)
from qsf_gen import gen_qsf, make_lccomb
from compile import compile_and_export, setup_project, run_quartus, compile_full, generate_rbf, extract_routing
from rbf_diff import diff_rbf_files, diff_rbf, print_diff, diff_summary
from database import get_db, log_experiment, store_bit_diffs, register_rbf, store_routing_path


def ensure_dirs():
    os.makedirs(RBF_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)


def rbf_path(name: str) -> str:
    return os.path.join(RBF_DIR, f"{name}.rbf")


# ---------------------------------------------------------------------------
# Campaign: Baseline
# ---------------------------------------------------------------------------
def cmd_baseline(args):
    """Generate baseline RBF with empty design (no logic, just I/O)."""
    ensure_dirs()
    print("=== Generating baseline RBF ===")

    verilog = gen_empty()
    qsf = gen_qsf()
    out = rbf_path("baseline")

    rbf, elapsed, err = compile_and_export(
        "baseline", verilog, qsf, rbf_output=out,
    )
    if rbf:
        print(f"Baseline RBF: {rbf} ({os.path.getsize(rbf)} bytes, {elapsed:.1f}s)")
        db = get_db()
        register_rbf(db, "baseline", rbf, "Empty design, no logic")
        db.close()
    else:
        print(f"FAILED: {err}", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Campaign: Discover Node Name
# ---------------------------------------------------------------------------
def cmd_discover_node(args):
    """Compile a simple LUT4 design without placement to discover the synthesized node name."""
    ensure_dirs()
    print("=== Discovering synthesized node name ===")

    verilog = gen_lut4("A & B")
    qsf = gen_qsf()  # no placement constraints

    proj_dir = setup_project("discover", verilog, qsf)
    ok, elapsed, err = compile_full("discover", proj_dir)
    if not ok:
        print(f"FAILED: {err}", file=sys.stderr)
        sys.exit(1)

    # Parse the fit report to find where lut_out was placed
    fit_rpt = os.path.join(proj_dir, "output_files", "discover.fit.rpt")
    if os.path.exists(fit_rpt):
        with open(fit_rpt, "r", errors="replace") as f:
            content = f.read()

        # Look for LCCOMB entries
        matches = re.findall(r'(LCCOMB_X\d+_Y\d+_N\d+)', content)
        if matches:
            print(f"Found LCCOMB placements: {set(matches)}")

        # Look for the node name in the "Fitter Resource Usage Summary"
        # and "Resource Section" of the report
        node_matches = re.findall(r';?\s*([\w|~\[\]]+)\s*;\s*LCCOMB_X(\d+)_Y(\d+)_N(\d+)', content)
        if node_matches:
            print("\nNode -> Location mappings:")
            for node, x, y, n in node_matches:
                print(f"  {node} -> LCCOMB_X{x}_Y{y}_N{n}")
        else:
            # Try alternative format from map report
            map_rpt = os.path.join(proj_dir, "output_files", "discover.map.rpt")
            if os.path.exists(map_rpt):
                with open(map_rpt, "r", errors="replace") as f:
                    map_content = f.read()
                # Look for combinational node names
                comb_matches = re.findall(r';\s*([\w|~\[\]]+)\s*;\s*combout\s*;', map_content)
                if comb_matches:
                    print(f"\nCombinational nodes from map report: {comb_matches}")

    # Also try quartus_cdb to enumerate nodes
    print("\n--- Trying quartus_cdb for node enumeration ---")
    tcl_script = os.path.join(proj_dir, "get_nodes.tcl")
    with open(tcl_script, "w") as f:
        f.write("""
project_open discover
load_package names
set names_ids [get_names -filter * -node_type comb]
foreach_in_collection name_id $names_ids {
    set name [get_name_info -info full_path $name_id]
    puts "COMB_NODE: $name"
}
set names_ids [get_names -filter * -node_type pin]
foreach_in_collection name_id $names_ids {
    set name [get_name_info -info full_path $name_id]
    puts "PIN_NODE: $name"
}
project_close
""")

    result = subprocess.run(
        [os.path.join(QUARTUS_BIN, "quartus_cdb"), "-t", tcl_script],
        cwd=proj_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    for line in result.stdout.split('\n'):
        if 'COMB_NODE:' in line or 'PIN_NODE:' in line:
            print(f"  {line.strip()}")

    print(f"\nCompile time: {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# Campaign: LUT Single — 16 minterms at one LE
# ---------------------------------------------------------------------------
def cmd_lut_single(args):
    """Fuzz 16 minterms at a single LE location to find truth table bits."""
    x, y, n = args.x, args.y, args.n
    ensure_dirs()

    baseline_path = rbf_path("baseline")
    if not os.path.exists(baseline_path):
        print("Baseline not found. Run 'baseline' first.", file=sys.stderr)
        sys.exit(1)

    with open(baseline_path, "rb") as f:
        baseline = f.read()

    node_name = args.node or "lut_out"
    placement = {node_name: make_lccomb(x, y, n)}

    print(f"=== LUT Truth Table Fuzzing at ({x}, {y}, {n}) ===")
    print(f"Node: {node_name} -> {placement[node_name]}")
    print()

    db = get_db()
    results = {}

    for bit_idx, expr in MINTERM_EXPRESSIONS.items():
        name = f"minterm_{bit_idx}_X{x}_Y{y}_N{n}"
        print(f"  Minterm {bit_idx:2d}: {expr:30s} ... ", end="", flush=True)

        verilog = gen_lut4(expr)
        qsf = gen_qsf(placement=placement)
        out = rbf_path(name)

        rbf, elapsed, err = compile_and_export(name, verilog, qsf, rbf_output=out)
        if not rbf:
            print(f"FAILED: {err}")
            continue

        with open(rbf, "rb") as f:
            rbf_data = f.read()

        diffs = diff_rbf(baseline, rbf_data)
        results[bit_idx] = diffs

        exp_id = log_experiment(db, name, f"Minterm {bit_idx} at ({x},{y},{n})",
                                verilog=expr, qsf_placement=str(placement),
                                compile_time=elapsed, rbf_path=out)
        store_bit_diffs(db, x, y, n, f"lut_bit_{bit_idx}", diffs, exp_id)

        print(f"{len(diffs):3d} bits differ ({elapsed:.1f}s)")

    db.close()

    # Analysis
    print("\n=== Analysis ===")
    if not results:
        print("No successful compiles!")
        return

    # Find bits that appear in exactly one minterm (likely truth table bits)
    all_bit_positions = {}  # abs_bit -> set of minterm indices
    for bit_idx, diffs in results.items():
        for d in diffs:
            ab = d.abs_bit
            all_bit_positions.setdefault(ab, set()).add(bit_idx)

    unique_bits = {ab: idxs for ab, idxs in all_bit_positions.items() if len(idxs) == 1}
    shared_bits = {ab: idxs for ab, idxs in all_bit_positions.items() if len(idxs) > 1}

    print(f"Total unique bit positions touched: {len(all_bit_positions)}")
    print(f"Bits unique to one minterm: {len(unique_bits)}")
    print(f"Bits shared across minterms: {len(shared_bits)}")

    # Map: minterm_index -> its unique bits
    minterm_unique = {}
    for ab, idxs in unique_bits.items():
        idx = list(idxs)[0]
        minterm_unique.setdefault(idx, []).append(ab)

    print("\nPer-minterm unique bits (candidate truth table bits):")
    for idx in range(16):
        bits = sorted(minterm_unique.get(idx, []))
        byte_offs = [f"0x{b // 8:05X}:{b % 8}" for b in bits]
        print(f"  Minterm {idx:2d}: {len(bits)} unique bits: {', '.join(byte_offs[:5])}")

    if shared_bits:
        print(f"\nShared bits ({len(shared_bits)}) — likely LE enable/mode bits:")
        for ab in sorted(shared_bits.keys())[:10]:
            idxs = sorted(shared_bits[ab])
            print(f"  0x{ab // 8:05X}:{ab % 8} -> minterms {idxs}")


# ---------------------------------------------------------------------------
# Campaign: LUT Verify — test with known functions
# ---------------------------------------------------------------------------
def cmd_lut_verify(args):
    """Verify truth table mapping using known logic functions."""
    x, y, n = args.x, args.y, args.n
    ensure_dirs()

    baseline_path = rbf_path("baseline")
    if not os.path.exists(baseline_path):
        print("Baseline not found. Run 'baseline' first.", file=sys.stderr)
        sys.exit(1)

    node_name = args.node or "lut_out"
    placement = {node_name: make_lccomb(x, y, n)}

    print(f"=== LUT Verification at ({x}, {y}, {n}) ===")

    with open(baseline_path, "rb") as f:
        baseline = f.read()

    for func_name, expr in LOGIC_FUNCTIONS.items():
        name = f"verify_{func_name}_X{x}_Y{y}_N{n}"
        print(f"  {func_name:8s}: {expr:20s} ... ", end="", flush=True)

        verilog = gen_lut4(expr)
        qsf = gen_qsf(placement=placement)
        out = rbf_path(name)

        rbf, elapsed, err = compile_and_export(name, verilog, qsf, rbf_output=out)
        if not rbf:
            print(f"FAILED: {err}")
            continue

        with open(rbf, "rb") as f:
            rbf_data = f.read()
        diffs = diff_rbf(baseline, rbf_data)
        print(f"{len(diffs):3d} bits differ ({elapsed:.1f}s)")


# ---------------------------------------------------------------------------
# Campaign: LAB — all 16 LEs in one LAB
# ---------------------------------------------------------------------------
def cmd_lut_lab(args):
    """Fuzz all 16 LEs in a LAB with a single function to find N-index mapping."""
    x, y = args.x, args.y
    ensure_dirs()

    baseline_path = rbf_path("baseline")
    if not os.path.exists(baseline_path):
        print("Baseline not found.", file=sys.stderr)
        sys.exit(1)

    with open(baseline_path, "rb") as f:
        baseline = f.read()

    expr = "A & B"
    node_name = args.node or "lut_out"

    print(f"=== LAB Scan at ({x}, {y}) — all 16 LEs ===")
    print(f"Function: {expr}")
    print()

    db = get_db()

    for n in LE_N:
        placement = {node_name: make_lccomb(x, y, n)}
        name = f"lab_X{x}_Y{y}_N{n}"
        print(f"  N={n:2d} -> {placement[node_name]:30s} ... ", end="", flush=True)

        verilog = gen_lut4(expr)
        qsf = gen_qsf(placement=placement)
        out = rbf_path(name)

        rbf, elapsed, err = compile_and_export(name, verilog, qsf, rbf_output=out)
        if not rbf:
            print(f"FAILED: {err}")
            continue

        with open(rbf, "rb") as f:
            rbf_data = f.read()
        diffs = diff_rbf(baseline, rbf_data)

        summary = diff_summary(diffs)
        exp_id = log_experiment(db, name, f"LAB scan ({x},{y}) N={n}",
                                verilog=expr, qsf_placement=str(placement),
                                compile_time=elapsed, rbf_path=out)
        store_bit_diffs(db, x, y, n, "lut_and", diffs, exp_id)

        region_str = ", ".join(f"0x{s:05X}-0x{e:05X}" for s, e in summary["regions"][:3])
        print(f"{len(diffs):3d} bits, regions: {region_str} ({elapsed:.1f}s)")

    db.close()


# ---------------------------------------------------------------------------
# Campaign: Grid Scan — one function across all LABs
# ---------------------------------------------------------------------------
def cmd_grid_scan(args):
    """Scan one LUT function across all LABs (N=0) to build the memory map."""
    ensure_dirs()

    # Use mask=0x0000 (placed LUT, all-zero) as baseline for cleaner diffs
    zero_path = rbf_path("prim_zero_ref")
    if not os.path.exists(zero_path):
        print("Generating placed-LUT zero baseline...")
        # We need a reference that doesn't have any specific placement
        # Use the global baseline instead
        pass

    baseline_path = rbf_path("baseline")
    if not os.path.exists(baseline_path):
        print("Baseline not found.", file=sys.stderr)
        sys.exit(1)

    with open(baseline_path, "rb") as f:
        baseline = f.read()

    # Use primitive LUT for precise mask control
    mask = 0x8888  # A & B truth table
    node_name = "lut_inst"
    n = 0  # always use first LE in LAB

    total = len(LAB_X) * len(LAB_Y)
    print(f"=== Grid Scan — mask 0x{mask:04X} at N={n} across {total} positions ===")
    print()

    db = get_db()
    count = 0
    failed = 0
    t_start = time.time()

    for yi, y in enumerate(LAB_Y):
        for xi, x in enumerate(LAB_X):
            count += 1
            placement = {node_name: make_lccomb(x, y, n)}
            name = f"grid_X{x}_Y{y}"
            progress = f"[{count}/{total}]"
            print(f"  {progress:10s} ({x:2d},{y:2d}) ... ", end="", flush=True)

            verilog = gen_lut4_primitive(mask)
            qsf = gen_qsf(placement=placement)
            out = rbf_path(name)

            rbf, elapsed, err = compile_and_export(name, verilog, qsf, rbf_output=out)
            if not rbf:
                print(f"FAILED: {err}")
                failed += 1
                continue

            with open(rbf, "rb") as f:
                rbf_data = f.read()
            diffs = diff_rbf(baseline, rbf_data)

            summary = diff_summary(diffs)
            exp_id = log_experiment(db, name, f"Grid scan ({x},{y},{n})",
                                    verilog=f"mask=0x{mask:04X}", qsf_placement=str(placement),
                                    compile_time=elapsed, rbf_path=out)
            store_bit_diffs(db, x, y, n, "lut_and", diffs, exp_id)

            min_off = summary["byte_range"][0] if diffs else 0
            print(f"{len(diffs):3d} bits @ 0x{min_off:05X} ({elapsed:.1f}s)")

    t_total = time.time() - t_start
    db.close()
    print(f"\n=== Done: {count - failed}/{count} succeeded in {t_total:.0f}s ===")


# ---------------------------------------------------------------------------
# Campaign: Grid Pair-Diff — clean LUT SRAM mapping across all LABs
# ---------------------------------------------------------------------------
def cmd_grid_pairdiff(args):
    """Pair-diff (mask=0x0000 vs 0xFFFF) at every LAB position for clean LUT bits."""
    ensure_dirs()

    node_name = "lut_inst"
    n = 0

    total = len(LAB_X) * len(LAB_Y)
    print(f"=== Grid Pair-Diff — N={n} across {total} positions ===")
    print()

    db = get_db()
    count = 0
    failed = 0
    skipped = 0
    t_start = time.time()

    for yi, y in enumerate(LAB_Y):
        for xi, x in enumerate(LAB_X):
            count += 1
            progress = f"[{count}/{total}]"

            # Check if already done in DB
            cursor = db.execute(
                "SELECT COUNT(*) FROM bit_mapping WHERE x=? AND y=? AND n=? AND feature='lut_pairdiff'",
                (x, y, n))
            if cursor.fetchone()[0] > 0:
                skipped += 1
                continue

            print(f"  {progress:10s} ({x:2d},{y:2d}) ... ", end="", flush=True)

            placement = {node_name: make_lccomb(x, y, n)}
            qsf = gen_qsf(placement=placement)

            # Use separate work dir to avoid conflicts with grid_scan
            gp_work = os.path.join(os.path.dirname(WORK_DIR), "work_gp")

            # Compile mask=0x0000
            v_zero = gen_lut4_primitive(0x0000)
            name_zero = f"gp_zero_{x}_{y}"
            rbf_zero, e1, err = compile_and_export(name_zero, v_zero, qsf,
                                                    work_dir=gp_work)
            if not rbf_zero:
                print(f"FAILED (zero): {err}")
                failed += 1
                continue

            with open(rbf_zero, "rb") as f:
                data_zero = f.read()

            # Compile mask=0xFFFF (reuse project — only mask changes)
            v_full = gen_lut4_primitive(0xFFFF)
            name_full = f"gp_full_{x}_{y}"
            rbf_full, e2, err = compile_and_export(name_full, v_full, qsf,
                                                    work_dir=gp_work)
            if not rbf_full:
                print(f"FAILED (full): {err}")
                failed += 1
                continue

            with open(rbf_full, "rb") as f:
                data_full = f.read()

            # Clean up RBF files — we only need the diff result
            os.remove(rbf_zero)
            os.remove(rbf_full)

            diffs = diff_rbf(data_zero, data_full)
            elapsed = e1 + e2

            exp_id = log_experiment(db, f"gp_X{x}_Y{y}",
                                    f"Grid pair-diff ({x},{y},{n})",
                                    verilog="mask=0x0000 vs 0xFFFF",
                                    qsf_placement=str(placement),
                                    compile_time=elapsed)
            store_bit_diffs(db, x, y, n, "lut_pairdiff", diffs, exp_id)

            min_off = min(d.byte_offset for d in diffs) if diffs else 0
            print(f"{len(diffs):3d} bits @ 0x{min_off:05X} ({elapsed:.1f}s)")

    t_total = time.time() - t_start
    db.close()
    done = count - failed - skipped
    print(f"\n=== Done: {done} new + {skipped} skipped + {failed} failed = {count} total in {t_total:.0f}s ===")


# ---------------------------------------------------------------------------
# Campaign: N-Sweep — pair-diff at all 16 N values for selected columns
# ---------------------------------------------------------------------------
def cmd_n_sweep(args):
    """Pair-diff at all 16 N values for selected (X,Y) positions."""
    ensure_dirs()

    node_name = "lut_inst"
    x, y = args.x, args.y

    print(f"=== N-Sweep Pair-Diff — X={x}, Y={y}, all N ===\n")

    db = get_db()
    gp_work = os.path.join(os.path.dirname(WORK_DIR), "work_gp")
    failed = 0

    for n in LE_N:
        feature = f"lut_pairdiff_n{n}"

        cursor = db.execute(
            "SELECT COUNT(*) FROM bit_mapping WHERE x=? AND y=? AND n=? AND feature=?",
            (x, y, n, feature))
        if cursor.fetchone()[0] > 0:
            print(f"  N={n:2d}: skipped (already done)")
            continue

        print(f"  N={n:2d}: ", end="", flush=True)

        placement = {node_name: make_lccomb(x, y, n)}
        qsf = gen_qsf(placement=placement)

        v_zero = gen_lut4_primitive(0x0000)
        rbf_zero, e1, err = compile_and_export(
            f"ns_zero_{x}_{y}_{n}", v_zero, qsf, work_dir=gp_work)
        if not rbf_zero:
            print(f"FAILED (zero): {err}")
            failed += 1
            continue

        with open(rbf_zero, "rb") as f:
            data_zero = f.read()

        v_full = gen_lut4_primitive(0xFFFF)
        rbf_full, e2, err = compile_and_export(
            f"ns_full_{x}_{y}_{n}", v_full, qsf, work_dir=gp_work)
        if not rbf_full:
            print(f"FAILED (full): {err}")
            failed += 1
            continue

        with open(rbf_full, "rb") as f:
            data_full = f.read()

        os.remove(rbf_zero)
        os.remove(rbf_full)

        diffs = diff_rbf(data_zero, data_full)
        elapsed = e1 + e2

        exp_id = log_experiment(db, f"ns_X{x}_Y{y}_N{n}",
                                f"N-sweep pair-diff ({x},{y},{n})",
                                verilog="mask=0x0000 vs 0xFFFF",
                                qsf_placement=str(placement),
                                compile_time=elapsed)
        store_bit_diffs(db, x, y, n, feature, diffs, exp_id)

        min_off = min(d.byte_offset for d in diffs) if diffs else 0
        print(f"{len(diffs):3d} bits @ 0x{min_off:05X} ({elapsed:.1f}s)")

    db.close()
    if failed:
        print(f"\n{failed} failures")


# ---------------------------------------------------------------------------
# Campaign: Route Pair — two connected LUTs at controlled distance
# ---------------------------------------------------------------------------
def gen_route_qsf(placement: dict, seed: int = 1) -> str:
    """Generate QSF with routing-fuzz pin assignments."""
    return gen_qsf(placement=placement, seed=seed,
                   extra_pins={k: v for k, v in ROUTE_FUZZ_PINS.items()
                               if k not in FUZZ_PINS})


def compile_route_pair(tag: str, x1: int, y1: int, n1: int,
                       x2: int, y2: int, n2: int,
                       mask1: int = 0x8888, mask2: int = 0xAAAA,
                       seed: int = 1) -> tuple[str | None, float, str]:
    """Compile a two-LUT design with specified placements."""
    ensure_dirs()
    verilog = gen_two_luts_primitive(mask1, mask2)
    placement = {
        "lut1": make_lccomb(x1, y1, n1),
        "lut2": make_lccomb(x2, y2, n2),
    }
    qsf = gen_route_qsf(placement, seed=seed)
    out = rbf_path(tag)
    return compile_and_export(tag, verilog, qsf, rbf_output=out)


def compile_route_baseline_abcd(tag: str, x: int, y: int, n: int,
                                mask: int = 0x8888, seed: int = 1):
    """Single-LUT baseline matching gen_two_luts_single_input's IO signature
    (A,B,C,D inputs only). Use as the diff baseline for single-input pair tests.
    """
    ensure_dirs()
    verilog = gen_lut4_primitive(mask)
    placement = {"lut_inst": make_lccomb(x, y, n)}
    qsf = gen_route_qsf(placement, seed=seed)
    out = rbf_path(tag)
    return compile_and_export(tag, verilog, qsf, rbf_output=out)


def compile_route_pair_single_input(tag: str, x1: int, y1: int, n1: int,
                                    x2: int, y2: int, n2: int,
                                    connect_port: str = "datab",
                                    mask1: int = 0x8888, mask2: int = 0xAAAA,
                                    seed: int = 1) -> tuple[str | None, float, str]:
    """Two-LUT route where lut2 has only ONE meaningful input (rest tied to 0).

    Lets us probe a SINGLE (src, dst_N, dst_port) LI activation in isolation
    instead of getting a union of 4 input ports' activations.
    """
    ensure_dirs()
    verilog = gen_two_luts_single_input(mask1, mask2, connect_port=connect_port)
    placement = {
        "lut1": make_lccomb(x1, y1, n1),
        "lut2": make_lccomb(x2, y2, n2),
    }
    qsf = gen_route_qsf(placement, seed=seed)
    out = rbf_path(tag)
    return compile_and_export(tag, verilog, qsf, rbf_output=out)


def compile_route_pair_single_input_clocked(
        tag: str, x1: int, y1: int, n1: int,
        x2: int, y2: int, n2: int,
        connect_port: str = "datab",
        mask1: int = 0x8888, mask2: int = 0xAAAA,
        seed: int = 1) -> tuple[str | None, float, str]:
    """Clocked variant of compile_route_pair_single_input.

    Identical placement and lut1/lut2 wiring; adds a CLK port and registers Q.
    Used to give Quartus' STA a real timing arc for routing extraction.
    """
    ensure_dirs()
    verilog = gen_two_luts_single_input_clocked(mask1, mask2, connect_port=connect_port)
    placement = {
        "lut1": make_lccomb(x1, y1, n1),
        "lut2": make_lccomb(x2, y2, n2),
    }
    qsf = gen_route_qsf(placement, seed=seed)
    out = rbf_path(tag)
    return compile_and_export(tag, verilog, qsf, rbf_output=out)


def compile_route_pair_pinned_clocked(
        tag: str, x1: int, y1: int, n1: int,
        x2: int, y2: int, n2: int,
        connect_port: str = "datab",
        mask1: int = 0x8888, mask2: int = 0xAAAA,
        seed: int = 1) -> tuple[str | None, float, str]:
    """Pinned + clocked variant: lut2 unused inputs from real pins E,F,G,
    Q registered. Eliminates 1'b0 constant routing AND keeps lut1/lut2 in
    the STA timing graph."""
    ensure_dirs()
    verilog = gen_two_luts_pinned_clocked(mask1, mask2, connect_port=connect_port)
    placement = {
        "lut1": make_lccomb(x1, y1, n1),
        "lut2": make_lccomb(x2, y2, n2),
    }
    qsf = gen_route_qsf(placement, seed=seed)
    out = rbf_path(tag)
    return compile_and_export(tag, verilog, qsf, rbf_output=out)


def compile_route_single(tag: str, x1: int, y1: int, n1: int,
                         mask: int = 0x8888, seed: int = 1) -> tuple[str | None, float, str]:
    """Compile a single-LUT design (route baseline) with same I/O as two-LUT."""
    ensure_dirs()
    verilog = gen_single_lut_primitive_extra_inputs(mask)
    placement = {"lut1": make_lccomb(x1, y1, n1)}
    qsf = gen_route_qsf(placement, seed=seed)
    out = rbf_path(tag)
    return compile_and_export(tag, verilog, qsf, rbf_output=out)


def cmd_route_local(args):
    """Fuzz routing within the same LAB (local interconnect, direct links)."""
    x, y = args.x, args.y
    ensure_dirs()
    print(f"=== Route Local — same LAB ({x},{y}) ===")

    db = get_db()

    # Baseline: single LUT at (x,y,0)
    base_tag = f"rlocal_base_X{x}_Y{y}"
    print(f"  Compiling single-LUT baseline... ", end="", flush=True)
    rbf1, elapsed, err = compile_route_single(base_tag, x, y, 0)
    if not rbf1:
        print(f"FAILED: {err}")
        return
    print(f"OK ({elapsed:.1f}s)")
    with open(rbf1, "rb") as f:
        base_data = f.read()

    # Connect lut1(x,y,0) -> lut2(x,y,N) for each N
    for n2 in LE_N:
        if n2 == 0:
            continue  # skip self
        tag = f"rlocal_X{x}_Y{y}_N0_N{n2}"
        print(f"  N=0 -> N={n2:2d} ... ", end="", flush=True)

        rbf2, elapsed, err = compile_route_pair(tag, x, y, 0, x, y, n2)
        if not rbf2:
            print(f"FAILED: {err}")
            continue

        with open(rbf2, "rb") as f:
            pair_data = f.read()
        diffs = diff_rbf(base_data, pair_data)
        summary = diff_summary(diffs)

        exp_id = log_experiment(db, tag,
                                f"Route local ({x},{y}) N=0->N={n2}",
                                verilog=f"lut1@N0->lut2@N{n2}",
                                qsf_placement=f"({x},{y},0)->({x},{y},{n2})",
                                compile_time=elapsed, rbf_path=rbf2)
        store_bit_diffs(db, x, y, n2, f"route_local_from_0", diffs, exp_id)

        region_str = ", ".join(f"0x{s:05X}-0x{e:05X}" for s, e in summary["regions"][:3])
        print(f"{len(diffs):3d} bits, regions: {region_str} ({elapsed:.1f}s)")

    db.close()


def cmd_route_column(args):
    """Fuzz routing within the same column (C4/C16 wires)."""
    x = args.x
    y_src = args.y_src
    ensure_dirs()
    print(f"=== Route Column — X={x}, source Y={y_src} ===")

    db = get_db()

    # Baseline: single LUT at (x, y_src, 0)
    base_tag = f"rcol_base_X{x}_Y{y_src}"
    print(f"  Compiling single-LUT baseline... ", end="", flush=True)
    rbf1, elapsed, err = compile_route_single(base_tag, x, y_src, 0)
    if not rbf1:
        print(f"FAILED: {err}")
        return
    print(f"OK ({elapsed:.1f}s)")
    with open(rbf1, "rb") as f:
        base_data = f.read()

    # Connect lut1(x, y_src, 0) -> lut2(x, y_dst, 0) for each y_dst
    for y_dst in LAB_Y:
        if y_dst == y_src:
            continue
        dy = y_dst - y_src
        tag = f"rcol_X{x}_Y{y_src}_to_Y{y_dst}"
        print(f"  Y={y_src} -> Y={y_dst} (dy={dy:+d}) ... ", end="", flush=True)

        rbf2, elapsed, err = compile_route_pair(tag, x, y_src, 0, x, y_dst, 0)
        if not rbf2:
            print(f"FAILED: {err}")
            continue

        with open(rbf2, "rb") as f:
            pair_data = f.read()
        diffs = diff_rbf(base_data, pair_data)
        summary = diff_summary(diffs)

        exp_id = log_experiment(db, tag,
                                f"Route column X={x} Y={y_src}->Y={y_dst}",
                                verilog=f"lut1@Y{y_src}->lut2@Y{y_dst}",
                                qsf_placement=f"({x},{y_src},0)->({x},{y_dst},0)",
                                compile_time=elapsed, rbf_path=rbf2)
        store_bit_diffs(db, x, y_dst, 0, f"route_col_from_Y{y_src}", diffs, exp_id)

        region_str = ", ".join(f"0x{s:05X}-0x{e:05X}" for s, e in summary["regions"][:3])
        print(f"{len(diffs):3d} bits, regions: {region_str} ({elapsed:.1f}s)")

    db.close()


def cmd_route_row(args):
    """Fuzz routing across columns in the same row (R4/R24 wires)."""
    y = args.y
    x_src = args.x_src
    ensure_dirs()
    print(f"=== Route Row — Y={y}, source X={x_src} ===")

    db = get_db()

    # Baseline: single LUT at (x_src, y, 0)
    base_tag = f"rrow_base_X{x_src}_Y{y}"
    print(f"  Compiling single-LUT baseline... ", end="", flush=True)
    rbf1, elapsed, err = compile_route_single(base_tag, x_src, y, 0)
    if not rbf1:
        print(f"FAILED: {err}")
        return
    print(f"OK ({elapsed:.1f}s)")
    with open(rbf1, "rb") as f:
        base_data = f.read()

    # Connect lut1(x_src, y, 0) -> lut2(x_dst, y, 0) for each x_dst
    for x_dst in LAB_X:
        if x_dst == x_src:
            continue
        dx = x_dst - x_src
        tag = f"rrow_Y{y}_X{x_src}_to_X{x_dst}"
        print(f"  X={x_src} -> X={x_dst} (dx={dx:+d}) ... ", end="", flush=True)

        rbf2, elapsed, err = compile_route_pair(tag, x_src, y, 0, x_dst, y, 0)
        if not rbf2:
            print(f"FAILED: {err}")
            continue

        with open(rbf2, "rb") as f:
            pair_data = f.read()
        diffs = diff_rbf(base_data, pair_data)
        summary = diff_summary(diffs)

        exp_id = log_experiment(db, tag,
                                f"Route row Y={y} X={x_src}->X={x_dst}",
                                verilog=f"lut1@X{x_src}->lut2@X{x_dst}",
                                qsf_placement=f"({x_src},{y},0)->({x_dst},{y},0)",
                                compile_time=elapsed, rbf_path=rbf2)
        store_bit_diffs(db, x_dst, y, 0, f"route_row_from_X{x_src}", diffs, exp_id)

        region_str = ", ".join(f"0x{s:05X}-0x{e:05X}" for s, e in summary["regions"][:3])
        print(f"{len(diffs):3d} bits, regions: {region_str} ({elapsed:.1f}s)")

    db.close()


def cmd_route_map(args):
    """Systematic routing analysis: compile + STA path extraction + RBF diff.

    For each (source, destination) pair, records:
    1. The exact routing wire path (from STA report_timing -show_routing)
    2. The bitstream diff (single-LUT baseline vs two-LUT connected)

    This builds a mapping from routing wire names to CRAM bits.
    """
    x_src, y_src = args.x, args.y
    ensure_dirs()

    db = get_db()
    gp_work = os.path.join(os.path.dirname(WORK_DIR), "work_route")

    # Step 1: Compile single-LUT baseline
    base_name = f"rmap_base_X{x_src}_Y{y_src}"
    print(f"=== Route Map — source ({x_src},{y_src},0) ===")
    print(f"  Compiling baseline... ", end="", flush=True)

    v_base = gen_single_lut_primitive_extra_inputs(0x8888)
    placement_base = {"lut1": make_lccomb(x_src, y_src, 0)}
    qsf_base = gen_route_qsf(placement_base)
    rbf_base, elapsed, err = compile_and_export(
        base_name, v_base, qsf_base, work_dir=gp_work)
    if not rbf_base:
        print(f"FAILED: {err}")
        return
    with open(rbf_base, "rb") as f:
        base_data = f.read()
    print(f"OK ({elapsed:.1f}s)")

    # Step 2: For each destination, compile two-LUT + extract routing + diff
    targets = []
    if args.direction == "column":
        targets = [(x_src, y, 0) for y in LAB_Y if y != y_src
                    and (x_src, y) not in INVALID_LABS]
    elif args.direction == "row":
        targets = [(x, y_src, 0) for x in LAB_X if x != x_src
                    and (x, y_src) not in INVALID_LABS]
    elif args.direction == "local":
        targets = [(x_src, y_src, n) for n in LE_N if n != 0]

    for dx, dy, dn in targets:
        tag = f"rmap_X{x_src}Y{y_src}_to_X{dx}Y{dy}N{dn}"
        feat = f"rmap_{args.direction}_X{x_src}Y{y_src}"

        # Skip if already done
        existing = db.execute(
            "SELECT COUNT(*) FROM routing_paths WHERE src_x=? AND src_y=? AND src_n=0 "
            "AND dst_x=? AND dst_y=? AND dst_n=?",
            (x_src, y_src, dx, dy, dn)).fetchone()[0]
        if existing:
            print(f"  -> ({dx},{dy},{dn}): skipped (done)")
            continue

        print(f"  -> ({dx},{dy},{dn}): ", end="", flush=True)

        # Compile two-LUT design
        proj_name = f"rmap_{x_src}{y_src}_{dx}{dy}{dn}"
        v = gen_two_luts_primitive(0x8888, 0xAAAA)
        placement = {
            "lut1": make_lccomb(x_src, y_src, 0),
            "lut2": make_lccomb(dx, dy, dn),
        }
        qsf = gen_route_qsf(placement)
        proj_dir = setup_project(proj_name, v, qsf, work_dir=gp_work)

        t0 = time.time()
        ok, _, err_msg = compile_full(proj_name, proj_dir)
        if not ok:
            print(f"COMPILE FAILED: {err_msg}")
            continue

        rbf = generate_rbf(proj_name, proj_dir)
        if not rbf:
            print(f"RBF FAILED")
            continue

        with open(rbf, "rb") as f:
            pair_data = f.read()

        # Extract routing path via STA
        segs = extract_routing(proj_name, proj_dir)

        elapsed = time.time() - t0

        # Diff
        diffs = diff_rbf(base_data, pair_data)

        # Filter to RE (routing element) segments between lut1 and lut2
        route_segs = []
        in_route = False
        for s in segs:
            if "lut1|combout" in s.get("element", ""):
                in_route = True
                continue
            if "lut2|" in s.get("element", "") and s["type"] == "IC":
                in_route = False
                continue
            if in_route:
                route_segs.append(s)

        # Store
        exp_id = log_experiment(db, tag,
                                f"Route map ({x_src},{y_src},0)->({dx},{dy},{dn})",
                                verilog=f"lut1->lut2",
                                qsf_placement=str(placement),
                                compile_time=elapsed)
        store_bit_diffs(db, dx, dy, dn, feat, diffs, exp_id)
        store_routing_path(db, exp_id,
                           (x_src, y_src, 0), (dx, dy, dn), segs)

        wire_names = [s["location"] for s in route_segs if s.get("location")]
        wire_str = " → ".join(wire_names[:5])
        if len(wire_names) > 5:
            wire_str += f" ... ({len(wire_names)} hops)"
        print(f"{len(diffs):3d} bits, {len(route_segs)} wire hops: {wire_str} ({elapsed:.1f}s)")

    db.close()


def _rmap_worker(task):
    """Worker function for parallel route_map.

    Runs in a separate process with its own work directory.
    Returns a dict with results (or error info) to be written to DB by the main process.
    """
    x_src, y_src, dx, dy, dn, base_data, worker_id, direction = task
    tag = f"rmap_X{x_src}Y{y_src}_to_X{dx}Y{dy}N{dn}"
    feat = f"rmap_{direction}_X{x_src}Y{y_src}"

    gp_work = os.path.join(os.path.dirname(WORK_DIR), f"work_route_w{worker_id}")

    proj_name = f"rmap_{x_src}{y_src}_{dx}{dy}{dn}"
    v = gen_two_luts_primitive(0x8888, 0xAAAA)
    placement = {
        "lut1": make_lccomb(x_src, y_src, 0),
        "lut2": make_lccomb(dx, dy, dn),
    }
    qsf = gen_route_qsf(placement)
    proj_dir = setup_project(proj_name, v, qsf, work_dir=gp_work)

    t0 = time.time()
    ok, _, err_msg = compile_full(proj_name, proj_dir)
    if not ok:
        # Clean up work dir
        shutil.rmtree(proj_dir, ignore_errors=True)
        return {"ok": False, "error": f"COMPILE FAILED: {err_msg}",
                "dx": dx, "dy": dy, "dn": dn}

    rbf = generate_rbf(proj_name, proj_dir)
    if not rbf:
        shutil.rmtree(proj_dir, ignore_errors=True)
        return {"ok": False, "error": "RBF FAILED",
                "dx": dx, "dy": dy, "dn": dn}

    with open(rbf, "rb") as f:
        pair_data = f.read()

    segs = extract_routing(proj_name, proj_dir)
    elapsed = time.time() - t0

    diffs = diff_rbf(base_data, pair_data)

    # Filter to route segments between lut1 and lut2
    route_segs = []
    in_route = False
    for s in segs:
        if "lut1|combout" in s.get("element", ""):
            in_route = True
            continue
        if "lut2|" in s.get("element", "") and s["type"] == "IC":
            in_route = False
            continue
        if in_route:
            route_segs.append(s)

    wire_names = [s["location"] for s in route_segs if s.get("location")]

    # Clean up work dir immediately
    shutil.rmtree(proj_dir, ignore_errors=True)

    return {
        "ok": True,
        "tag": tag, "feat": feat,
        "x_src": x_src, "y_src": y_src,
        "dx": dx, "dy": dy, "dn": dn,
        "placement": str(placement),
        "elapsed": elapsed,
        "diffs": [(d.byte_offset, d.bit_position, d.direction) for d in diffs],
        "segs": segs,
        "wire_names": wire_names,
        "n_route_segs": len(route_segs),
    }


def cmd_route_map_parallel(args):
    """Parallel version of route_map using multiprocessing.

    Each worker compiles in its own work directory. Results are collected
    and written to SQLite by the main process (no lock contention).
    """
    x_src, y_src = args.x, args.y
    n_workers = args.jobs
    ensure_dirs()

    db = get_db()
    gp_work = os.path.join(os.path.dirname(WORK_DIR), "work_route")

    # Step 1: Compile single-LUT baseline (serial — only once)
    base_name = f"rmap_base_X{x_src}_Y{y_src}"
    print(f"=== Parallel Route Map — source ({x_src},{y_src},0), {n_workers} workers ===")
    print(f"  Compiling baseline... ", end="", flush=True)

    v_base = gen_single_lut_primitive_extra_inputs(0x8888)
    placement_base = {"lut1": make_lccomb(x_src, y_src, 0)}
    qsf_base = gen_route_qsf(placement_base)
    rbf_base, elapsed, err = compile_and_export(
        base_name, v_base, qsf_base, work_dir=gp_work)
    if not rbf_base:
        print(f"FAILED: {err}")
        return
    with open(rbf_base, "rb") as f:
        base_data = f.read()
    print(f"OK ({elapsed:.1f}s)")

    # Build target list
    targets = []
    if args.direction == "column":
        targets = [(x_src, y, 0) for y in LAB_Y if y != y_src
                    and (x_src, y) not in INVALID_LABS]
    elif args.direction == "row":
        targets = [(x, y_src, 0) for x in LAB_X if x != x_src
                    and (x, y_src) not in INVALID_LABS]
    elif args.direction == "local":
        targets = [(x_src, y_src, n) for n in LE_N if n != 0]

    # Filter already-done targets
    todo = []
    for dx, dy, dn in targets:
        existing = db.execute(
            "SELECT COUNT(*) FROM routing_paths WHERE src_x=? AND src_y=? AND src_n=0 "
            "AND dst_x=? AND dst_y=? AND dst_n=?",
            (x_src, y_src, dx, dy, dn)).fetchone()[0]
        if existing:
            print(f"  -> ({dx},{dy},{dn}): skipped (done)")
        else:
            todo.append((dx, dy, dn))

    if not todo:
        print("  Nothing to do.")
        db.close()
        return

    print(f"  {len(todo)} targets to compile, dispatching to {n_workers} workers...")
    t_start = time.time()

    # Build task list — assign worker_id round-robin
    tasks = []
    for i, (dx, dy, dn) in enumerate(todo):
        wid = i % n_workers
        tasks.append((x_src, y_src, dx, dy, dn, base_data, wid, args.direction))

    # Run in parallel
    done = 0
    failed = 0
    with multiprocessing.Pool(processes=n_workers) as pool:
        for result in pool.imap_unordered(_rmap_worker, tasks):
            done += 1
            dx, dy, dn = result["dx"], result["dy"], result["dn"]

            if not result["ok"]:
                failed += 1
                print(f"  [{done}/{len(tasks)}] ({dx},{dy},{dn}): {result['error']}")
                continue

            # Write to DB (single-threaded, no lock contention)
            from rbf_diff import BitDiff
            diffs = [BitDiff(bo, bp, d) for bo, bp, d in result["diffs"]]

            exp_id = log_experiment(db, result["tag"],
                                    f"Route map ({x_src},{y_src},0)->({dx},{dy},{dn})",
                                    verilog="lut1->lut2",
                                    qsf_placement=result["placement"],
                                    compile_time=result["elapsed"])
            store_bit_diffs(db, dx, dy, dn, result["feat"], diffs, exp_id)
            store_routing_path(db, exp_id,
                               (x_src, y_src, 0), (dx, dy, dn), result["segs"])

            wire_str = " → ".join(result["wire_names"][:5])
            if len(result["wire_names"]) > 5:
                wire_str += f" ... ({len(result['wire_names'])} hops)"
            print(f"  [{done}/{len(tasks)}] ({dx},{dy},{dn}): "
                  f"{len(diffs):3d} bits, {result['n_route_segs']} wire hops: "
                  f"{wire_str} ({result['elapsed']:.1f}s)")

    t_total = time.time() - t_start
    db.close()

    # Clean up worker dirs
    for wid in range(n_workers):
        wdir = os.path.join(os.path.dirname(WORK_DIR), f"work_route_w{wid}")
        if os.path.exists(wdir):
            shutil.rmtree(wdir, ignore_errors=True)

    print(f"\n=== Done: {done - failed}/{done} OK in {t_total:.0f}s "
          f"({t_total / max(done, 1):.1f}s effective/target) ===")


def cmd_route_map_batch(args):
    """Run route_map_parallel for multiple (source, direction) combinations.

    Usage: runner.py route_map_batch --sources 4,10 29,10 10,17 --direction row --jobs 4
    """
    n_workers = args.jobs
    ensure_dirs()

    sources = []
    for s in args.sources:
        parts = s.split(",")
        sources.append((int(parts[0]), int(parts[1])))

    print(f"=== Batch Route Map — {len(sources)} sources, {args.direction}, {n_workers} workers ===")

    for x_src, y_src in sources:
        # Reuse parallel logic by creating a fake args object
        class FakeArgs:
            pass
        fa = FakeArgs()
        fa.x = x_src
        fa.y = y_src
        fa.direction = args.direction
        fa.jobs = n_workers
        cmd_route_map_parallel(fa)
        print()


def cmd_route_seed(args):
    """Test routing determinism — same placement, different fitter seeds."""
    x1, y1 = args.x1, args.y1
    x2, y2 = args.x2, args.y2
    ensure_dirs()
    print(f"=== Route Seed Test — ({x1},{y1},0) -> ({x2},{y2},0) ===")

    results = {}
    for seed in range(1, args.num_seeds + 1):
        tag = f"rseed_s{seed}_X{x1}Y{y1}_X{x2}Y{y2}"
        print(f"  seed={seed} ... ", end="", flush=True)
        rbf, elapsed, err = compile_route_pair(tag, x1, y1, 0, x2, y2, 0, seed=seed)
        if not rbf:
            print(f"FAILED: {err}")
            continue
        with open(rbf, "rb") as f:
            results[seed] = f.read()
        print(f"OK ({elapsed:.1f}s)")

    # Compare all pairs
    seeds = sorted(results.keys())
    print(f"\n  Pairwise diffs (seed A vs seed B):")
    for i, sa in enumerate(seeds):
        for sb in seeds[i+1:]:
            diffs = diff_rbf(results[sa], results[sb])
            print(f"    seed {sa} vs {sb}: {len(diffs)} bits differ")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="EP4CE6 Bitstream Fuzzer")
    parser.add_argument("--node", default=None, help="Override synthesized node name")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("baseline", help="Generate baseline (empty) RBF")
    sub.add_parser("discover_node", help="Discover synthesized LUT node name")

    p = sub.add_parser("lut_single", help="Fuzz 16 minterms at one LE")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("n", type=int)

    p = sub.add_parser("lut_verify", help="Verify with common logic functions")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("n", type=int)

    p = sub.add_parser("lut_lab", help="Fuzz all 16 LEs in one LAB")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)

    sub.add_parser("grid_scan", help="Scan one function across all LABs")
    sub.add_parser("grid_pairdiff", help="Pair-diff (0x0000 vs 0xFFFF) across all LABs")

    p = sub.add_parser("n_sweep", help="Pair-diff all 16 N values at one LAB")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)

    p = sub.add_parser("route_local", help="Fuzz intra-LAB routing")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)

    p = sub.add_parser("route_column", help="Fuzz intra-column routing (C4/C16)")
    p.add_argument("x", type=int)
    p.add_argument("y_src", type=int)

    p = sub.add_parser("route_row", help="Fuzz intra-row routing (R4/R24)")
    p.add_argument("y", type=int)
    p.add_argument("x_src", type=int)

    p = sub.add_parser("route_map", help="Systematic routing with STA path extraction")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("direction", choices=["column", "row", "local"])

    p = sub.add_parser("route_map_parallel", help="Parallel route_map with multiprocessing")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("direction", choices=["column", "row", "local"])
    p.add_argument("--jobs", "-j", type=int, default=4, help="Number of parallel workers")

    p = sub.add_parser("route_map_batch", help="Batch route_map_parallel across multiple sources")
    p.add_argument("--sources", nargs="+", required=True, help="Source positions as X,Y pairs")
    p.add_argument("--direction", required=True, choices=["column", "row", "local"])
    p.add_argument("--jobs", "-j", type=int, default=4, help="Number of parallel workers")

    p = sub.add_parser("route_seed", help="Test routing determinism across seeds")
    p.add_argument("x1", type=int)
    p.add_argument("y1", type=int)
    p.add_argument("x2", type=int)
    p.add_argument("y2", type=int)
    p.add_argument("--num-seeds", type=int, default=5)

    args = parser.parse_args()

    commands = {
        "baseline": cmd_baseline,
        "discover_node": cmd_discover_node,
        "lut_single": cmd_lut_single,
        "lut_verify": cmd_lut_verify,
        "lut_lab": cmd_lut_lab,
        "grid_scan": cmd_grid_scan,
        "grid_pairdiff": cmd_grid_pairdiff,
        "n_sweep": cmd_n_sweep,
        "route_local": cmd_route_local,
        "route_column": cmd_route_column,
        "route_row": cmd_route_row,
        "route_map": cmd_route_map,
        "route_map_parallel": cmd_route_map_parallel,
        "route_map_batch": cmd_route_map_batch,
        "route_seed": cmd_route_seed,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
