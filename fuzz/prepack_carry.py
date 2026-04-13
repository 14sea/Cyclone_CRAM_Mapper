#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.4 — pre-pack BEL pinning for CE6_CARRY chains.

nextpnr-generic has no chain-aware placer, so a counter synthesized
through ``synth/ep4ce6_map.v`` will be scattered across the fabric and
will not close routing against our sig-cache. This script does the
placement we can't yet teach nextpnr to do: it reads a post-Yosys JSON,
walks the ``$alu``-replacement chain, and stamps every CE6_CARRY,
matching b_buf LUT, and sibling DFF with an explicit ``NEXTPNR_BEL``
attribute. The annotated JSON is consumed *directly* by ``np2fasm.py``
— nextpnr-generic is skipped for the first-flash path because its
built-in packer rejects the ``CE6_CARRY`` cell type (only
``GENERIC_SLICE`` bels exist in the chipdb), and all routing is
already covered by the sig-cache at the chosen LAB.

First-flash target LAB: **(4, 18)**. This is the only LAB on chip
that is (a) fully calibrated in ep4ce6_bitdb.sqlite (all 16 N slots ×
all 16 LUT minterms, so fasm2rbf can bake arbitrary LUT masks at every
LE) and (b) has enough sig-cache entries to carry a 3-bit CE6_CARRY
chain with Route-A feedback buffers. The uniform-datab (6,17) layout
from the earlier solver is unusable because (6,17) has zero minterm
calibration in the bitdb. The (4,18) layout is mixed-port on the
buffer input side:

  bit 0: CARRY @ N4, buffer @ N12, feedback pip = dataa
  bit 1: CARRY @ N6, buffer @ N14, feedback pip = datac
  bit 2: CARRY @ N8, buffer @ N2,  feedback pip = datad

``synth/ep4ce6_map.v`` uses a uniform ``INIT=0xfffe`` (LUT4 OR-identity
on whichever single input is driven) plus a per-bit wire plug to feed
B_used into the correct LUT4 pin so nextpnr routes the feedback onto
the sig-cache-backed dataX pip for that bit.

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

# LAB(4, 18) mixed-port 3-bit chain slots (see module docstring).
LAB_X = 4
LAB_Y = 18
CARRY_NS = (4, 6, 8)    # contiguous arith-mode LEs
BUF_NS   = (12, 14, 2)  # b_buf LUTs (normal-mode LEs in same LAB)

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
    bufs:    dict[int, tuple[str, dict]] = {}
    dffs_by_d_net: dict[int, tuple[str, dict]] = {}

    for name, cell in cells.items():
        ctype = cell.get("type", "")
        if ctype == "CE6_CARRY":
            bit = _chain_bit(name)
            if bit is None:
                warns.append(f"CARRY without chain[]: {name}")
                continue
            carries[bit] = (name, cell)
        elif ctype == "LUT":
            bit = _chain_bit(name)
            if bit is None:
                continue  # some other LUT — leave alone
            bufs[bit] = (name, cell)
        elif ctype in ("DFF", "$_DFF_P_", "$_DFF_PP0_"):
            d_bits = cell.get("connections", {}).get("D", [])
            if len(d_bits) == 1 and isinstance(d_bits[0], int):
                dffs_by_d_net[d_bits[0]] = (name, cell)

    n_chain = len(carries)
    if n_chain == 0:
        warns.append("no CE6_CARRY chain found — nothing to pre-pack")
        return design, warns
    if n_chain > len(CARRY_NS):
        warns.append(
            f"ERROR: chain length {n_chain} exceeds LAB(6,17) capacity "
            f"{len(CARRY_NS)} — re-target a different LAB or split")
        return design, warns

    # Sort bit indices ascending and assign N slots in chain order.
    sorted_bits = sorted(carries.keys())
    for rank, bit in enumerate(sorted_bits):
        carry_name, carry_cell = carries[bit]
        carry_n = CARRY_NS[rank]
        carry_cell.setdefault("attributes", {})[
            "NEXTPNR_BEL"] = f"SLICE_X{LAB_X}_Y{LAB_Y}_N{carry_n}"

        # Matching buffer for this bit.
        if bit in bufs:
            buf_name, buf_cell = bufs[bit]
            buf_cell.setdefault("attributes", {})[
                "NEXTPNR_BEL"] = f"SLICE_X{LAB_X}_Y{LAB_Y}_N{BUF_NS[rank]}"
        else:
            warns.append(f"WARN: bit {bit} has no b_buf — route won't close")

        # Matching DFF: its D input is the CARRY.S output net.
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
