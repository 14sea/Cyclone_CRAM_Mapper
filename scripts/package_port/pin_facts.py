#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reduce a Quartus .pin report to a facts-only package pin table (CSV).

The raw .pin is a Quartus output file carrying Intel's license header, so it
stays local (gitignored by `*.pin`).  What we actually need from it is the
device fact per package pin: location, I/O bank, and role.  Design-specific
columns (direction, I/O standard, the unused-pin reserve mode) are dropped.

Role normalisation:
    RESERVED_* (unused user I/O)          -> IO
    GND+ (unused dedicated input)         -> DEDICATED_INPUT
    ~ALTERA_<name>~[ / reserve-mode]      -> <name> (dual-purpose config pin)
    everything else (GND, VCCINT, VCCIO<n>, nCONFIG, TCK, MSEL<n>, ...) as-is

    python3 scripts/package_port/pin_facts.py <in.pin> <out.csv>
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

HEADER = re.compile(r"^Pin Name/Usage\s*:")


def role(usage: str) -> str:
    usage = usage.strip()
    m = re.match(r"~ALTERA_(\w+?)~", usage)
    if m:
        return m.group(1)
    if usage.startswith("RESERVED"):
        return "IO"
    if usage == "GND+":
        return "DEDICATED_INPUT"
    return usage


def pin_facts(pin: Path):
    """Yield (location, bank, role) rows from a Quartus .pin report."""
    body = False
    for line in pin.read_text(errors="replace").splitlines():
        if HEADER.match(line):
            body = True
            continue
        if not body or not line.strip() or line.lstrip().startswith("-"):
            continue
        cols = [c.strip() for c in line.split(" : ")]
        if len(cols) < 6:
            continue
        yield cols[1], cols[5], role(cols[0])


def _key(row):
    loc = row[0]
    return (0, int(loc), "") if loc.isdigit() else (1, 0, loc)


def write_csv(pin: Path, out: Path) -> int:
    rows = sorted(pin_facts(pin), key=_key)
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["location", "bank", "role"])
        w.writerows(rows)
    return len(rows)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    n = write_csv(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"{n} pins -> {sys.argv[2]}")
