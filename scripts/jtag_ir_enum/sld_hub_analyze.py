#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Parse SLD Hub Info Register capture from sld_hub_probe.tcl.

AN 628 Virtual JTAG Hub Info Register layout (32-bit words,
shifted LSB-first so bit 0 of the register pops out first):

    Word 0 (hub header):
       [31:27] m            VIR length (bits)
       [26:19] n            number of SLD instrument nodes
       [18:08] mfg_id       JEP106 manufacturer (Altera = 0x06E)
       [07:04] hub_ip_rev
       [03:00] info_version (usually 0)

    Word i (1..n): one per SLD node:
       [31:27] inst_id      instance identifier (usually 0..n-1)
       [26:19] mfg_id_hi    JEP106 high byte (Altera tools expect 0x06E)
       [18:08] node_id      Altera "IP" ID — SignalTap = 0x000, etc.
       [07:00] node_version

Classification table (node_id → instrument type, partial — expand as
more instruments are seen):
    0x000  SignalTap II logic analyser
    0x001  In-System Memory Content Editor (ISMCE)
    0x002  Virtual Pins (in-system sources/probes)
    0x004  Debug Master (Nios II)
    0x006  Reconfig (PLL reconfig)
    0x008  Reserved / toolchain
    0x010  HPS Debug / SOCEYE (Cyclone V+)

A node_id that is NOT one of the known toolchain instruments is a
strong hint that the Cyclone IV silicon ships an undocumented SLD
node — potentially a CRAM-access channel.

Raw capture convention (sld_hub_probe.tcl):
    The VDR stream is dumped as one long hex string, MSB-hex first.
    Stream length matches STREAM_BITS (1024 bits default → 256 hex).
    Shift-order: the LSB of the hex value corresponds to the FIRST bit
    shifted out. We walk the bit-stream LSB-first in 32-bit slices.

Usage:
    sld_hub_analyze.py <raw_capture.txt> [--json OUT.json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


KNOWN_NODES = {
    0x000: "SignalTap II",
    0x001: "ISMCE (In-System Memory Content Editor)",
    0x002: "Virtual I/O (sources/probes)",
    0x003: "In-System Sources & Probes",
    0x004: "Nios II Debug",
    0x005: "Remote Update / Reconfig Controller",
    0x006: "PLL Reconfig",
    0x008: "Toolchain / reserved",
    0x010: "HPS / SOCEYE debug",
    0x132: "Signal Probe",
}

# JEP106 manufacturer ID for Altera (continuation-code 0 bank): 0x6E
ALTERA_MFG = 0x06E


def parse_stream_lines(path: Path) -> list[dict]:
    """Return list of {'vir_hex', 'stream_hex'} from a probe dump."""
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.startswith("VIR "):
            continue
        _, vir_hex, stream_hex = line.strip().split(None, 2)
        rows.append({"vir_hex": vir_hex, "stream_hex": stream_hex})
    return rows


def hex_to_int_lsb_first(hex_str: str) -> int:
    """Hex string → integer. Bit 0 of result = first bit shifted out.

    device_dr_shift -value_in_hex returns hex with the MSB of the
    hex value = last bit shifted. Python int() already interprets hex
    MSB-first, and our 'shift order' convention matches bit numbering
    (bit 0 of the int = first TDO bit).
    """
    return int(hex_str, 16)


def extract_word(bits: int, offset: int, width: int = 32) -> int:
    return (bits >> offset) & ((1 << width) - 1)


def parse_hub_word(w: int) -> dict:
    return {
        "raw": f"0x{w:08X}",
        "m": (w >> 27) & 0x1F,
        "n": (w >> 19) & 0xFF,
        "mfg_id": (w >> 8) & 0x7FF,
        "hub_ip_rev": (w >> 4) & 0xF,
        "info_version": w & 0xF,
    }


def parse_node_word(w: int) -> dict:
    node_id = (w >> 8) & 0x7FF
    return {
        "raw": f"0x{w:08X}",
        "inst_id": (w >> 27) & 0x1F,
        "mfg_id_hi": (w >> 19) & 0xFF,
        "node_id": node_id,
        "node_id_hex": f"0x{node_id:03X}",
        "node_version": w & 0xFF,
        "classification": KNOWN_NODES.get(node_id, "UNKNOWN — lead!"),
    }


def analyze_stream(stream_hex: str) -> dict:
    bits = hex_to_int_lsb_first(stream_hex)
    total_bits = len(stream_hex) * 4
    hub_w = extract_word(bits, 0, 32)
    hub = parse_hub_word(hub_w)

    # sanity checks on hub header
    hub["looks_valid"] = (
        hub["mfg_id"] == ALTERA_MFG
        and 1 <= hub["m"] <= 16
        and 0 <= hub["n"] <= 31
    )

    nodes: list[dict] = []
    # Even if the header looks bogus, still try to walk subsequent words
    # up to either n (if valid) or ~31 (fits in 1024-bit stream).
    n_walk = hub["n"] if hub["looks_valid"] else 31
    for i in range(n_walk):
        off = 32 * (i + 1)
        if off + 32 > total_bits:
            break
        nodes.append(parse_node_word(extract_word(bits, off, 32)))

    unknown_nodes = [
        nd for nd in nodes if nd["node_id"] not in KNOWN_NODES
    ]
    return {
        "hub_header": hub,
        "nodes": nodes,
        "unknown_node_count": len(unknown_nodes),
        "unknown_nodes": unknown_nodes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("capture", type=Path, help="raw capture from sld_hub_probe.tcl")
    ap.add_argument("--json", type=Path, default=None, help="write JSON report")
    args = ap.parse_args()

    rows = parse_stream_lines(args.capture)
    if not rows:
        print(f"ERROR: no VIR lines parsed from {args.capture}", file=sys.stderr)
        return 1

    report = []
    for r in rows:
        a = analyze_stream(r["stream_hex"])
        report.append({
            "vir_hex": r["vir_hex"],
            "analysis": a,
        })

    # --- console summary ---
    print("=" * 72)
    print(f"SLD Hub probe analysis — {args.capture}")
    print("=" * 72)
    for entry in report:
        a = entry["analysis"]
        hub = a["hub_header"]
        lead = "VALID" if hub["looks_valid"] else "invalid"
        print(f"\nVIR = 0x{entry['vir_hex']}   hub header: {lead}")
        print(f"  raw           = {hub['raw']}")
        print(f"  m (VIR len)   = {hub['m']}")
        print(f"  n (nodes)     = {hub['n']}")
        print(f"  mfg_id        = 0x{hub['mfg_id']:03X}"
              f" {'(Altera)' if hub['mfg_id'] == ALTERA_MFG else '(NON-ALTERA)'}")
        print(f"  hub_ip_rev    = {hub['hub_ip_rev']}")
        print(f"  info_version  = {hub['info_version']}")
        if a["nodes"]:
            print(f"  nodes enumerated: {len(a['nodes'])}")
            for i, nd in enumerate(a["nodes"]):
                flag = " ← UNKNOWN" if nd["node_id"] not in KNOWN_NODES else ""
                print(f"    [{i}] inst={nd['inst_id']:2d} "
                      f"node_id={nd['node_id_hex']} "
                      f"mfg_hi=0x{nd['mfg_id_hi']:02X} "
                      f"ver={nd['node_version']} "
                      f"— {nd['classification']}{flag}")
        if a["unknown_node_count"]:
            print(f"  *** {a['unknown_node_count']} unknown node(s) — investigate ***")

    if args.json:
        args.json.write_text(json.dumps(report, indent=2))
        print(f"\nJSON report: {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
