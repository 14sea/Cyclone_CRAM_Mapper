#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 M4 — nextpnr-generic routed JSON to FASM converter.

Reads the placed-and-routed JSON emitted by nextpnr-generic (via
``chipdb_ep4ce6.py``) and emits FASM directives that ``fasm2rbf.py``
can consume to produce a CRC-valid EP4CE6 RBF.

The converter extracts **logical connectivity** from the placed netlist
(which source bel drives which sink bel input) and looks up each
(src→dst.port) pair in the Plan D' sig-cache.  This decouples FASM
generation from nextpnr's abstract routing topology — the chipdb's
LOCAL/INTRA_LAB overlay pips are invisible to this tool.

Supported directive output
--------------------------
* ``X{x}Y{y}N{n}.LUT = 0x{mask}`` — LUT truth table from cell INIT.
* ``ROUTE X{sx}Y{sy}N{sn} -> X{dx}Y{dy}N{dn}.{port}`` — physical
  route from sig-cache, emitted for every placed (src→dst) arc that
  has a sig-cache entry.

Usage
-----
::

    python3 synth/np2fasm.py routed.json > design.fasm
    python3 fuzz/fasm2rbf.py design.fasm base.rbf out.rbf
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FUZZ = HERE.parent / "fuzz"
sys.path.insert(0, str(FUZZ))

# Load sig-cache for ROUTE lookup
_SIG_CACHE: dict | None = None
_CACHE_PATH = HERE.parent / "results" / "route_cells_full.json"
if _CACHE_PATH.exists():
    _SIG_CACHE = json.loads(_CACHE_PATH.read_text())

# Load IOB cell map to decide whether a given pin has a per-pin IOB
# cell set (normal I/O pads do; dedicated clock pads like PIN_E1 don't
# — they were excluded from the IOB sweep because GCLK_PIN handles
# their CRAM configuration directly).
_IOB_MAP: dict | None = None
_IOB_MAP_PATH = HERE.parent / "results" / "iob_cell_map.json"
if _IOB_MAP_PATH.exists():
    _IOB_MAP = json.loads(_IOB_MAP_PATH.read_text())


def _pin_has_iob_entry(pin_loc: str, direction: str) -> bool:
    """Return True if pin_loc (e.g. 'PIN_E1') has a per-pin IOB entry
    for the given direction ('input' or 'output')."""
    if _IOB_MAP is None:
        return True  # assume yes when map unavailable
    short = pin_loc[4:] if pin_loc.startswith("PIN_") else pin_loc
    key = "per_pin_input" if direction == "input" else "per_pin_output"
    return short in _IOB_MAP.get(key, {})


# IOB_CLK_INPUT is a hdr-band delta activating a dedicated clock-bank
# pin as a GCLK driver.  Currently 12 F17 pins are mined; GCLK_PIN
# paired with IOB_CLK_INPUT closes the nv-baseline hdr frame for
# IOB-driven DFF.CLK nets.  Missing entries fall through silently —
# designs that use a CLK pin outside this set still get GCLK_PIN but
# the hdr band may need a separate delta.
_IOB_CLK_PIN_SET: set[str] | None = None
_IOB_CLK_PIN_PATH = HERE.parent / "results" / "iob_clk_pin_hdr_cells.json"


def _pin_has_iob_clk_entry(pin_loc: str) -> bool:
    """True if pin_loc has an IOB_CLK_INPUT hdr-band delta mined."""
    global _IOB_CLK_PIN_SET
    if _IOB_CLK_PIN_SET is None:
        if _IOB_CLK_PIN_PATH.exists():
            data = json.loads(_IOB_CLK_PIN_PATH.read_text())
            _IOB_CLK_PIN_SET = set(data.get("cells", {}).keys())
        else:
            _IOB_CLK_PIN_SET = set()
    short = pin_loc[4:] if pin_loc.startswith("PIN_") else pin_loc
    return short in _IOB_CLK_PIN_SET


# IOB_ROUTE sig-cache — direct IOB-pad → SLICE.port routes.  When an
# IOB's `O` net drives a LUT input (or CE6_CARRY.A/.B), look up the
# (pin, dx, dy, dn, port) key here to decide whether to emit
# `IOB_ROUTE PIN_X -> X{dx}Y{dy}N{dn}.{port}` in place of the missing
# slice-driven ROUTE (the main ROUTE pass below only fires on SLICE
# drivers).
_IOB_ROUTE_KEYS: set[str] | None = None
_IOB_ROUTE_PATH = HERE.parent / "results" / "iob_to_slice_sigcache.json"


def _iob_route_available(pin_loc: str, dx: int, dy: int, dn: int,
                         port: str) -> bool:
    """True if the IOB→SLICE route is in the sig-cache (either
    absolute_cells or single_le_cells bucket — fasm2rbf's
    `_iob_route_cells` loader merges both)."""
    global _IOB_ROUTE_KEYS
    if _IOB_ROUTE_KEYS is None:
        if _IOB_ROUTE_PATH.exists():
            data = json.loads(_IOB_ROUTE_PATH.read_text())
            keys = set(data.get("absolute_cells", {}).keys())
            keys |= set(data.get("single_le_cells", {}).keys())
            _IOB_ROUTE_KEYS = keys
        else:
            _IOB_ROUTE_KEYS = set()
    short = pin_loc[4:] if pin_loc.startswith("PIN_") else pin_loc
    return f"IOB_{short}->{dx},{dy},{dn},{port}" in _IOB_ROUTE_KEYS

