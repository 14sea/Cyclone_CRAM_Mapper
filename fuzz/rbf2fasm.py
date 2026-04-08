# SPDX-License-Identifier: GPL-3.0-or-later
"""rbf2fasm — Phase 4 reverse tool.

Dumps an EP4CE6 RBF (vs a zero baseline) into the FASM dialect consumed
by fasm2rbf. The primitive form is a BIT-level XOR diff over the CRAM
region (frames 25..1751), annotated with RouteCodec switch names as
comments for humans. Applying the dump with fasm2rbf against the same
zero baseline reproduces the original RBF's CRAM bit-for-bit.

Usage:
    python3 rbf2fasm.py <target.rbf> <zero.rbf> [out.fasm]
    python3 rbf2fasm.py target.rbf zero.rbf -       # stdout
"""
import os
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bitstream import (
    RouteCodec,
    CRC_PREAMBLE,
    CRC_FRAME_SIZE,
    CRC_DATA_SIZE,
    CRC_FIRST_CRAM_FRAME,
    CRC_LAST_FRAME,
)
import route_signatures
import route_decompose

ROOT_DIR = Path(HERE).parent


def _cram_byte_range():
    """Iterable of CRAM-region byte offsets (data bytes only, excluding the
    2-byte CRC trailer of each frame)."""
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        yield range(s, s + CRC_DATA_SIZE)


def diff_cells(target, zero):
    """Every (off, bp) where target differs from zero in the CRAM data area.
    CRC trailer bytes are skipped so a CRC-patched RBF round-trips cleanly.
    """
    cells = []
    for rng in _cram_byte_range():
        lo, hi = rng.start, rng.stop
        for off in range(lo, hi):
            x = target[off] ^ zero[off]
            if not x:
                continue
            for bp in range(8):
                if (x >> bp) & 1:
                    cells.append((off, bp))
    return cells


def annotate(cells, target, zero):
    """Build (off,bp) -> list[str] annotations from RouteCodec.read_switches.
    One cell can resolve to multiple wire names (expected for LI pair_map),
    so we join them with '|'.
    """
    ann = {}
    codec = RouteCodec()
    sw = codec.read_switches(target, zero)
    for kind, lst in sw.items():
        for entry in lst:
            # entries: (name, off, bp, ...)
            name = entry[0]
            off = entry[1]
            bp = entry[2]
            ann.setdefault((off, bp), []).append(f"{kind}:{name}")
    return ann


def emit(target, zero, path_hint=None, semantic=False):
    cells = diff_cells(target, zero)
    ann = annotate(cells, target, zero)
    lines = []
    if path_hint:
        lines.append(f"# rbf2fasm dump of {path_hint}")
    lines.append(f"# {len(cells)} CRAM cell(s) differ from zero baseline")
    lines.append("")

    # Semantic decoder: try full-match single-route first, then fall back
    # to greedy set-cover decomposition over all known route signatures.
    if semantic:
        table = route_signatures.load()
        cells_table = route_signatures.load_cells()
        if table is not None:
            entry, _ = route_signatures.lookup(table, cells)
            if entry is not None:
                lines.append(f"# matched signature: {entry['n_cells']} cells")
                lines.append(
                    f"ROUTE X{entry['sx']}Y{entry['sy']} -> "
                    f"X{entry['dx']}Y{entry['dy']}N{entry['dn']}.{entry['port']}"
                )
                return "\n".join(lines) + "\n"
        if cells_table is not None:
            # Try to also consume source-overhead chunks so cross-source
            # merges emit clean SRC directives instead of BIT residue.
            overhead_tab = None
            oh_path = ROOT_DIR / "results" / "source_overhead.json"
            if oh_path.exists():
                import json as _json
                raw = _json.loads(oh_path.read_text())
                overhead_tab = {k: [(o, b) for o, b in v] for k, v in raw.items()}
            picked, residue = route_decompose.decompose(
                cells, cells_table, overhead_table=overhead_tab
            )
            if picked:
                n_routes = sum(1 for p in picked if p.startswith("route:"))
                n_srcs = sum(1 for p in picked if p.startswith("src:"))
                lines.append(
                    f"# decomposed: {n_routes} route(s), {n_srcs} src(s), "
                    f"{len(residue)} residue cell(s)"
                )
                for tag in picked:
                    if tag.startswith("route:"):
                        lines.append(route_decompose.rk_to_fasm(tag[6:]))
                    elif tag.startswith("src:"):
                        sx, sy = tag[4:].split(",")
                        lines.append(f"SRC X{sx}Y{sy}")
                if residue:
                    lines.append("# residue BITs:")
                    for off, bp in sorted(residue):
                        tags = ann.get((off, bp))
                        suffix = (
                            f"  # {' | '.join(sorted(set(tags)))}" if tags else ""
                        )
                        lines.append(f"BIT 0x{off:05x} {bp}{suffix}")
                return "\n".join(lines) + "\n"
            lines.append("# semantic: no decomposition, falling back to BIT dump")
        else:
            lines.append(
                "# semantic: no cells table, run route_signatures.py first"
            )

    # Group by frame for readability
    last_frame = None
    for off, bp in cells:
        frame = (off - CRC_PREAMBLE) // CRC_FRAME_SIZE
        if frame != last_frame:
            lines.append(f"# --- frame {frame} ---")
            last_frame = frame
        tags = ann.get((off, bp))
        suffix = f"  # {' | '.join(sorted(set(tags)))}" if tags else ""
        lines.append(f"BIT 0x{off:05x} {bp}{suffix}")
    return "\n".join(lines) + "\n"


def main(argv):
    args = [a for a in argv[1:] if a != "--semantic"]
    semantic = "--semantic" in argv
    if len(args) not in (2, 3):
        print(
            "usage: rbf2fasm.py [--semantic] <target.rbf> <zero.rbf> [out.fasm|-]",
            file=sys.stderr,
        )
        return 2
    target = Path(args[0]).read_bytes()
    zero = Path(args[1]).read_bytes()
    out = emit(target, zero, path_hint=args[0], semantic=semantic)
    if len(args) == 2 or args[2] == "-":
        sys.stdout.write(out)
    else:
        Path(args[2]).write_text(out)
        print(f"wrote {args[2]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
