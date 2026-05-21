# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine the per-position canon-cell table for the 14 D1++ positions.

Path 5 of rot_tpu_handoff mode H reply: for each (x, y, n, mask) build in
``results/golden_rbf_modeH/``, compute the symmetric difference between
Quartus's actual mask-vs-baseline diff (.cells JSON) and the EP4CE6 codec's
``LutCodec.predict_sram(mask)``.  The result is an additive XOR table such
that ``predict_sram(M) XOR canon_cells[(x,y,n)][M] == Quartus_mask_M_diff``
(modulo per-build variable header bytes documented in D4 and frame CRC
bytes that the consumer recomputes anyway).

Output: ``results/canon_2input_codec_table_d1pp.json``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import LutCodec  # noqa: E402

GOLDEN = ROOT / "results" / "golden_rbf_modeH"
OUT_PATH = ROOT / "results" / "canon_2input_codec_table_d1pp.json"

# Per D4: rbf_safe_byte_ranges.md — per-build variable bytes.
PER_BUILD_RANGES = [(0x29, 0x35), (0x49, 0x4B)]


def in_per_build_variable(addr: int) -> bool:
    return any(lo <= addr < hi for lo, hi in PER_BUILD_RANGES)


def is_crc_byte(addr: int) -> bool:
    """Frame CRC: last 2 bytes of each 210-byte CRAM frame, frames 25..1751."""
    if not (5282 <= addr < 367952):
        return False
    return (addr - 32) % 210 >= 208


def classify_region(addr: int) -> str:
    if addr < 5282:
        return "header"
    if addr >= 367952:
        return "postamble"
    frame_idx = (addr - 32) // 210
    if 1692 <= frame_idx <= 1738:
        return "block_band"
    return "lab_cram"


def load_cells(path: Path) -> set[tuple[int, int]]:
    obj = json.loads(path.read_text())
    cells = obj["cells"] if isinstance(obj, dict) and "cells" in obj else obj
    return {(int(c["addr"], 16), int(c["bit"])) for c in cells}


def mine() -> dict:
    sweep = json.loads((GOLDEN / "sweep_summary.json").read_text())
    table = {
        "schema_version": 1,
        "source": "results/golden_rbf_modeH/sweep_summary.json",
        "quartus_version": sweep.get("quartus_version", "Lite 21.1"),
        "formula": (
            "Quartus_mask_M_diff = predict_sram(M) XOR "
            "canon_cells[(x,y,n)][M], where diffs are vs the position-local "
            "mask=0x0000 baseline; per-build variable bytes and frame CRC "
            "bytes are filtered out (consumer recomputes CRC)."
        ),
        "per_build_variable_ranges": [[f"0x{lo:X}", f"0x{hi:X}"]
                                       for lo, hi in PER_BUILD_RANGES],
        "per_position": {},
    }

    for r in sweep["results"]:
        if r.get("is_baseline"):
            continue
        x, y, n = r["x"], r["y"], r["n"]
        mask_s = r["mask"]
        mask = int(mask_s, 16)
        stem = f"X{x}_Y{y}_N{n}_mask{mask_s[2:].upper()}_q211"
        cells_path = GOLDEN / f"{stem}.cells"
        if not cells_path.exists():
            raise FileNotFoundError(cells_path)

        q_cells = load_cells(cells_path)
        codec = LutCodec.from_cram_model(x, y, n)
        p_cells = codec.predict_sram(mask)

        canon_raw = q_cells ^ p_cells

        # Strip per-build variable header bytes (D4) + frame CRC bytes
        # (consumer must call patch_rbf_crc after XOR-applying canon cells).
        canon = {(off, bp) for off, bp in canon_raw
                 if not in_per_build_variable(off) and not is_crc_byte(off)}

        # Diagnostic counters
        n_per_build = sum(1 for off, _ in canon_raw if in_per_build_variable(off))
        n_crc = sum(1 for off, _ in canon_raw if is_crc_byte(off))

        regions = {"header": 0, "lab_cram": 0, "block_band": 0, "postamble": 0}
        cells_list = []
        for off, bp in sorted(canon):
            reg = classify_region(off)
            regions[reg] += 1
            cells_list.append({"addr": f"0x{off:X}", "bit": bp, "region": reg})

        key = f"{x},{y},{n}"
        pos_entry = table["per_position"].setdefault(
            key, {"x": x, "y": y, "n": n, "masks": {}}
        )
        pos_entry["masks"][mask_s] = {
            "n_canon_cells": len(cells_list),
            "n_quartus_cells_in_diff": len(q_cells),
            "n_predict_sram": len(p_cells),
            "n_filtered_per_build_variable": n_per_build,
            "n_filtered_crc": n_crc,
            "regions": regions,
            "cells": cells_list,
        }
    return table


def main() -> None:
    table = mine()
    OUT_PATH.write_text(json.dumps(table, indent=2))
    print(f"wrote {OUT_PATH.relative_to(ROOT)}")
    print()
    print("per-position summary:")
    for key, p in table["per_position"].items():
        print(f"  ({key}):")
        for mask_s, d in p["masks"].items():
            print(
                f"    {mask_s}: {d['n_canon_cells']:3} canon "
                f"(Q={d['n_quartus_cells_in_diff']:3} P={d['n_predict_sram']:2} "
                f"-per_build={d['n_filtered_per_build_variable']} "
                f"-crc={d['n_filtered_crc']})  "
                f"regions={d['regions']}"
            )


if __name__ == "__main__":
    main()
