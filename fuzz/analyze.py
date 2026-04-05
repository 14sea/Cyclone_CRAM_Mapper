#!/usr/bin/env python3
"""Post-hoc analysis and visualization of fuzzing results.

Usage:
    python analyze.py summary             -- Show database summary
    python analyze.py lut_table X Y N     -- Show truth table bit mapping for one LE
    python analyze.py grid_map            -- Show bitstream address grid map
    python analyze.py export              -- Export full database to JSON
"""

import argparse
import os
import sys

from config import DB_PATH, LAB_X, LAB_Y, LE_N, RBF_SIZE
from database import get_db, get_le_features, get_all_locations, get_feature_bits, export_json


def cmd_summary(args):
    """Show database summary statistics."""
    db = get_db()

    exp_count = db.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    bit_count = db.execute("SELECT COUNT(*) FROM bit_mapping").fetchone()[0]
    loc_count = db.execute("SELECT COUNT(DISTINCT x || '_' || y || '_' || n) FROM bit_mapping").fetchone()[0]
    feat_count = db.execute("SELECT COUNT(DISTINCT feature) FROM bit_mapping").fetchone()[0]

    print(f"=== EP4CE6 Bitstream Database Summary ===")
    print(f"  Experiments:     {exp_count}")
    print(f"  Bit mappings:    {bit_count}")
    print(f"  LE locations:    {loc_count}")
    print(f"  Unique features: {feat_count}")

    if feat_count > 0:
        print(f"\n  Features:")
        rows = db.execute(
            "SELECT feature, COUNT(*) FROM bit_mapping GROUP BY feature ORDER BY feature"
        ).fetchall()
        for feat, cnt in rows:
            print(f"    {feat:25s}: {cnt:6d} bits")

    # RBF registry
    rbfs = db.execute("SELECT name, path FROM rbf_registry ORDER BY name").fetchall()
    if rbfs:
        print(f"\n  Registered RBFs:")
        for name, path in rbfs:
            exists = "OK" if os.path.exists(path) else "MISSING"
            print(f"    {name:30s} [{exists}]")

    db.close()


def cmd_lut_table(args):
    """Show truth table bit mapping for one LE."""
    x, y, n = args.x, args.y, args.n
    db = get_db()

    print(f"=== LUT Truth Table at ({x}, {y}, {n}) ===\n")

    for bit_idx in range(16):
        feature = f"lut_bit_{bit_idx}"
        bits = get_feature_bits(db, x, y, n, feature)
        if bits:
            addrs = [f"0x{bo:05X}:{bp}" for bo, bp, _ in bits]
            print(f"  Bit {bit_idx:2d} (minterm {bit_idx:04b}): {', '.join(addrs)}")
        else:
            print(f"  Bit {bit_idx:2d} (minterm {bit_idx:04b}): <no data>")

    # Show shared/mode bits
    features = get_le_features(db, x, y, n)
    non_lut = {k: v for k, v in features.items() if not k.startswith("lut_bit_")}
    if non_lut:
        print(f"\n  Other features:")
        for feat, bits in non_lut.items():
            addrs = [f"0x{bo:05X}:{bp}" for bo, bp in bits]
            print(f"    {feat}: {', '.join(addrs[:10])}")

    db.close()


def cmd_grid_map(args):
    """Show bitstream address grid map for LUT placement across the chip."""
    db = get_db()

    print(f"=== Bitstream Address Grid Map ===\n")

    # Collect min byte offset for each (x, y)
    grid = {}
    rows = db.execute(
        """SELECT x, y, MIN(byte_offset) as min_off, COUNT(*) as bit_count
           FROM bit_mapping
           WHERE feature = 'lut_and'
           GROUP BY x, y
           ORDER BY x, y"""
    ).fetchall()

    for x, y, min_off, bit_count in rows:
        grid[(x, y)] = (min_off, bit_count)

    if not grid:
        print("No grid data. Run 'grid_scan' first.")
        db.close()
        return

    # Print as table
    print(f"{'Y\\X':>6s}", end="")
    for x in LAB_X:
        print(f"  {x:>6d}", end="")
    print()
    print("-" * (8 + 8 * len(LAB_X)))

    for y in LAB_Y:
        print(f"{y:>6d}", end="")
        for x in LAB_X:
            if (x, y) in grid:
                off, cnt = grid[(x, y)]
                print(f"  {off:06X}", end="")
            else:
                print(f"  {'--':>6s}", end="")
        print()

    # Column analysis: check if X coordinates map to contiguous regions
    print(f"\n=== Column Address Ranges ===")
    for x in LAB_X:
        offsets = [grid[(x, y)][0] for y in LAB_Y if (x, y) in grid]
        if offsets:
            print(f"  X={x:2d}: 0x{min(offsets):05X} - 0x{max(offsets):05X} "
                  f"(span: {max(offsets) - min(offsets)} bytes, {len(offsets)} rows)")

    # Row analysis
    print(f"\n=== Row Address Ranges ===")
    for y in LAB_Y:
        offsets = [grid[(x, y)][0] for x in LAB_X if (x, y) in grid]
        if offsets:
            print(f"  Y={y:2d}: 0x{min(offsets):05X} - 0x{max(offsets):05X} "
                  f"(span: {max(offsets) - min(offsets)} bytes, {len(offsets)} cols)")

    db.close()


