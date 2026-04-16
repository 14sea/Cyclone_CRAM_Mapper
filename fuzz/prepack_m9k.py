#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 — pre-pack BEL pinning for EP4CE6_M9K cells.

nextpnr-generic doesn't model the M9K BRAM placer cleanly (the chipdb
M9K bels carry routable pips but the generic packer can't infer
placement from a memory cell). This script reads a post-Yosys JSON,
finds every ``EP4CE6_M9K`` cell, and stamps it with an explicit
``NEXTPNR_BEL`` attribute drawn from the calibrated
``M9K_INIT_ANCHORS`` table (so np2fasm can later emit
``X{x}Y{y}N{n}.INIT_{w}x{d} = 0x...``).

The annotated JSON is consumed *directly* by ``np2fasm.py`` —
nextpnr-generic is skipped for the M9K-only path because its built-in
packer doesn't know how to route the M9K data buses to the fabric.

Site selection
--------------
Sites are drawn (in order) from those entries in
``M9K_INIT_ANCHORS`` whose ``(WIDTH, DEPTH)`` match the cell's
``(WIDTH_A, DEPTH)`` parameters. If the user passes ``--sites
S1,S2,...`` on the command line, that ordered list overrides the
default ascending pass.

Usage
-----
::

    python3 fuzz/prepack_m9k.py ram_post_techmap.json ram_placed.json
    python3 fuzz/prepack_m9k.py --sites X15_Y10_N0,X15_Y11_N0,...        ram.json ram_placed.json

If a chain doesn't fit (more cells than calibrated sites at the
required (W, D)), the script bails with a clear error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from m9k_init_basis import M9K_INIT_ANCHORS


_BEL_RE = re.compile(r"M9K_X(\d+)_Y(\d+)_N(\d+)")


def _yosys_int(val) -> int | None:
    """Yosys serializes parameters as little-endian binary strings."""
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return int(s, 2)
        except ValueError:
            try:
                return int(s, 0)
            except ValueError:
                return None
    return None


def _candidate_sites(width: int, depth: int) -> list[str]:
    """Sorted list of calibrated sites supporting (width, depth)."""
    return sorted(
        site for (site, w, d) in M9K_INIT_ANCHORS
        if w == width and d == depth
    )


def _parse_sites_arg(arg: str | None) -> list[str] | None:
    if not arg:
        return None
    sites = [s.strip() for s in arg.split(",") if s.strip()]
    bad = [s for s in sites if not _BEL_RE.match(s)]
    if bad:
        raise SystemExit(f"--sites: malformed entries {bad!r}")
    return sites


def prepack(design: dict, sites_override: list[str] | None
            ) -> tuple[dict, list[str]]:
    """Stamp NEXTPNR_BEL on every EP4CE6_M9K. Returns (design, warns)."""
    warns: list[str] = []

    modules = design.get("modules", {})
    BLACKBOX = {"CE6_CARRY", "DFF", "LUT", "GENERIC_SLICE",
                "GENERIC_IOB", "EP4CE6_M9K"}
    mod_name = next(
        (m for m in modules if m not in BLACKBOX),
        next(iter(modules), None),
    )
    if mod_name is None:
        warns.append("ERROR: no modules in JSON")
        return design, warns

    cells = modules[mod_name]["cells"]
    m9k_cells = [
        (name, cell) for name, cell in cells.items()
        if cell.get("type") == "EP4CE6_M9K"
    ]
    if not m9k_cells:
        warns.append("no EP4CE6_M9K cells found — nothing to pre-pack")
        return design, warns

    # Group cells by (WIDTH_A, DEPTH) — every cell in the same group
    # consumes a calibrated anchor at that (W, D).
    by_geom: dict[tuple[int, int], list[tuple[str, dict]]] = {}
    for name, cell in m9k_cells:
        params = cell.get("parameters", {})
        w = _yosys_int(params.get("WIDTH_A", 9))
        d = _yosys_int(params.get("DEPTH", 512))
        if w is None or d is None:
            warns.append(f"cell {name}: cannot parse WIDTH_A/DEPTH")
            continue
        by_geom.setdefault((w, d), []).append((name, cell))

    used_sites: set[str] = set()
    for (w, d), group in by_geom.items():
        if sites_override is not None:
            available = [s for s in sites_override if s not in used_sites]
        else:
            available = [
                s for s in _candidate_sites(w, d) if s not in used_sites
            ]
        if len(available) < len(group):
            warns.append(
                f"ERROR: {len(group)} EP4CE6_M9K cells at width={w} "
                f"depth={d} need anchors but only {len(available)} "
                f"calibrated sites left "
                f"(known: {_candidate_sites(w, d)})"
            )
            continue
        # Sort cells by name so the assignment is deterministic across runs.
        for (name, cell), site in zip(sorted(group), available):
            cell.setdefault("attributes", {})[
                "NEXTPNR_BEL"] = f"M9K_{site}"
            used_sites.add(site)

    return design, warns


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_json")
    ap.add_argument("output_json")
    ap.add_argument(
        "--sites",
        help="comma-separated ordered site list "
             "(e.g. X15_Y10_N0,X15_Y11_N0). Default: ascending pass over "
             "calibrated anchors at the matching (W, D).",
    )
    args = ap.parse_args(argv[1:])

    sites_override = _parse_sites_arg(args.sites)

    design = json.loads(Path(args.input_json).read_text())
    design, warns = prepack(design, sites_override)
    for w in warns:
        print(f"# {w}", file=sys.stderr)
    Path(args.output_json).write_text(json.dumps(design, indent=2))
    has_error = any(w.startswith("ERROR") for w in warns)
    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
