#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare two JTAG IR enumeration raw outputs (configured vs unconfigured).

Detects three kinds of differences per IR code:
  1. DR length changed — FPGA selects a different register under this IR
     depending on its state. Strong lead for state-gated registers.
  2. Captured value changed within the DR — same register, different
     content. Exposes live status bits that weren't visible in the
     unconfigured baseline.
  3. IR exists in one scan but not the other (set-difference).

Captured value extraction: the raw output has cap_a (after shifting
pattern 0xAAA..., captured first) and cap_b (after pattern 0x555...,
captured after A). Both DR shifts CAPTURE the register state before
shifting, so bits [0..dr_len-1] of cap_a and cap_b are identical and
equal the captured register state.

Usage:
  compare_scans.py <phase1_raw.txt> <phase2_raw.txt> [output.json]
"""
import json
import sys
from pathlib import Path


def hex_xor(a: str, b: str) -> str:
    return "".join(
        format(int(ca, 16) ^ int(cb, 16), "X") for ca, cb in zip(a, b)
    )


def first_set_bit(hex_str: str) -> int:
    val = int(hex_str, 16)
    if val == 0:
        return -1
    return (val & -val).bit_length() - 1


def parse_scan(path: Path) -> dict:
    """Return {ir_code: {dr_len, captured_hex, cap_a_raw, cap_b_raw}}."""
    scan = {}
    meta = {"path": str(path)}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("# IDCODE:"):
            meta["idcode"] = line.split(":", 1)[1].strip()
        elif line.startswith("# MAX_DR:"):
            try:
                meta["max_dr"] = int(line.split()[2])
            except (IndexError, ValueError):
                pass
        elif line.startswith("# MODE:"):
            meta["mode"] = line.split(":", 1)[1].strip()
        elif line.startswith("IR "):
            parts = line.split()
            if len(parts) != 4:
                continue
            ir = int(parts[1])
            cap_a = parts[2].upper()
            cap_b = parts[3].upper()
            xor_str = hex_xor(cap_a, cap_b)
            dr_len = first_set_bit(xor_str)

            if dr_len > 0:
                mask = (1 << dr_len) - 1
                captured = int(cap_a, 16) & mask
            elif dr_len == 0:
                captured = 0  # 1-bit BYPASS: shifts in the pattern LSB
            else:
                captured = None  # DR longer than probe window

            scan[ir] = {
                "dr_len": dr_len,
                "captured": captured,
                "cap_a": cap_a,
                "cap_b": cap_b,
            }
    return scan, meta


def fmt_captured(val, dr_len: int) -> str:
    if val is None:
        return "(DR>probe)"
    hex_chars = max(1, (dr_len + 3) // 4)
    return f"0x{val:0{hex_chars}X}"


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <phase1_raw.txt> <phase2_raw.txt> "
              f"[output.json]", file=sys.stderr)
        sys.exit(1)

    p1 = Path(sys.argv[1])
    p2 = Path(sys.argv[2])
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 \
        else Path("jtag_scan_diff.json")

    s1, m1 = parse_scan(p1)
    s2, m2 = parse_scan(p2)

    dr_len_changed = []
    value_changed = []
    only_in_1 = []
    only_in_2 = []

    all_ir = sorted(set(s1.keys()) | set(s2.keys()))
    for ir in all_ir:
        if ir in s1 and ir not in s2:
            only_in_1.append(ir)
            continue
        if ir in s2 and ir not in s1:
            only_in_2.append(ir)
            continue
        e1, e2 = s1[ir], s2[ir]
        if e1["dr_len"] != e2["dr_len"]:
            dr_len_changed.append({
                "ir": ir,
                "ir_hex": f"0x{ir:03X}",
                "phase1_dr": e1["dr_len"],
                "phase2_dr": e2["dr_len"],
            })
        elif e1["captured"] != e2["captured"]:
            value_changed.append({
                "ir": ir,
                "ir_hex": f"0x{ir:03X}",
                "dr_len": e1["dr_len"],
                "phase1_val": fmt_captured(e1["captured"], e1["dr_len"]),
                "phase2_val": fmt_captured(e2["captured"], e2["dr_len"]),
                "phase1_hex": (f"0x{e1['captured']:X}"
                               if e1["captured"] is not None else None),
                "phase2_hex": (f"0x{e2['captured']:X}"
                               if e2["captured"] is not None else None),
            })

    report = {
        "meta": {
            "phase1": m1,
            "phase2": m2,
            "phase1_ir_count": len(s1),
            "phase2_ir_count": len(s2),
            "overlap_ir_count": len(set(s1) & set(s2)),
        },
        "dr_len_changed": dr_len_changed,
        "value_changed": value_changed,
        "only_in_phase1": only_in_1,
        "only_in_phase2": only_in_2,
    }
    out_path.write_text(json.dumps(report, indent=2))

    # --- summary ---
    print("=" * 64)
    print(f"JTAG scan diff:  {p1.name}  →  {p2.name}")
    print("=" * 64)
    print(f"Phase 1: {m1.get('mode', 'unknown mode')}  "
          f"({len(s1)} IR codes)")
    print(f"Phase 2: {m2.get('mode', 'unknown mode')}  "
          f"({len(s2)} IR codes)")
    print(f"Overlap: {len(set(s1) & set(s2))} IR codes")
    print()

    if only_in_1:
        print(f"IRs only in phase 1 ({len(only_in_1)}):  "
              f"{[f'0x{c:03X}' for c in only_in_1[:20]]}"
              f"{'...' if len(only_in_1) > 20 else ''}")
    if only_in_2:
        print(f"IRs only in phase 2 ({len(only_in_2)}):  "
              f"{[f'0x{c:03X}' for c in only_in_2[:20]]}"
              f"{'...' if len(only_in_2) > 20 else ''}")

    print(f"\nDR LENGTH CHANGES — {len(dr_len_changed)}")
    for e in dr_len_changed[:40]:
        print(f"  {e['ir_hex']}: DR {e['phase1_dr']} → {e['phase2_dr']} bits")
    if len(dr_len_changed) > 40:
        print(f"  ... +{len(dr_len_changed) - 40} more")

    print(f"\nCAPTURED VALUE CHANGES — {len(value_changed)}")
    for e in value_changed[:40]:
        print(f"  {e['ir_hex']} (DR={e['dr_len']}): "
              f"{e['phase1_val']} → {e['phase2_val']}")
    if len(value_changed) > 40:
        print(f"  ... +{len(value_changed) - 40} more")

    print(f"\nFull diff report: {out_path}")


if __name__ == "__main__":
    main()