def cmd_cram_map(args):
    """Analyze CRAM address structure from grid scan data.

    Uses lut_and bits but filters to bit-4-only (control bytes) in the
    X column CRAM range to find the LUT TT base address per position.
    """
    db = get_db()
    print("=== CRAM Address Map Analysis ===\n")

    # For each position, find the CRAM column range by looking at
    # which byte offsets have bit-4 changes (LUT ctrl bytes)
    rows = db.execute(
        """SELECT x, y, byte_offset, bit_position
           FROM bit_mapping
           WHERE feature = 'lut_and'
           ORDER BY x, y, byte_offset"""
    ).fetchall()

    # Group by position
    from collections import defaultdict
    pos_bits = defaultdict(list)
    for x, y, bo, bp in rows:
        pos_bits[(x, y)].append((bo, bp))

    # For each column, find the CRAM column range
    # The LUT TT ctrl bytes are bit-4 only bytes in a specific range
    # We need to find the cluster of bit-4 bytes that corresponds to LUT TT

    # Known CRAM column bases from FINDINGS
    known_bases = {
        3: 0x076A4, 4: 0x0935A, 6: 0x0CCC6, 7: 0x0E97C,
        8: 0x10632, 10: 0x13F9E, 11: 0x15C54, 12: 0x1790A,
        13: 0x195C0, 16: 0x2BF86, 17: 0x2DC3C, 18: 0x2FC3A,
        19: 0x318F0, 21: 0x34A28, 22: 0x366DE, 23: 0x38394,
        24: 0x3A04A, 25: 0x3BD00, 26: 0x3D9B6, 28: 0x4E6C6,
        29: 0x5037C, 31: 0x53CE8,
    }

    # For each position, find bit-4 bytes in the expected CRAM column range
    grid = {}
    for (x, y), bits in sorted(pos_bits.items()):
        if x not in known_bases:
            continue

        col_base = known_bases[x]
        # LUT TT spans ~1600 bytes from the base address
        # Look for bit-4 bytes in range [col_base - 200, col_base + 2000]
        col_range = (col_base - 200, col_base + 2000)

        bit4_in_range = [bo for bo, bp in bits if bp == 4 and col_range[0] <= bo <= col_range[1]]
        if bit4_in_range:
            min_ctrl = min(bit4_in_range)
            max_ctrl = max(bit4_in_range)
            grid[(x, y)] = (min_ctrl, max_ctrl, len(bit4_in_range))

    # Print results
    print(f"{'Y\\X':>6s}", end="")
    for x in LAB_X:
        print(f"  {x:>7s}", end="")
    print()
    print("-" * (8 + 9 * len(LAB_X)))

    for y in LAB_Y:
        print(f"{y:>6d}", end="")
        for x in LAB_X:
            if (x, y) in grid:
                min_c, max_c, cnt = grid[(x, y)]
                print(f"  {min_c:07X}", end="")
            else:
                print(f"  {'--':>7s}", end="")
        print()

    # Column analysis
    print(f"\n=== Per-Column LUT Ctrl Base ===")
    for x in LAB_X:
        bases = [(y, grid[(x, y)][0]) for y in LAB_Y if (x, y) in grid]
        if bases:
            ys = [b[0] for b in bases]
            addrs = [b[1] for b in bases]
            known = known_bases.get(x, 0)
            print(f"  X={x:2d}: known=0x{known:05X}, found min=0x{min(addrs):05X}, max=0x{max(addrs):05X}, {len(bases)} rows")
            if len(bases) > 1:
                # Show row spacing
                for i in range(1, len(bases)):
                    delta = bases[i][1] - bases[i-1][1]
                    print(f"         Y={bases[i-1][0]:2d}->Y={bases[i][0]:2d}: delta={delta:+d}")

    db.close()


