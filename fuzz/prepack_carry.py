#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.4 — pre-pack BEL pinning for CE6_CARRY chains.

nextpnr-generic has no chain-aware placer, so a counter synthesized
through ``synth/ep4ce6_map.v`` will be scattered across the fabric and
will not close routing against our sig-cache. This script reads a
post-Yosys JSON, walks the ``$alu``-replacement chain, and stamps every
CE6_CARRY and sibling DFF with an explicit ``NEXTPNR_BEL`` attribute.
The annotated JSON is consumed *directly* by ``np2fasm.py`` — nextpnr-
generic is skipped for the first-flash path because its built-in packer
rejects ``CE6_CARRY`` cells.

LE-internal feedback (no Route-A buffers): Quartus carry counters have
ZERO external route cells — DFF.Q → carry input feedback is LE-internal
on Cyclone IV silicon. Each carry bit needs exactly one LE (CE6_CARRY +
DFF on the same N slot). No buffer LEs are needed, so a single LAB can
hold up to 16 carry bits.

First-flash target LAB: **(4, 18)** — the only LAB with full 16×16 LUT
minterm calibration in ep4ce6_bitdb.sqlite.

Usage
-----
::

    python3 fuzz/prepack_carry.py counter3.json counter3_placed.json
    python3 synth/np2fasm.py counter3_placed.json > counter3.fasm
    python3 fuzz/fasm2rbf.py counter3.fasm base.rbf counter3.rbf
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# LAB(4, 18) — first-flash target. With LE-internal feedback (no
# Route-A buffers), each carry bit needs exactly one LE. All 16
# even-N slots are available for carry.
LAB_X = 4
LAB_Y = 18
ALL_NS = (0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30)

_CHAIN_RE = re.compile(r"chain\[(\d+)\]")


def _chain_bit(cell_name: str) -> int | None:
    """Extract the bit index from a Yosys chain cell name, e.g.
    ``$auto$alumacc.cc:512:replace_alu$4.chain[2].bit_`` -> 2."""
    m = _CHAIN_RE.search(cell_name)
    return int(m.group(1)) if m else None


def prepack(design: dict) -> tuple[dict, list[str]]:
    """Stamp NEXTPNR_BEL on every chain cell. Returns (design, warns)."""
    warns: list[str] = []

    modules = design.get("modules", {})
    BLACKBOX = {"CE6_CARRY", "DFF", "LUT", "GENERIC_SLICE", "GENERIC_IOB"}
    mod_name = next(
        (m for m in modules if m not in BLACKBOX),
        next(iter(modules), None),
    )
    if mod_name is None:
        warns.append("ERROR: no modules in JSON")
        return design, warns

    cells = modules[mod_name]["cells"]

    carries: dict[int, tuple[str, dict]] = {}
    dffs_by_d_net: dict[int, tuple[str, dict]] = {}

    for name, cell in cells.items():
        ctype = cell.get("type", "")
        if ctype == "CE6_CARRY":
            bit = _chain_bit(name)
            if bit is None:
                warns.append(f"CARRY without chain[]: {name}")
                continue
            carries[bit] = (name, cell)
        elif ctype in ("DFF", "$_DFF_P_", "$_DFF_PP0_"):
            d_bits = cell.get("connections", {}).get("D", [])
            if len(d_bits) == 1 and isinstance(d_bits[0], int):
                dffs_by_d_net[d_bits[0]] = (name, cell)

    n_chain = len(carries)
    if n_chain == 0:
        warns.append("no CE6_CARRY chain found — nothing to pre-pack")
        return design, warns
    if n_chain > len(ALL_NS):
        warns.append(
            f"ERROR: chain length {n_chain} exceeds single-LAB capacity "
            f"{len(ALL_NS)} — re-target multiple LABs or split")
        return design, warns

    # Sort bit indices ascending and assign contiguous N slots.
    sorted_bits = sorted(carries.keys())
    for rank, bit in enumerate(sorted_bits):
        carry_name, carry_cell = carries[bit]
        carry_n = ALL_NS[rank]
        carry_cell.setdefault("attributes", {})[
            "NEXTPNR_BEL"] = f"SLICE_X{LAB_X}_Y{LAB_Y}_N{carry_n}"

        # Matching DFF: its D input is the CARRY.S output net.
        # DFF is placed on the SAME LE as the CARRY — LE-internal
        # feedback means no external routing needed.
        s_bits = carry_cell.get("connections", {}).get("S", [])
        if len(s_bits) == 1 and isinstance(s_bits[0], int):
            dff_entry = dffs_by_d_net.get(s_bits[0])
            if dff_entry:
                dff_name, dff_cell = dff_entry
                dff_cell.setdefault("attributes", {})[
                    "NEXTPNR_BEL"] = f"SLICE_X{LAB_X}_Y{LAB_Y}_N{carry_n}"

    return design, warns


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(__doc__)
        print("usage: prepack_carry.py <in.json> <out.json>", file=sys.stderr)
        return 2
    src = Path(argv[1])
    dst = Path(argv[2])

    design = json.loads(src.read_text())
    design, warns = prepack(design)
    for w in warns:
        print(f"# {w}", file=sys.stderr)
    dst.write_text(json.dumps(design, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
