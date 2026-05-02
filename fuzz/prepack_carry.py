#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.4 — pre-pack BEL pinning for CE6_CARRY chains.

nextpnr-generic has no chain-aware placer, so a counter synthesized
through ``synth/ep4ce6_map.v`` will be scattered across the fabric and
the router will fail (cout→cin pips only exist within a column, with
N=30 → N=0 of LAB(x, y-1) the only cross-LAB hop).  This script reads
a post-Yosys JSON, walks the ``$alu``-replacement chain, and stamps
every CE6_CARRY and sibling DFF with an explicit ``NEXTPNR_BEL``.

Two consumer paths
------------------

1. **np2fasm direct**: nextpnr-generic is skipped — annotated JSON is
   read directly by ``np2fasm.py``.  CE6_CARRY[i] and DFF[i] both go
   to ``SLICE_X{x}_Y{y}_N{n}`` (same bel name, np2fasm doesn't care
   about the chipdb's CARRY_/SLICE_ split).  This was the original
   first-flash target (LAB (4, 18), single-LAB ≤ 16 bits).

2. **nextpnr-generic + router2**: ``mode="nextpnr"`` writes to the
   chipdb's actual bel names — ``CARRY_X{x}_Y{y}_N{n}`` for the carry
   primitive and ``SLICE_X{x}_Y{y}_N{n_dff}`` for the DFF.  The DFF
   N is intentionally **different** from the carry's N so the
   CE6_CARRY's A/B inputs don't share dataa/datab wires with a
   passthrough DFF (those wires are ``carry_*`` since the chipdb fix
   for the X4_Y21_N28 collision, but the placer can still pick a
   colliding pattern in dense layouts).  Multi-LAB chains pack
   sequentially: bits 0..15 at (X, Y), 16..31 at (X, Y-1) so
   N=30 → N=0 cross-LAB carry pip handles bit 15→16.

LE-internal feedback (silicon truth, mode="np2fasm"): Quartus carry
counters have ZERO external route cells — DFF.Q → carry-B feedback is
LE-internal on Cyclone IV silicon.  Each carry bit + register pair
fits in one LE.  np2fasm's LUT_ARITH-multi-LAB emission handles the
single-LAB and multi-LAB chains via the FASM ``LUT_ARITH`` /
``LUT_ARITH_MULTI_LAB`` directives.

For the nextpnr path, S→D goes through external routing because the
chipdb model can't represent silicon's internal FF-D-from-S MUX.  The
router emits an INTRA_LAB pip from carry_S to a SLICE I[0] in the
same LAB; np2fasm picks that up as a normal route emission.

Usage
-----
::

    # np2fasm direct (legacy, single-LAB)
    python3 fuzz/prepack_carry.py counter3.json counter3_placed.json
    python3 synth/np2fasm.py counter3_placed.json > counter3.fasm
    python3 fuzz/fasm2rbf.py counter3.fasm base.rbf counter3.rbf

    # nextpnr-generic mode (multi-LAB allowed)
    python3 fuzz/prepack_carry.py --mode nextpnr counter3.json out.json
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

# Multi-LAB nextpnr-mode column.  cout→cin pip goes N=30@(x,y) →
# N=0@(x,y-1) ONLY when Y-1 is a valid LAB at the same X (silicon
# adjacency, gap-free).  config.LAB_Y has gaps at Y=15 and Y=20;
# config.INVALID_LABS additionally excises specific (x,y) cells —
# notably X∈{3..9} for Y∈{12,13,14,16}.
#
# So per-X column shape varies.  X=4: valid Y = [2..11, 17, 18, 19,
# 21]; longest run = 11..2 = 10 LABs (160 LE).  X=10: valid Y =
# [2..14, 17, 18, 19, 21]; longest run = 14..2 = 13 LABs.
#
# Single-LAB default: X=4 / Y=21 — only LAB with both full
# LAB_CLK_SEL_LE N=0..30 mining AND OUTROUTE_G15-mined N=0 (matches
# scripts/led_blink/build_open.py's LED_DRIVER_BEL).
NEXTPNR_LAB_X = 4
NEXTPNR_LAB_Y_TOP = 21

# Multi-LAB default: X=4 / Y=18 → Y=17 — the silicon-validated
# W=17/W=23 hand-FASM column (memory `multi_lab_carry_silicon_
# validated_2026_05_03`).  Both LABs have full LAB_CLK_SEL_LE
# coverage, the multi_lab arith blob is mined here, and
# OUTROUTE_G15 is mined for X4Y17N0 + X4Y17N12 — meaning a 17-bit
# chain (chain[16]@X4Y17N0) and a 23-bit chain (chain[22]@X4Y17N12)
# both naturally place chain[high] on a mined output position.
NEXTPNR_LAB_X_LONG = 4
NEXTPNR_LAB_Y_TOP_LONG = 18


def _build_valid_set() -> set[tuple[int, int]]:
    # Mirror config.LAB_X / LAB_Y / INVALID_LABS without importing
    # so this module stays standalone-runnable.
    lab_x = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21,
             22, 23, 24, 25, 26, 28, 29, 31]
    lab_y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14,
             16, 17, 18, 19, 21]
    invalid = (
        {(x, y) for x in [3, 4, 5, 6, 7, 8] for y in [12, 13, 14, 16]}
        | {(9, y) for y in [12, 13, 14, 16]}
        | {(x, 15) for x in lab_x + [5, 9, 14, 30, 32, 33]}
    )
    return {(x, y) for x in lab_x for y in lab_y if (x, y) not in invalid}


