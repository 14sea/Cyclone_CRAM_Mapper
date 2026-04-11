# SPDX-License-Identifier: GPL-3.0-or-later
"""fasm2rbf — Phase 4 MVP bitgen.

Parses a minimal FASM dialect and emits a CRC-valid EP4CE6 RBF by driving
LutCodec + RouteCodec + patch_rbf_crc. The goal of this first cut is to
prove that the Phase 2/3 codecs can be composed from a human-readable
feature list — the same composition that a future nextpnr/Yosys backend
would emit.

Supported lines (whitespace + blank + '#' comments ignored):

    # LUT truth table at a specific LE
    X{x}Y{y}N{n}.LUT = 0xHHHH

    # Inter-LAB route from source LAB to a destination LE input port
    ROUTE X{sx}Y{sy} -> X{dx}Y{dy}N{dn}.{port}

    # Enable global clock network (PIN_E1 → all LAB CLK inputs)
    GCLK

    # Enable DFF register at a specific LE
    X{x}Y{y}N{n}.DFF

The base RBF must be a valid "zero" baseline for the source LAB (e.g.
results/rbf/lits_zero_{sx}_{sy}.rbf). Multiple ROUTE lines are merged
into a single apply_routing call. LUT writes are XOR-deltas, applied on
top of the routed buffer — safe because LUT TT bits and routing bits
live in disjoint CRAM bytes (LUT in pairs ~16-23, LI in pairs 0-8, R4/
R24 in the prev column).

Usage:
    python3 fasm2rbf.py <design.fasm> <base.rbf> <out.rbf>
"""
import os
import re
import sys
import sqlite3
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import LutCodec, RouteCodec, patch_rbf_crc
from route_synth import parse_need, plan_hops, pick_li_envelope, emit_ops
import route_signatures

ROOT = Path(HERE).parent
DB_PATH = ROOT / "results" / "ep4ce6_bitdb.sqlite"


_LUT_RE = re.compile(
    r"^X(?P<x>\d+)Y(?P<y>\d+)N(?P<n>\d+)\.LUT\s*=\s*0x(?P<mask>[0-9a-fA-F]+)$"
)
_ROUTE_RE = re.compile(
    r"^ROUTE\s+X(?P<sx>\d+)Y(?P<sy>\d+)(?:N(?P<sn>\d+))?\s*->\s*"
    r"X(?P<dx>\d+)Y(?P<dy>\d+)N(?P<dn>\d+)\.(?P<port>\w+)$"
)
_BIT_RE = re.compile(
    r"^BIT\s+(?P<off>0x[0-9a-fA-F]+|\d+)\s+(?P<bp>[0-7])$"
)
_SRC_RE = re.compile(r"^SRC\s+X(?P<sx>\d+)Y(?P<sy>\d+)$")
_DFF_RE = re.compile(
    r"^DFF\s+X(?P<x>\d+)Y(?P<y>\d+)\.(?P<mode>ARST|ENA)$"
)
# Per-LE DFF enable: X{x}Y{y}N{n}.DFF
_DFF_LE_RE = re.compile(
    r"^X(?P<x>\d+)Y(?P<y>\d+)N(?P<n>\d+)\.DFF$"
)
# M9K init content: X{x}Y{y}N{n}.INIT_{width}x{depth} = 0x<hex>
# The hex payload is depth words, word 0 first, each `width` bits wide,
# MSB-first within the byte string (standard Python int.to_bytes style).
_M9K_INIT_RE = re.compile(
    r"^X(?P<x>\d+)Y(?P<y>\d+)N(?P<n>\d+)\.INIT_"
    r"(?P<width>\d+)x(?P<depth>\d+)\s*=\s*0x(?P<hex>[0-9a-fA-F]+)$"
)
_GCLK_RE = re.compile(r"^GCLK$")

# 17 position-independent, seed-stable GCLK cells mined 2026-04-10
# from 4-position × 4-seed intersection of comb-vs-reg pair-diffs.
# These enable the global clock network that routes PIN_E1 (CLK) to
# every LAB's clock input.
_GCLK_CELLS = [
    (11746, 4), (12167, 4), (13191, 4), (13401, 4), (13613, 4),
    (15292, 4), (15923, 4), (18001, 4), (18218, 2), (18869, 2),
    (19678, 4), (20099, 4), (247550, 2), (248189, 2), (363039, 2),
    (363459, 2), (363883, 2),
]


_DFF_CELLS_CACHE = None


