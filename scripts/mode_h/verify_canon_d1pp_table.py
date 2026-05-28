# SPDX-License-Identifier: GPL-3.0-or-later
"""Reconstruct each D1++ golden RBF from its position's mask=0x0000 baseline
+ ``predict_sram(M)`` + the mined ``canon_cells[(x,y,n)][M]``, then bit-compare
against the Quartus golden RBF.

Pass criterion: after XOR-applying ``predict_sram(M) ^ canon_cells[M]`` to the
mask=0x0000 baseline and recomputing per-frame CRC, the reconstructed RBF
matches the Quartus golden modulo per-build variable header bytes documented
in D4.

SCOPE CAVEAT — this is a *lossless encode/decode round-trip* gate, NOT an
independent silicon/physics validation. The table is mined as
``canon_cells := (gold ^ baseline) ^ predict_sram`` and the reconstruction is
``baseline ^ predict_sram ^ canon_cells == gold`` by construction. So a green
result proves the table losslessly re-encodes each gold AND that the apply/CRC/
per-build-exclusion paths are correct (the negative control: corrupting one
canon cell yields diff_bytes>0) — but it CANNOT detect a systematically-wrong
canon model, because every gold checked here was also used to mine the table.
There is no hold-out. Do not cite a green run as evidence the canon model
generalizes to unmined masks/positions or is silicon-correct. See memory
``path5_canon_d1pp_table_landed_2026_05_21`` caveat #5.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import LutCodec, patch_rbf_crc  # noqa: E402

GOLDEN = ROOT / "results" / "golden_rbf_modeH"
TABLE_PATH = ROOT / "results" / "canon_2input_codec_table_d1pp.json"

PER_BUILD_RANGES = [(0x29, 0x35), (0x49, 0x4B)]


def in_per_build_variable(addr: int) -> bool:
    return any(lo <= addr < hi for lo, hi in PER_BUILD_RANGES)


def load_table_cells(entry) -> set[tuple[int, int]]:
    return {(int(c["addr"], 16), c["bit"]) for c in entry["cells"]}


def xor_apply(rbf: bytes, cells: set[tuple[int, int]]) -> bytes:
    buf = bytearray(rbf)
    for off, bp in cells:
        buf[off] ^= (1 << bp)
    return bytes(buf)


def verify_build(x: int, y: int, n: int, mask_s: str,
                 canon_cells: set[tuple[int, int]]) -> dict:
    mask = int(mask_s, 16)
    stem_base = f"X{x}_Y{y}_N{n}_mask0000_q211.rbf"
    stem_gold = f"X{x}_Y{y}_N{n}_mask{mask_s[2:].upper()}_q211.rbf"
    base = (GOLDEN / stem_base).read_bytes()
    gold = (GOLDEN / stem_gold).read_bytes()

    codec = LutCodec.from_cram_model(x, y, n)
    p_cells = codec.predict_sram(mask)

    delta = p_cells ^ canon_cells
    recon = xor_apply(base, delta)
    recon = patch_rbf_crc(recon)

    diffs = [
        i for i in range(len(gold))
        if recon[i] != gold[i] and not in_per_build_variable(i)
    ]
    return {
        "x": x, "y": y, "n": n, "mask": mask_s,
        "len_gold": len(gold),
        "len_recon": len(recon),
        "diff_bytes_non_per_build": len(diffs),
        "first_5_diffs": [f"0x{o:X}" for o in diffs[:5]],
    }


def main() -> int:
    table = json.loads(TABLE_PATH.read_text())
    results = []
    for key, pos in table["per_position"].items():
        x, y, n = pos["x"], pos["y"], pos["n"]
        for mask_s, entry in pos["masks"].items():
            cells = load_table_cells(entry)
            r = verify_build(x, y, n, mask_s, cells)
            results.append(r)
            tag = "PASS" if r["diff_bytes_non_per_build"] == 0 else "FAIL"
            print(
                f"  [{tag}] X{x}Y{y}N{n} {mask_s}: "
                f"diff_bytes={r['diff_bytes_non_per_build']} "
                f"{r['first_5_diffs']}"
            )
    n_pass = sum(1 for r in results if r["diff_bytes_non_per_build"] == 0)
    print(f"\n{n_pass}/{len(results)} builds reconstruct byte-identical to Quartus gold "
          f"(excluding per-build variable bytes).")
    print("  [scope] lossless mine->verify round-trip on the SAME builds — "
          "table-integrity/CRC/apply gate, NOT hold-out or silicon validation.")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
