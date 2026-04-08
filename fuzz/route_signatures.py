# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and query a routing-signature lookup table.

For every lits_pair_*.rbf in the corpus, compute the CRAM cell set
(XOR diff vs that island's lits_zero baseline) and key it by a
deterministic frozenset. Lets rbf2fasm match an arbitrary RBF's cell
set against known single-route signatures and emit a high-level ROUTE
directive instead of a pile of BIT lines.
"""
import os
import re
import sys
import json
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import (
    CRC_PREAMBLE,
    CRC_FRAME_SIZE,
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_LAST_FRAME,
)

ROOT = Path(HERE).parent
RBF = ROOT / "results" / "rbf"
TABLE_PATH = ROOT / "results" / "route_signatures.json"
CELLS_PATH = ROOT / "results" / "route_cells.json"
CELLS_CONSOLIDATED_PATH = ROOT / "results" / "route_cells_consolidated.json"

NAME_RE = re.compile(
    r"lits_pair_X(\d+)Y(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf$"
)


def _diff_cells(target, zero):
    cells = []
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for off in range(s, s + CRC_DATA_SIZE):
            x = target[off] ^ zero[off]
            if not x:
                continue
            for bp in range(8):
                if (x >> bp) & 1:
                    cells.append((off, bp))
    return frozenset(cells)


def _sig_key(cells):
    """Stable string key for a cell set, suitable for JSON."""
    return "|".join(f"{o:x}:{b}" for o, b in sorted(cells))


def _route_key(sx, sy, dx, dy, dn, port):
    return f"{sx},{sy}->{dx},{dy},{dn},{port}"


def build(verbose=True):
    """Walk the corpus and return (sig_table, cells_table).

    sig_table: {sig_key: {src, dst, n_cells}}  — cell-set → route identity
    cells_table: {route_key: [[off,bp], ...]}  — route identity → cell list
    """
    islands = {}
    for p in RBF.glob("lits_pair_*.rbf"):
        m = NAME_RE.match(p.name)
        if not m:
            continue
        sx, sy = int(m[1]), int(m[2])
        islands.setdefault((sx, sy), []).append(p)

    sig_table = {}
    cells_table = {}
    collisions = 0
    for (sx, sy), rbfs in sorted(islands.items()):
        zpath = RBF / f"lits_zero_{sx}_{sy}.rbf"
        if not zpath.exists():
            continue
        zero = zpath.read_bytes()
        for p in sorted(rbfs):
            m = NAME_RE.match(p.name)
            dx, dy, dn, port = int(m[3]), int(m[4]), int(m[5]), m[6]
            cells = _diff_cells(p.read_bytes(), zero)
            key = _sig_key(cells)
            entry = {
                "sx": sx, "sy": sy,
                "dx": dx, "dy": dy, "dn": dn, "port": port,
                "n_cells": len(cells),
            }
            if key in sig_table and sig_table[key] != entry:
                collisions += 1
            sig_table[key] = entry
            cells_table[_route_key(sx, sy, dx, dy, dn, port)] = sorted(
                [o, b] for o, b in cells
            )
        if verbose:
            print(f"  ({sx:2d},{sy:2d}) {len(rbfs)} routes")

    if verbose:
        print(
            f"built {len(sig_table)} sig / {len(cells_table)} cells "
            f"entries, {collisions} collisions"
        )
    return sig_table, cells_table


_CELLS_CACHE = {}


def _expand_consolidated(raw):
    """Expand {src,dst,dn: {common, port_delta: {p: [...]}}} into the
    flat {route_key: [(o,b),...]} form, unioning common ∪ port_delta[p].
    Semantic invariant self-tested 1725/1725 against route_cells.json.
    """
    out = {}
    for key, grp in raw.items():
        common = [tuple(c) for c in grp["common"]]
        for port, delta in grp["port_delta"].items():
            cells = common + [tuple(c) for c in delta]
            out[f"{key},{port}"] = sorted(set(cells))
    return out


def load_cells(path=CELLS_PATH):
    key = str(path)
    if key in _CELLS_CACHE:
        return _CELLS_CACHE[key]
    # Prefer consolidated form when the default path is requested and
    # the consolidated file is present — 34% file / 37% cell savings,
    # identical semantic content (self-tested invariant:
    # common ∪ port_delta[p] == route_cells.json[key+",p"]).
    if path == CELLS_PATH and CELLS_CONSOLIDATED_PATH.exists():
        raw = json.loads(CELLS_CONSOLIDATED_PATH.read_text())
        parsed = _expand_consolidated(raw)
        _CELLS_CACHE[key] = parsed
        return parsed
    if not path.exists():
        _CELLS_CACHE[key] = None
        return None
    raw = json.loads(path.read_text())
    parsed = {k: [(o, b) for o, b in v] for k, v in raw.items()}
    _CELLS_CACHE[key] = parsed
    return parsed


def save(table, path=TABLE_PATH):
    path.write_text(json.dumps(table, indent=1))


def load(path=TABLE_PATH):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def lookup(table, cells):
    """Return (entry, None) if the cell set matches a known route exactly,
    else (None, residue) where residue is the caller's cell set unchanged.
    Future work: subset/decomposition match for multi-route RBFs."""
    key = _sig_key(cells)
    if key in table:
        return table[key], None
    return None, frozenset(cells)


def main():
    sig, cells = build()
    save(sig)
    CELLS_PATH.write_text(json.dumps(cells))
    print(f"wrote {TABLE_PATH}")
    print(f"wrote {CELLS_PATH}")


if __name__ == "__main__":
    main()