def cmd_cram_model(args):
    """Build CRAM address model from pair-diff data (lut_pairdiff feature).

    Requires grid_pairdiff to have been run first.
    Falls back to analyzing existing pair-diff RBF files if no DB data.
    """
    from collections import defaultdict
    from rbf_diff import diff_rbf_files, diff_rbf

    db = get_db()

    # Check if pair-diff data is in DB
    count = db.execute("SELECT COUNT(*) FROM bit_mapping WHERE feature='lut_pairdiff'").fetchone()[0]

    if count > 0:
        # Use DB data
        rows = db.execute(
            """SELECT x, y, byte_offset, bit_position
               FROM bit_mapping
               WHERE feature = 'lut_pairdiff'
               ORDER BY x, y, byte_offset"""
        ).fetchall()
    else:
        print("No lut_pairdiff data in DB. Use 'python runner.py grid_pairdiff' first.")
        # Try to use any available pair-diff RBF files
        import glob
        pairs = glob.glob(os.path.join(os.path.dirname(DB_PATH), "rbf", "arith_n*_zero.rbf"))
        if not pairs:
            db.close()
            return
        print("Using arith_n*_zero/full RBF files for X=10...")
        rows = []
        for n in [0, 6, 8, 10, 12, 14]:
            zero_path = os.path.join(os.path.dirname(DB_PATH), "rbf", f"arith_n{n}_zero.rbf")
            full_path = os.path.join(os.path.dirname(DB_PATH), "rbf", f"arith_n{n}_full.rbf")
            if not os.path.exists(zero_path) or not os.path.exists(full_path):
                continue
            diffs = diff_rbf_files(zero_path, full_path)
            for d in diffs:
                rows.append((10, 10, d.byte_offset, d.bit_position))

    # Group by (x, y)
    pos_data = defaultdict(list)
    for x, y, bo, bp in rows:
        pos_data[(x, y)].append((bo, bp))

    print(f"\n=== CRAM Address Model ({len(pos_data)} positions) ===\n")

    # For each position, extract LUT TT structure
    col_models = defaultdict(list)  # x -> [(y, ctrl_base, ctrl_top, inter_pair, ctrl_data_offset)]

    for (x, y), bits in sorted(pos_data.items()):
        # Group by byte address
        by_addr = defaultdict(list)
        for bo, bp in bits:
            by_addr[bo].append(bp)

        # Pure ctrl bytes: only bit-4
        pure_ctrl = sorted(a for a, bps in by_addr.items() if bps == [4])

        if len(pure_ctrl) < 4:
            continue  # not enough to determine structure

        # Find ctrl pairs (consecutive addresses)
        ctrl_pairs = []
        i = 0
        while i < len(pure_ctrl) - 1:
            if pure_ctrl[i+1] - pure_ctrl[i] == 1:
                ctrl_pairs.append((pure_ctrl[i], pure_ctrl[i+1]))
                i += 2
            else:
                i += 1

        if len(ctrl_pairs) < 4:
            continue

        # Find data pairs (multi-bit addresses in ctrl+data range)
        data_pairs = []
        data_addrs = sorted(a for a, bps in by_addr.items() if len(bps) > 1)
        i = 0
        while i < len(data_addrs) - 1:
            if data_addrs[i+1] - data_addrs[i] == 1:
                data_pairs.append((data_addrs[i], data_addrs[i+1]))
                i += 2
            else:
                i += 1

        # Compute inter-pair spacing (ctrl pairs)
        spacings = []
        for i in range(1, len(ctrl_pairs)):
            spacings.append(ctrl_pairs[i][0] - ctrl_pairs[i-1][0])

        # Compute ctrl→data offset
        ctrl_data_offsets = []
        for cp in ctrl_pairs:
            for dp in data_pairs:
                offset = dp[0] - cp[0]
                if 50 <= offset <= 150:  # reasonable range
                    ctrl_data_offsets.append(offset)
                    break

        ctrl_base = ctrl_pairs[0][0]
        ctrl_top = ctrl_pairs[-1][1]
        avg_spacing = sum(spacings) / len(spacings) if spacings else 0
        avg_cd_offset = sum(ctrl_data_offsets) / len(ctrl_data_offsets) if ctrl_data_offsets else 0

        col_models[x].append({
            'y': y,
            'ctrl_base': ctrl_base,
            'ctrl_top': ctrl_top,
            'n_pairs': len(ctrl_pairs),
            'inter_pair': avg_spacing,
            'ctrl_data': avg_cd_offset,
        })

    # Print per-column summary
    for x in sorted(col_models.keys()):
        entries = col_models[x]
        print(f"Column X={x}:")
        print(f"  {'Y':>3s}  {'Ctrl base':>10s}  {'Pairs':>5s}  {'Spacing':>8s}  {'C→D':>5s}")
        for e in entries:
            print(f"  {e['y']:3d}  0x{e['ctrl_base']:05X}     {e['n_pairs']:3d}    {e['inter_pair']:6.1f}   {e['ctrl_data']:5.1f}")

        if len(entries) > 1:
            # Y spacing analysis
            y_deltas = []
            for i in range(1, len(entries)):
                dy = entries[i]['y'] - entries[i-1]['y']
                da = entries[i]['ctrl_base'] - entries[i-1]['ctrl_base']
                y_deltas.append((entries[i-1]['y'], entries[i]['y'], da))
                print(f"  Y={entries[i-1]['y']:2d}→Y={entries[i]['y']:2d}: ctrl_base delta={da:+d}")

    db.close()