def _load_dff_cells():
    global _DFF_CELLS_CACHE
    if _DFF_CELLS_CACHE is not None:
        return _DFF_CELLS_CACHE
    path = ROOT / "results" / "dff_cells_mined.json"
    if path.exists():
        import json
        raw = json.loads(path.read_text())
        _DFF_CELLS_CACHE = {
            k: [(off, bp) for off, bp in v] for k, v in raw.items()
        }
    else:
        _DFF_CELLS_CACHE = {}
    return _DFF_CELLS_CACHE


def _dff_le_cells(x, y, n):
    """Return per-LE DFF enable CRAM cells for LE at (x, y, n).

    Uses lookup table from multi-seed comb-vs-reg pair-diff mining
    (results/dff_cells_mined.json).  Falls back to empty list if
    unmined — under-mining is safe because unstripped DFF cells in
    the sig-cache route ops survive as single-flip routing.
    """
    table = _load_dff_cells()
    key = f"{x},{y},{n}"
    return table.get(key, [])


class FasmError(ValueError):
    pass


def parse_fasm(text):
    """Return (luts, routes) from FASM text.

    luts:   list of (x, y, n, mask_int)
    routes: list of (sx, sy, dx, dy, dn, port)
    """
    luts = []
    routes = []
    bits = []
    srcs = []
    dffs = []  # list[(x, y, mode)] mode in {"ARST","ENA"}
    dff_les = []  # list[(x, y, n)] per-LE DFF enable
    m9k_inits = []  # list[(x, y, n, width, depth, target_words)]
    gclk = False
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _LUT_RE.match(line)
        if m:
            luts.append(
                (int(m["x"]), int(m["y"]), int(m["n"]), int(m["mask"], 16))
            )
            continue
        m = _ROUTE_RE.match(line)
        if m:
            if m["sn"] is not None:
                routes.append(
                    (
                        int(m["sx"]),
                        int(m["sy"]),
                        int(m["sn"]),
                        int(m["dx"]),
                        int(m["dy"]),
                        int(m["dn"]),
                        m["port"],
                    )
                )
            else:
                routes.append(
                    (
                        int(m["sx"]),
                        int(m["sy"]),
                        int(m["dx"]),
                        int(m["dy"]),
                        int(m["dn"]),
                        m["port"],
                    )
                )
            continue
        m = _SRC_RE.match(line)
        if m:
            srcs.append((int(m["sx"]), int(m["sy"])))
            continue
        m = _BIT_RE.match(line)
        if m:
            off = int(m["off"], 0)
            bp = int(m["bp"])
            bits.append((off, bp))
            continue
        m = _DFF_LE_RE.match(line)
        if m:
            dff_les.append((int(m["x"]), int(m["y"]), int(m["n"])))
            continue
        m = _DFF_RE.match(line)
        if m:
            dffs.append((int(m["x"]), int(m["y"]), m["mode"]))
            continue
        m = _GCLK_RE.match(line)
        if m:
            gclk = True
            continue
        m = _M9K_INIT_RE.match(line)
        if m:
            x = int(m["x"]); y = int(m["y"]); n = int(m["n"])
            width = int(m["width"]); depth = int(m["depth"])
            hex_str = m["hex"]
            total_bits = width * depth
            expected_hex = (total_bits + 3) // 4
            if len(hex_str) != expected_hex:
                raise FasmError(
                    f"line {lineno}: INIT_{width}x{depth} expects "
                    f"{expected_hex} hex chars, got {len(hex_str)}"
                )
            blob_int = int(hex_str, 16)
            mask = (1 << width) - 1
            # Word 0 is the LSB-most word; word i = bits [i*width, (i+1)*width)
            words = [(blob_int >> (i * width)) & mask for i in range(depth)]
            m9k_inits.append((x, y, n, width, depth, words))
            continue
        raise FasmError(f"line {lineno}: unrecognized FASM: {raw!r}")
    return luts, routes, bits, srcs, dffs, dff_les, m9k_inits, gclk


