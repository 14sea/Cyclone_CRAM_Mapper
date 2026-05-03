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

    # Multi-LAB carry chain activation (widths 17..32).  Consumes
    # results/arith_blockband_by_width.json's multi_lab["16+N"] entries
    # (N = 1..16, total width = 16 + N).  XOR-parity semantics: double-
    # emit of the same width cancels.  Emit alongside the per-LE
    # LUT_ARITH lines that carry the truth-table masks for each LE in
    # the chain.
    LUT_ARITH_MULTI_LAB WIDTH=17

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
# Multi-LAB arith carry chain activation (widths 17..32).  The single-
# LAB LUT_ARITH blob (100 SETs + 4 CLEARs) only activates chains up to
# 16 LEs (one LAB).  Wider chains need a width-specific blob that also
# activates the N=30→N=0 inter-LAB link in the LAB below.  Data lives
# in results/arith_blockband_by_width.json under multi_lab["16+N"] for
# N = 1..16 (total width = 16 + N).  XOR-parity semantics: double-emit
# of the same width cancels.
_LUT_ARITH_MULTI_LAB_RE = re.compile(
    r"^LUT_ARITH_MULTI_LAB\s+WIDTH\s*=\s*(?P<width>\d+)$"
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
# M9K mode/enable cells: X{x}Y{y}N{n}.M9K_MODE_{width}x{depth}[_{template}]
# XOR-applies the per-(site, width, depth, template) block-band cells from
# results/m9k_mode_bits.json — these are the "site is configured as a
# {width}x{depth} M9K" bits.  Without them an INIT-only build carries
# valid data but the silicon block is not enabled, so HW would not
# read back the user pattern.
#
# `template` (optional, defaults to "altsyncram") selects which Quartus
# code path the mining specimen used.  Stage C.1 probe (2026-04-16,
# fuzz/m9k_mode_template_probe.py) found that the 29-cell residual
# between altsyncram-direct mining and Quartus inferred-RAM smoke gold
# does NOT close by switching the mining template — even verbatim
# smoke-gold Verilog under the specimen factory diverges from the gold
# by 77 cells (worse than altsyncram's 29).  The sub-flag is therefore
# scaffolded as the per-template bucket carrier rather than the
# closure mechanism: `M9K_MODE_{w}x{d}_altsyncram` reads
# `cells_by_template["altsyncram"]`, `_inferred` reads
# `cells_by_template["inferred"]`, and the bare `M9K_MODE_{w}x{d}`
# (legacy form) reads the top-level `cells` field — which equals
# `cells_by_template["altsyncram"]` for newly mined entries and
# legacy-mined contaminated cells for older entries.
#
# np2fasm emission stays gated until either bucket lands within ≤5
# cells of a real Quartus build.  See memory
# m9k_mode_template_residual.md for the full diagnosis.
_M9K_MODE_RE = re.compile(
    r"^X(?P<x>\d+)Y(?P<y>\d+)N(?P<n>\d+)\.M9K_MODE_"
    r"(?P<width>\d+)x(?P<depth>\d+)"
    r"(?:_(?P<template>quartus_gold_sdp|quartus_gold_tdp|quartus_gold"
    r"|inferred_goldintersect|m9k_blink_diff_nv|altsyncram|inferred))?$"
)
_M9K_MODE_CACHE = None
# Default template when the bare `M9K_MODE_{w}x{d}` form is emitted.
# Backward-compatible: legacy callers and existing test fixtures get
# the altsyncram bucket (the closer match to gold per probe data).
_M9K_MODE_DEFAULT_TEMPLATE = "altsyncram"
# `quartus_gold` is the 2026-04-24 re-mined bucket: per-(w,d) variant
# intersection of real Quartus data-path builds at X15_Y10_N0, diffed
# against a pinout-matched no-M9K baseline.  Sizes: (4,2048)=19,
# (9,512)=52, (18,512)=59, (9,1024)=43, (36,256)=68.  See
# scripts/m9k_mode_quartus_gold_mine.py + memory
# m9k_mode_quartus_gold_mining_landed.md.  This bucket is
# CONTENT-CORRECT (cells appear in the real Quartus diff, unlike the
# `inferred_goldintersect` bucket which the 2026-04-24 data-path probe
# proved to be fabric-safe noise).  End-to-end functional HW
# validation is per-width: a width only migrates into
# `np2fasm._M9K_MODE_FUNCTIONAL_VALIDATED` after its data-path
# reconstruction blinks on AX301 as expected.
_M9K_MODE_VALID_TEMPLATES = (
    "altsyncram", "inferred", "inferred_goldintersect", "quartus_gold",
    # Per-operation-mode buckets (mined 2026-04-25 by
    # scripts/m9k_mode_quartus_gold_mine.py --mode {sdp,tdp}).
    # `quartus_gold` above stays the SP (SINGLE_PORT) bucket; the two
    # below are the DUAL_PORT (SDP) and BIDIR_DUAL_PORT (TDP) equivalents.
    # Emission dispatch happens in np2fasm._emit_m9k_mode based on the
    # techmapped EP4CE6_M9K cell's MODE parameter.
    "quartus_gold_sdp", "quartus_gold_tdp",
    # 2026-04-30 v5-derived bucket: per-site Quartus m9k_blink_full RBF
    # XOR'd directly against nv_zero_global, restricted to block-band
    # frames 1692-1738 (byte<208).  Mined by
    # scripts/m9k_blink_diff_nv_mine.py.  Unlike the inferred /
    # inferred_goldintersect / quartus_gold buckets — which all proved
    # silicon-mode-incorrect under --base nv (memos
    # m9k_mode_codec_silicon_broken_2026_04_25 +
    # m9k_mode_v5_finding_gi_codec_unnecessary_2026_04_30) — this bucket
    # captures the cells the M9K hardware actually reads as its mode
    # encoding at each site.  Cell counts are tight (~12 per site,
    # slot=1 sites such as X15_Y6 may produce ~6) because we diff the
    # complete Quartus design against nv_zero_global directly.
    "m9k_blink_diff_nv",
)
# Per-(width, depth) silicon-falsified masks. Applied at load time — cells
# here are stripped from whichever template bucket the caller asked for.
#
# These masks are FABRIC-SAFETY-only: they clear cells whose XOR overlay on
# the simple_led baseline leaves LED0 stuck / KEY2 inert.  They DO NOT
# affirm that the remaining cells encode the real M9K (w, d) mode; a
# 2026-04-24 data-path probe at X15_Y10_N0 showed real Quartus (4,2048)
# and (9,512) builds have 0% overlap with their gi buckets, i.e. the gi
# buckets are a site-invariant block-band pattern that is fabric-safe
# but NOT what Quartus emits to configure a given M9K mode.  See memory
# m9k_mode_gi_bucket_not_quartus_encoding.md.
#
# (4, 2048): bisection on AX301 2026-04-24 (scripts/stage0_flash_bundle/
# build_m9k_mode_w4x2048_bisect.py) isolated an adjacent-byte pair
# interaction at frame 1733 — (364092,2) and (364093,2) flipped together
# break the fabric; either singleton is safe.  Dropping (364093,2) breaks
# the pair and CLEAN23 PASSed silicon.  np2fasm's `_M9K_MODE_HW_VALIDATED`
# set does NOT include (4,2048) after the data-path probe invalidated the
# gi bucket as mode cells, but the mask is retained so any manual caller
# asking for the (4,2048) bucket still gets the fabric-safe 23-cell form.
_M9K_MODE_SILICON_FALSIFIED = {
    (4, 2048): {(364093, 2)},
}
# DSPMULT global-enable: a single boolean directive that XOR-applies the
# 23-cell intersection across all 42 X=20 mult sites (re-mined 2026-04-16
# under specimen factory; fuzz/dspmult_persite_remine.py + analyzer).
# Per-Y MODE bits are also clean (~9 cells/Y, perfect N-invariance) but
# not yet exposed as a directive — there is no Yosys $mul → DSPMULT
# techmap consumer yet, so per-Y emission is deferred. The 23-cell
# global-on cells live in results/dspmult_persite_analyze.json under
# `universal_cells`. See dspmult_global_on_clean_remine.md memory.
_DSPMULT_GLOBAL_ON_RE = re.compile(r"^DSPMULT_GLOBAL_ON$")
_DSPMULT_GLOBAL_ON_CACHE = None
# Design-specific block-band pack: DESIGN_BLOCK_BAND_PACK <tag>
# XOR-applies the full block-band cell set (frames 1692-1738 data bytes)
# mined from a per-design Quartus reference RBF via
# scripts/mine_design_block_band.py.  Each design tag is a one-time
# Quartus codec build; runtime emission is fully Quartus-free.  See
# memory m9k_multi_infra_step_b_c_findings_2026_05_01.md for why this
# directive replaces the silicon-broken `quartus_gold + --base nv` path
# and the structurally-insufficient per-site `m9k_blink_diff_nv` path
# for multi-M9K NEORV32-class designs.
#
# Storage: results/design_block_band.json (tag → cells list + metadata).
# Emission semantic: XOR-parity composition with other directives, so
# emitting twice cancels.  Applied AFTER per-site M9K_MODE so design-
# specific cells override per-site emissions where they conflict.
_DESIGN_BLOCK_BAND_PACK_RE = re.compile(
    r"^DESIGN_BLOCK_BAND_PACK\s+(?P<tag>[a-zA-Z0-9_-]+)$"
)
_DESIGN_BLOCK_BAND_PACK_CACHE = None
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
_IOB_RE = re.compile(
    r"^IOB_(?P<role>IN|OUT)(?P<bidir>_BIDIR)?\s+PIN_(?P<pin>[A-Z]\d+)$"
)
# Bidir-safe cells known to leak when composed atop a design that already
# has another IOB active (falsified by the bidir probe 2026-04-17).  The
# per_pin_input/output tables in iob_cell_map.json are cells unique to
# each pin across the whole IOB sweep — most pins compose cleanly, but a
# few cells in per_pin_output happen to overlap a user design's fabric.
# Entries here are removed from the bidir-emit set for that pin.
# Format: (role, pin) -> frozenset((off, bp), ...) to exclude.
_IOB_BIDIR_FALSIFIED: dict[tuple[str, str], frozenset[tuple[int, int]]] = {
    # R5 per_pin_output: 2 fabric-band cells (frames 401/403) that coincide
    # with simple_led_pure's active cells when used on top of the
    # simple_led_pure prefix.  Safety-gated out by build_simple_led_iob_
    # bidir_r5_probe.py.  If your design's fabric differs, these exclusions
    # may be unnecessary — but keeping them is conservative (they're
    # mining-template LED-route artifacts, not IOB pad-config cells).
    ("OUT", "R5"): frozenset({(84275, 3), (84868, 4)}),
}


# IOB_IN/OUT cross-column noise filter — cells in input_delta / output_delta
# that fall on column ranges physically distant from the pin's natural CRAM
# region.  These are mining-template artifacts (cells captured during the
# pair-diff sweep that came from neighboring fabric, not the pin's own pad
# config).  Audited 2026-05-03 against cl_and gold (which uses E16+M16+G15
# at X=33Y4 LAB): 0/27 X=33-region cells across E16+M16 input_delta
# matched gold — pure noise.
#
# Format: (role, pin) -> frozenset of column indices to STRIP from the
# pin's delta cell set (cells whose offset falls within COLUMN_BASE[x] ..
# COLUMN_BASE[x] + 7350 are dropped).
_IOB_DELTA_COLUMN_STRIP: dict[tuple[str, str], frozenset[int]] = {
    # Right-edge input pins: X=33 cells in input_delta are noise.
    # Confirmed against cl_and gold which uses these pins at X=33Y4 LAB
    # — none of the X=33 cells appeared in gold.
    #
    # AUDIT SCOPE (2026-05-03): single design — cl_and (cross_lab.v at
    # SLICE_X33_Y4_N4 + N=6).  If a future X=33Y? design at a different
    # (Y, N) needs E16/M16 pad cells in the X=33 column, this filter
    # would over-strip.  Re-audit before adding new X=33 design classes.
    ("IN", "E16"): frozenset({33}),
    ("IN", "M16"): frozenset({33}),
}
# IOB→SLICE route directive (XOR-delta, nv_zero_global frame).  Applies
# absolute cells from results/iob_to_slice_sigcache.json — the
# bridge-translated R(IOB→target LE) footprint for pins mined under
# scripts/iob_slice_mining/.  See memory iob_slice_bridge_delta_unblocks_
# injection.md for the algebra (abs = delta ^ bridge(pin)).
_IOB_ROUTE_RE = re.compile(
    r"^IOB_ROUTE\s+PIN_(?P<pin>[A-Z]\d+)\s*->\s*"
    r"X(?P<dx>\d+)Y(?P<dy>\d+)N(?P<dn>\d+)\.(?P<port>\w+)$"
)
# IOB output-enable (tristate) directive — Stage B-narrow scope.
# Activates the OE/tristate driver bits for one of the 16 sdram_dq pins
# NEORV32 uses on AX301 (S_DB[0]..S_DB[15]).  Cells from
# results/iob_oe_cell_map.json (per-pin diff between an OE-on tristate
# specimen and an OE-off passthrough specimen, harness frozen — see
# fuzz/iob_oe_specimen.py).  XOR-delta semantics: emitting twice cancels
# (boolean per-pin, parity-applied).  Only the 16 mined pins are valid
# arguments — the loader raises FasmError on any other pin.  Composes
# additively with IOB_IN/IOB_OUT for the same pin (DQ is bidir, so both
# IOB_OUT (drive path) and IOB_OE (tristate enable) need to land).
_IOB_OE_RE = re.compile(r"^IOB_OE\s+PIN_(?P<pin>[A-Z]\d+)$")
_IOB_OE_CACHE = None
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

# IOB_PAD_NV — 方案B IOB pad infrastructure (241 cells).  Direct delta
# from nv_zero_global for E16+M16 input + G15 output pin configuration.
# Replaces IOB_BASELINE_NV + IOB_IN + IOB_OUT for designs using the
# standard AX301 pin set.  XOR-idempotent (double-emit cancels).
# Data: results/output_route_nv_mining.json → iob_pad_cells.
_IOB_PAD_NV_RE = re.compile(r"^IOB_PAD_NV$")
_IOB_PAD_NV_CACHE = None

# X=33 jailbreak column LUT TT codec — per-nibble (b%4) cell sets.  Mined
# 2026-05-04 from 6-variant cross_lab Quartus builds at the natural X=33
# placement.  Pair stride at X=33 is 420 bytes (2 frames), 4 nibble classes
# encode all 16 TT bits collectively, NOT 1:1 per-bit like CE6 columns.
# Data: results/x33_lut_codec.json.
_X33_NIB_CACHE = None

# X=33Y4 LE infra override cells — calibrated 2026-05-03 from cl_and gold
# (cross_lab.v 2-LE at SLICE_X33_Y4_N4 + N=6).  Acts as a shim while proper
# per-directive mining (LAB_CLK_SEL_LE, same-LAB ROUTE) is pending.
# Data: results/x33y4_infra_override.json.
_X33Y4_INFRA_CACHE = None

# OUTROUTE_G15 — position-specific output routing from SLICE to PIN_G15.
# Looks up results/output_route_sigcache.json by source SLICE position.
_OUTROUTE_G15_RE = re.compile(
    r"^OUTROUTE_G15\s+X(?P<sx>\d+)Y(?P<sy>\d+)N(?P<sn>\d+)$")
_OUTROUTE_SIGCACHE = None

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
#                              residue (~1 104 cells after Phase B split)
#                              — non-LAB-column chip-global infra.
#   M9K_BLOCK_DEFAULT_PACK     X=15 ∪ X=27 M9K block columns
#                              (~848 cells).  Idle-M9K default footprint
#                              in the NV baseline.
#   MULT_BLOCK_DEFAULT_PACK    X=20 DSPMULT block column (~17 cells).
_NV_BASELINE_PACK_RE = re.compile(r"^NV_BASELINE_PACK$")
_IOB_BANK_DEFAULT_PACK_RE = re.compile(r"^IOB_BANK_DEFAULT_PACK$")
_LOCAL_CLK_E1_BASELINE_RE = re.compile(r"^LOCAL_CLK_E1_BASELINE$")
_LOCAL_CLK_PATH_A_RE = re.compile(r"^LOCAL_CLK_PATH_A$")
_LAB_LOCAL_CLK_RE = re.compile(r"^LAB_LOCAL_CLK\s+X(?P<x>\d+)$")
_NV_BLOCK_COL_INFRA_RE = re.compile(r"^NV_BLOCK_COL_INFRA$")
_M9K_BLOCK_DEFAULT_PACK_RE = re.compile(r"^M9K_BLOCK_DEFAULT_PACK$")
_MULT_BLOCK_DEFAULT_PACK_RE = re.compile(r"^MULT_BLOCK_DEFAULT_PACK$")
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


def _load_m9k_mode_cells(site, width, depth, template=None):
    """Return the per-(site, width, depth, template) M9K mode/enable cells.

    Reads results/m9k_mode_bits.json.  Each entry is the diff vs
    m9k_baseline_empty.rbf restricted to the block band (frames
    1692-1738).  XOR-applying these cells to a baseline that has the
    M9K idle marks the site as configured for {width}x{depth}.

    Template buckets (Stage C.1 sub-flag scaffolding, 2026-04-16):

      template == "altsyncram" or None:
        Returns `cells_by_template["altsyncram"]` if present, else falls
        back to the legacy top-level `cells` field.  This is the
        backward-compatible default — legacy callers and existing tests
        get the altsyncram bucket without modification.

      template == "inferred":
        Returns `cells_by_template["inferred"]`.  Raises FasmError if
        the entry doesn't carry an inferred bucket (i.e. it was mined
        before the sub-flag landed and only has the altsyncram cells).

    Schema reference (`results/m9k_mode_bits.json` per entry):
      {
        "site": "X15_Y10_N0",
        "width": 9, "depth": 512,
        "cells": [...],                       # legacy = altsyncram bucket
        "cells_by_template": {                # NEW (Stage C.1)
          "altsyncram": [...],
          "inferred":   [...],
        },
        "source": "..."
      }
    """
    global _M9K_MODE_CACHE
    if _M9K_MODE_CACHE is None:
        import json
        path = ROOT / "results" / "m9k_mode_bits.json"
        if not path.exists():
            raise FasmError(
                "M9K_MODE used but results/m9k_mode_bits.json missing; "
                "run fuzz/m9k_mode_mine.py"
            )
        _M9K_MODE_CACHE = json.loads(path.read_text())
    key = f"{site}_{width}x{depth}"
    if key not in _M9K_MODE_CACHE:
        # Site-invariant fallback: M9K_MODE cells are identical across all
        # calibrated sites for a given (width, depth, template). Use any
        # mined entry with matching geometry.
        suffix = f"_{width}x{depth}"
        fallback = next(
            (k for k in _M9K_MODE_CACHE if k.endswith(suffix)), None
        )
        if fallback is None:
            raise FasmError(
                f"M9K_MODE {site} {width}x{depth}: no mined entry in "
                f"m9k_mode_bits.json; mine the baseline RBF and re-run "
                f"fuzz/m9k_mode_mine.py"
            )
        key = fallback
    entry = _M9K_MODE_CACHE[key]
    chosen = template if template is not None else _M9K_MODE_DEFAULT_TEMPLATE
    if chosen not in _M9K_MODE_VALID_TEMPLATES:
        raise FasmError(
            f"M9K_MODE template {chosen!r} not in {_M9K_MODE_VALID_TEMPLATES}"
        )
    by_template = entry.get("cells_by_template")
    if by_template is None:
        # Pre-sub-flag entry — only the legacy `cells` field exists.
        # Legacy schema is treated as the altsyncram bucket (the closer
        # match to gold).  Asking for `inferred` against a legacy entry
        # is a hard error: there's no data.
        if chosen == "inferred":
            raise FasmError(
                f"M9K_MODE {site} {width}x{depth}: requested template "
                f"'inferred' but entry only carries the legacy "
                f"`cells` field (= altsyncram).  Re-mine the site via "
                f"fuzz/m9k_mode_template_probe.py to populate "
                f"cells_by_template['inferred']."
            )
        raw = [tuple(c) for c in entry["cells"]]
    elif chosen not in by_template:
        raise FasmError(
            f"M9K_MODE {site} {width}x{depth}: template {chosen!r} not "
            f"in cells_by_template (have: {sorted(by_template)})"
        )
    else:
        raw = [tuple(c) for c in by_template[chosen]]
    mask = _M9K_MODE_SILICON_FALSIFIED.get((width, depth))
    if mask:
        raw = [c for c in raw if c not in mask]
    return raw


def _load_design_block_band_pack(tag):
    """Return the (off, bp) cells for a design block-band pack.

    Reads results/design_block_band.json; raises FasmError if the file
    or the tag is missing.  Mining: scripts/mine_design_block_band.py.
    """
    global _DESIGN_BLOCK_BAND_PACK_CACHE
    if _DESIGN_BLOCK_BAND_PACK_CACHE is None:
        import json
        path = ROOT / "results" / "design_block_band.json"
        if not path.exists():
            raise FasmError(
                "DESIGN_BLOCK_BAND_PACK used but "
                "results/design_block_band.json missing; mine via "
                "scripts/mine_design_block_band.py --tag <tag> --rbf <path>"
            )
        _DESIGN_BLOCK_BAND_PACK_CACHE = json.loads(path.read_text())
    if tag not in _DESIGN_BLOCK_BAND_PACK_CACHE:
        raise FasmError(
            f"DESIGN_BLOCK_BAND_PACK tag {tag!r} not in "
            f"design_block_band.json; have: "
            f"{sorted(_DESIGN_BLOCK_BAND_PACK_CACHE)}"
        )
    return [tuple(c) for c in _DESIGN_BLOCK_BAND_PACK_CACHE[tag]["cells"]]


def _load_dspmult_global_on_cells():
    """Return the 22-cell silicon-clean DSPMULT enable set.

    Reads results/dspmult_persite_analyze.json and returns the
    `universal_cells` list — the intersection of block-band diffs across
    all 42 X=20 mult sites — with the silicon-falsified cell excluded.

    2026-04-17 bisection on AX301 (scripts/stage0_flash_bundle/
    build_dspmult_bisect.py) localized a single leaky cell in the
    mined 23-cell set: off=363236 bp=2 frame=1729. Flipping this
    cell on simple_led stuck LED0 constant-on; the other 22 cells
    applied together are silicon-safe (LED follows KEY2 as baseline).

    The leaky cell stays in the JSON (it's the empirical mining
    intersection), but this loader masks it out so np2fasm and any
    consumer emits only the silicon-verified subset.
    """
    global _DSPMULT_GLOBAL_ON_CACHE
    if _DSPMULT_GLOBAL_ON_CACHE is None:
        import json
        path = ROOT / "results" / "dspmult_persite_analyze.json"
        if not path.exists():
            raise FasmError(
                "DSPMULT_GLOBAL_ON used but "
                "results/dspmult_persite_analyze.json missing; run "
                "fuzz/dspmult_persite_remine.py --full + "
                "fuzz/dspmult_persite_analyze.py"
            )
        data = json.loads(path.read_text())
        SILICON_FALSIFIED = {(363236, 2)}  # HW 2026-04-17
        _DSPMULT_GLOBAL_ON_CACHE = [
            tuple(c) for c in data["universal_cells"]
            if tuple(c) not in SILICON_FALSIFIED
        ]
    return _DSPMULT_GLOBAL_ON_CACHE


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
      'lab_col_X<n>'             (<n> = integer column index)
      'm9k_block_default_pack'   (X=15 ∪ X=27)
      'mult_block_default_pack'  (X=20)
      'nv_block_col_infra'       (low + high + residue — chip-global only)
      'nv_all'                   (every bucket above ∪ all lab_columns)
    """
    data = _load_nv_baseline_pack()
    if bucket == "nv_all":
        out = []
        for k in ("iob_bank_default_pack", "local_clk_e1_baseline",
                  "local_clk_path_a", "low_frame_infra",
                  "high_frame_infra", "residue",
                  "m9k_block_default_pack", "mult_block_default_pack"):
            # Older JSONs without the Phase B block buckets still load —
            # the reconstruction gate in that case reports a diff and
            # asks the user to rerun the miner.
            out.extend(data.get(k, []))
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


def _x33_nibble_cells():
    """Return {(y, n): {nibble_class (0..3): set of (off, bp)}} for X=33 LUT TT.

    Per-position per-nibble cell tables mined from cross_lab.v variants:
    - (4, 4) → Stage A position, from cl_*.v (Stage A varies, Stage B buf)
    - (4, 6) → Stage B position, from rcl_*.v (Stage A buf, Stage B varies)

    Each nibble class `k` covers TT bits {k, k+4, k+8, k+12} and emits
    12-16 cells across a pair of consecutive CRAM frames.  Activation
    semantics are nibble-OR (NOT per-bit XOR): the cell set fires when
    ANY bit in the nibble is set in the LUT mask.
    """
    global _X33_NIB_CACHE
    if _X33_NIB_CACHE is not None:
        return _X33_NIB_CACHE
    import json
    path = ROOT / "results" / "x33_lut_codec.json"
    if not path.exists():
        raise FasmError(
            "X=33 LUT used but results/x33_lut_codec.json missing — "
            "regenerate from scripts/cross_lab/x33_lut_mining mining diffs"
        )
    data = json.loads(path.read_text())
    out = {}
    if "positions" in data:
        for pos_str, pos_data in data["positions"].items():
            # pos_str like "(4, 4)" → (y, n)
            yn = tuple(int(x.strip()) for x in pos_str.strip("()").split(","))
            out[yn] = {
                int(k): set((int(off), int(bp)) for off, bp in cells)
                for k, cells in pos_data["nibble_classes"].items()
            }
    else:
        # Legacy single-position format (Stage A only, deprecated)
        out[(4, 4)] = {
            int(k): set((int(off), int(bp)) for off, bp in cells)
            for k, cells in data["nibble_classes"].items()
        }
    _X33_NIB_CACHE = out
    return out


_X33Y4_SHIM_VICTIM_COLS = frozenset({5, 9, 10, 17, 22, 24, 32})


def _x33y4_cross_lab_shim_should_apply(x33_luts, all_luts, routes, iobs,
                                        lab_clk_sels, iob_pad_nv=False):
    """Return True only when FASM matches the exact cross_lab.v topology
    that the X33Y4 shim was calibrated for.  Refuses otherwise so the
    override doesn't clobber legitimate state in unrelated designs that
    happen to also place an X=33Y4 LE.

    Calibration topology (cl_and / cross_lab.v):
      * BOTH SLICE_X33_Y4_N4 and SLICE_X33_Y4_N6 occupied by an LE
      * Design uses E16+M16 input + G15 output (either via the legacy
        IOB_IN/IOB_OUT triplet OR the unified IOB_PAD_NV directive)
      * LAB_CLK_SEL X33Y4 present
      * Design uses NO LE in any X ∈ {5,9,10,17,22,24,32} (the shim
        XOR-flips cells in those columns; flipping legitimate cells
        of another design at those columns silently corrupts it)
    """
    yn_set = {(y, n) for x_, y, n, _ in x33_luts}
    if (4, 4) not in yn_set or (4, 6) not in yn_set:
        return False
    # IOB pin set: accept legacy (IOB_IN/OUT triplet) OR new (IOB_PAD_NV
    # which folds in E16/M16/G15 atomically).  np2fasm switches to the
    # IOB_PAD_NV path when OUTROUTE_G15 X33Y4N6 is in the sigcache.
    pin_set = {(role, pin) for role, pin in iobs}
    legacy_pins = {('IN', 'E16'), ('IN', 'M16'), ('OUT', 'G15')}
    if not (legacy_pins.issubset(pin_set) or iob_pad_nv):
        return False
    if (33, 4) not in {(x, y) for x, y in lab_clk_sels}:
        return False
    used_cols = {x for x, y, n, _ in all_luts}
    for r in routes:
        if len(r) == 7:
            sx, sy, sn, dx, dy, dn, port = r
        else:
            sx, sy, dx, dy, dn, port = r
        used_cols.add(sx); used_cols.add(dx)
    if used_cols & _X33Y4_SHIM_VICTIM_COLS:
        return False
    return True


def _x33y4_infra_cells():
    """Return X=33Y4 LE infrastructure cells (LAB_CLK_SEL_LE + same-LAB
    ROUTE + SRC overhead) as a single override set.

    Calibrated from cl_and gold residual analysis 2026-05-03.  Auto-applied
    by fasm2rbf whenever the cross_lab.v topology preconditions are met
    (see `_x33y4_cross_lab_shim_should_apply`).  Design-specific shim
    until proper per-directive mining is done.
    """
    global _X33Y4_INFRA_CACHE
    if _X33Y4_INFRA_CACHE is not None:
        return _X33Y4_INFRA_CACHE
    import json
    path = ROOT / "results" / "x33y4_infra_override.json"
    if not path.exists():
        # Not an error if missing — just no shim, gap stays open
        _X33Y4_INFRA_CACHE = []
        return _X33Y4_INFRA_CACHE
    data = json.loads(path.read_text())
    _X33Y4_INFRA_CACHE = [tuple(c) for c in data["cells"]]
    return _X33Y4_INFRA_CACHE


def _load_iob_pad_nv_cells():
    """Load IOB pad cells (nop_vs_nv delta) from
    results/output_route_nv_mining.json.  Currently 139 cells after
    the 2026-05-04 cleanup (commit a5e4a0e) that removed 102 over-emit
    cells from the original 241-cell mining baseline."""
    global _IOB_PAD_NV_CACHE
    if _IOB_PAD_NV_CACHE is not None:
        return _IOB_PAD_NV_CACHE
    import json
    path = ROOT / "results" / "output_route_nv_mining.json"
    if not path.exists():
        raise FasmError(
            "IOB_PAD_NV used but results/output_route_nv_mining.json "
            "missing; run scripts/minimal_1lut/mine_outroute_nv.py"
        )
    data = json.loads(path.read_text())
    _IOB_PAD_NV_CACHE = [tuple(c) for c in data["iob_pad_cells"]]
    return _IOB_PAD_NV_CACHE


_IOB_PAD_ARITH_EXT_CACHE = None


def _load_iob_pad_arith_ext_cells():
    """Carry-chain IOB pad extension cells.  Of the 102 cells removed by
    commit a5e4a0e (IOB_PAD_NV cleanup), 74 are present in silicon-
    validated W=23 RBF (md5 905dfc85ad37c44da9966dfbd9cf3a16) but
    absent from all 20 simple-G15 mined designs (and2/or2/cl_*/rcl_*/
    1le_g15/probe2/baseline).  These are specific to designs with
    multi-LE carry chains driving G15.  Emitted only when both
    IOB_PAD_NV and any LUT_ARITH (or LUT_ARITH_MULTI_LAB) directive
    are present in the FASM."""
    global _IOB_PAD_ARITH_EXT_CACHE
    if _IOB_PAD_ARITH_EXT_CACHE is not None:
        return _IOB_PAD_ARITH_EXT_CACHE
    import json
    path = ROOT / "results" / "output_route_nv_mining.json"
    data = json.loads(path.read_text())
    _IOB_PAD_ARITH_EXT_CACHE = [tuple(c)
                                 for c in data.get("iob_pad_arith_ext_cells", [])]
    return _IOB_PAD_ARITH_EXT_CACHE


def _load_outroute_g15_cells(sx, sy, sn):
    """Load position-specific output route cells from
    results/output_route_sigcache.json for SLICE(sx,sy,sn) → G15."""
    global _OUTROUTE_SIGCACHE
    if _OUTROUTE_SIGCACHE is None:
        import json
        path = ROOT / "results" / "output_route_sigcache.json"
        if not path.exists():
            raise FasmError(
                "OUTROUTE_G15 used but results/output_route_sigcache.json "
                "missing; run scripts/minimal_1lut/sweep_outroute_nv.py"
            )
        _OUTROUTE_SIGCACHE = json.loads(path.read_text())
    key = f"X{sx}Y{sy}N{sn}"
    routes = _OUTROUTE_SIGCACHE.get("routes", {})
    if key not in routes:
        raise FasmError(
            f"OUTROUTE_G15 X{sx}Y{sy}N{sn}: position not in "
            f"output_route_sigcache.json ({len(routes)} positions mined)"
        )
    cells = [tuple(c) for c in routes[key]["position_specific"]]
    for c in _OUTROUTE_SIGCACHE.get("g15_invariant_cells", []):
        cells.append(tuple(c))
    return cells


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


def _iob_delta_cells(role, pin, iob_map, *, lenient=False):
    """Return XOR-delta cells (off, bp) from baseline to pin for one role.

    role in {'IN','OUT','IN_BIDIR','OUT_BIDIR'}.

    Non-BIDIR roles read pair-delta sets (input_delta/output_delta) vs
    the iob_in_E15 / iob_out_G15 anchors — correct for SINGLE-axis IOB
    designs (one IOB_IN + one IOB_OUT).  Multi-IOB_IN composition on
    those deltas double-flips the E15 anchor cells → false activation
    of E15-specific pad cells that overlap simple_led_pure's E16 bridge.

    BIDIR roles read per_pin_input / per_pin_output — cells active in
    EXACTLY this pin's RBF across the sweep.  These are safe to XOR-
    compose atop a design that already has unrelated IOBs active (the
    sdram_dq $tribuf use case), at the cost of possibly omitting
    semi-shared cells Quartus may need for functional activation.
    A short known-leak exclusion table (_IOB_BIDIR_FALSIFIED) removes
    per-pin cells that empirically collide with user-design fabric.
    """
    bidir = role.endswith("_BIDIR")
    base_role = role.removesuffix("_BIDIR")
    if bidir:
        table_key = "per_pin_input" if base_role == "IN" else "per_pin_output"
    else:
        table_key = "input_delta" if base_role == "IN" else "output_delta"
    if table_key not in iob_map:
        raise FasmError(
            f"IOB directive needs iob_map['{table_key}']; re-run "
            f"fuzz/iob_analyze.py to regenerate iob_cell_map.json"
        )
    table = iob_map[table_key]
    if pin not in table:
        if not lenient:
            raise FasmError(
                f"IOB_{role} PIN_{pin}: no entry in iob_cell_map.json "
                f"(known: {sorted(table)})"
            )
        return []
    cells = [tuple(c) for c in table[pin]]
    if bidir:
        mask = _IOB_BIDIR_FALSIFIED.get((base_role, pin))
        if mask:
            cells = [c for c in cells if c not in mask]
    # Cross-column noise strip: drop cells from columns physically distant
    # from this pin's pad region (mining template artifacts).
    strip_cols = _IOB_DELTA_COLUMN_STRIP.get((base_role, pin))
    if strip_cols:
        from config import COLUMN_BASE as _CB
        ranges = [(_CB[x], _CB[x] + 7350) for x in strip_cols if x in _CB]
        cells = [c for c in cells
                 if not any(lo <= c[0] < hi for lo, hi in ranges)]
    return cells

_IOB_ROUTE_CACHE = None


_IOB_ROUTE_NODEDUP_KEYS: set | None = None


_IOB_ROUTE_LEGACY_CACHE: dict | None = None


def _load_iob_route_cells(pin, dx, dy, dn, port):
    """Return XOR-delta cells (off, bp) for IOB_ROUTE PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}.

    Cells come from results/iob_to_slice_sigcache.json.  Two live buckets
    are consulted in priority order:

      1. ``padnv_cells`` — derived for the IOB_PAD_NV directive path as
         ``(gold_fab ⊕ base_fab) - LUT_cells`` where *base* includes
         IOB_PAD_NV, OUTROUTE, CLK, and IOB_CLK_INPUT but NOT IOB_ROUTE.
         These entries compose correctly via XOR parity **without** dedup
         stripping.

      2. ``absolute_cells`` — pair-template fallback (15 HW-verified
         entries at X∈{10,16}, Y∈{4,10}). Requires dedup.

    ``single_le_cells_stale`` in the JSON is quarantined as of 2026-04-24
    and is NOT consulted — directive-stack drift since 2026-04-15 derives
    caused full-RBF reconstructions to miss (120 byte diffs vs
    simple_led gold for E16->10,4,0,dataa). 94 pin/target combos that
    exist ONLY in that bucket are intentionally unroutable until a
    re-sweep lands.
    """
    global _IOB_ROUTE_CACHE, _IOB_ROUTE_NODEDUP_KEYS
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
        padnv = data.get("padnv_cells", {})
        absolute = data.get("absolute_cells", {})
        merged = dict(absolute)
        merged.update(padnv)
        _IOB_ROUTE_CACHE = merged
        _IOB_ROUTE_NODEDUP_KEYS = set(padnv.keys())
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


def _iob_route_needs_dedup(pin, dx, dy, dn, port):
    """Return True if this IOB_ROUTE entry needs dedup stripping."""
    global _IOB_ROUTE_NODEDUP_KEYS
    if _IOB_ROUTE_NODEDUP_KEYS is None:
        _load_iob_route_cells(pin, dx, dy, dn, port)
    key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
    return key not in _IOB_ROUTE_NODEDUP_KEYS


def _load_iob_route_cells_legacy(pin, dx, dy, dn, port):
    """Pre-6b6cda9 IOB_ROUTE lookup — consults ``single_le_cells`` /
    ``single_le_cells_stale`` as the override bucket, falling back to
    ``absolute_cells``.

    The ``single_le_cells`` bucket was renamed to ``single_le_cells_stale``
    in bdfec54 (quarantine) and the live path (``_load_iob_route_cells``)
    no longer consults it.  Legacy bitgen mode (``legacy_iob_route=True``)
    needs those cells verbatim: the cff800e / d48c13e HW-PASS simple_led
    probes baked the 164-cell single_le_cells delta for
    E16->X10Y4N0.dataa, and dropping to absolute_cells (196) + dedup + hdr
    skip breaks silicon (43b byte drift vs HW-PASS ref).

    Caller applies the returned cells via pure XOR parity with no dedup
    or header-band filtering.
    """
    global _IOB_ROUTE_LEGACY_CACHE
    if _IOB_ROUTE_LEGACY_CACHE is None:
        import json
        path = ROOT / "results" / "iob_to_slice_sigcache.json"
        if not path.exists():
            raise FasmError(
                "IOB_ROUTE (legacy) directive used but "
                "results/iob_to_slice_sigcache.json missing"
            )
        data = json.loads(path.read_text())
        # Per-key preference:
        #   1. ``single_le_cells`` — fresh 2026-04-24 Fix B re-mine
        #      against the legacy apply-path (109 entries).
        #   2. ``single_le_cells_stale`` — 2026-04-15 bucket, retained
        #      as a fallback for any key that a future sweep drops.
        #   3. ``absolute_cells`` — pair-derived reconstruction
        #      (15 entries).  Fallback for designs whose key is only
        #      present in the pair bucket.
        merged = dict(data.get("absolute_cells", {}))
        merged.update(data.get("single_le_cells_stale", {}))
        merged.update(data.get("single_le_cells", {}))
        _IOB_ROUTE_LEGACY_CACHE = merged
    key = f"IOB_{pin}->{dx},{dy},{dn},{port}"
    if key not in _IOB_ROUTE_LEGACY_CACHE:
        raise FasmError(
            f"IOB_ROUTE (legacy) PIN_{pin} -> X{dx}Y{dy}N{dn}.{port}: "
            f"no entry in single_le_cells_stale / absolute_cells buckets "
            f"of iob_to_slice_sigcache.json."
        )
    return [tuple(c) for c in _IOB_ROUTE_LEGACY_CACHE[key]]


def _load_iob_oe_cells(pin):
    """Return XOR-delta cells (off, bp) for `IOB_OE PIN_X`.

    Reads results/iob_oe_cell_map.json (Stage B-narrow output of
    fuzz/iob_oe_specimen.py).  The JSON only carries the 16 sdram_dq
    pins NEORV32 uses on AX301 (S_DB[0]..S_DB[15]); arbitrary IOB
    pairs are explicitly out of scope.  The mining harness fixed
    CLK=E1 / K_IN=E16 / OE_IN=M16 / LED=G15 — applying these cells
    on top of an IOB_IN/IOB_OUT-built design at the same pin
    activates the tristate driver path.

    Silicon-falsification mask (2026-04-17 HW bisection on PIN_R5):
      * (363236, 2) frame=1729 — shared with DSPMULT_GLOBAL_ON
        (isolated 2026-04-17 Stage 0).  Present in all 16 sdram_dq
        pin sets.  Stuck-on leak without it.
      * (363672, 2) frame=1731 — R5-unique second leaky cell
        (isolated 2026-04-17 Stage 1 via A∪B bisection; A = R5 ∩
        DSPMULT CLEAN22, B = R5-unique).  Present in 14/16 pin sets
        (all except T10, T2).  Stuck-on leak without it.
    Both cells were verified by a CLEAN38 flash: R5 minus both
    leaky cells passes silicon (LED follows KEY2).  The mask is
    applied pin-agnostic so the same bits are stripped from every
    pin's emitted cell set; pins where the cell doesn't occur are
    unaffected.
    """
    global _IOB_OE_CACHE
    if _IOB_OE_CACHE is None:
        import json
        path = ROOT / "results" / "iob_oe_cell_map.json"
        if not path.exists():
            raise FasmError(
                "IOB_OE used but results/iob_oe_cell_map.json missing; "
                "run fuzz/iob_oe_specimen.py first"
            )
        data = json.loads(path.read_text())
        SILICON_FALSIFIED = {(363236, 2), (363672, 2)}  # HW 2026-04-17
        # Pin keys in the per_pin_oe table are full names like
        # "S_DB[0]"; the FASM directive references the package pin
        # (e.g. PIN_R5).  Build a PIN_XX -> cells lookup keyed by the
        # second-half of the harness assignment.
        meta = data.get("meta", {})
        pin_map = {}  # PIN_XX -> cells
        # Each entry has the canonical loc tuple (pin, loc) under
        # data["entries"] for pure pin lookups.
        for e in data.get("entries", []):
            loc = e.get("loc", "")
            cells = data["per_pin_oe"].get(e["pin"], [])
            if loc.startswith("PIN_"):
                cleaned = [c for c in cells
                           if tuple(c) not in SILICON_FALSIFIED]
                pin_map[loc[len("PIN_"):]] = cleaned
        _IOB_OE_CACHE = pin_map
    if pin not in _IOB_OE_CACHE:
        raise FasmError(
            f"IOB_OE PIN_{pin}: no entry in iob_oe_cell_map.json "
            f"(known: {sorted(_IOB_OE_CACHE)}). Stage B-narrow scope "
            f"is the 16 sdram_dq pins NEORV32 uses on AX301; rerun "
            f"fuzz/iob_oe_specimen.py if the pin set has changed."
        )
    return [tuple(c) for c in _IOB_OE_CACHE[pin]]


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


def _load_lab_clk_sel_cells(x, y, *, lenient=False):
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
        if not lenient:
            raise FasmError(
                f"LAB_CLK_SEL X{x}Y{y}: no mined data at {path.name}. "
                f"Run: python3 fuzz/clk_lab_sel_probe.py --lab {x},{y}"
            )
        return []
    data = json.loads(path.read_text())
    cells = [tuple(c) for c in data.get("lab_clk_sel", [])]
    _LAB_CLK_SEL_CACHE[key] = cells
    return cells


def _load_lab_clk_sel_le_cells(x, y, n, *, lenient=False):
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
        if not lenient:
            raise FasmError(
                f"LAB_CLK_SEL_LE X{x}Y{y}N{n}: no mined data for LAB. "
                f"Run: python3 fuzz/clk_lab_sel_probe.py --lab {x},{y}"
                f" then python3 fuzz/clk_lab_sel_per_le.py"
            )
        return []
    # X=33 entries in clk_lab_sel_per_le.json are mining garbage —
    # the X=33 mining sweep used LCFF LOC overrides which Quartus Lite
    # rejects, so the recorded "X=33" cells are from misplaced builds
    # at other columns.  Audited 2026-05-03 vs cl_and gold: 1/30 cells
    # match at X33Y4 N=4+N=6.  Skip the lookup to avoid emitting wrong
    # cells; X=33 LE infra is provided by X33Y4_INFRA override instead.
    if x == 33:
        import sys as _sys
        print(
            f"WARN: LAB_CLK_SEL_LE X33Y{y}N{n} silently dropped "
            f"(clk_lab_sel_per_le.json X33 entries are LOC-rejected "
            f"mining garbage; X=33 LE clock infra is supplied by the "
            f"X33Y4_CROSS_LAB_SHIM override when topology matches).",
            file=_sys.stderr,
        )
        return []
    entry = _LAB_CLK_SEL_LE_CACHE[key]
    bucket = f"n{n}_specific"
    if bucket not in entry:
        if not lenient:
            raise FasmError(
                f"LAB_CLK_SEL_LE X{x}Y{y}N{n}: N={n} not mined "
                f"(available buckets: {[k for k in entry if k.endswith('_specific')]}). "
                f"Extend clk_lab_sel_probe.py N_SLOTS and rerun for "
                f"LAB X{x}Y{y}."
            )
        return []
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


_ARITH_MULTI_LAB_CACHE = None


def _load_arith_multi_lab_blob():
    """Return the parsed arith_blockband_by_width.json, cached.

    Schema (see scripts/arith_sweep/):
      d["multi_lab"]["16+N"] = {
         "topology": "full_lab_plus_partial_lab_down",
         "set":   [[cram_off, bp], ...],     # width-dependent SET cells
         "clear": [[cram_off, bp], ...],     # width-dependent CLEAR cells
         "n_set": int, "n_clear": int,
      }
    for N ∈ {1..16} giving total chain widths 17..32 spanning
    LAB(4,18) (full, 16 LEs) + LAB(4,17) (N extra bits) with the
    N=30→N=0 inter-LAB carry link.
    """
    global _ARITH_MULTI_LAB_CACHE
    if _ARITH_MULTI_LAB_CACHE is not None:
        return _ARITH_MULTI_LAB_CACHE
    import json
    path = ROOT / "results" / "arith_blockband_by_width.json"
    if path.exists():
        _ARITH_MULTI_LAB_CACHE = json.loads(path.read_text())
    return _ARITH_MULTI_LAB_CACHE


def _arith_multi_lab_cells(width):
    """Return (set_cells, clear_cells) for a `width`-bit multi-LAB carry chain.

    SET cells: gold has bit=1, baseline (zero+v4_blob) has bit=0 → toggle on.
    CLEAR cells: gold has bit=0, baseline has bit=1 → must force to 0.

    The two sets are applied with different semantics by the consumer:
    - SET via XOR (with optional dedup against IOB-class single-flip cells).
    - CLEAR via AND-clear (force 0), bypassing dedup so v4-blob overflow
      cells that LAB_CLK_SEL or other phases pre-set get correctly cleared.
      See `multi_lab_carry_silicon_validated_2026_05_03` for the W=23
      cell (365143, 2) case where dedup-skipped XOR-clear left the cell
      poisoning the chain.
    """
    if width < 17 or width > 32:
        raise FasmError(
            f"LUT_ARITH_MULTI_LAB WIDTH={width}: only widths 17..32 "
            f"have mined blobs; single-LAB widths 2..16 use LUT_ARITH"
        )
    blob = _load_arith_multi_lab_blob()
    if blob is None:
        raise FasmError(
            "LUT_ARITH_MULTI_LAB: results/arith_blockband_by_width.json "
            "missing; run scripts/arith_sweep/ for widths 17..32"
        )
    key = f"16+{width - 16}"
    ml = blob.get("multi_lab", {})
    if key not in ml:
        raise FasmError(
            f"LUT_ARITH_MULTI_LAB WIDTH={width}: no multi_lab[{key!r}] "
            f"entry in arith_blockband_by_width.json"
        )
    entry = ml[key]
    set_cells = [(int(o), int(b)) for o, b in entry.get("set", [])]
    clear_cells = [(int(o), int(b)) for o, b in entry.get("clear", [])]
    return set_cells, clear_cells


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


_PRAGMA_RE = re.compile(r"^\s*#\s*fasm2rbf\s*:\s*(\w+)\s*=\s*(\S+)\s*$")


def parse_pragmas(text):
    """Scan ``# fasm2rbf: key=value`` pragma comments.

    Returns a dict of kwargs ready to forward to :func:`bitgen`.
    Currently recognised keys:

    * ``legacy_iob_route`` — boolean (``1``/``0`` / ``true``/``false``)

    Unknown keys raise ``ValueError`` so silent drift is impossible.
    Callers that use np2fasm's ``--legacy-iob-route`` should wire this
    through explicitly::

        pragmas = parse_pragmas(fasm_text)
        rbf = bitgen(fasm_text, base_rbf, **pragmas)
    """
    out = {}
    for line in text.splitlines():
        m = _PRAGMA_RE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).lower()
        if key == "legacy_iob_route":
            if val in ("1", "true", "yes", "on"):
                out["legacy_iob_route"] = True
            elif val in ("0", "false", "no", "off"):
                out["legacy_iob_route"] = False
            else:
                raise ValueError(
                    f"parse_pragmas: legacy_iob_route={val!r} "
                    f"must be 1/0/true/false")
        else:
            raise ValueError(f"parse_pragmas: unknown pragma {key!r}")
    return out


def parse_fasm(text):
    """Return (luts, routes) from FASM text.

    luts:   list of (x, y, n, mask_int)
    routes: list of (sx, sy, dx, dy, dn, port)
    """
    luts = []
    lut_arith = []  # list[(x, y, n, mask_int)] — arith-mode LEs
    lut_arith_multi_labs = []  # list[int] — widths 17..32 requested
    routes = []
    bits = []
    srcs = []
    dffs = []  # list[(x, y, mode)] mode in {"ARST","ENA"}
    dff_les = []  # list[(x, y, n)] per-LE DFF enable
    m9k_inits = []  # list[(x, y, n, width, depth, target_words)]
    m9k_modes = []  # list[(x, y, n, width, depth)] — per-site enable
    design_packs = []  # list[str] — DESIGN_BLOCK_BAND_PACK tags
    dspmult_global_on = False  # DSPMULT_GLOBAL_ON directive seen
    iobs = []  # list[(role, pin)] where role in {'IN','OUT'}
    iob_routes = []  # list[(pin, dx, dy, dn, port)] — nv_zero_global-frame
    iob_oes = []  # list[pin] — IOB_OE PIN_X (Stage B-narrow tristate)
    iob_baseline_nv = False  # IOB_BASELINE_NV directive seen
    iob_pad_nv = False  # IOB_PAD_NV directive seen (方案B)
    outroute_g15s = []  # list[(sx, sy, sn)] — OUTROUTE_G15 positions
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
        m = _LUT_ARITH_MULTI_LAB_RE.match(line)
        if m:
            lut_arith_multi_labs.append(int(m["width"]))
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
        m = _IOB_PAD_NV_RE.match(line)
        if m:
            iob_pad_nv = not iob_pad_nv  # XOR parity
            continue
        m = _OUTROUTE_G15_RE.match(line)
        if m:
            outroute_g15s.append(
                (int(m["sx"]), int(m["sy"]), int(m["sn"])))
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
        m = _M9K_BLOCK_DEFAULT_PACK_RE.match(line)
        if m:
            nv_buckets.append("m9k_block_default_pack")
            continue
        m = _MULT_BLOCK_DEFAULT_PACK_RE.match(line)
        if m:
            nv_buckets.append("mult_block_default_pack")
            continue
        m = _IOB_ROUTE_RE.match(line)
        if m:
            iob_routes.append(
                (m["pin"], int(m["dx"]), int(m["dy"]),
                 int(m["dn"]), m["port"])
            )
            continue
        m = _IOB_OE_RE.match(line)
        if m:
            iob_oes.append(m["pin"])
            continue
        m = _IOB_RE.match(line)
        if m:
            role = m["role"] + ("_BIDIR" if m["bidir"] else "")
            iobs.append((role, m["pin"]))
            continue
        m = _M9K_MODE_RE.match(line)
        if m:
            template = m["template"] or _M9K_MODE_DEFAULT_TEMPLATE
            m9k_modes.append((
                int(m["x"]), int(m["y"]), int(m["n"]),
                int(m["width"]), int(m["depth"]),
                template,
            ))
            continue
        m = _DSPMULT_GLOBAL_ON_RE.match(line)
        if m:
            dspmult_global_on = not dspmult_global_on  # XOR parity
            continue
        m = _DESIGN_BLOCK_BAND_PACK_RE.match(line)
        if m:
            design_packs.append(m["tag"])
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
            iob_baseline_nv, iob_clk_inputs, nv_buckets, m9k_modes,
            dspmult_global_on, iob_oes, lut_arith_multi_labs,
            iob_pad_nv, outroute_g15s, design_packs)


def build_route_ops(routes, cells_table=None, extra_cells=None,
                    lenient=False):
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
        # Sig-cache miss — try the fingerprint-snapshot shortcut before
        # falling through to the formula path.  synth_route uses the
        # same snapshot lookup ahead of parse_need, which is how
        # jailbreak/edge Y=15 and Y=5 sources get routed bit-perfect
        # despite LAB_Y not including those rows.  Mirror that here so
        # fasm2rbf.bitgen gets the same coverage.
        from route_synth import _snapshot_ops_if_present
        snap_ops = _snapshot_ops_if_present(
            (sx, sy), (dx, dy, dn, port)
        )
        if snap_ops is not None:
            for op in snap_ops:
                sig_cells.add((op["offset"], op["bp"]))
            continue
        if lenient:
            continue
        # X=33 jailbreak column has no calibrated route formula — the
        # CE6-derived parse_need + plan_hops + emit_ops fallback emits
        # cells at structurally wrong offsets (proven 0/9 hit on
        # cl_and gold for ROUTE 33,4,4 → 33,4,6.dataa).  Skip emission
        # rather than corrupt the bitstream; the route still needs a
        # real sig-cache entry mined from a working Quartus reference
        # before silicon will function.
        if sx == 33 or dx == 33:
            import sys as _sys
            print(
                f"WARN: ROUTE X{sx}Y{sy}N{sn}->X{dx}Y{dy}N{dn}.{port} "
                f"silently dropped (X=33 has no formula path; needs "
                f"sig-cache entry).  Same-LAB X=33 routes are covered "
                f"by X33Y4_CROSS_LAB_SHIM when topology matches.",
                file=_sys.stderr,
            )
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


def bitgen(fasm_text, base_rbf, db_path=DB_PATH, patch_crc=True,
           lenient=False, legacy_iob_route=False):
    """Core entry — FASM text + base RBF → finished RBF bytes.

    ``legacy_iob_route=True`` restores the pre-6b6cda9 IOB_ROUTE cell
    application path: cells come from the legacy
    ``single_le_cells`` / ``single_le_cells_stale`` bucket (falling back
    to ``absolute_cells``) and are applied via pure XOR parity with no
    dedup stripping and no header-band ``off < 5282`` filter.  This
    reproduces the semantics under which the cff800e / d48c13e simple_led
    M9K_MODE probes were built and HW-validated on AX301.  The live path
    (default ``legacy_iob_route=False``) is correct for pair-derived
    ``padnv_cells`` / ``absolute_cells`` entries consumed by two_lab /
    NEORV32 ζ flows.
    """
    (luts, lut_arith, routes, bits, srcs, dffs, dff_les, m9k_inits,
     iobs, iob_routes, gclk, gclk_pins, lab_clk_sels,
     lab_clk_sel_les, iob_baseline_nv,
     iob_clk_inputs, nv_buckets, m9k_modes,
     dspmult_global_on, iob_oes,
     lut_arith_multi_labs,
     iob_pad_nv, outroute_g15s, design_packs) = parse_fasm(fasm_text)

    codec = RouteCodec()
    work = bytes(base_rbf)

    # Track cells applied by design directives so IOB_ROUTE can skip
    # overlapping cells.  IOB_ROUTE sig-cache entries are absolute deltas
    # (iob_pair ^ nv_zero_global) that include IOB_IN/OUT, SRC, ROUTE,
    # GCLK cells — applying them alongside dedicated directives for those
    # groups causes XOR double-flip (cancellation).  We collect all design
    # cells and subtract from IOB_ROUTE before applying.
    _iob_route_dedup = set()

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
                _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    src_cells = set()
    if srcs:
        overhead = _load_overhead()
        if overhead is None:
            import warnings
            warnings.warn(
                "SRC directive used but results/source_overhead.json missing; "
                "source overhead cells skipped (sig-cache routes carry them)"
            )
            overhead = {}
        for sx, sy in srcs:
            key = f"{sx},{sy}"
            if key not in overhead:
                continue
            for off, bp in overhead[key]:
                src_cells.add((off, bp))

    # LI MUX lockdown bookkeeping (the LUT phase below uses σ⁻¹ TT
    # predictions that have ~160 false-positive collisions with LI
    # MUX bytes per pipeline_test-class build — Phase 1 clears them,
    # Phase 2 sometimes XOR-sets non-canonical ones, producing
    # invalid envelopes).  We snapshot the full LI MUX state after
    # apply_routing and restore it byte-for-byte after the LUT phase.
    # Default empty sets keep this a no-op when there's no routing.
    li_locked_state = {}  # (off, bp) -> 0/1 expected after LUT
    if routes or src_cells:
        cells_table = route_signatures.load_cells_full() if routes else None
        ops = build_route_ops(routes, cells_table=cells_table,
                             extra_cells=src_cells, lenient=lenient)
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
                if op.get("type") != "raw"
                or (op["offset"], op["bp"]) not in strip
            ]
        for op in ops:
            if op.get("type") == "raw":
                _iob_route_dedup.add((op["offset"], op["bp"]))
        # Multi-route LI envelope merge: when several routes target (or
        # originate at) the same LAB, build_route_ops emits one li op per
        # route.  apply_routing applies each via XOR, which double-flips
        # shared cells (two routes terminating at the same LAB cancel
        # their shared envelope cells).  Coalesce all li ops by (lx, ly)
        # into a single op whose pair_bases is the *union* of every
        # contributing route's cells — written once with XOR-from-zero
        # semantics gives the intended final state.
        #
        # Path X (2026-05-02): the src-driver `[(8,0),(8,1)]` lives in
        # the same LAB's LI MUX as the dst-tail's single P8 base.  When
        # a LAB is BOTH a source and a destination, the src-driver's
        # second P8 base collides with the dst-tail.  Quartus's gold
        # for pipeline_test has empty LI cells at the affected LABs
        # (different placement; no ground truth to compare against).
        # Resolution: if a LAB has both src_driver and dst_tail roles,
        # drop the src_driver (the dst_tail's P8 cells are sufficient
        # for the LE-input-MUX engagement).  See memory
        # step_3_jailbreak_x_cram_gap_2026_05_02.
        if any(op.get("type") == "li" for op in ops):
            from bitstream import RouteCodec as _RC
            dst_labs = {(op["lx"], op["ly"]) for op in ops
                        if op.get("type") == "li"
                        and op.get("role") != "src_driver"}
            merged_li = {}
            non_li_ops = []
            for op in ops:
                if op.get("type") == "li":
                    key = (op["lx"], op["ly"])
                    if op.get("role") == "src_driver" and key in dst_labs:
                        continue  # Path X: dst_tail handles P8 here
                    bag = merged_li.setdefault(key, set())
                    for pb in op.get("pair_bases", op.get("pairs", [])):
                        bag.add(tuple(pb))
                else:
                    non_li_ops.append(op)
            # Path Y' (2026-05-02): when a LAB is a dst, REPLACE the
            # unioned cells with the canonical typical envelope for
            # that LAB's column mode.  Different routes can pick
            # alternating-vs-paired variants at the same LAB; their
            # union produces an invalid hybrid (>9 cells, mixed modes)
            # that validate_safe_for_hardware rejects.  Clamping to a
            # single canonical envelope gives the LE-input MUX a
            # well-defined mode while still selecting the lanes the
            # routes need.  src_driver-only LABs keep their union.
            for key in list(merged_li.keys()):
                if key in dst_labs:
                    lx, _ly = key
                    try:
                        mode = _RC.select_li_mode(lx)
                        merged_li[key] = set(_RC.LI_TYPICAL_ENVELOPE[mode])
                    except KeyError:
                        pass  # non-LAB X — leave union as-is
            ops = non_li_ops + [
                {"type": "li", "lx": lx, "ly": ly,
                 "pair_bases": sorted(bag)}
                for (lx, ly), bag in merged_li.items()
            ]
        work = codec.apply_routing(work, ops)
        # Snapshot LI MUX state for every valid LAB (lx ∈ LAB_X,
        # ly ∈ LAB_Y) so we can restore it post-LUT and overwrite
        # σ⁻¹'s collateral writes.
        from config import COLUMN_BASE as _CB, PAIR_SPACING as _PS, LAB_X as _LX, LAB_Y as _LY
        from bitstream import (_LI_SLOT_OFFSET as _LSO,
                               _cram_group_bit as _cgb)
        for lx in _LX:
            if lx not in _CB:
                continue
            cs = _CB[lx] - 136
            for ly in _LY:
                grp, slt, bp = _cgb(ly)
                so = _LSO[slt]
                for pair in range(9):
                    for base_idx in (0, 1):
                        off = cs + 70 + base_idx + pair * _PS + so + 3 * grp
                        li_locked_state[(off, bp)] = (work[off] >> bp) & 1

    if gclk:
        buf = bytearray(work)
        for off, bp in _GCLK_CELLS:
            buf[off] |= (1 << bp)       # absolute SET, not XOR toggle
            _iob_route_dedup.add((off, bp))
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
            for off, bp in _load_lab_clk_sel_cells(x, y, lenient=lenient):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        for x, y, n in lab_clk_sel_les:
            for off, bp in _load_lab_clk_sel_le_cells(x, y, n, lenient=lenient):
                key = (off, bp)
                parity[key] = parity.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in parity.items():
            if v:
                buf[off] ^= (1 << bp)
                _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    # DFF directives are parsed but intentionally no-op: Cyclone IV's
    # flip-flop is intrinsic to every LE (no per-LE enable cell in CRAM).
    # Registered vs combinational output is selected by downstream routing.
    # See _dff_le_cells() docstring for HW verification details.

    if bits:
        buf = bytearray(work)
        for off, bp in bits:
            buf[off] ^= (1 << bp)
            _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    if iob_baseline_nv:
        buf = bytearray(work)
        for off, bp in _load_iob_baseline_hdr_cells():
            buf[off] ^= (1 << bp)
            _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    if iob_pad_nv:
        buf = bytearray(work)
        for off, bp in _load_iob_pad_nv_cells():
            buf[off] ^= (1 << bp)
            _iob_route_dedup.add((off, bp))
        # Carry-chain extension: when IOB_PAD_NV is requested AND the
        # design has any LUT_ARITH or LUT_ARITH_MULTI_LAB directive,
        # additionally emit the 74 cells that silicon-validated W=23
        # (905dfc85) requires but simple-G15 designs do not.  These
        # cells were originally part of the 241-cell IOB_PAD_NV
        # baseline but were correctly stripped by a5e4a0e for simple
        # designs; they're restored conditionally here for carry-chain
        # designs only.
        if lut_arith or lut_arith_multi_labs:
            for off, bp in _load_iob_pad_arith_ext_cells():
                buf[off] ^= (1 << bp)
                _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    if outroute_g15s:
        buf = bytearray(work)
        for (sx, sy, sn) in outroute_g15s:
            for off, bp in _load_outroute_g15_cells(sx, sy, sn):
                buf[off] ^= (1 << bp)
                _iob_route_dedup.add((off, bp))
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
                _iob_route_dedup.add((off, bp))
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
            for off, bp in _iob_delta_cells(role, pin, iob_map, lenient=lenient):
                key = (off, bp)
                flips[key] = flips.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in flips.items():
            if v:
                buf[off] ^= (1 << bp)
                _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    if iob_routes:
        # IOB_ROUTE sig-cache entries are XOR-delta cell sets.  Two
        # derivation flavours exist:
        #
        #   padnv_cells — derived as (gold ⊕ base) minus LUT cells,
        #       where base = nv + IOB_PAD_NV + OUTROUTE + CLK.  These
        #       entries already account for directive overlap and compose
        #       correctly via XOR parity WITHOUT dedup stripping.
        #
        #   single_le_cells / absolute_cells — legacy entries derived
        #       against IOB_BASELINE_NV path.  They include cells shared
        #       with other directives and NEED dedup stripping.
        #
        # When ``legacy_iob_route=True`` the caller is asking for the
        # pre-6b6cda9 path: consult the legacy single_le bucket and
        # apply cells via pure XOR parity (no dedup, no hdr-skip).  This
        # reproduces cff800e / d48c13e HW-PASS simple_led semantics for
        # single-LE designs that the live path breaks (443-byte drift).
        parity = {}
        skipped = 0
        for pin, dx, dy, dn, port in iob_routes:
            if legacy_iob_route:
                cells = _load_iob_route_cells_legacy(pin, dx, dy, dn, port)
                for off, bp in cells:
                    key = (off, bp)
                    parity[key] = parity.get(key, 0) ^ 1
                continue
            needs_dedup = _iob_route_needs_dedup(pin, dx, dy, dn, port)
            for off, bp in _load_iob_route_cells(pin, dx, dy, dn, port):
                if off < 5282:
                    skipped += 1
                    continue
                key = (off, bp)
                if needs_dedup and key in _iob_route_dedup:
                    skipped += 1
                    continue
                parity[key] = parity.get(key, 0) ^ 1
        buf = bytearray(work)
        for (off, bp), v in parity.items():
            if v:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

    if iob_oes:
        # IOB_OE PIN_X — Stage B-narrow tristate enable for the 16
        # sdram_dq pins.  XOR-parity composition (boolean per pin —
        # double-emit cancels).  Cells come from
        # results/iob_oe_cell_map.json (mined by fuzz/iob_oe_specimen.py
        # under a frozen CLK/K/OE/LED harness; only invariance-probed
        # pins are trusted).
        parity = {}
        for pin in iob_oes:
            for off, bp in _load_iob_oe_cells(pin):
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
        buf = bytearray(work)

        # X=33 jailbreak column uses per-NIBBLE (b%4) encoding with pair stride
        # 420 (2 frames) — completely incompatible with the CE6 σ⁻¹ XOR-linear
        # model.  Mined 2026-05-04 from 6-variant cross_lab Quartus builds; see
        # results/x33_lut_codec.json + memory note `x33_lut_per_nibble_codec`.
        # Partition out X=33 LUTs and apply nibble-OR semantics directly.
        x33_luts = [t for t in all_luts if t[0] == 33]
        std_luts = [t for t in all_luts if t[0] != 33]

        lut_cache = {}
        tt_cells_cache = {}
        arith_keys = {(x, y, n) for x, y, n, _ in lut_arith}
        for x, y, n, mask in std_luts:
            key = (x, y, n)
            if key in lut_cache:
                continue
            lut = LutCodec.from_cram_model(x, y, n)
            lut_cache[key] = lut
            tt_cells_cache[key] = lut.predict_sram(0xFFFF)

        # Phase 1: clear TRUE TT cells to 0 (nv_zero_global baseline).
        # predict_sram(0xFFFF) yields exactly the 16 true TT cells
        # (from_cram_model has 1 cell per minterm, no shared LAB noise).
        # SKIP for arith-mode LEs — arith has no normal-mode presence.
        for x, y, n, mask in std_luts:
            if (x, y, n) in arith_keys:
                continue
            for addr, bitpos in tt_cells_cache[(x, y, n)]:
                buf[addr] &= ~(1 << bitpos)

        # Phase 2: XOR-flip true TT cells for each LUT mask.
        for x, y, n, mask in std_luts:
            lut = lut_cache[(x, y, n)]
            tt_only = tt_cells_cache[(x, y, n)]
            for addr, bitpos in lut.predict_sram(mask) & tt_only:
                buf[addr] ^= (1 << bitpos)

        # X=33 nibble-OR phase.  Per-position per-nibble cell tables
        # mined from cross_lab.v variants: (Y=4, N=4) is Stage A,
        # (Y=4, N=6) is Stage B.  For LEs at uncovered (Y, N), skip
        # emission rather than emit at wrong offsets.
        #
        # Each covered LE: determine which of the 4 nibble classes
        # (b%4) have any TT bit set; XOR-flip the union of those
        # nibbles' cell sets against the working buffer (which is at
        # the nv_zero_global baseline by virtue of the prior
        # NV_BASELINE_PACK directive).  Cells emitted ONCE regardless
        # of how many bits in a nibble are set (per-nibble OR
        # semantics, not per-bit XOR).
        if x33_luts:
            nib_table = _x33_nibble_cells()  # {(y,n): {0..3: cell_set}}
            x33_flip_cells = set()
            for x, y, n, mask in x33_luts:
                if (x, y, n) in arith_keys:
                    continue
                pos_nibs = nib_table.get((y, n))
                if pos_nibs is None:
                    # No per-position table → leave LUT TT bits alone
                    # (better than emitting at wrong offsets and
                    # silently corrupting other (Y, N) cells).
                    import sys as _sys
                    print(
                        f"WARN: X=33 LE at (Y={y}, N={n}) has no "
                        f"nibble codec table; LUT TT bits unset.  "
                        f"Mine this position via "
                        f"scripts/cross_lab/x33_lut_mining/ before "
                        f"flashing.  Available positions: "
                        f"{sorted(nib_table.keys())}",
                        file=_sys.stderr,
                    )
                    continue
                for k in range(4):
                    if (mask >> k) & 0x1111:
                        x33_flip_cells |= pos_nibs[k]
            for addr, bitpos in x33_flip_cells:
                buf[addr] ^= (1 << bitpos)

            # X=33Y4 LE infrastructure override.  When ANY X=33Y4 LE
            # is present, apply the residual cell set calibrated from
            # cl_and gold (cross_lab.v 2-LE topology at SLICE_X33_Y4_N4
            # + N=6).  These cells aren't covered by any other
            # directive (LAB_CLK_SEL_LE X=33 was mining-garbage and
            # is now skipped; same-LAB ROUTE at X=33 is also skipped
            # for lack of sig-cache).  Design-specific shim until
            # proper per-directive mining is done.
        # Phase 3 (2026-05-02): restore LI MUX state from the
        # post-apply_routing snapshot.  σ⁻¹'s `from_cram_model`
        # mis-classifies ~160 LI MUX bytes as "true TT cells" per
        # pipeline_test-class build — Phase 1 clears them, Phase 2
        # sometimes XOR-sets non-canonical ones.  Stamping the
        # snapshot verbatim cancels both effects: the LI MUX ends
        # up exactly where apply_routing left it (canonical envelope
        # for dst LABs; nothing for unrelated LABs).
        for (off, bp), v in li_locked_state.items():
            if v:
                buf[off] |= (1 << bp)
            else:
                buf[off] &= ~(1 << bp)

        # X33Y4_CROSS_LAB_SHIM applied AFTER Phase 3 — some override
        # cells land on LI MUX positions of OTHER LABs (e.g. (83503,4)
        # is X=10 LAB Y=10 P8 base) which the snapshot/restore
        # mechanism would otherwise clobber.  Override needs the last
        # word for these cell positions.
        #
        # SAFETY: shim is design-specific (cross_lab.v topology) and
        # touches 8 columns (X=5,9,10,17,22,24,32,33 + header).  Apply
        # only when ALL preconditions match cross_lab's exact shape;
        # refuse otherwise to avoid clobbering legitimate state in
        # unrelated designs that happen to also use X=33Y4.
        if _x33y4_cross_lab_shim_should_apply(
                x33_luts, all_luts, routes, iobs, lab_clk_sels,
                iob_pad_nv=iob_pad_nv):
            infra_cells = _x33y4_infra_cells()
            for addr, bitpos in infra_cells:
                buf[addr] ^= (1 << bitpos)
        work = bytes(buf)

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

    if lut_arith_multi_labs:
        # Multi-LAB carry-chain activation for widths 17..32.  Each
        # requested width pulls its own cell set from
        # results/arith_blockband_by_width.json (multi_lab["16+N"]).
        # XOR-parity semantics: emitting the same width twice cancels;
        # emitting two different widths composes their cell unions with
        # XOR on any overlap.
        #
        # Mined against LAB(4,18)+LAB(4,17) as the concrete placement —
        # position-independence is NOT yet proven for multi-LAB blobs
        # (the single-LAB v4 triangle test only covers 2..16).  Callers
        # who place the chain elsewhere may see residual diffs.
        #
        # Dedup against _iob_route_dedup: the multi_lab JSON includes the
        # carry-chain LI MUX input cells at LAB(4,17) (pairs 0/1) which
        # also appear in OUTROUTE_G15 X4Y17N* sigcache (the chain MSB's
        # output route shares those LI MUX cells with the carry-input
        # path). Without dedup, the OUTROUTE-then-MULTI_LAB XOR sequence
        # cancels them — see memory `multi_lab_codec_fixed_2026_05_03.md`.
        parity = {}
        clear_force = set()
        for width in lut_arith_multi_labs:
            sc_set, sc_clear = _arith_multi_lab_cells(width)
            for off, bp in sc_set:
                if (off, bp) in _iob_route_dedup:
                    continue
                parity[(off, bp)] = parity.get((off, bp), 0) ^ 1
            # CLEAR cells are AND-clear: force 0 regardless of dedup, since
            # they target v4-blob OR-in overflow that other phases (LAB_CLK_SEL
            # etc.) may also have set + dedup-locked.  XOR semantics fail when
            # the cell is dedup-locked at 1; AND-clear unconditionally fixes it.
            for off, bp in sc_clear:
                clear_force.add((off, bp))
        buf = bytearray(work)
        for (off, bp), p in parity.items():
            if p:
                buf[off] ^= (1 << bp)
                _iob_route_dedup.add((off, bp))
        for off, bp in clear_force:
            buf[off] &= ~(1 << bp) & 0xFF
            _iob_route_dedup.add((off, bp))
        work = bytes(buf)

    if m9k_modes:
        # Per-(site, width, depth, template) M9K enable cells from
        # results/m9k_mode_bits.json.  XOR-parity composition: each cell
        # toggled an odd number of times across all M9K_MODE directives
        # is flipped exactly once.  Applied BEFORE INIT so the M9K
        # primary CRAM is in the {width}x{depth} configured state when
        # write_init lays down user words.
        #
        # `template` defaults to "altsyncram" when the bare
        # `M9K_MODE_{w}x{d}` form is used (legacy + most current
        # callers); the explicit `_altsyncram` / `_inferred` suffix
        # selects the corresponding `cells_by_template` bucket.
        parity = {}
        for x, y, n, width, depth, template in m9k_modes:
            site = f"X{x}_Y{y}_N{n}"
            for off, bp in _load_m9k_mode_cells(
                site, width, depth, template
            ):
                parity[(off, bp)] = parity.get((off, bp), 0) ^ 1
        buf = bytearray(work)
        for (off, bp), p in parity.items():
            if p:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

    if design_packs:
        # Design-specific block-band pack from results/design_block_band.json.
        # XOR-parity composition with M9K_MODE: any cell toggled an odd
        # number of times across (per-site M9K_MODE + DESIGN_BLOCK_BAND_PACK)
        # is flipped exactly once.  Applied AFTER M9K_MODE and BEFORE
        # M9K_INIT so the M9K block-band reaches its design-correct state
        # before init data is laid down.
        parity = {}
        for tag in design_packs:
            for off, bp in _load_design_block_band_pack(tag):
                parity[(off, bp)] = parity.get((off, bp), 0) ^ 1
        buf = bytearray(work)
        for (off, bp), p in parity.items():
            if p:
                buf[off] ^= (1 << bp)
        work = bytes(buf)

    if dspmult_global_on:
        # 23-cell universal DSPMULT enable from
        # results/dspmult_persite_analyze.json (re-mined 2026-04-16 under
        # specimen factory; old contaminated 29-cell set is wrong, see
        # dspmult_global_on_clean_remine.md). Boolean directive: emitting
        # twice cancels (parity already collapsed in parse_fasm).
        buf = bytearray(work)
        for off, bp in _load_dspmult_global_on_cells():
            buf[off] ^= (1 << bp)
        work = bytes(buf)

    if m9k_inits:
        from m9k_init_basis import (
            M9K_INIT_ANCHORS, write_init, read_init,
            SDP_4X2048_BASE_FRAMES, write_init_sdp4x2048, read_init_sdp4x2048,
            SP_9X1024_BASE_FRAMES,  write_init_sp9x1024,  read_init_sp9x1024,
            SP_36X256_BASE_FRAMES,  write_init_sp36x256,  read_init_sp36x256,
        )
        # Dispatch table: (width, depth) → (base_frames_dict, read_fn, write_fn).
        # Entries here use the dedicated codec instead of the legacy linear
        # `write_init`, because the M9K's per-(width, depth) cell layout differs.
        _SPECIAL_INIT_CODECS = {
            (4, 2048):  (SDP_4X2048_BASE_FRAMES, read_init_sdp4x2048, write_init_sdp4x2048),
            (9, 1024):  (SP_9X1024_BASE_FRAMES,  read_init_sp9x1024,  write_init_sp9x1024),
            (36, 256):  (SP_36X256_BASE_FRAMES,  read_init_sp36x256,  write_init_sp36x256),
        }
        for x, y, n, width, depth, target_words in m9k_inits:
            site = f"X{x}_Y{y}_N{n}"
            special = _SPECIAL_INIT_CODECS.get((width, depth))

            if special is not None:
                base_frames, _read_fn, _write_fn = special
                if site not in base_frames:
                    if lenient:
                        sys.stderr.write(
                            f"warn: M9K {site} {width}x{depth}: no calibrated "
                            f"base_frame for dedicated codec — skipping INIT\n"
                        )
                        continue
                    raise FasmError(
                        f"M9K {site} {width}x{depth}: no calibrated base_frame; "
                        f"only X15_Y10_N0 is silicon-validated for this width."
                    )
                base_frame = base_frames[site]
                try:
                    base_words = _read_fn(work, base_frame, depth=depth)
                    work = _write_fn(work, base_frame, base_words, target_words,
                                     depth=depth)
                except (IndexError, Exception) as e:
                    if lenient:
                        sys.stderr.write(
                            f"warn: M9K {site} {width}x{depth}: "
                            f"INIT codec error ({e}) — skipping\n"
                        )
                        continue
                    raise
                continue

            # Legacy linear-formula path: 9×512 / 18×512 (other widths fall
            # through here and will fail the anchor check below).
            key = (site, width, depth)
            if key not in M9K_INIT_ANCHORS:
                if lenient:
                    sys.stderr.write(
                        f"warn: M9K {site} {width}x{depth}: "
                        f"no calibrated anchor — skipping INIT\n"
                    )
                    continue
                raise FasmError(
                    f"M9K {site} {width}x{depth}: no calibrated anchor; "
                    f"run fuzz/m9k_anchor_sweep.py for this site/mode"
                )
            anchor, bp = M9K_INIT_ANCHORS[key]
            try:
                base_words = read_init(work, anchor, width=width, depth=depth, bp=bp)
                work = write_init(work, anchor, base_words, target_words,
                                  width=width, depth=depth, bp=bp)
            except (IndexError, Exception) as e:
                if lenient:
                    sys.stderr.write(
                        f"warn: M9K {site} {width}x{depth}: "
                        f"INIT codec error ({e}) — skipping\n"
                    )
                    continue
                raise

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
