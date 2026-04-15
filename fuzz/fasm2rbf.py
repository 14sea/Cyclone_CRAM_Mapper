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

    # Arith-mode LUT (carry chain) — same 16-bit mask layout as .LUT
    # (upper byte = sum LUT, lower byte = cout LUT in Cyclone IV arith
    # encoding) but also triggers the LAB-wide carry-chain activation
    # cells from results/arith_cells_mined.json.  Multiple arith LEs in
    # the same LAB union-fill from a single blob lookup.
    X{x}Y{y}N{n}.LUT_ARITH = 0xHHHH

    # Inter-LAB route from source LAB to a destination LE input port
    ROUTE X{sx}Y{sy} -> X{dx}Y{dy}N{dn}.{port}

    # Legacy GCLK directive (17-cell hardcoded list) — actually local-
    # clock distribution at LAB(10,4), NOT a real GCLK_BUS.  Works for
    # tiny test designs where Quartus refuses auto-promotion.  Absolute
    # OR (not XOR), so composes additively with any baseline.
    GCLK

    # Per-pin GCLK source activate (XOR-delta).  Flips the cells that
    # Quartus would flip when forcing GLOBAL_SIGNAL on CLK at PIN_X.
    # Cells from results/clk_cross_pin_spine_check.json.  Known pins:
    # PIN_E1 (3 cells → GCLK2), PIN_R8 (5 cells → GCLK3).
    GCLK_PIN PIN_E1

    # Per-LAB CLK_SEL (XOR-delta).  Flips the cells that route a global
    # clock into this LAB.  Cells from results/clk_lab_sel_probe_X{x}Y{y}
    # .json.  Known LABs: (10,4)=26 cells, (10,16)=53 cells,
    # (22,10)=45 cells.  Mine more with fuzz/clk_lab_sel_probe.py.
    LAB_CLK_SEL X10Y4

    # Per-LE CLK_SEL layer (XOR-delta).  The N-invariant LAB_CLK_SEL above
    # captures only cells that are shared between N=0 and N=4 sinks.  Per-
    # LE sink routing (e.g. the clock network fanin to LE N=0) lives in
    # cells that the N-invariant intersection filters out as "noise".  HW
    # verified 2026-04-14 at LAB(10,4).N=0: the N-invariant subset alone
    # is not functional, the full N=0 forced-vs-auto diff is.  Emit this
    # directive alongside LAB_CLK_SEL for every LE that needs a clock.
    # Disjoint from LAB_CLK_SEL (by construction: N-invariant = ∩, per-LE
    # = difference), so XOR composition is safe.
    LAB_CLK_SEL_LE X10Y4N0

    # DFF register marker (no-op — DFF is intrinsic to every LE)
    X{x}Y{y}N{n}.DFF

    # I/O block pin assignment (XOR-delta from K=E15 / LED=G15 baseline)
    IOB_IN  PIN_M16    # K input wired to chip pin M16
    IOB_OUT PIN_F15    # LED output wired to chip pin F15

    # IOB→SLICE route (XOR-delta, nv_zero_global frame).  Applies the
    # absolute cell set from results/iob_to_slice_sigcache.json, which
    # was derived by translating pair-vs-iob_zero mining deltas through
    # the pin bridge delta bridge(pin) = iob_zero(pin) ^ nv_zero_global.
    # Requires the base RBF to be nv_zero_global (or a design built on
    # top of it).  Known entries: E16/E15/M16 × {10,4,0}/{10,10,0}/
    # {16,4,0}/{10,4,2}/{10,4,4}, port=dataa.  Port canonicalization:
    # Quartus rewrites single-input LUTs to dataa, so other ports for
    # single-input designs resolve to the same cell set.
    IOB_ROUTE PIN_E16 -> X10Y4N0.dataa

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
# Arith-mode LUT: same 16-bit mask layout as normal LUT (upper byte = sum,
# lower byte = cout in Cyclone IV arith encoding), but also triggers LAB-
# wide carry-chain activation cells from results/arith_cells_mined.json.
_LUT_ARITH_RE = re.compile(
    r"^X(?P<x>\d+)Y(?P<y>\d+)N(?P<n>\d+)\.LUT_ARITH\s*=\s*0x(?P<mask>[0-9a-fA-F]+)$"
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
# Per-pin GCLK source-activate: GCLK_PIN PIN_E1
# XOR-delta semantic (diff from AUTO-mode baseline → forced-GCLK).  Cell
# sets live in results/clk_cross_pin_spine_check.json under
# per_pin_forced_vs_auto_intersection.PIN_X.  E1 → GCLK2 (3 cells),
# R8 → GCLK3 (5 cells), others TBD.  See memory gclk_per_pin_one_hot.md.
_GCLK_PIN_RE = re.compile(r"^GCLK_PIN\s+PIN_(?P<pin>[A-Z]\d+)$")
# Per-LAB CLK_SEL: LAB_CLK_SEL X{x}Y{y}
# XOR-delta semantic.  Cell sets live in
# results/clk_lab_sel_probe_X{x}Y{y}.json under "lab_clk_sel" key.
# Mined 2026-04-14 for LAB(10,4), LAB(10,16), LAB(22,10); additional
# LABs require re-running fuzz/clk_lab_sel_probe.py --lab X,Y.
_LAB_CLK_SEL_RE = re.compile(r"^LAB_CLK_SEL\s+X(?P<x>\d+)Y(?P<y>\d+)$")
# Per-LE CLK_SEL layer: LAB_CLK_SEL_LE X{x}Y{y}N{n}
# XOR-delta semantic, disjoint from LAB_CLK_SEL.  Cell sets come from
# results/clk_lab_sel_per_le.json (derived by fuzz/clk_lab_sel_per_le.py
# from the per-LAB probe JSONs; uses "n0_specific" / "n4_specific"
# buckets = per_n_forced_vs_auto[N] − N-invariant).  N must be in
# {0, 4} with the current probe; extend probe to mine more N slots.
_LAB_CLK_SEL_LE_RE = re.compile(
    r"^LAB_CLK_SEL_LE\s+X(?P<x>\d+)Y(?P<y>\d+)N(?P<n>\d+)$"
)
# IOB pin assignment.  ROLE is INPUT or OUTPUT; PIN follows the AX301
# pin-name convention (e.g. PIN_E15, PIN_G15, PIN_M16).
#
#   IOB_IN  PIN_M16   # K input wired to chip pin M16
#   IOB_OUT PIN_F15   # LED output wired to chip pin F15
#
# Cells come from results/iob_cell_map.json (per-pin mining campaign,
# 2026-04-14).  XOR-applied as a delta against the iob_in_E15 baseline,
# which is byte-identical to iob_out_G15 — that file is the canonical
# (K=E15, LED=G15) reference for IOB synthesis.
#
# Single-axis use is bit-perfect (44/44 ground-truth match): hold the
# input at PIN_E15 OR the output at PIN_G15 and vary the other.  Cross-
# axis combinations (both pins non-anchor) leak ~50-60 bytes of joint-
# placement state that Quartus chose differently in the single-axis
# sweep — those bits live in frame 0 (header) and frames 1720-1736
# (block band).  The bitstream may still be functional on hardware
# (multiple valid encodings exist), but byte-for-byte parity with a
# fresh Quartus build of the same (K, LED) pair is not guaranteed.
# Closing the cross-axis gap would need a 2D K×LED sweep.
_IOB_RE = re.compile(r"^IOB_(?P<role>IN|OUT)\s+PIN_(?P<pin>[A-Z]\d+)$")
# IOB→SLICE route directive (XOR-delta, nv_zero_global frame).  Applies
# absolute cells from results/iob_to_slice_sigcache.json — the
# bridge-translated R(IOB→target LE) footprint for pins mined under
# scripts/iob_slice_mining/.  See memory iob_slice_bridge_delta_unblocks_
# injection.md for the algebra (abs = delta ^ bridge(pin)).
_IOB_ROUTE_RE = re.compile(
    r"^IOB_ROUTE\s+PIN_(?P<pin>[A-Z]\d+)\s*->\s*"
    r"X(?P<dx>\d+)Y(?P<dy>\d+)N(?P<dn>\d+)\.(?P<port>\w+)$"
)
# Baseline-bridge directive.  Resolves the frame-split between IOB_IN/
# IOB_OUT (iob_in_E15 frame, fabric + E15/G15 pin config) and IOB_ROUTE
# (nv_zero_global frame, zero fabric + virtual pins).  When the user
# starts from nv_zero_global and wants IOB_IN/IOB_OUT to behave as if
# the base were iob_in_E15, they emit `IOB_BASELINE_NV` once; the
# directive XOR-applies results/iob_baseline_hdr_cells.json (the 74-
# byte / 132-bit-cell hdr delta (nv_zero_global ^ iob_in_E15, scoped
# to off < 5282)), turning the nv hdr band into the E15/G15 pin
# baseline without touching CRAM.  After that, IOB_IN PIN_X / IOB_OUT
# PIN_Y apply their usual pair-deltas and end up in the target pin's
# hdr config.
_IOB_BASELINE_NV_RE = re.compile(r"^IOB_BASELINE_NV$")
_IOB_BASELINE_HDR_CACHE = None

# Clock-bank pin directive.  Dedicated clock pins (E1 and siblings)
# are not in iob_cell_map.json — fuzz/iob_sweep.py only covered 44
# regular user IO pins.  IOB_CLK_INPUT PIN_X XOR-applies a hdr-band
# cell set from results/iob_clk_pin_hdr_cells.json that activates
# pin X as a GCLK driver (IOB bank config + GCLK mux selection).
# Complements `GCLK_PIN PIN_X`, which controls the fabric-side
# per-LAB clock-source activate (frames 34-35 etc.).
_IOB_CLK_INPUT_RE = re.compile(r"^IOB_CLK_INPUT\s+PIN_(?P<pin>[A-Z]\d+)$")
_IOB_CLK_INPUT_CACHE = None

# NV_BASELINE_PACK — Phase 3 of nv_zero_global retirement.  Expresses the
# byte delta nv_zero_global.rbf ^ pure_zero_rbf() as layered XOR directives
# so a caller can start from PURE_ZERO and rebuild nv_zero_global (or any
# chosen subset of it) additively.  Data source:
# results/nv_baseline_pack.json, produced by
# scripts/baseline/mine_nv_baseline_pack.py.  All cells are XOR-applied
# with parity, so double-emit (e.g. the meta NV_BASELINE_PACK plus a
# sub-directive for the same bucket) cancels cleanly.
#
# Directives (see parse_fasm for the state list):
#   NV_BASELINE_PACK           meta — applies every bucket (all 21 640
#                              cells), reproducing nv_zero_global on top
#                              of PURE_ZERO byte-for-byte.
#   IOB_BANK_DEFAULT_PACK      hdr band only (off < 5282), ~5 068 cells
#                              — per-pin LVTTL + bank-config defaults.
#   LOCAL_CLK_E1_BASELINE      2 cells at (7312,4) & (7519,4) — universal
#                              local-clock anchor (memory note
#                              lab_clk_sel_decomposes_into_local_and_gclk).
#   LOCAL_CLK_PATH_A           cells at the spine frame/bp envelope from
#                              memory gclk_16cell_spine_9_of_13_labs that
#                              actually flipped in nv_zero_global (only 2
#                              of the 16-cell candidate set; the rest are
#                              in the lab_columns buckets).
#   LAB_LOCAL_CLK X{x}         all 28 LAB-column buckets (X=3..33) —
#                              per-LAB default local-clk / idle-routing
#                              cells.  X must match a key in
#                              data["lab_columns"].
#   NV_BLOCK_COL_INFRA         low_frame_infra ∪ high_frame_infra ∪
#                              residue (~1 981 cells) — non-LAB-column
#                              infrastructure (M9K X={15,27}, mult X=20,
#                              chip-global trailer).
_NV_BASELINE_PACK_RE = re.compile(r"^NV_BASELINE_PACK$")
_IOB_BANK_DEFAULT_PACK_RE = re.compile(r"^IOB_BANK_DEFAULT_PACK$")
_LOCAL_CLK_E1_BASELINE_RE = re.compile(r"^LOCAL_CLK_E1_BASELINE$")
_LOCAL_CLK_PATH_A_RE = re.compile(r"^LOCAL_CLK_PATH_A$")
_LAB_LOCAL_CLK_RE = re.compile(r"^LAB_LOCAL_CLK\s+X(?P<x>\d+)$")
_NV_BLOCK_COL_INFRA_RE = re.compile(r"^NV_BLOCK_COL_INFRA$")
_NV_BASELINE_CACHE = None

# Reference pins: the iob_in_E15.rbf / iob_out_G15.rbf baselines were
# compiled with K=E15 (input) and LED=G15 (output).  Any FASM IOB_IN
# at PIN_E15 or IOB_OUT at PIN_G15 reduces to a no-op delta.
_IOB_K_REF = "E15"
_IOB_LED_REF = "G15"
_IOB_MAP_CACHE = None


def _load_iob_clk_input_cells(pin):
    """Return hdr-band cells activating `pin` as a clock-bank driver.

    Reads results/iob_clk_pin_hdr_cells.json (keyed by pin string).
    Raises FasmError if the pin hasn't been mined yet.
    """
    global _IOB_CLK_INPUT_CACHE
    if _IOB_CLK_INPUT_CACHE is None:
        import json
        path = ROOT / "results" / "iob_clk_pin_hdr_cells.json"
        if not path.exists():
            raise FasmError(
                "IOB_CLK_INPUT used but "
                "results/iob_clk_pin_hdr_cells.json missing; run "
                "scripts/iob_slice_mining/compute_clk_pin_hdr.py"
            )
        data = json.loads(path.read_text())
        _IOB_CLK_INPUT_CACHE = data["cells"]
    if pin not in _IOB_CLK_INPUT_CACHE:
        raise FasmError(
            f"IOB_CLK_INPUT PIN_{pin}: no entry in "
            f"iob_clk_pin_hdr_cells.json (known: "
            f"{sorted(_IOB_CLK_INPUT_CACHE)}).  Mine with "
            f"scripts/iob_slice_mining/compute_clk_pin_hdr.py"
        )
    return [tuple(c) for c in _IOB_CLK_INPUT_CACHE[pin]]


def _load_nv_baseline_pack():
    """Load results/nv_baseline_pack.json once and return the dict.

    Schema (see scripts/baseline/mine_nv_baseline_pack.py):
      meta.total_cells / meta.buckets.*  (counts only)
      iob_bank_default_pack : [[off, bp], ...]   hdr band
      local_clk_e1_baseline : [[off, bp], ...]   2 anchor cells
      local_clk_path_a      : [[off, bp], ...]   spine-candidate hits
      low_frame_infra       : [[off, bp], ...]
      high_frame_infra      : [[off, bp], ...]
      residue               : [[off, bp], ...]
      lab_columns           : {"X": [[off, bp], ...], ...}  (str keys)
    """
    global _NV_BASELINE_CACHE
    if _NV_BASELINE_CACHE is not None:
        return _NV_BASELINE_CACHE
    import json
    path = ROOT / "results" / "nv_baseline_pack.json"
    if not path.exists():
        raise FasmError(
            "NV_BASELINE_PACK / sub-directive used but "
            "results/nv_baseline_pack.json missing; run "
            "scripts/baseline/mine_nv_baseline_pack.py"
        )
    _NV_BASELINE_CACHE = json.loads(path.read_text())
    return _NV_BASELINE_CACHE


def _nv_bucket_cells(bucket):
    """Return [(off, bp), ...] for one bucket name.

    Recognised bucket names:
      'iob_bank_default_pack'
      'local_clk_e1_baseline'
      'local_clk_path_a'
      'lab_col_X<n>'        (<n> = integer column index)
      'nv_block_col_infra'  (low + high + residue)
      'nv_all'              (every bucket above ∪ all lab_columns)
    """
    data = _load_nv_baseline_pack()
    if bucket == "nv_all":
        out = []
        for k in ("iob_bank_default_pack", "local_clk_e1_baseline",
                  "local_clk_path_a", "low_frame_infra",
                  "high_frame_infra", "residue"):
            out.extend(data[k])
        for v in data["lab_columns"].values():
            out.extend(v)
        return [tuple(c) for c in out]
    if bucket == "nv_block_col_infra":
        out = []
        for k in ("low_frame_infra", "high_frame_infra", "residue"):
            out.extend(data[k])
        return [tuple(c) for c in out]
    if bucket.startswith("lab_col_X"):
        x_str = bucket[len("lab_col_X"):]
        cols = data["lab_columns"]
        if x_str not in cols:
            raise FasmError(
                f"LAB_LOCAL_CLK X{x_str}: no entry in "
                f"nv_baseline_pack.json lab_columns "
                f"(known: {sorted(cols, key=int)})"
            )
        return [tuple(c) for c in cols[x_str]]
    return [tuple(c) for c in data[bucket]]


def _load_iob_baseline_hdr_cells():
    """Return the 132-bit-cell hdr-band delta (nv_zero_global ^ iob_in_E15).

    Source: results/iob_baseline_hdr_cells.json, produced by
    scripts/iob_slice_mining/compute_baseline_hdr.py.  Cells are scoped
    to the header band (off < 5282) — applying them on top of nv_zero_
    global reproduces iob_in_E15's hdr bytes (the E15/G15 pin baseline
    that IOB_IN and IOB_OUT pair-deltas expect).
    """
    global _IOB_BASELINE_HDR_CACHE
    if _IOB_BASELINE_HDR_CACHE is not None:
        return _IOB_BASELINE_HDR_CACHE
    import json
    path = ROOT / "results" / "iob_baseline_hdr_cells.json"
    if not path.exists():
        raise FasmError(
            "IOB_BASELINE_NV used but results/iob_baseline_hdr_cells.json "
            "missing; run scripts/iob_slice_mining/compute_baseline_hdr.py"
        )
    data = json.loads(path.read_text())
    _IOB_BASELINE_HDR_CACHE = [tuple(c) for c in data["cells"]]
    return _IOB_BASELINE_HDR_CACHE


def _load_iob_map():
    """Load results/iob_cell_map.json once (per-pin signature corpus)."""
    global _IOB_MAP_CACHE
    if _IOB_MAP_CACHE is not None:
        return _IOB_MAP_CACHE
    import json
    path = ROOT / "results" / "iob_cell_map.json"
    if not path.exists():
        _IOB_MAP_CACHE = None
        return None
    _IOB_MAP_CACHE = json.loads(path.read_text())
    return _IOB_MAP_CACHE


def _iob_delta_cells(role, pin, iob_map):
    """Return XOR-delta cells (off, bp) from baseline to pin for one role.

    role in {'IN','OUT'}.  Reads pre-computed pair-delta sets written by
    iob_analyze.py — these are full XOR diffs vs the iob_in_E15 (K=E15)
    or iob_out_G15 (LED=G15) anchor RBFs and capture every cell that
    flips going from anchor to target, including semi-shared cells that
    the legacy per_pin_unique decomposition misses.
    """
    table_key = "input_delta" if role == "IN" else "output_delta"
    if table_key not in iob_map:
        raise FasmError(
            f"IOB directive needs iob_map['{table_key}']; re-run "
            f"fuzz/iob_analyze.py to regenerate iob_cell_map.json"
        )
    table = iob_map[table_key]
    if pin not in table:
        raise FasmError(
            f"IOB_{role} PIN_{pin}: no entry in iob_cell_map.json "
            f"(known: {sorted(table)})"
        )
    return [tuple(c) for c in table[pin]]

_IOB_ROUTE_CACHE = None


def _load_iob_route_cells(pin, dx, dy, dn, port):
    """Return XOR-delta cells (off, bp) for IOB_ROUTE PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}.

    Cells come from results/iob_to_slice_sigcache.json, which was built
    by scripts/iob_slice_mining/compute_absolute_cells.py as
      abs_cells = delta(pin, tgt) ^ bridge(pin)
    with bridge(pin) = iob_zero(pin) ^ nv_zero_global.  So the cells
    reproduce, when XOR'd against nv_zero_global, the exact pair RBF
    that Quartus would emit for the (pin, tgt) two-LE design — which is
    HW-verified on AX301 for the (E16, 10,4,0, dataa) entry.

    Caller must be applying this delta on top of nv_zero_global (or a
    design built on top of nv_zero_global).  Applying it on any other
    baseline produces bit-garbage silently.
    """
    global _IOB_ROUTE_CACHE
    if _IOB_ROUTE_CACHE is None:
        import json
        path = ROOT / "results" / "iob_to_slice_sigcache.json"
        if not path.exists():
            raise FasmError(
                "IOB_ROUTE directive used but "
                "results/iob_to_slice_sigcache.json missing; run "
                "scripts/iob_slice_mining/compute_absolute_cells.py"
            )
        data = json.loads(path.read_text())
        # Prefer per-entry single-LE derived cells when present.  These
        # compose cleanly with other directives (GCLK_PIN / IOB_IN /
        # IOB_OUT / LAB_CLK_SEL_LE) without pair-template secondary-LE
        # residue.  absolute_cells is the pair-derived fallback (still
        # HW-verified vs the pair RBF itself).
        single_le = data.get("single_le_cells", {})
        absolute = data.get("absolute_cells", {})
        merged = dict(absolute)
        merged.update(single_le)
        _IOB_ROUTE_CACHE = merged
    key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
    if key not in _IOB_ROUTE_CACHE:
        raise FasmError(
            f"IOB_ROUTE PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}: no entry in "
            f"iob_to_slice_sigcache.json. Known entries: "
            f"{sorted(_IOB_ROUTE_CACHE)[:5]}... "
            f"({len(_IOB_ROUTE_CACHE)} total). "
            f"Mine more with scripts/iob_slice_mining/mine_iob_routes.py "
            f"then rerun compute_absolute_cells.py."
        )
    return [tuple(c) for c in _IOB_ROUTE_CACHE[key]]


_GCLK_PIN_CACHE = None
_LAB_CLK_SEL_CACHE = {}
_LAB_CLK_SEL_LE_CACHE = None


def _load_gclk_pin_cells(pin):
    """Return XOR-delta cells for `GCLK_PIN PIN_X`.

    Data lives in results/clk_cross_pin_spine_check.json under
    per_pin_forced_vs_auto_intersection.PIN_X.  These are the cells that
    flip when PIN_X becomes the driver of a forced GCLK (vs the AUTO
    baseline where the pin is a regular input).
    """
    global _GCLK_PIN_CACHE
    if _GCLK_PIN_CACHE is None:
        import json
        path = ROOT / "results" / "clk_cross_pin_spine_check.json"
        if not path.exists():
            raise FasmError(
                "GCLK_PIN directive used but "
                "results/clk_cross_pin_spine_check.json missing; run "
                "fuzz/clk_cross_pin_spine_check.py"
            )
        data = json.loads(path.read_text())
        _GCLK_PIN_CACHE = data.get("per_pin_forced_vs_auto_intersection", {})
    key = f"PIN_{pin}"
    if key not in _GCLK_PIN_CACHE:
        raise FasmError(
            f"GCLK_PIN PIN_{pin}: no entry in clk_cross_pin_spine_check.json "
            f"(known: {sorted(_GCLK_PIN_CACHE)}). Mine it with "
            f"fuzz/clk_force_gclk_probe.py + clk_cross_pin_spine_check.py."
        )
    return [tuple(c) for c in _GCLK_PIN_CACHE[key]]


def _load_lab_clk_sel_cells(x, y):
    """Return XOR-delta cells for `LAB_CLK_SEL X{x}Y{y}`.

    Per-LAB JSONs are written by fuzz/clk_lab_sel_probe.py --lab X,Y to
    results/clk_lab_sel_probe_X{x}Y{y}.json.  The "lab_clk_sel" key is
    the N-invariant forced-vs-auto intersection minus the E1 activate
    spine — i.e., the cells that flip to route a global clock into this
    LAB (plus shared row-GCLK-tree cells, idempotent under union).
    """
    key = (x, y)
    if key in _LAB_CLK_SEL_CACHE:
        return _LAB_CLK_SEL_CACHE[key]
    import json
    path = ROOT / "results" / f"clk_lab_sel_probe_X{x}Y{y}.json"
    if not path.exists():
        raise FasmError(
            f"LAB_CLK_SEL X{x}Y{y}: no mined data at {path.name}. "
            f"Run: python3 fuzz/clk_lab_sel_probe.py --lab {x},{y}"
        )
    data = json.loads(path.read_text())
    cells = [tuple(c) for c in data.get("lab_clk_sel", [])]
    _LAB_CLK_SEL_CACHE[key] = cells
    return cells


def _load_lab_clk_sel_le_cells(x, y, n):
    """Return XOR-delta cells for `LAB_CLK_SEL_LE X{x}Y{y}N{n}`.

    Data lives in results/clk_lab_sel_per_le.json under the "X{x}Y{y}"
    entry.  Available N slots depend on which N values the per-LAB probe
    included; the probe now mines N ∈ {0, 2, 4} by default, with older
    probe JSONs still valid at N ∈ {0, 4}.  Additional N slots require
    extending clk_lab_sel_probe.py N_SLOTS and rerunning.
    """
    global _LAB_CLK_SEL_LE_CACHE
    if _LAB_CLK_SEL_LE_CACHE is None:
        import json
        path = ROOT / "results" / "clk_lab_sel_per_le.json"
        if not path.exists():
            raise FasmError(
                "LAB_CLK_SEL_LE directive used but "
                "results/clk_lab_sel_per_le.json missing; run "
                "fuzz/clk_lab_sel_per_le.py"
            )
        _LAB_CLK_SEL_LE_CACHE = json.loads(path.read_text())
    key = f"X{x}Y{y}"
    if key not in _LAB_CLK_SEL_LE_CACHE:
        raise FasmError(
            f"LAB_CLK_SEL_LE X{x}Y{y}N{n}: no mined data for LAB. "
            f"Run: python3 fuzz/clk_lab_sel_probe.py --lab {x},{y}"
            f" then python3 fuzz/clk_lab_sel_per_le.py"
        )
    entry = _LAB_CLK_SEL_LE_CACHE[key]
    bucket = f"n{n}_specific"
    if bucket not in entry:
        raise FasmError(
            f"LAB_CLK_SEL_LE X{x}Y{y}N{n}: N={n} not mined "
            f"(available buckets: {[k for k in entry if k.endswith('_specific')]}). "
            f"Extend clk_lab_sel_probe.py N_SLOTS and rerun for "
            f"LAB X{x}Y{y}."
        )
    return [tuple(c) for c in entry[bucket]]


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


_ARITH_BLOB_CACHE = None


def _load_arith_blob():
    """Load v4 universal arith activation blob.

    v4 data is the result of a 3-LAB triangle test (2026-04-14) at
    (4,18), (10,18), (4,10) which proved the arith activation cells
    are 100% position-independent: the SAME 100 SETs + 4 CLEARs unlock
    arith mode at any LAB on the chip.

    Schema:
      v4["set"]   = [[cram_off, bp], ...]  # 100 cells to OR-in
      v4["clear"] = [[cram_off, bp], ...]  # 4 cells to AND-clear

    Verified: 0 data + 0 CRC diffs at all 3 tested LABs when applied
    to identity baseline.  The blob is per-chip, not per-LAB and not
    per-LE — applied once when ANY arith LE exists in the design.

    Falls back to v3 (per-LAB SETs only, no CLEARs) for old data.
    """
    global _ARITH_BLOB_CACHE
    if _ARITH_BLOB_CACHE is not None:
        return _ARITH_BLOB_CACHE
    import json
    v4_path = ROOT / "results" / "arith_blockband_v4.json"
    if v4_path.exists():
        _ARITH_BLOB_CACHE = json.loads(v4_path.read_text())
        return _ARITH_BLOB_CACHE
    v3_path = ROOT / "results" / "arith_blockband_v3.json"
    if v3_path.exists():
        _ARITH_BLOB_CACHE = json.loads(v3_path.read_text())
        return _ARITH_BLOB_CACHE
    _ARITH_BLOB_CACHE = None
    return None


def _arith_set_clear():
    """Return (set_cells, clear_cells) for universal arith activation.

    set_cells:   list of (offset, bp) to OR-in on the base RBF
    clear_cells: list of (offset, bp) to AND-clear on the base RBF
    """
    blob = _load_arith_blob()
    if blob is None:
        raise FasmError(
            "LUT_ARITH: results/arith_blockband_v4.json missing; "
            "run the triangle-test mining campaign"
        )
    if blob.get("version") == 4:
        set_cells = [(int(o), int(b)) for o, b in blob["set"]]
        clear_cells = [(int(o), int(b)) for o, b in blob["clear"]]
        return set_cells, clear_cells
    # v3 fallback: per-LAB SETs only, use (4,18) as universal proxy
    labs = blob.get("labs", {})
    if "4,18" not in labs:
        raise FasmError("LUT_ARITH: v3 fallback requires (4,18) entry")
    set_cells = [(int(o), int(b)) for o, b in labs["4,18"]["cells"]]
    return set_cells, []


def _dff_le_cells(x, y, n):
    """Return per-LE DFF enable CRAM cells — currently EMPTY.

    Cyclone IV's flip-flop is intrinsic to every LE — always present,
    no per-LE enable CRAM cell exists.  The registered vs combinational
    output is selected by downstream routing (which LE output the next
    stage reads).  For LE-internal feedback (carry counters, Q<=Q),
    zero DFF-specific CRAM cells are needed.

    HW-verified 2026-04-13: identity_led (16 DFFs at LAB(4,18)) vs
    nv_zero shows ZERO diffs in the LAB CRAM column.  15-vs-16 DFF
    controlled test also shows 0 LAB column diffs.  The former
    dff_cells_mined.json contained routing infrastructure noise.
    """
    return []


class FasmError(ValueError):
    pass


def parse_fasm(text):
    """Return (luts, routes) from FASM text.

    luts:   list of (x, y, n, mask_int)
    routes: list of (sx, sy, dx, dy, dn, port)
    """
    luts = []
    lut_arith = []  # list[(x, y, n, mask_int)] — arith-mode LEs
    routes = []
    bits = []
    srcs = []
    dffs = []  # list[(x, y, mode)] mode in {"ARST","ENA"}
    dff_les = []  # list[(x, y, n)] per-LE DFF enable
    m9k_inits = []  # list[(x, y, n, width, depth, target_words)]
    iobs = []  # list[(role, pin)] where role in {'IN','OUT'}
    iob_routes = []  # list[(pin, dx, dy, dn, port)] — nv_zero_global-frame
    iob_baseline_nv = False  # IOB_BASELINE_NV directive seen
    iob_clk_inputs = []  # list[pin] — IOB_CLK_INPUT PIN_X
    # NV_BASELINE_PACK family — each entry is a bucket name consumed by
    # _nv_bucket_cells().  All are XOR-applied with parity, so emitting
    # both the meta NV_BASELINE_PACK and a sub-directive for the same
    # bucket cancels that bucket out (intentional; double-emit is a
    # no-op rather than a silent double-flip).
    nv_buckets = []  # list[str]
    gclk = False
    gclk_pins = []  # list[pin] — per-pin GCLK source activate (XOR)
    lab_clk_sels = []  # list[(x, y)] — per-LAB CLK_SEL (XOR)
    lab_clk_sel_les = []  # list[(x, y, n)] — per-LE CLK_SEL layer (XOR)
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = _LUT_ARITH_RE.match(line)
        if m:
            lut_arith.append(
                (int(m["x"]), int(m["y"]), int(m["n"]), int(m["mask"], 16))
            )
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
        m = _GCLK_PIN_RE.match(line)
        if m:
            gclk_pins.append(m["pin"])
            continue
        m = _LAB_CLK_SEL_LE_RE.match(line)
        if m:
            lab_clk_sel_les.append(
                (int(m["x"]), int(m["y"]), int(m["n"]))
            )
            continue
        m = _LAB_CLK_SEL_RE.match(line)
        if m:
            lab_clk_sels.append((int(m["x"]), int(m["y"])))
            continue
        m = _GCLK_RE.match(line)
        if m:
            gclk = True
            continue
        m = _IOB_BASELINE_NV_RE.match(line)
        if m:
            iob_baseline_nv = True
            continue
        m = _IOB_CLK_INPUT_RE.match(line)
        if m:
            iob_clk_inputs.append(m["pin"])
            continue
        m = _NV_BASELINE_PACK_RE.match(line)
        if m:
            nv_buckets.append("nv_all")
            continue
        m = _IOB_BANK_DEFAULT_PACK_RE.match(line)
        if m:
            nv_buckets.append("iob_bank_default_pack")
            continue
        m = _LOCAL_CLK_E1_BASELINE_RE.match(line)
        if m:
            nv_buckets.append("local_clk_e1_baseline")
            continue
        m = _LOCAL_CLK_PATH_A_RE.match(line)
        if m:
            nv_buckets.append("local_clk_path_a")
            continue
        m = _LAB_LOCAL_CLK_RE.match(line)
        if m:
            nv_buckets.append(f"lab_col_X{int(m['x'])}")
            continue
        m = _NV_BLOCK_COL_INFRA_RE.match(line)
        if m:
            nv_buckets.append("nv_block_col_infra")
            continue
        m = _IOB_ROUTE_RE.match(line)
        if m:
            iob_routes.append(
                (m["pin"], int(m["dx"]), int(m["dy"]),
                 int(m["dn"]), m["port"])
            )
            continue
        m = _IOB_RE.match(line)
        if m:
            iobs.append((m["role"], m["pin"]))
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
    return (luts, lut_arith, routes, bits, srcs, dffs, dff_les, m9k_inits,
            iobs, iob_routes, gclk, gclk_pins, lab_clk_sels, lab_clk_sel_les,
            iob_baseline_nv, iob_clk_inputs, nv_buckets)


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
    (luts, lut_arith, routes, bits, srcs, dffs, dff_les, m9k_inits,
     iobs, iob_routes, gclk, gclk_pins, lab_clk_sels,
     lab_clk_sel_les, iob_baseline_nv,
     iob_clk_inputs, nv_buckets) = parse_fasm(fasm_text)

    codec = RouteCodec()
    work = bytes(base_rbf)

    # NV_BASELINE_PACK family — applied FIRST so downstream directives
    # (IOB_IN / IOB_OUT / IOB_ROUTE / ROUTE etc.) land on top of the
    # synthesised nv_zero_global frame rather than on PURE_ZERO.  XOR-
    # parity composition across buckets: a cell that appears in several
    # named sub-directives is flipped only if the count of emitting
    # directives is odd.  The meta NV_BASELINE_PACK ('nv_all') contains
    # every bucket, so emitting it alongside a sub-directive cancels
    # that sub — that is the intended behaviour (double-emit = no-op).
    if nv_buckets:
        parity = {}
        for bucket in nv_buckets:
            for off, bp in _nv_bucket_cells(bucket):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in parity.items():
            if v:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

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

    # GCLK_PIN + LAB_CLK_SEL: XOR-delta from AUTO-mode baseline.
    # Use XOR so overlapping cells between multiple LAB_CLK_SELs (or
    # between a GCLK_PIN and a LAB_CLK_SEL that shares row-tree cells)
    # cancel properly under pair-wise composition.  Collect into a
    # {cell: parity} map and apply each cell with odd parity once.
    if gclk_pins or lab_clk_sels or lab_clk_sel_les:
        parity = {}
        for pin in gclk_pins:
            for off, bp in _load_gclk_pin_cells(pin):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        for x, y in lab_clk_sels:
            for off, bp in _load_lab_clk_sel_cells(x, y):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        for x, y, n in lab_clk_sel_les:
            for off, bp in _load_lab_clk_sel_le_cells(x, y, n):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in parity.items():
            if v:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

    # DFF directives are parsed but intentionally no-op: Cyclone IV's
    # flip-flop is intrinsic to every LE (no per-LE enable cell in CRAM).
    # Registered vs combinational output is selected by downstream routing.
    # See _dff_le_cells() docstring for HW verification details.

    if bits:
        buf = bytearray(work)
        for off, bp in bits:
            buf[off] ^= (1 << bp)
        work = bytes(buf)

    if iob_baseline_nv:
        # Apply the hdr-band bridge (nv_zero_global ^ iob_in_E15, scoped
        # to off < 5282).  This must run BEFORE IOB_IN / IOB_OUT so their
        # pair-deltas land on top of the E15/G15 baseline they expect.
        buf = bytearray(work)
        for off, bp in _load_iob_baseline_hdr_cells():
            buf[off] ^= (1 << bp)
        work = bytes(buf)

    if iob_clk_inputs:
        # Clock-bank pin activate (hdr band only).  Uses XOR parity so
        # duplicate lines cancel.  Runs alongside IOB_IN / IOB_OUT; both
        # touch the hdr band but scoped to different bytes.
        parity = {}
        for pin in iob_clk_inputs:
            for off, bp in _load_iob_clk_input_cells(pin):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in parity.items():
            if v:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

    if iobs:
        iob_map = _load_iob_map()
        if iob_map is None:
            raise FasmError(
                "IOB directive used but results/iob_cell_map.json missing; "
                "run fuzz/iob_sweep.py + fuzz/iob_analyze.py"
            )
        # Collect all flips into a multiset so a cell flipped by both an
        # IOB_IN and IOB_OUT line cancels (currently the per_pin_input /
        # per_pin_output sets are disjoint, but defensive XOR-counting
        # keeps the directive safe under future overlap).
        flips = {}
        for role, pin in iobs:
            for off, bp in _iob_delta_cells(role, pin, iob_map):
                key = (off, bp)
                flips[key] = flips.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in flips.items():
            if v:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

    if iob_routes:
        # IOB_ROUTE cells are in the nv_zero_global frame.  Apply as XOR;
        # overlap between multiple IOB_ROUTEs (e.g. two pins driving the
        # same target but different ports — which Quartus canonicalizes
        # to the same dataa anyway) will cancel correctly under parity.
        parity = {}
        for pin, dx, dy, dn, port in iob_routes:
            for off, bp in _load_iob_route_cells(pin, dx, dy, dn, port):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in parity.items():
            if v:
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

    # LUT TT phase processes normal and arith LUTs differently.
    #
    # Normal-mode LEs: reset to minterm_0 baseline (undo routing
    # contamination + presence delta), then XOR predict_sram(mask).
    #
    # Arith-mode LEs: skip the minterm_0 reset entirely.  In arith mode
    # the LE has zero normal-mode "presence" cells — the minterm_0 RBF
    # was compiled in normal mode and its 35+ presence cells are wrong
    # for arith configuration.  predict_sram(mask) still works because
    # the TT-cell → mask mapping is the same physical SRAM; only the
    # baseline differs (arith baseline = nv_zero, not minterm_0).
    # Verified: predict_sram output doesn't overlap with minterm_0
    # presence cells, so the XOR produces correct results either way.
    all_luts = list(luts) + list(lut_arith)

    if all_luts:
        db = sqlite3.connect(db_path)
        try:
            buf = bytearray(work)

            _m0_cache = {}
            lut_cache = {}
            arith_keys = {(x, y, n) for x, y, n, _ in lut_arith}
            for x, y, n, mask in all_luts:
                key = (x, y, n)
                if key in lut_cache:
                    continue
                try:
                    lut_cache[key] = LutCodec.from_db(db, x, y, n)
                except ValueError as e:
                    if key in arith_keys:
                        sys.stderr.write(
                            f"warn: LUT_ARITH X{x}Y{y}N{n}: "
                            f"no minterm calibration — skipping TT write "
                            f"(activation cells still applied)\n"
                        )
                        lut_cache[key] = None
                    else:
                        raise

            # Phase 1: reset normal-mode LUT cells to minterm_0 baseline.
            # SKIP for arith-mode LEs — arith has no normal-mode presence.
            for x, y, n, mask in all_luts:
                if (x, y, n) in arith_keys:
                    continue  # arith: no minterm_0 reset
                lut = lut_cache[(x, y, n)]
                if lut is None:
                    continue
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
            # For normal LEs: relative to minterm_0 (Phase 1 aligned).
            # For arith LEs: relative to nv_zero (Phase 1 skipped).
            for x, y, n, mask in all_luts:
                lut = lut_cache[(x, y, n)]
                if lut is None:
                    continue
                for addr, bitpos in lut.predict_sram(mask):
                    buf[addr] ^= (1 << bitpos)
            work = bytes(buf)
        finally:
            db.close()

    if lut_arith:
        # Chip-wide carry-chain activation cells (block band + infra).
        # Applied AFTER the LUT TT phase so that any activation cell
        # which overlaps with a lut.all_cells reset isn't clobbered.
        #
        # The arith blob is POSITION-INDEPENDENT (v4): the same 100 SETs
        # + 4 CLEARs activate arith mode at any LAB.  Triangle-test
        # verified at (4,18), (10,18), (4,10) — 0 data diffs each.
        # Applied once even if multiple LABs have arith LEs.
        set_cells, clear_cells = _arith_set_clear()
        buf = bytearray(work)
        for off, bp in set_cells:
            buf[off] |= (1 << bp)            # OR-in activation bits
        for off, bp in clear_cells:
            buf[off] &= ~(1 << bp) & 0xFF    # AND-clear deactivation bits
        work = bytes(buf)

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