def cmd_export(args):
    """Export full database to JSON."""
    db = get_db()
    out = args.output or os.path.join(os.path.dirname(DB_PATH), "ep4ce6_bitdb.json")
    export_json(db, out)
    print(f"Exported to {out}")
    db.close()


def cmd_read_c4(args):
    """Read C4 I=0 switch states from an RBF file.

    Uses the verified CRAM address model to decode which C4 column routing
    switches are active at each (X, Y) position.
    """
    from config import LAB_X, LAB_Y

    # LAB column CRAM cluster ends (at Y=10) — from pairdiff analysis
    LAB_CRAM_END = {
        3: 0x07ccf, 4: 0x09985, 6: 0x0d2f1, 7: 0x0efa7, 8: 0x10c5d,
        10: 0x145c9, 11: 0x1627f, 12: 0x17f35, 13: 0x19beb,
        16: 0x2c5b1, 17: 0x2e267, 18: 0x30265, 19: 0x31f1b,
        21: 0x35053, 22: 0x36d09, 23: 0x389bf, 24: 0x3a675,
        25: 0x3c32b, 26: 0x3dfe1, 28: 0x4ecf1, 29: 0x509a7, 31: 0x54313,
    }
    SLOT_BASE = {0: 2405, 1: 2475, 2: 2338}

    with open(args.rbf, "rb") as f:
        rbf = f.read()
    with open(args.zero, "rb") as f:
        zero = f.read()

    # C4 wires exist at ALL Y positions 1..21, not just LAB Y positions
    ALL_Y = list(range(1, 22))

    active = []
    for x in LAB_X:
        if x not in LAB_CRAM_END:
            continue
        for y in ALL_Y:
            group = (y - 2) // 3
            slot = (y - 2) % 3
            offset = LAB_CRAM_END[x] + SLOT_BASE[slot] + 3 * group
            bp = (6 - group) if slot == 2 else (7 - group)
            if offset >= len(rbf) or offset >= len(zero):
                continue
            rbf_bit = (rbf[offset] >> bp) & 1
            zero_bit = (zero[offset] >> bp) & 1
            if rbf_bit != zero_bit:
                active.append((x, y, offset, bp, rbf_bit))

    if args.diff_only:
        print(f"=== Active C4_I0 switches (design vs zero) ===")
    else:
        print(f"=== C4_I0 switch states ===")

    print(f"Found {len(active)} active C4 I=0 switches")
    for x, y, off, bp, val in active:
        print(f"  C4_X{x}_Y{y}_N0_I0  offset=0x{off:05x} bp={bp} val={val}")


def cmd_read_tt(args):
    """Read LUT truth table from an RBF file at a calibrated position."""
    from bitstream import LutCodec

    db = get_db()
    try:
        codec = LutCodec.from_db(db, args.x, args.y, args.n)
    except ValueError as e:
        print(f"Error: {e}")
        db.close()
        return

    with open(args.rbf, "rb") as f:
        rbf_data = f.read()
    with open(args.zero, "rb") as f:
        zero_data = f.read()

    mask = codec.read_tt(rbf_data, zero_data)
    print(f"LE ({args.x},{args.y},{args.n}): LUT mask = 0x{mask:04X} (0b{mask:016b})")
    db.close()