_VALID_LABS = _build_valid_set()

_CHAIN_RE = re.compile(r"chain\[(\d+)\]")


def _chain_bit(cell_name: str) -> int | None:
    """Extract the bit index from a Yosys chain cell name, e.g.
    ``$auto$alumacc.cc:512:replace_alu$4.chain[2].bit_`` -> 2."""
    m = _CHAIN_RE.search(cell_name)
    return int(m.group(1)) if m else None


def prepack(design: dict, *, mode: str = "np2fasm") -> tuple[dict, list[str]]:
    """Stamp NEXTPNR_BEL on every chain cell.

    mode="np2fasm" (default) — single-LAB ≤16 carry bits, CARRY+DFF
        co-located at same N (silicon-correct LE-internal feedback;
        nextpnr is bypassed).  Backward compatible with first-flash
        path.
    mode="nextpnr" — chain follows a column down (top LAB Y → Y-1 → …)
        16 bits per LAB.  CARRY pinned to ``CARRY_X{x}_Y{y}_N{n}``,
        DFF pinned to a *different* SLICE in the same LAB so dataa /
        datab wires don't collide between PACKER_GND and live nets.

        Note: nextpnr-generic 0.10 resolves NEXTPNR_BEL JSON
        attributes during JSON read, *before* the chipdb's
        --pre-pack / --run script has added bels — so the JSON-attr
        path crashes with ``no bel named CARRY_X*_Y*_N*``.  Use
        ``emit_pre_place_hook`` (and pass the resulting .py to
        ``--pre-place``) instead.

    Returns (design, warns).
    """
    warns: list[str] = []

    if mode not in ("np2fasm", "nextpnr"):
        warns.append(f"ERROR: unknown mode {mode!r}")
        return design, warns

    modules = design.get("modules", {})
    # Pick the user module: the only one that actually contains
    # cells.  Blackbox declarations (CE6_CARRY, DFF, LUT,
    # GENERIC_SLICE, GENERIC_IOB, EP4CE6_M9K, $__M9K_*) all have empty
    # ``cells`` sections.
    mod_name = next(
        (m for m, body in modules.items() if body.get("cells")),
        None,
    )
    if mod_name is None:
        warns.append("ERROR: no module with cells in JSON")
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

    sorted_bits = sorted(carries.keys())

    if mode == "np2fasm":
        if n_chain > len(ALL_NS):
            warns.append(
                f"ERROR: np2fasm-mode chain length {n_chain} exceeds "
                f"single-LAB capacity {len(ALL_NS)} — use mode=nextpnr "
                f"or split the chain")
            return design, warns

        for rank, bit in enumerate(sorted_bits):
            carry_name, carry_cell = carries[bit]
            carry_n = ALL_NS[rank]
            bel = f"SLICE_X{LAB_X}_Y{LAB_Y}_N{carry_n}"
            carry_cell.setdefault("attributes", {})["NEXTPNR_BEL"] = bel

            # Matching DFF: D input is the CARRY.S output net.
            # CARRY + DFF on the same LE — LE-internal feedback.
            s_bits = carry_cell.get("connections", {}).get("S", [])
            if len(s_bits) == 1 and isinstance(s_bits[0], int):
                dff_entry = dffs_by_d_net.get(s_bits[0])
                if dff_entry:
                    _, dff_cell = dff_entry
                    dff_cell.setdefault("attributes", {})[
                        "NEXTPNR_BEL"] = bel

        return design, warns

    # mode == "nextpnr": pin to chipdb's actual bel names, walk Y down
    # for chains > 16 bits.  Carry chain pips only exist between
    # silicon-adjacent Y rows, so we walk through _VALID_LABS in
    # contiguous runs only.
    #
    # CARRY + DFF co-locate at the SAME N (silicon-correct LE-internal
    # feedback).  The chipdb fix that gave CE6_CARRY its own carry_A /
    # carry_B wires (separate from GENERIC_SLICE.dataa / datab) lets
    # the two cells share an LE without dataa / datab nets colliding
    # between PACKER_GND on the carry input and a real D-net on the
    # DFF input.  np2fasm's carry-chain walker emits one LUT_ARITH per
    # carry-DFF LE pair without sig-cache ROUTE for the S→D feedback,
    # which is the silicon-validated emission shape.
    LAB_CAPACITY = len(ALL_NS)
    n_labs = (n_chain + LAB_CAPACITY - 1) // LAB_CAPACITY
    if n_labs == 1:
        chain_x = NEXTPNR_LAB_X
        primary_top = NEXTPNR_LAB_Y_TOP
    else:
        chain_x = NEXTPNR_LAB_X_LONG
        primary_top = NEXTPNR_LAB_Y_TOP_LONG

    def _contiguous_run(x: int, top_y: int, length: int) -> list[int] | None:
        if (x, top_y) not in _VALID_LABS:
            return None
        ys: list[int] = [top_y]
        cur = top_y
        while len(ys) < length:
            nxt = cur - 1
            if (x, nxt) not in _VALID_LABS:
                return None
            ys.append(nxt)
            cur = nxt
        return ys

    chain_ys = _contiguous_run(chain_x, primary_top, n_labs)
    if chain_ys is None:
        # Fall back: search every valid LAB column for a long-enough run.
        candidates = sorted(_VALID_LABS, key=lambda xy: (-xy[1], xy[0]))
        for cx, cy in candidates:
            run = _contiguous_run(cx, cy, n_labs)
            if run is not None:
                chain_x = cx
                chain_ys = run
                break
    if chain_ys is None:
        warns.append(
            f"ERROR: no contiguous Y run of {n_labs} LABs in any column "
            f"(chain length {n_chain})")
        return design, warns

    # CARRY[bit] -> CARRY_X{chain_x}_Y{lab_y}_N{n}.  DFFs go to the
    # SAME LAB but a *different* N from the carry that produced their
    # D net, so the dff's I[0] (=dataa) and the carry's A (=carry_A,
    # post chipdb fix) live on disjoint wires.  Pick DFF N = carry N
    # of the bit's adjacent partner via a fixed offset; if that
    # collides because two carries map to the same DFF home, fall
    # back to the first free even-N in the same LAB.
    occupied: dict[tuple[int, int], set[int]] = {}
    carry_loc: dict[int, tuple[int, int, int]] = {}

    for rank, bit in enumerate(sorted_bits):
        lab_idx = rank // LAB_CAPACITY
        within = rank % LAB_CAPACITY
        ly = chain_ys[lab_idx]
        cn = ALL_NS[within]
        carry_loc[bit] = (chain_x, ly, cn)
        # Same-N placement: the GENERIC_SLICE bel at z=cn is occupied
        # by the matching DFF in the loop below.  We don't add cn to
        # occupied[(chain_x, ly)] here because the CARRY itself sits
        # at z=cn+100 (different bel-z, same LE) — the DFF needs the
        # GENERIC_SLICE z=cn slot, which is still free at this point.
        carry_name, carry_cell = carries[bit]
        carry_cell.setdefault("attributes", {})[
            "NEXTPNR_BEL"] = f"CARRY_X{chain_x}_Y{ly}_N{cn}"

    # DFFs: pin to the SAME (X, Y, N) as the CARRY whose S they
    # capture.  The chipdb's GENERIC_SLICE (z=cn) and CE6_CARRY
    # (z=cn+100) are co-located bels; LE-internal feedback (Q →
    # carry_B) is modelled by the LE_INTERNAL pip introduced
    # alongside the carry_A / carry_B wire split.
    for bit in sorted_bits:
        carry_name, carry_cell = carries[bit]
        s_bits = carry_cell.get("connections", {}).get("S", [])
        if len(s_bits) != 1 or not isinstance(s_bits[0], int):
            continue
        dff_entry = dffs_by_d_net.get(s_bits[0])
        if not dff_entry:
            continue
        cx, cy, cn = carry_loc[bit]
        _, dff_cell = dff_entry
        dff_cell.setdefault("attributes", {})[
            "NEXTPNR_BEL"] = f"SLICE_X{cx}_Y{cy}_N{cn}"

    return design, warns


