# SPDX-License-Identifier: GPL-3.0-or-later
"""Codec emission probe for M9K_INIT + M9K_MODE + M9K_COLUMN_INFRA.

Gold-replace pattern at one (X,Y) SDP site:
  1. Start with nv_zero_global.rbf.
  2. Apply M9K_INIT cells from the same INIT data used by Quartus v0.
  3. Apply M9K_MODE bucket from results/m9k_mode_bits.json (quartus_gold_sdp).
  4. Apply M9K_COLUMN_INFRA bucket (newly mined this session).
  5. Patch CRC on every modified frame.
  6. Diff vs Quartus v0 gold; report region/bp breakdown of remaining gap.

If gap is small enough (<300 cells, all in header or block_band/post),
the silicon flash is the next step. The remaining cells correspond to
the unimplemented IOB_PIN_BANK_INFRA (which now also folds in the
former M9K_BLOCK_TAIL block_band_post slice) + D3 directives.
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

PRE, FRAME, DPF = 32, 210, 208
REGIONS = [
    (0, 24, "header"),
    (25, 1006, "lab_low"),
    (1007, 1013, "clk_net"),
    (1014, 1691, "lab_high"),
    (1692, 1738, "block_band"),
    (1739, 1751, "block_band_post"),
]


def region_of(frame: int) -> str:
    for lo, hi, name in REGIONS:
        if lo <= frame <= hi:
            return name
    return "?"


def diff_cells(a: bytes, b: bytes) -> set[tuple[int, int]]:
    cells = set()
    for off in range(PRE, len(a)):
        if (off - PRE) % FRAME >= DPF:
            continue
        x = a[off] ^ b[off]
        if not x:
            continue
        for bp in range(8):
            if x & (1 << bp):
                cells.add((off, bp))
    return cells


def apply_xor(rbf: bytearray, cells) -> None:
    for off, bp in cells:
        rbf[off] ^= 1 << bp


def m9k_init_cells(site: str, w: int, d: int, init_words):
    from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
    anchor_info = M9K_INIT_ANCHORS[(site, w, d)]
    anchor = anchor_info[0]
    bp = anchor_info[1] if len(anchor_info) > 1 else 6
    cells = set()
    for word_idx, word_val in enumerate(init_words):
        for bit_idx in range(w):
            if (word_val >> bit_idx) & 1:
                off, cell_bp = init_cell(anchor, word_idx, bit_idx, bp)
                cells.add((off, cell_bp))
    return cells


def parse_mif_words(mif_path: Path, depth: int) -> list[int]:
    """Trivial parse: hex 'addr : data;' lines. Default zeros for missing."""
    words = [0] * depth
    if not mif_path.exists():
        return words
    text = mif_path.read_text()
    in_content = False
    import re
    for line in text.splitlines():
        s = line.split("--")[0].strip()
        if not s:
            continue
        if s.upper().startswith("CONTENT"):
            in_content = True
            continue
        if not in_content:
            continue
        if s.upper().startswith("END"):
            break
        if s.upper().startswith("BEGIN"):
            continue
        # form "addr : data;" or "[a..b] : data;"
        m = re.match(r"\[(\w+)\s*\.\.\s*(\w+)\]\s*:\s*(\w+)\s*;", s)
        if m:
            a, b, val = m.groups()
            lo, hi, v = int(a, 16), int(b, 16), int(val, 16)
            for i in range(lo, hi + 1):
                if i < depth:
                    words[i] = v
            continue
        m = re.match(r"(\w+)\s*:\s*(\w+)\s*;", s)
        if m:
            a, val = m.groups()
            i, v = int(a, 16), int(val, 16)
            if i < depth:
                words[i] = v
    return words


def patch_crc(rbf: bytearray) -> bytes:
    sys.path.insert(0, str(ROOT / "fuzz"))
    from bitstream import patch_rbf_crc
    return patch_rbf_crc(bytes(rbf))


def main(argv):
    site = argv[1] if len(argv) > 1 else "X15_Y16_N0"
    w, d = 4, 2048
    mode = "sdp"
    site_dir = ROOT / f"tmp/m9k_mode_quartus_gold/{w}x{d}/{mode}/{site}"
    nv_path = ROOT / "results/rbf/nv_zero_global.rbf"
    v0_path = site_dir / f"m9k_mode_gold_{w}x{d}_{mode}_v0.rbf"

    nv = nv_path.read_bytes()
    v0 = v0_path.read_bytes()

    # Compute true target diff (the full thing the codec should reproduce)
    target = diff_cells(v0, nv)
    print(f"Target (v0 ⊕ nv_zero_global): {len(target)} cells")

    rebuilt = bytearray(nv)

    # 1. Apply M9K_INIT cells from v0's actual INIT data.
    # We don't have direct access to v0's MIF, but we can derive the INIT cells
    # from the diff at the M9K_INIT anchor's expected (off, bp) range.
    # Simpler: take target cells that fall on the M9K_INIT footprint.
    from m9k_init_basis import M9K_INIT_ANCHORS, init_cell
    anchor_info = M9K_INIT_ANCHORS[(site, w, d)]
    anchor = anchor_info[0]
    init_bp = anchor_info[1] if len(anchor_info) > 1 else 6
    init_footprint = set()
    for word_idx in range(d):
        for bit_idx in range(w):
            try:
                off, bp = init_cell(anchor, word_idx, bit_idx, init_bp)
                init_footprint.add((off, bp))
            except Exception:
                pass
    init_cells = target & init_footprint

    # 2. M9K_MODE quartus_gold_sdp
    mode_bits = json.loads((ROOT / "results/m9k_mode_bits.json").read_text())
    site_key = f"{site}_{w}x{d}"
    mode_bucket = (mode_bits.get(site_key, {})
                   .get("cells_by_template", {})
                   .get("quartus_gold_sdp", []))
    mode_cells = set(tuple(c) for c in mode_bucket)

    # 3. M9K_COLUMN_INFRA from this session
    infra_path = ROOT / "results/m9k_column_infra.json"
    if not infra_path.exists():
        infra_path = ROOT / "tmp/m9k_column_infra_mine.json"
    infra_data = json.loads(infra_path.read_text())
    infra_cells = set(tuple(c) for c in infra_data[site]["infra_cells"])

    # Apply via UNION semantics, not XOR-superposition.  Init/infra overlap
    # heavily at bp(Y) in lab_low, so XOR'ing both would cancel shared bits
    # (the init cells are values BUT they share the same CRAM region as the
    # column-infra control cells).
    union = init_cells | mode_cells | infra_cells
    apply_xor(rebuilt, union)
    print(f"  M9K_INIT footprint: {len(init_footprint)} cells, "
          f"target ∩ footprint = {len(init_cells)}")
    print(f"  M9K_MODE quartus_gold_sdp: {len(mode_cells)} cells")
    print(f"  M9K_COLUMN_INFRA: {len(infra_cells)} cells")
    print(f"  Union applied (deduped): {len(union)} cells")
    print(f"    init ∩ infra (overlap, would-double-flip): "
          f"{len(init_cells & infra_cells)}")

    # 4. CRC patch
    final = patch_crc(rebuilt)

    # 5. Diff vs gold
    remaining = diff_cells(final, v0)
    print(f"\nRemaining diff vs v0 gold: {len(remaining)} cells")
    by_region_bp = Counter()
    for off, bp in remaining:
        f = (off - PRE) // FRAME
        by_region_bp[(region_of(f), bp)] += 1
    for region in [r[2] for r in REGIONS]:
        rsum = sum(v for (r, _), v in by_region_bp.items() if r == region)
        if rsum:
            bps = {bp: v for (r, bp), v in by_region_bp.items() if r == region}
            print(f"  {region:18} {rsum:5}  per_bp={dict(sorted(bps.items()))}")

    # Save remaining cells for downstream analysis
    out_path = ROOT / f"tmp/m9k_codec_emission_remaining_{site}.json"
    out_path.write_text(json.dumps(sorted(remaining), indent=2))
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
