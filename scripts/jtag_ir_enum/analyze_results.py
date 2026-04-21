#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Analyze JTAG IR enumeration results.

Reads raw output from enumerate_ir.tcl (stdin or file argument),
computes DR length for each IR code, groups results, and writes
a JSON report.

DR length detection:
  Two DR shifts with complementary patterns (0xAAA... / 0x555...).
  XOR of captures = 0 for the first DR_LEN bits, then all 1s.
  DR_LEN = position of the first set bit in the XOR.

Usage:
  python3 analyze_results.py raw_output.txt [output.json]
  quartus_stp -t enumerate_ir.tcl | python3 analyze_results.py - results.json
"""

import json
import sys
from collections import defaultdict

KNOWN_IR = {
    0x000: "EXTEST",
    0x001: "PULSE_NCONFIG",
    0x002: "CONFIG_IO",
    0x004: "NCE (config error)",
    0x005: "SAMPLE/PRELOAD",
    0x006: "IDCODE",
    0x007: "USERCODE",
    0x008: "CLAMP",
    0x009: "HIGHZ",
    0x00C: "USER0 (VIR)",
    0x00E: "USER1 (VDR)",
    0x3FF: "BYPASS",
}


def hex_xor(a: str, b: str) -> str:
    """XOR two equal-length hex strings."""
    return "".join(
        format(int(ca, 16) ^ int(cb, 16), "X") for ca, cb in zip(a, b)
    )


def find_first_set_bit(hex_str: str) -> int:
    """Find position of the lowest set bit in a hex string (LSB on the right).

    Returns -1 if all zeros (DR longer than probe window).
    """
    val = int(hex_str, 16)
    if val == 0:
        return -1
    return (val & -val).bit_length() - 1


def count_trailing_ones(hex_str: str) -> int:
    """Count consecutive 1-bits from the MSB end of the hex string.

    For the complementary-pattern XOR, bits [DR_LEN .. MAX_DR-1] should
    all be 1.  This counts how many are, as a consistency check.
    """
    val = int(hex_str, 16)
    total_bits = len(hex_str) * 4
    count = 0
    for i in range(total_bits - 1, -1, -1):
        if val & (1 << i):
            count += 1
        else:
            break
    return count


def analyze(lines: list[str], max_dr: int = 1024) -> dict:
    """Parse raw output and compute DR lengths."""
    results = {}
    idcode = None
    hw_name = None
    dev_name = None

    for line in lines:
        line = line.strip()
        if not line or line.startswith("# progress"):
            continue
        if line.startswith("# IDCODE:"):
            idcode = line.split(":")[1].strip()
        elif line.startswith("# HW:"):
            hw_name = line.split(":", 1)[1].strip()
        elif line.startswith("# DEV:"):
            dev_name = line.split(":", 1)[1].strip()
        elif line.startswith("# "):
            continue
        elif line.startswith("IR "):
            parts = line.split()
            if len(parts) != 4:
                continue
            ir_code = int(parts[1])
            cap_a = parts[2].upper()
            cap_b = parts[3].upper()

            xor_val = hex_xor(cap_a, cap_b)
            dr_len = find_first_set_bit(xor_val)

            # consistency: all bits above dr_len should be 1
            ones_above = 0
            if dr_len >= 0:
                xor_int = int(xor_val, 16)
                expected_mask = ((1 << max_dr) - 1) ^ ((1 << dr_len) - 1)
                ones_above = bin(xor_int & expected_mask).count("1")

            # check if capture values differ in the DR region (non-deterministic)
            non_deterministic = False
            if dr_len >= 0 and dr_len > 0:
                dr_mask = (1 << dr_len) - 1
                xor_low = int(xor_val, 16) & dr_mask
                non_deterministic = xor_low != 0

            results[ir_code] = {
                "dr_len": dr_len,
                "cap_a": cap_a,
                "cap_b": cap_b,
                "xor": xor_val,
                "ones_above_dr": ones_above,
                "non_deterministic": non_deterministic,
            }

    # --- group by DR length ---
    by_length = defaultdict(list)
    for ir_code, info in sorted(results.items()):
        by_length[info["dr_len"]].append(ir_code)

    # --- build report ---
    report = {
        "meta": {
            "hw": hw_name,
            "dev": dev_name,
            "idcode": idcode,
            "max_dr_probed": max_dr,
            "total_ir_codes": len(results),
        },
        "by_dr_length": {},
        "interesting": [],
        "non_deterministic": [],
        "per_ir": {},
    }

    for dr_len in sorted(by_length.keys()):
        codes = by_length[dr_len]
        entry = {
            "count": len(codes),
            "ir_codes": codes,
        }
        if dr_len == 1:
            entry["note"] = "BYPASS (expected for unassigned codes)"
        elif dr_len == 32:
            entry["note"] = "likely IDCODE/USERCODE (32-bit)"
        elif dr_len == -1:
            entry["note"] = f"DR longer than {max_dr} bits (or no DR)"
        report["by_dr_length"][str(dr_len)] = entry

    # interesting = not BYPASS (1-bit), not well-known
    bypass_codes = set(by_length.get(1, []))
    for ir_code, info in sorted(results.items()):
        label = KNOWN_IR.get(ir_code, "")
        dr_len = info["dr_len"]

        if dr_len != 1:
            report["interesting"].append({
                "ir": ir_code,
                "ir_hex": f"0x{ir_code:03X}",
                "dr_len": dr_len,
                "known_as": label or "UNKNOWN",
            })

        if info["non_deterministic"]:
            report["non_deterministic"].append({
                "ir": ir_code,
                "ir_hex": f"0x{ir_code:03X}",
                "dr_len": dr_len,
            })

        # compact per-IR record (skip raw captures to keep JSON small)
        report["per_ir"][str(ir_code)] = {
            "dr_len": dr_len,
            "known_as": label,
            "non_det": info["non_deterministic"],
        }

    return report


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <raw_output.txt> [output.json]",
              file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = (sys.argv[2] if len(sys.argv) > 2
                   else "jtag_ir_enum_results.json")

    if input_path == "-":
        lines = sys.stdin.readlines()
    else:
        with open(input_path) as f:
            lines = f.readlines()

    # detect max_dr from the data
    max_dr = 1024
    for line in lines:
        if line.startswith("# MAX_DR:"):
            try:
                max_dr = int(line.split()[2])
            except (IndexError, ValueError):
                pass
            break

    report = analyze(lines, max_dr)

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)

    # --- print summary ---
    meta = report["meta"]
    print(f"\n{'='*60}")
    print(f"JTAG IR Enumeration — {meta['dev']}")
    print(f"IDCODE: {meta['idcode']}")
    print(f"Probed {meta['total_ir_codes']} IR codes, max DR = {meta['max_dr_probed']} bits")
    print(f"{'='*60}\n")

    print("DR length distribution:")
    for dr_len, entry in sorted(report["by_dr_length"].items(),
                                key=lambda x: int(x[0])):
        note = entry.get("note", "")
        codes = entry["ir_codes"]
        if len(codes) > 16:
            code_str = f"{len(codes)} codes"
        else:
            code_str = ", ".join(f"0x{c:03X}" for c in codes)
        print(f"  DR={dr_len:>5s} bits: {code_str}  {note}")

    if report["interesting"]:
        print(f"\nInteresting (non-BYPASS) IR codes ({len(report['interesting'])}):")
        for item in report["interesting"]:
            det = ""
            if any(nd["ir"] == item["ir"] for nd in report["non_deterministic"]):
                det = " [NON-DETERMINISTIC]"
            print(f"  IR {item['ir_hex']} ({item['ir']:>4d}): "
                  f"DR={item['dr_len']} bits  "
                  f"{item['known_as']}{det}")

    if report["non_deterministic"]:
        print(f"\nNon-deterministic captures ({len(report['non_deterministic'])}):")
        for item in report["non_deterministic"]:
            print(f"  IR {item['ir_hex']}: DR region differs between "
                  f"complementary probes")

    print(f"\nFull report: {output_path}")


if __name__ == "__main__":
    main()