def cmd_write_tt(args):
    """Write LUT truth table into an RBF file at a calibrated position."""
    from bitstream import LutCodec

    db = get_db()
    try:
        codec = LutCodec.from_db(db, args.x, args.y, args.n)
    except ValueError as e:
        print(f"Error: {e}")
        db.close()
        return

    with open(args.zero, "rb") as f:
        zero_data = f.read()

    mask = int(args.mask, 0)  # supports 0x, 0b, decimal
    new_rbf = codec.write_tt(zero_data, mask)

    with open(args.output, "wb") as f:
        f.write(new_rbf)
    print(f"Wrote LUT mask 0x{mask:04X} at ({args.x},{args.y},{args.n}) → {args.output}")
    db.close()


def cmd_read_route(args):
    """Read routing switch states from RBF using RouteCodec."""
    from bitstream import RouteCodec

    with open(args.rbf, "rb") as f:
        rbf = f.read()
    with open(args.zero, "rb") as f:
        zero = f.read()

    rc = RouteCodec()
    wire_types = None if args.type == "all" else {args.type}
    switches = rc.read_switches(rbf, zero, wire_types)

    total = 0
    for wtype in sorted(switches):
        wires = switches[wtype]
        total += len(wires)
        label = {"c4": "C4 (column)", "r4": "R4 (row)", "li": "LOCAL_INTERCONNECT"}
        print(f"\n=== {label.get(wtype, wtype)} — {len(wires)} active switches ===")
        for entry in sorted(wires):
            if len(entry) == 4:  # LI has candidates list
                name, off, bp, cands = entry
                print(f"  {name:40s}  offset=0x{off:05x} bp={bp}  I-cands={cands}")
            else:
                name, off, bp = entry
                print(f"  {name:40s}  offset=0x{off:05x} bp={bp}")

    print(f"\nTotal: {total} active routing switches")


def main():
    parser = argparse.ArgumentParser(description="EP4CE6 Bitstream Analysis")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("summary", help="Show database summary")

    p = sub.add_parser("lut_table", help="Show LUT truth table bit mapping")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("n", type=int)

    sub.add_parser("grid_map", help="Show bitstream address grid map")
    sub.add_parser("cram_map", help="Analyze CRAM address structure from grid data")
    sub.add_parser("cram_model", help="Build CRAM model from pair-diff data")

    p = sub.add_parser("export", help="Export to JSON")
    p.add_argument("-o", "--output", help="Output JSON path")

    p = sub.add_parser("read_c4", help="Read C4 I=0 switch states from RBF")
    p.add_argument("rbf", help="RBF file to read")
    p.add_argument("zero", help="Zero-mask baseline RBF for comparison")
    p.add_argument("--diff-only", action="store_true", default=True)

    p = sub.add_parser("read_tt", help="Read LUT truth table from RBF")
    p.add_argument("rbf", help="RBF file to read")
    p.add_argument("zero", help="Zero-mask baseline RBF")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("n", type=int)

    p = sub.add_parser("write_tt", help="Write LUT truth table to RBF")
    p.add_argument("zero", help="Zero-mask baseline RBF")
    p.add_argument("mask", help="16-bit TT mask (hex: 0x8888, bin: 0b1010...)")
    p.add_argument("output", help="Output RBF path")
    p.add_argument("x", type=int)
    p.add_argument("y", type=int)
    p.add_argument("n", type=int)

    p = sub.add_parser("read_route", help="Read routing switch states from RBF")
    p.add_argument("rbf", help="RBF file to read")
    p.add_argument("zero", help="Zero-mask baseline RBF")
    p.add_argument("--type", choices=["c4", "r4", "li", "all"], default="all",
                   help="Wire type to read (default: all)")

    args = parser.parse_args()

    commands = {
        "summary": cmd_summary,
        "lut_table": cmd_lut_table,
        "grid_map": cmd_grid_map,
        "cram_map": cmd_cram_map,
        "cram_model": cmd_cram_model,
        "export": cmd_export,
        "read_c4": cmd_read_c4,
        "read_tt": cmd_read_tt,
        "write_tt": cmd_write_tt,
        "read_route": cmd_read_route,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