def build_route_ops(routes, cells_table=None, extra_cells=None):
    """Expand ROUTE directives into a flat apply_routing op list.

    Signature-backed path: if the route is present in cells_table, collect
    raw cells directly and skip synth_route entirely. This unlocks yellow-
    zone sources AND jailbreak rows (Y=15) that parse_need rejects.

    Multi-route safety: raw cells are unioned into a set before emission, so
    cells shared between two signature-backed ROUTEs (e.g. the source-side
    R4 launch driver that appears in every route from the same src) are
    flipped exactly once — critical because apply_routing raw ops are XORs
    and a double-flip cancels.
    """
    sig_cells = set(extra_cells) if extra_cells else set()
    synth_ops = []
    for route in routes:
        # Accept both 6-tuple (legacy ROUTE X{sx}Y{sy}->X{dx}Y{dy}N{dn}.port)
        # and 7-tuple (Plan D' ROUTE X{sx}Y{sy}N{sn}->...) forms.
        if len(route) == 7:
            sx, sy, sn, dx, dy, dn, port = route
        else:
            sx, sy, dx, dy, dn, port = route
            sn = 0  # legacy corpus used src_N=0
        rk_full = route_signatures._route_key_full(
            sx, sy, sn, dx, dy, dn, port
        )
        rk_legacy = route_signatures._route_key(sx, sy, dx, dy, dn, port)
        hit = None
        if cells_table is not None:
            if rk_full in cells_table:
                hit = cells_table[rk_full]
            elif rk_legacy in cells_table:
                hit = cells_table[rk_legacy]
        if hit is not None:
            for off, bp in hit:
                sig_cells.add((off, bp))
            continue
        need = parse_need((sx, sy), (dx, dy, dn, port))
        plan = plan_hops(need)
        li = pick_li_envelope(need)
        synth_ops.extend(emit_ops(plan, li, need))

    all_ops = [
        {"type": "raw", "offset": o, "bp": b, "value": True}
        for o, b in sig_cells
    ]
    all_ops.extend(synth_ops)
    return all_ops


_OVERHEAD_CACHE = {}


def _load_overhead():
    key = "overhead"
    if key in _OVERHEAD_CACHE:
        return _OVERHEAD_CACHE[key]
    import json
    path = ROOT / "results" / "source_overhead.json"
    if not path.exists():
        _OVERHEAD_CACHE[key] = None
        return None
    raw = json.loads(path.read_text())
    parsed = {k: [(o, b) for o, b in v] for k, v in raw.items()}
    _OVERHEAD_CACHE[key] = parsed
    return parsed