# I[n] index → Cyclone IV port name
_IDX_TO_PORT = {0: "dataa", 1: "datab", 2: "datac", 3: "datad"}


# ---------------------------------------------------------------------------
# M9K BRAM emission — STUB (TODO).
#
# Current status: the chipdb (`fuzz/chipdb_gen.py`) provides
# EP4CE6_M9K bels at (X∈{15,27}, Y∈[2..21], N=0) with an `anchor`
# attribute that feeds the `M9K.INIT_{w}x{d}` FASM directive.  The
# Yosys side (`synth/m9k.lib` + draft `\$__M9K_SP_` techmap rule in
# `synth/ep4ce6_map.v`) is also stubbed but gated behind a
# `M9K_TECHMAP` ifdef.  This emitter is the final piece: convert a
# placed EP4CE6_M9K cell in the routed JSON into an
# `X{x}Y{y}N{n}.INIT_{w}x{d} = 0x{hex}` line.
#
# Inputs expected when wired up:
#   - cell.type == "EP4CE6_M9K"
#   - cell.attributes.NEXTPNR_BEL == "M9K_X{x}_Y{y}_N0"
#   - cell.parameters.INIT (Yosys binary string, LSB-first)
#   - cell.parameters.WIDTH_A / DEPTH (or MODE for SDP/TDP demux)
#
# Blocker: the techmap rule and the nextpnr M9K BEL wire pips are
# not yet routable end-to-end. Until a tiny_ram design synthesizes
# through `synth_ep4ce6.sh` and places on an M9K bel, this code path
# is dead.  See `fuzz/test_np2fasm_m9k.py` for the xfail contract.
# ---------------------------------------------------------------------------