def compute_bel_map(design: dict, *, mode: str = "nextpnr"
                    ) -> tuple[dict[str, str], list[str]]:
    """Return ``{cell_name: bel_name}`` for chain CARRY + matching DFFs.

    Wraps ``prepack`` and parses the resulting NEXTPNR_BEL attributes
    out of the in-memory design.  ``mode`` defaults to ``"nextpnr"``
    here because the helper exists specifically to feed the
    --pre-place hook for the nextpnr-generic flow.
    """
    annotated, warns = prepack(design, mode=mode)
    bel_map: dict[str, str] = {}
    for mname, m in annotated.get("modules", {}).items():
        for cname, cell in m.get("cells", {}).items():
            attrs = cell.get("attributes", {})
            bel = attrs.get("NEXTPNR_BEL")
            if bel:
                bel_map[cname] = bel
    return bel_map, warns


def emit_pre_place_hook(bel_map: dict[str, str], *,
                        extra_pin_lines: str = "") -> str:
    """Render a --pre-place Python script that ``ctx.bindBel``s
    every (cell -> bel) pair, with locked strength.

    ``extra_pin_lines`` is appended verbatim and is intended for the
    caller to splice in IOB pin bindings.  The cell-name lookup is
    string-keyed because Yosys preserves cell names through the
    nextpnr-generic packer's LUT-FF / non-LUT-FF passes only with
    specific suffixes (``_DFFLC``, ``_LC``); we strip those at lookup
    time so the map matches both pre- and post-pack names.
    """
    import json as _json
    return (
        "# SPDX-License-Identifier: GPL-3.0-or-later\n"
        "# Auto-generated by fuzz/prepack_carry.py:emit_pre_place_hook\n"
        "import nextpnrpy_generic as npnr  # type: ignore\n"
        "BEL_MAP = " + _json.dumps(bel_map, indent=2) + "\n"
        "_PACK_SUFFIXES = ('_DFFLC', '_LC')\n"
        "def _strip(name):\n"
        "    for s in _PACK_SUFFIXES:\n"
        "        if name.endswith(s):\n"
        "            return name[:-len(s)]\n"
        "    return name\n"
        "_bound = 0\n"
        "_missing = 0\n"
        "for kv in ctx.cells:\n"
        "    name = str(kv.first)\n"
        "    cell = kv.second\n"
        "    bel = BEL_MAP.get(name) or BEL_MAP.get(_strip(name))\n"
        "    if bel is None:\n"
        "        continue\n"
        "    try:\n"
        "        ctx.bindBel(bel, cell, npnr.STRENGTH_LOCKED)\n"
        "        _bound += 1\n"
        "    except Exception as e:\n"
        "        print(f'  WARN: bind {name} -> {bel}: {e}')\n"
        "        _missing += 1\n"
        "print(f'[prepack_carry] bound {_bound}/{len(BEL_MAP)} carry+DFF cells '\n"
        "      f'(missing {_missing})')\n"
        + extra_pin_lines
    )


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="prepack CE6_CARRY chains")
    ap.add_argument("input", help="input Yosys JSON")
    ap.add_argument("output", help="output annotated JSON")
    ap.add_argument("--mode", default="np2fasm",
                    choices=("np2fasm", "nextpnr"),
                    help="np2fasm (single-LAB direct, default) or "
                         "nextpnr (multi-LAB, chipdb bel names)")
    args = ap.parse_args(argv[1:])

    design = json.loads(Path(args.input).read_text())
    design, warns = prepack(design, mode=args.mode)
    for w in warns:
        print(f"# {w}", file=sys.stderr)
    Path(args.output).write_text(json.dumps(design, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