def bitgen(fasm_text, base_rbf, db_path=DB_PATH, patch_crc=True):
    """Core entry — FASM text + base RBF → finished RBF bytes."""
    luts, routes, bits, srcs, dffs, dff_les, m9k_inits, gclk = parse_fasm(fasm_text)

    codec = RouteCodec()
    work = bytes(base_rbf)

    src_cells = set()
    if srcs:
        overhead = _load_overhead()
        if overhead is None:
            raise FasmError(
                "SRC directive used but results/source_overhead.json missing; "
                "run fuzz/source_overhead_build.py"
            )
        for sx, sy in srcs:
            key = f"{sx},{sy}"
            if key not in overhead:
                raise FasmError(f"SRC X{sx}Y{sy}: no overhead entry")
            for off, bp in overhead[key]:
                src_cells.add((off, bp))

    if routes or src_cells:
        cells_table = route_signatures.load_cells_full() if routes else None
        ops = build_route_ops(routes, cells_table=cells_table, extra_cells=src_cells)
        # The sig-cache was mined from pair-diff compiles that included LUT TT,
        # GCLK, and DFF cells alongside actual routing cells.  Strip known
        # non-routing cells so they don't double-flip with the dedicated GCLK /
        # DFF / LUT sections below.
        strip = set()
        if gclk:
            strip.update(_GCLK_CELLS)
        if dff_les:
            for x, y, n in dff_les:
                strip.update(_dff_le_cells(x, y, n))
        if strip:
            ops = [
                op for op in ops
                if (op["offset"], op["bp"]) not in strip
            ]
        work = codec.apply_routing(work, ops)

    if gclk:
        buf = bytearray(work)
        for off, bp in _GCLK_CELLS:
            buf[off] |= (1 << bp)       # absolute SET, not XOR toggle
        work = bytes(buf)

    if dff_les:
        buf = bytearray(work)
        # Union all DFF cells before emitting — prevents double-flip
        # of LAB-level cells shared across multiple LEs in the same LAB.
        dff_all = set()
        for x, y, n in dff_les:
            dff_all.update(_dff_le_cells(x, y, n))
        for off, bp in dff_all:
            buf[off] |= (1 << bp)       # absolute SET, not XOR toggle
        work = bytes(buf)

    if bits:
        buf = bytearray(work)
        for off, bp in bits:
            buf[off] ^= (1 << bp)
        work = bytes(buf)

    if dffs:
        # DFF directive parsing retained, but apply is DISABLED as of
        # 2026-04-08: FFCodec._FF_ARST_CELLS / _FF_ENA_CELLS were mined
        # against a CRC-unpatched baseline and ≥94% of the "cells" land on
        # frame positions 208-209 (the per-frame CRC LE bytes). The entire
        # mapping was CRC side-effects, not real FF mode bits. See memory
        # note ff_arst_ena_crc_false_positive.md. Do NOT re-enable without
        # re-mining against patch_rbf_crc'd baselines.
        raise FasmError(
            "DFF.ARST / DFF.ENA disabled — underlying FFCodec mapping is "
            "CRC byte artifacts, not real FF mode bits. Needs re-mining."
        )

    if luts:
        db = sqlite3.connect(db_path)
        try:
            # The sig-cache includes LUT TT cells from factory pair-diffs
            # (masks 0x8888/0xAAAA), so routing contaminates LUT cell
            # positions.  Fix: reset every LUT cell to the pre-routing
            # base_rbf state, then apply the accumulated predict_sram XOR
            # for all LUTs simultaneously.
            #
            # LUT cells within a LAB share "data" bytes across N values.
            # The accumulated XOR (symmetric difference of predict_sram
            # sets) produces the correct multi-LE CRAM state because the
            # encoding is XOR-linear across LEs.  Per-LE read_tt can't
            # verify this (ctrl cells are shared), but the cell-level math
            # is proven correct.
            buf = bytearray(work)

            # Phase 1: reset each LUT cell to its minterm_0 (mask=0)
            # state.  This undoes both route sig-cache contamination AND
            # the "presence delta" between nv_zero_global (no LEs) and
            # minterm_0 (one LE placed at mask 0).  For shared cells
            # (rare: 8/113 disagree across LEs), last-processed LE wins —
            # functionally irrelevant per hardware verification.
            _m0_cache = {}
            for x, y, n, mask in luts:
                lut = LutCodec.from_db(db, x, y, n)
                zero_path = (
                    ROOT / "results" / "rbf"
                    / f"minterm_0_X{x}_Y{y}_N{n}.rbf"
                )
                if zero_path.exists():
                    if zero_path not in _m0_cache:
                        _m0_cache[zero_path] = zero_path.read_bytes()
                    m0 = _m0_cache[zero_path]
                    for addr, bitpos in lut.all_cells:
                        m0_bit = (m0[addr] >> bitpos) & 1
                        cur_bit = (buf[addr] >> bitpos) & 1
                        if cur_bit != m0_bit:
                            buf[addr] ^= (1 << bitpos)

            # Phase 2: accumulate XOR flips for all LUTs.
            # predict_sram(mask) gives cells relative to minterm_0, so
            # after Phase 1 alignment the XOR is exact.
            for x, y, n, mask in luts:
                lut = LutCodec.from_db(db, x, y, n)
                for addr, bitpos in lut.predict_sram(mask):
                    buf[addr] ^= (1 << bitpos)
            work = bytes(buf)
        finally:
            db.close()

    if m9k_inits:
        from m9k_init_basis import (
            M9K_INIT_ANCHORS, write_init, read_init,
        )
        for x, y, n, width, depth, target_words in m9k_inits:
            site = f"X{x}_Y{y}_N{n}"
            key = (site, width, depth)
            if key not in M9K_INIT_ANCHORS:
                raise FasmError(
                    f"M9K {site} {width}x{depth}: no calibrated anchor; "
                    f"run fuzz/m9k_anchor_sweep.py for this site/mode"
                )
            anchor, bp = M9K_INIT_ANCHORS[key]
            base_words = read_init(work, anchor, width=width, depth=depth, bp=bp)
            work = write_init(work, anchor, base_words, target_words,
                              width=width, depth=depth, bp=bp)

    if patch_crc:
        work = patch_rbf_crc(work)
    return bytes(work)


def main(argv):
    if len(argv) != 4:
        print(
            "usage: fasm2rbf.py <design.fasm> <base.rbf> <out.rbf>",
            file=sys.stderr,
        )
        return 2
    fasm_path, base_path, out_path = argv[1], argv[2], argv[3]
    fasm_text = Path(fasm_path).read_text()
    base_rbf = Path(base_path).read_bytes()
    out = bitgen(fasm_text, base_rbf)
    Path(out_path).write_bytes(out)
    print(f"wrote {len(out)} bytes -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