def _parse_yosys_int(val, default: int) -> int:
    """Yosys serializes scalar parameters as little-endian binary
    strings (e.g. '00000000000000000000000000010010' for 18). Tests
    sometimes pass plain ints. Accept both."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return default
        # Yosys-style binary string (only 0/1, ≥2 chars). int(s, 2) is
        # also valid for "0"/"1", but disambiguate from plain decimals.
        if all(c in "01" for c in s) and len(s) > 1:
            return int(s, 2)
        try:
            return int(s, 0)
        except ValueError:
            return default
    return default


def _parse_yosys_init(init_str: str, width: int, depth: int) -> list[int]:
    """Convert a Yosys `INIT` parameter (binary string, MSB-first as
    Yosys serializes parameters — word 0 is the LAST `width` chars)
    into the (word-LSB-first) list expected by the `INIT_{w}x{d}`
    FASM directive."""
    # Yosys param binary strings are MSB-first relative to bit index:
    # INIT[0] is the rightmost char.  Reverse to get LSB-first.
    total = width * depth
    cleaned = init_str.replace("_", "").strip()
    # Yosys uses 'x' / 'z' for don't-care bits — common when libmap
    # widens a user memory and the high bits of each cell-word are
    # unused. Treat them as 0 for INIT load (the bit is unused, so 0
    # is functionally safe and produces a deterministic FASM blob).
    if "x" in cleaned or "z" in cleaned or "X" in cleaned or "Z" in cleaned:
        cleaned = (cleaned
                   .replace("x", "0").replace("X", "0")
                   .replace("z", "0").replace("Z", "0"))
    # Pad / truncate to exact length
    if len(cleaned) < total:
        cleaned = "0" * (total - len(cleaned)) + cleaned
    elif len(cleaned) > total:
        cleaned = cleaned[-total:]
    # Reverse so index 0 = LSB
    bits = cleaned[::-1]
    mask = (1 << width) - 1
    words = []
    for i in range(depth):
        start = i * width
        chunk = bits[start:start + width]
        # chunk is LSB-first bit order now; reverse to parse as int
        val = int(chunk[::-1], 2) if chunk else 0
        words.append(val & mask)
    return words


def _emit_m9k_init(cell_name: str, cell: dict) -> tuple[str | None, str | None]:
    """Return (fasm_line, warning) for a placed EP4CE6_M9K cell.

    STUB — awaiting end-to-end M9K placement.  When active, emits:
        X{x}Y{y}N{n}.INIT_{width}x{depth} = 0x{hex_blob}
    using the cell's INIT parameter.  Returns (None, warning) when
    the cell isn't placed on a known M9K bel or when INIT is missing.
    """
    bel_str = cell.get("attributes", {}).get("NEXTPNR_BEL", "")
    m = re.match(r"M9K_X(\d+)_Y(\d+)_N(\d+)", bel_str)
    if not m:
        return (None, f"M9K cell {cell_name}: bel {bel_str!r} not an M9K site")
    x, y, n = int(m.group(1)), int(m.group(2)), int(m.group(3))

    params = cell.get("parameters", {})
    width = _parse_yosys_int(params.get("WIDTH_A", 9), default=9)
    depth = _parse_yosys_int(params.get("DEPTH", 512), default=512)
    init_str = params.get("INIT", "")
    if not init_str:
        # All-zero INIT — emit a zero blob (XOR no-op on zeroed baseline)
        words = [0] * depth
    else:
        words = _parse_yosys_init(init_str, width, depth)

    mask = (1 << width) - 1
    blob_int = 0
    for i, w in enumerate(words):
        blob_int |= (w & mask) << (i * width)
    hex_chars = (width * depth + 3) // 4
    hex_blob = f"{blob_int:0{hex_chars}x}"
    return (f"X{x}Y{y}N{n}.INIT_{width}x{depth} = 0x{hex_blob}", None)


def _emit_m9k_mode(cell_name: str, cell: dict) -> tuple[str | None, str | None]:
    """Return (fasm_line, warning) for the per-(site, W, D, template) enable.

    Pairs with `_emit_m9k_init`: same bel parse, same WIDTH_A/DEPTH
    extraction, but emits the `M9K_MODE_{w}x{d}_{template}` directive
    that flips the block-band cells `m9k_mode_bits.json` records for
    this site under the chosen template bucket.

    Template selection (HW flash 2026-04-17):

      Yosys's `$__M9K_SP_` techmap rule corresponds to inferred-RAM
      semantics on the Quartus side.  Stage C.1 empirical re-mine
      (`fuzz/m9k_mode_inferred_full_remine.py`) populated a
      `inferred_goldintersect` bucket = `inferred` ∩ Quartus smoke gold
      (38 cells, site-invariant across all 31 w=9 anchors).  Flashing
      that bucket at a w=9 site PASSed silicon (LED follows KEY2; see
      stage0_round2_flash_results.md 2026-04-17), so this helper emits
      with the explicit `_inferred_goldintersect` suffix — the one
      HW-validated bucket.

      w=18 sites currently lack any mined cells (5 anchors skipped
      due to pin F16 collision in the mining harness).  The helper
      returns a warning and no line in that case so the RAM still
      carries correct INIT data, matching the prior gated behaviour.

    Without this line the open-toolchain RBF carries valid INIT data
    but the silicon block remains in its "M9K idle" configuration, so
    HW would never read back the user pattern.
    """
    bel_str = cell.get("attributes", {}).get("NEXTPNR_BEL", "")
    m = re.match(r"M9K_X(\d+)_Y(\d+)_N(\d+)", bel_str)
    if not m:
        return (None, None)  # _emit_m9k_init already warns on this
    x, y, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
    params = cell.get("parameters", {})
    width = _parse_yosys_int(params.get("WIDTH_A", 9), default=9)
    depth = _parse_yosys_int(params.get("DEPTH", 512), default=512)
    if width != 9:
        return (
            None,
            f"cell {cell_name}: M9K_MODE emission skipped for "
            f"{width}x{depth} at X{x}Y{y}N{n} — only w=9 has a "
            f"silicon-validated `inferred_goldintersect` bucket "
            f"(HW 2026-04-17); rerun m9k_mode_inferred_full_remine.py "
            f"for other widths once the mining harness covers them.",
        )
    return (
        f"X{x}Y{y}N{n}.M9K_MODE_{width}x{depth}_inferred_goldintersect",
        None,
    )


def _parse_bel(bel_name: str) -> tuple[str, int, int, int] | None:
    """Parse 'SLICE_X3_Y19_N24' -> ('SLICE', 3, 19, 24)."""
    m = re.match(r"(SLICE|IOB|M9K)_X(\d+)_Y(\d+)_N(\d+)", bel_name)
    if not m:
        if bel_name.startswith("IOB_"):
            return ("IOB", 0, 0, 0)
        return None
    return (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))




def convert(
    routed_json: dict,
    baseline: str = "nv",
) -> tuple[list[str], list[str]]:
    """Convert routed JSON to (fasm_lines, warnings).

    baseline controls the header FASM line emitted to bridge the chosen
    base RBF into the frame every other directive assumes:
      "nv"   — caller will pass nv_zero_global.rbf as base_rbf.  No
               header directive (default, preserves legacy behaviour).
      "pure" — caller will pass make_pure_zero_rbf() as base_rbf.
               Emit `NV_BASELINE_PACK` at the top so the byte-exact
               equivalent of nv_zero_global is synthesised before any
               routing / IOB directive applies.
    """
    if baseline not in ("nv", "pure"):
        raise ValueError(
            f"convert(baseline={baseline!r}): must be 'nv' or 'pure'")
    fasm: list[str] = []
    warnings: list[str] = []
    if baseline == "pure":
        # Reproduce nv_zero_global on top of PURE_ZERO.  Everything else
        # in the emitted FASM (IOB_IN/OUT, ROUTE, GCLK_PIN, LAB_CLK_SEL,
        # LAB_CLK_SEL_LE) continues to assume the nv_zero_global frame,
        # which NV_BASELINE_PACK provides byte-exact.
        fasm.append("NV_BASELINE_PACK")

    modules = routed_json.get("modules", {})
    if not modules:
        warnings.append("ERROR: no modules in JSON")
        return fasm, warnings
    # Skip primitive blackbox modules that prims.v contributes — pick
    # the first module that actually contains placed cells (i.e. the
    # design top). When none is present, fall back to the first
    # module so empty-input error handling downstream still works.
    BLACKBOX_MODULES = {
        "CE6_CARRY", "DFF", "LUT", "GENERIC_SLICE", "GENERIC_IOB",
        "EP4CE6_M9K",
    }
    mod_name = next(
        (m for m in modules if m not in BLACKBOX_MODULES),
        next(iter(modules)),
    )
    mod = modules[mod_name]
    cells = mod.get("cells", {})
    nets = mod.get("netnames", {})

    # Build bel placement map: cell_name -> (kind, x, y, n)
    cell_bel: dict[str, tuple[str, int, int, int]] = {}
    for cell_name, cell in cells.items():
        bel_str = cell.get("attributes", {}).get("NEXTPNR_BEL", "")
        bel = _parse_bel(bel_str)
        if bel:
            cell_bel[cell_name] = bel

    # Pre-compute CE6_CARRY cell set for chain analysis.
    carry_cells = {n: c for n, c in cells.items()
                   if c.get("type") == "CE6_CARRY"}

    # --- Build net driver/sink index up-front ---
    # Needed BEFORE the cell iteration so the IOB emission pass can
    # identify clock-driving IOBs (whose only sinks are DFF.CLK) and
    # skip IOB_IN emission for them — clock pads aren't in
    # iob_cell_map.json (the IOB sweep excluded clock pins) and
    # GCLK_PIN already handles clock-pad CRAM configuration.
    bit_driver: dict[int, tuple[str, str]] = {}   # bit_id → (cell_name, port)
    bit_sinks: dict[int, list[tuple[str, str, int]]] = {}  # bit_id → [(cell, port, idx)]

    # Blackbox cells (CE6_CARRY, LUT, DFF) from prims.v don't always carry
    # port_directions in the JSON. Hardcode them so the net walker
    # can distinguish drivers from sinks.
    _BLACKBOX_DIRS = {
        "CE6_CARRY": {"A": "input", "B": "input", "CI": "input",
                       "S": "output", "CO": "output"},
        "LUT":       {"I": "input", "Q": "output"},
        "DFF":       {"CLK": "input", "D": "input", "Q": "output"},
    }

    for _cn, _c in cells.items():
        _ct = _c.get("type", "")
        _conns = _c.get("connections", {})
        _dirs = _c.get("port_directions", {})
        if not _dirs and _ct in _BLACKBOX_DIRS:
            _dirs = _BLACKBOX_DIRS[_ct]
        for _port, _port_bits in _conns.items():
            if _ct == "CE6_CARRY" and _port in ("CI", "CO"):
                continue
            _d = _dirs.get(_port, "")
            for _idx, _bit_id in enumerate(_port_bits):
                if isinstance(_bit_id, str):
                    continue
                if _d == "output":
                    bit_driver[_bit_id] = (_cn, _port)
                elif _d == "input":
                    bit_sinks.setdefault(_bit_id, []).append(
                        (_cn, _port, _idx))

    # Identify IOB cells that drive ONLY DFF.CLK sinks. For these we
    # MAY want to suppress IOB_IN — but only if the pin has no entry
    # in iob_cell_map.json (dedicated clock pads like E1). Normal I/O
    # pads used as clocks still need IOB_IN so the pad buffer stays
    # enabled.
    clock_only_iobs: set[str] = set()
    for cell_name, cell in cells.items():
        if cell.get("type") != "GENERIC_IOB":
            continue
        conns = cell.get("connections", {})
        o_bits = conns.get("O", [])
        if not o_bits or isinstance(o_bits[0], str):
            continue
        net_bit = o_bits[0]
        sinks = bit_sinks.get(net_bit, [])
        if not sinks:
            continue
        if all(
            cells.get(sc, {}).get("type") in ("DFF", "$_DFF_P_")
            and sp == "CLK"
            for sc, sp, _ in sinks
        ):
            clock_only_iobs.add(cell_name)

    # --- LUT / LUT_ARITH / DFF directives from cells ---
    has_dff = False
    dff_les: set[tuple[int, int, int]] = set()
    # Tracks whether any IOB_IN / IOB_OUT was emitted — determines if we
    # also need IOB_BASELINE_NV to bridge the nv_zero_global base into
    # the iob_in_E15 frame that IOB pair-deltas assume.
    iob_emitted = False
    # IOB_ROUTE lines queued during the cell pass — appended after the
    # main IOB block so per-pin IOB_IN and its IOB_ROUTE drives stay
    # adjacent in the FASM output.
    iob_routes: list[tuple[str, int, int, int, str]] = []  # (pin_loc, dx, dy, dn, port)
    iob_route_missing: list[tuple[str, int, int, int, str]] = []  # for warnings
    for cell_name, cell in cells.items():
        bel = cell_bel.get(cell_name)
        if bel is None:
            continue
        kind, x, y, n = bel
        ctype = cell.get("type", "")
        params = cell.get("parameters", {})

        if kind == "SLICE" and ctype == "CE6_CARRY":
            # Arith-mode LUT SRAM = 0x0000 for standard carry-chain
            # operations (+1, +, -). The block-band cells configure
            # dedicated XOR/AND circuitry that implements the adder
            # function independently of LUT SRAM content. Quartus
            # uses 0x0000 for all arith LEs (HW-verified 2026-04-13).
            fasm.append(f"X{x}Y{y}N{n}.LUT_ARITH = 0x0000")
        elif kind == "SLICE" and ctype in ("DFF", "$_DFF_P_"):
            # Yosys-level DFF cell placed on its own SLICE bel. In
            # Cyclone IV the FF lives inside the LE alongside the
            # LCCOMB/arith combinational part, so the DFF bel and the
            # matching LUT/CE6_CARRY bel should share the same (x,y,n).
            fasm.append(f"X{x}Y{y}N{n}.DFF")
            has_dff = True
            dff_les.add((x, y, n))
        elif kind == "SLICE":
            # Plain LUT (packed GENERIC_SLICE with INIT + FF_USED).
            init_bin = params.get("INIT", "")
            if init_bin:
                mask = int(init_bin, 2)
                if mask != 0:
                    fasm.append(f"X{x}Y{y}N{n}.LUT = 0x{mask:04x}")
            ff_bin = params.get("FF_USED", "0")
            if int(ff_bin, 2):
                fasm.append(f"X{x}Y{y}N{n}.DFF")
                has_dff = True
                dff_les.add((x, y, n))
        elif kind == "IOB":
            # Bel name format: "IOB_{logical}_{PIN_LOC}", e.g. IOB_B_PIN_M16.
            # Direction: in chipdb_gen.py the BEL's "O" pin is an output from
            # the BEL into the fabric (input pad path), and the "I" pin is an
            # input to the BEL from the fabric (output pad path). So:
            #   - cell drives "O" port → IOB is configured as INPUT (pad→fabric)
            #   - cell receives on "I" port → IOB is OUTPUT (fabric→pad)
            bel_str = cell.get("attributes", {}).get("NEXTPNR_BEL", "")
            m = re.match(r"IOB_[A-Za-z0-9]+_(PIN_[A-Z]\d+)", bel_str)
            if not m:
                warnings.append(
                    f"cell {cell_name}: IOB BEL name {bel_str!r} "
                    f"doesn't match IOB_<name>_PIN_<loc>; skipped"
                )
                continue
            pin_loc = m.group(1)  # already includes "PIN_" prefix
            conns = cell.get("connections", {})
            dirs = cell.get("port_directions", {})
            has_O = bool(conns.get("O"))
            has_I = bool(conns.get("I"))
            # Dedicated clock pads (e.g. PIN_E1) aren't in
            # iob_cell_map.json because the IOB sweep excluded them —
            # GCLK_PIN handles their CRAM directly. For clock-only IOBs
            # whose pin lacks an IOB entry, silently suppress the
            # IOB_IN/IOB_OUT directive (it would fail bitgen lookup).
            clock_only = cell_name in clock_only_iobs
            if has_O and not has_I:
                if clock_only and not _pin_has_iob_entry(pin_loc, "input"):
                    pass  # clock pad — GCLK_PIN covers it
                else:
                    fasm.append(f"IOB_IN {pin_loc}")
                    iob_emitted = True
            elif has_I and not has_O:
                fasm.append(f"IOB_OUT {pin_loc}")
                iob_emitted = True
            elif has_O and has_I:
                # Bidirectional — emit BIDIR-variant directives so fasm2rbf
                # dispatches to per_pin_input/per_pin_output (cells unique
                # to this pin) instead of input_delta/output_delta (XOR
                # diff vs E15/G15 anchor, which double-flips anchor cells
                # when multiple IOBs compose).  See
                # iob_in_out_r5_composition_falsified.md — the legacy
                # IOB_IN/IOB_OUT path trips the safety gate at Stage
                # B-narrow (sdram_dq).  The BIDIR variants are gated
                # by per-pin falsified masks in fasm2rbf._iob_delta_cells.
                warnings.append(
                    f"cell {cell_name}: IOB on {pin_loc} is bidirectional; "
                    f"emitting IOB_IN_BIDIR + IOB_OUT_BIDIR"
                )
                fasm.append(f"IOB_IN_BIDIR {pin_loc}")
                fasm.append(f"IOB_OUT_BIDIR {pin_loc}")
                iob_emitted = True
            else:
                # No connections — likely an unused IOB BEL placeholder.
                warnings.append(
                    f"cell {cell_name}: IOB on {pin_loc} has no I/O "
                    f"connections; no FASM emitted"
                )
        elif kind == "M9K":
            # Placed EP4CE6_M9K — emit INIT directive + M9K_MODE per-site
            # enable.  The MODE suffix is always `_inferred_goldintersect`
            # (HW-validated 2026-04-17 at a w=9 site); w=18 sites warn
            # and skip until the `inferred_goldintersect` bucket covers
            # them.  See stage0_round2_flash_results.md and
            # m9k_mode_template_residual.md for the closure history.
            line, warn = _emit_m9k_init(cell_name, cell)
            if line is not None:
                fasm.append(line)
            if warn is not None:
                warnings.append(warn)
            mode_line, mode_warn = _emit_m9k_mode(cell_name, cell)
            if mode_line is not None:
                fasm.append(mode_line)
            if mode_warn is not None:
                warnings.append(mode_warn)

    # --- Carry chain analysis ---
    # Walk every CE6_CARRY whose CI is a Verilog constant — that's a
    # chain start. For each start, follow CO→CI until the chain ends
    # (either last cell or CO unconsumed), verify the bels are on
    # contiguous N slots (intra-LAB N→N+2 or N30→next LAB N0), and
    # emit a placeholder FASM comment for the chain-start CRAM bit
    # (the bit itself is a separate mining campaign — a $add vs
    # $sub diff is the planned experiment).
    #
    # Mid-chain CI connections use the dedicated silicon carry pip
    # in nextpnr's chipdb — no LI-MUX routing needed, and explicitly
    # skipped from the ROUTE pass below.
    if carry_cells:
        # bit_id -> cell_name whose CO drives it
        co_driver: dict[int, str] = {}
        for name, cell in carry_cells.items():
            co = cell.get("connections", {}).get("CO", [])
            if len(co) == 1 and not isinstance(co[0], str):
                co_driver[co[0]] = name

        def _ci_info(cell: dict) -> tuple[str, int | None]:
            ci = cell.get("connections", {}).get("CI", [])
            if len(ci) != 1:
                return ("unknown", None)
            v = ci[0]
            if isinstance(v, str):
                return ("const", int(v) if v in ("0", "1") else None)
            return ("net", v)

        # Find chain starts (constant CI)
        visited: set[str] = set()
        for start_name, start_cell in carry_cells.items():
            kind, val = _ci_info(start_cell)
            if kind != "const" or val is None:
                continue
            # Walk the chain from this start
            chain: list[str] = []
            cur = start_name
            while cur and cur not in visited:
                visited.add(cur)
                chain.append(cur)
                cell = carry_cells[cur]
                co = cell.get("connections", {}).get("CO", [])
                if len(co) != 1 or isinstance(co[0], str):
                    break
                co_net = co[0]
                # Next cell is the one whose CI == co_net
                nxt = None
                for n2, c2 in carry_cells.items():
                    if n2 in visited:
                        continue
                    k2, v2 = _ci_info(c2)
                    if k2 == "net" and v2 == co_net:
                        nxt = n2
                        break
                cur = nxt
            # Report the chain
            start_bel = cell_bel.get(chain[0])
            end_bel = cell_bel.get(chain[-1])
            warnings.append(
                f"chain: {len(chain)} cells, CI={val}, "
                f"start={start_bel}, end={end_bel}")
            if start_bel:
                _, sx, sy, sn = start_bel
                fasm.append(
                    f"# CHAIN_START X{sx}Y{sy}N{sn} CI={val}"
                    f"  (chain length {len(chain)}; "
                    f"chain-start CRAM bit not yet mined)")
            # Verify N-contiguity on the chain's placed bels
            placed = [cell_bel.get(c) for c in chain]
            if all(b and b[0] == "SLICE" for b in placed):
                for i in range(len(placed) - 1):
                    _, ax, ay, an = placed[i]
                    _, bx, by, bn = placed[i + 1]
                    ok = False
                    if (ax, ay) == (bx, by) and bn == an + 2:
                        ok = True            # within-LAB chain step
                    elif ax == bx and ay == by + 1 and an == 30 and bn == 0:
                        ok = True            # between-LAB N30→N0
                    if not ok:
                        warnings.append(
                            f"chain discontinuity: "
                            f"{chain[i]}@{placed[i]} → "
                            f"{chain[i + 1]}@{placed[i + 1]}")

        # Any CE6_CARRY not touched by a forward walk: orphan / cascaded
        for name in carry_cells:
            if name not in visited:
                warnings.append(
                    f"carry cell {name} not reached from any chain start "
                    f"(cascaded CI not supported)")

    # --- ROUTE directives from logical connectivity ---
    # bit_driver / bit_sinks were built up-front (see above) so the IOB
    # emission pass could identify clock-only IOBs.

    # --- GCLK pipeline: GCLK_PIN (per-pin one-hot activate) + per-LAB
    # LAB_CLK_SEL (per-LAB clock-select XOR delta). ---
    #
    # For every DFF / CE6_CARRY cell that has a CLK/clock net, walk the
    # net back to its IOB driver and collect the pin location. Each
    # distinct IOB gets a `GCLK_PIN` directive; each distinct LAB that
    # contains a clocked LE gets a `LAB_CLK_SEL` directive.
    #
    # Falls back to legacy `GCLK` only when:
    #   - has_dff is True AND
    #   - no CLK net resolves to an IOB driver (e.g. on designs routed
    #     through non-IOB paths, or tests built without IOB cells).
    # This path exists so pre-GCLK_PIN test artifacts keep working.
    gclk_pins: list[str] = []
    lab_clk_sels: list[tuple[int, int]] = []
    lab_clk_sel_les: list[tuple[int, int, int]] = []
    unresolved_clk = False
    if has_dff or any(
            cells[c].get("type") == "CE6_CARRY" for c in cells):
        seen_pins: set[str] = set()
        seen_labs: set[tuple[int, int]] = set()
        seen_les: set[tuple[int, int, int]] = set()
        for cell_name, cell in cells.items():
            ctype = cell.get("type", "")
            # Which port carries the clock on this cell type?
            clk_port = None
            if ctype in ("DFF", "$_DFF_P_"):
                clk_port = "CLK"
            # CE6_CARRY is combinational — no CLK port — but its
            # sibling DFF (if any) in the same LE provides the clock.
            if clk_port is None:
                continue
            conns = cell.get("connections", {}).get(clk_port, [])
            if len(conns) != 1 or isinstance(conns[0], str):
                continue
            clk_bit = conns[0]
            drv = bit_driver.get(clk_bit)
            if drv is None:
                unresolved_clk = True
                continue
            drv_cell_name, drv_port = drv
            drv_cell = cells.get(drv_cell_name, {})
            if drv_cell.get("type") != "GENERIC_IOB":
                unresolved_clk = True
                continue
            bel_str = drv_cell.get("attributes", {}).get(
                "NEXTPNR_BEL", "")
            m = re.match(
                r"IOB_[A-Za-z0-9]+_(PIN_[A-Z]\d+)", bel_str)
            if not m:
                unresolved_clk = True
                continue
            pin_loc = m.group(1)
            if pin_loc not in seen_pins:
                seen_pins.add(pin_loc)
                gclk_pins.append(pin_loc)

            sink_bel = cell_bel.get(cell_name)
            if sink_bel and sink_bel[0] == "SLICE":
                _, sx, sy, sn = sink_bel
                if (sx, sy) not in seen_labs:
                    seen_labs.add((sx, sy))
                    lab_clk_sels.append((sx, sy))
                # Per-LE layer. HW verified 2026-04-14: the N-invariant
                # LAB_CLK_SEL alone is insufficient — per-LE clock
                # routing cells (N-specific) must also flip.
                if (sx, sy, sn) not in seen_les:
                    seen_les.add((sx, sy, sn))
                    lab_clk_sel_les.append((sx, sy, sn))

        # Emit resolved directives. GCLK_PIN activates the per-pin
        # fabric-side one-hot; IOB_CLK_INPUT activates the matching
        # hdr-band pad-side clock driver (12 F17 pins mined).  Pins
        # without an IOB_CLK_INPUT entry still get GCLK_PIN alone.
        for pin_loc in gclk_pins:
            fasm.append(f"GCLK_PIN {pin_loc}")
            if _pin_has_iob_clk_entry(pin_loc):
                fasm.append(f"IOB_CLK_INPUT {pin_loc}")
            else:
                warnings.append(
                    f"GCLK_PIN {pin_loc} emitted without matching "
                    f"IOB_CLK_INPUT (pin not in iob_clk_pin_hdr_cells.json)"
                )
        for (x, y) in lab_clk_sels:
            fasm.append(f"LAB_CLK_SEL X{x}Y{y}")
        for (x, y, n) in lab_clk_sel_les:
            fasm.append(f"LAB_CLK_SEL_LE X{x}Y{y}N{n}")

        # Fallback: legacy 17-cell local-clock directive only when we
        # couldn't resolve any clock pin. Downstream bitgen still
        # depends on the `nv_zero_global.rbf` base in that case.
        if has_dff and not gclk_pins:
            fasm.append("GCLK")
            warnings.append(
                "no IOB driver found for any DFF.CLK net — "
                "falling back to legacy GCLK (requires nv_zero_global base)")
        elif unresolved_clk:
            warnings.append(
                "some DFF.CLK nets did not resolve to an IOB driver; "
                "emitted GCLK_PIN/LAB_CLK_SEL for the ones that did")

    n_sig = 0
    n_miss = 0
    n_skip = 0
    n_iob_route = 0
    n_iob_route_miss = 0
    seen_routes: set[str] = set()
    seen_iob_routes: set[tuple[str, int, int, int, str]] = set()
    route_srcs: set[tuple[int, int]] = set()

    def _sink_port_name(sink_cell, sink_port, sink_idx):
        sink_ctype = cells[sink_cell].get("type", "")
        if sink_ctype == "CE6_CARRY":
            return {"A": "dataa", "B": "datab"}.get(sink_port)
        return _IDX_TO_PORT.get(sink_idx)

    for bit_id, (drv_cell, drv_port) in bit_driver.items():
        drv_bel = cell_bel.get(drv_cell)
        if drv_bel is None:
            continue

        # IOB driver — candidate for IOB_ROUTE.  The net's "O" output
        # of a GENERIC_IOB becomes a direct pad → SLICE.port drive.
        # Skip CLK-only IOBs: those are handled by GCLK_PIN +
        # IOB_CLK_INPUT, no IOB_ROUTE sig-cache entry exists.
        if drv_bel[0] == "IOB":
            drv_cell_obj = cells.get(drv_cell, {})
            if drv_cell_obj.get("type") != "GENERIC_IOB":
                continue
            if drv_cell in clock_only_iobs:
                continue
            bel_str = drv_cell_obj.get("attributes", {}).get(
                "NEXTPNR_BEL", "")
            m = re.match(r"IOB_[A-Za-z0-9]+_(PIN_[A-Z]\d+)", bel_str)
            if not m:
                continue
            pin_loc = m.group(1)
            for sink_cell, sink_port, sink_idx in bit_sinks.get(bit_id, []):
                sink_bel = cell_bel.get(sink_cell)
                if sink_bel is None or sink_bel[0] != "SLICE":
                    continue
                _, dx, dy, dn = sink_bel
                port_name = _sink_port_name(sink_cell, sink_port, sink_idx)
                if port_name is None:
                    continue
                tup = (pin_loc, dx, dy, dn, port_name)
                if tup in seen_iob_routes:
                    continue
                seen_iob_routes.add(tup)
                if _iob_route_available(pin_loc, dx, dy, dn, port_name):
                    iob_routes.append(tup)
                    n_iob_route += 1
                else:
                    iob_route_missing.append(tup)
                    n_iob_route_miss += 1
                    warnings.append(
                        f"no iob_to_slice sig-cache: "
                        f"IOB_{pin_loc[4:]}->{dx},{dy},{dn},{port_name}")
            continue

        if drv_bel[0] != "SLICE":
            continue
        _, sx, sy, sn = drv_bel

        for sink_cell, sink_port, sink_idx in bit_sinks.get(bit_id, []):
            sink_bel = cell_bel.get(sink_cell)
            if sink_bel is None or sink_bel[0] != "SLICE":
                n_skip += 1
                continue
            _, dx, dy, dn = sink_bel

            # Intra-LE path: any connection within the same (x,y,n)
            # is LE-internal and needs no ROUTE. This covers:
            #   - LUT/CARRY → DFF (combinational output to register)
            #   - DFF.Q → CARRY input (LE-internal feedback in arith
            #     mode — Quartus carry counters have 0 external routes)
            if (sx, sy, sn) == (dx, dy, dn):
                continue

            # Map sink port to Cyclone IV input name. CE6_CARRY uses
            # named single-bit ports (A→dataa, B→datab); plain SLICE
            # LUT uses a 4-bit I[] vector indexed 0..3.
            port_name = _sink_port_name(sink_cell, sink_port, sink_idx)
            if port_name is None:
                n_skip += 1
                continue

            # Sig-cache lookup
            key = f"{sx},{sy},{sn}->{dx},{dy},{dn},{port_name}"
            if key in seen_routes:
                continue  # dedup
            seen_routes.add(key)

            fasm.append(
                f"ROUTE X{sx}Y{sy}N{sn} -> "
                f"X{dx}Y{dy}N{dn}.{port_name}")
            route_srcs.add((sx, sy))
            if _SIG_CACHE and key in _SIG_CACHE:
                n_sig += 1
            else:
                n_miss += 1
                warnings.append(f"no sig-cache: {key}")

    # Emit IOB_ROUTE lines after the main ROUTE block for readability.
    for (pin_loc, dx, dy, dn, port_name) in iob_routes:
        fasm.append(
            f"IOB_ROUTE {pin_loc} -> X{dx}Y{dy}N{dn}.{port_name}"
        )

    # Emit SRC X{x}Y{y} once per unique LAB that sourced any SLICE→SLICE
    # ROUTE.  SRC lines add per-source overhead that fasm2rbf unions
    # with route cells before XOR-flipping (protects against the
    # double-flip footgun documented in feedback_fasm_xor_doubleflip.md).
    for (sx, sy) in sorted(route_srcs):
        fasm.append(f"SRC X{sx}Y{sy}")

    # IOB_BASELINE_NV: bridge hdr band from nv_zero_global → iob_in_E15
    # so IOB_IN / IOB_OUT pair-deltas land correctly.  Boolean,
    # idempotent, and required whenever any IOB direction directive is
    # emitted; IOB_ROUTE cells are already in the nv frame so they
    # don't need the bridge on their own.
    if iob_emitted:
        # Place right after NV_BASELINE_PACK if present, else at the top.
        insert_at = 1 if (fasm and fasm[0] == "NV_BASELINE_PACK") else 0
        fasm.insert(insert_at, "IOB_BASELINE_NV")

    warnings.insert(0,
        f"# {n_sig} ROUTE (FASM-backed), {n_miss} missing, "
        f"{n_skip} skipped (non-slice/CLK); "
        f"{n_iob_route} IOB_ROUTE, {n_iob_route_miss} IOB_ROUTE missing")

    return fasm, warnings


def main() -> None:
    # Very small CLI: [--base nv|pure] <routed.json> [output.fasm]
    argv = list(sys.argv[1:])
    baseline = "nv"
    if argv and argv[0] == "--base":
        if len(argv) < 2 or argv[1] not in ("nv", "pure"):
            print("--base expects 'nv' or 'pure'", file=sys.stderr)
            sys.exit(1)
        baseline = argv[1]
        argv = argv[2:]

    if len(argv) < 1:
        print(
            f"Usage: {sys.argv[0]} [--base nv|pure] "
            f"<routed.json> [output.fasm]\n"
            f"  --base pure  emit NV_BASELINE_PACK header so caller can\n"
            f"               pass make_pure_zero_rbf() as base_rbf;\n"
            f"               default nv assumes nv_zero_global.rbf base.",
            file=sys.stderr,
        )
        sys.exit(1)

    routed = json.loads(Path(argv[0]).read_text())
    fasm_lines, warnings = convert(routed, baseline=baseline)

    out = sys.stdout
    if len(argv) >= 2:
        out = open(argv[1], "w")

    out.write("# Auto-generated by np2fasm.py\n")
    for w in warnings:
        out.write(f"# WARN: {w}\n")
    out.write("\n")
    for line in fasm_lines:
        out.write(line + "\n")

    if out is not sys.stdout:
        out.close()
        print(f"Wrote {len(fasm_lines)} FASM lines to {argv[1]}",
              file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
