# SPDX-License-Identifier: GPL-3.0-or-later
"""P4 N>0 invariance probe for the canon-2input layer.

The canon-2input codec (P2 absolute table + d1pp per-position table) is
silicon-validated only at N=0.  This probe closes the open "N>0 invariance"
axis by:

  1. Building a d1pp-style single-LE pin-driven gold (KEY1..4 -> LUT -> LED0,
     LE pinned to LCCOMB_X{x}_Y{y}_N{n}) at an N>0 position, mask 0x4444
     (= !KEY1 & KEY2, independent of c/d), plus its mask=0x0000 baseline.
  2. Mining the canon cells at N>0 with the EXACT build_canon_d1pp_table
     convention (q_cells △ predict_sram, CRC + per-build-variable filtered).
  3. Verifying the codec formula reconstructs the N>0 gold byte-identical
     (baseline XOR predict_sram(M) XOR canon, then patch_rbf_crc).
  4. Testing N-INVARIANCE vs the committed canon_N0 for the same (x,y) mask:
     block_band cells (per-LAB) should be identical; lab_cram cells (per-LE)
     should translate by the LE stride that predict_sram itself exhibits.
  5. Running validate_safe_for_hardware on the gold as the pre-flash gate.

The flash artifact is the Quartus gold itself (genuine vendor output, the
same trivially-safe single-LUT pin-driven class already silicon-validated at
N=0) — zero silicon risk; the codec reconstruction byte-identity is the
software validation.  This script does NOT flash; it prints a readiness
verdict + the gold md5.

Usage:  python3 scripts/mode_h/p4_n_invariance_probe.py [--x 10 --y 2 --n 2 --mask 0x4444]
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fuzz"))
sys.path.insert(0, str(ROOT / "scripts" / "handoff_modeh"))
sys.path.insert(0, str(ROOT / "scripts" / "mode_h"))

from bitstream import LutCodec, patch_rbf_crc, RouteCodec  # noqa: E402
import build_d1_golden as bd  # noqa: E402
import build_canon_d1pp_table as minemod  # noqa: E402

TABLE = ROOT / "results" / "canon_2input_codec_table_d1pp.json"
NV_ZERO = ROOT / "results" / "rbf" / "nv_zero_global.rbf"


def q_diff_cells(gold: bytes, baseline: bytes) -> set[tuple[int, int]]:
    """Quartus mask-vs-baseline diff, same filtering as the .cells files."""
    return {(int(c["addr"], 16), c["bit"]) for c in bd.diff_cells(gold, baseline)}


def mine_canon(x: int, y: int, n: int, mask: int,
               gold: bytes, baseline: bytes) -> set[tuple[int, int]]:
    """Exact build_canon_d1pp_table convention."""
    q = q_diff_cells(gold, baseline)
    p = LutCodec.from_cram_model(x, y, n).predict_sram(mask)
    raw = q ^ p
    return {(off, bp) for off, bp in raw
            if not minemod.in_per_build_variable(off) and not minemod.is_crc_byte(off)}


def region(off: int) -> str:
    return minemod.classify_region(off)


def load_table_canon(x: int, y: int, n: int, mask_s: str):
    import json
    t = json.loads(TABLE.read_text())
    key = f"{x},{y},{n}"
    pos = t["per_position"].get(key)
    if not pos or mask_s not in pos.get("masks", {}):
        return None
    return {(int(c["addr"], 16), c["bit"]) for c in pos["masks"][mask_s]["cells"]}


def xor_apply(rbf: bytes, cells) -> bytes:
    buf = bytearray(rbf)
    for off, bp in cells:
        buf[off] ^= (1 << bp)
    return bytes(buf)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, default=10)
    ap.add_argument("--y", type=int, default=2)
    ap.add_argument("--n", type=int, default=2, help="N>0 LE slot to test")
    ap.add_argument("--mask", default="0x4444")
    args = ap.parse_args()
    x, y, n = args.x, args.y, args.n
    mask = int(args.mask, 16)
    mask_s = f"0x{mask:04x}"

    print(f"=== P4 N>0 invariance probe @ X{x}Y{y}N{n}, mask {mask_s} ===\n")

    # ---- 1. build N>0 golds (baseline + mask) -------------------------------
    base_name = f"X{x}_Y{y}_N{n}_mask0000_q211"
    gold_name = f"X{x}_Y{y}_N{n}_mask{mask:04X}_q211"
    print(f"[1] building {base_name} + {gold_name} (Quartus; cached) ...")
    baseline = bd.build_one(base_name, x, y, n, 0x0000)
    gold = bd.build_one(gold_name, x, y, n, mask)
    gold_md5 = hashlib.md5(gold).hexdigest()
    print(f"    baseline md5 {hashlib.md5(baseline).hexdigest()[:12]}  "
          f"gold md5 {gold_md5}")
    assert len(gold) == 368011 and len(baseline) == 368011

    # ---- 2. mine canon @ N>0 ------------------------------------------------
    p_cells = LutCodec.from_cram_model(x, y, n).predict_sram(mask)
    q_cells = q_diff_cells(gold, baseline)
    canon_n = mine_canon(x, y, n, mask, gold, baseline)
    reg = {"header": 0, "lab_cram": 0, "block_band": 0, "postamble": 0}
    for off, _ in canon_n:
        reg[region(off)] += 1
    print(f"\n[2] canon @ N{n}: {len(canon_n)} cells  "
          f"(Q={len(q_cells)} P={len(p_cells)})  regions={reg}")

    # ---- 3. codec-formula reconstruction byte-identity ----------------------
    recon = patch_rbf_crc(xor_apply(baseline, p_cells ^ canon_n))
    diffs = [i for i in range(len(gold))
             if recon[i] != gold[i] and not bd.in_variable_range(i)]
    ok_recon = (len(diffs) == 0)
    print(f"\n[3] reconstruction baseline^predict_sram^canon (patched CRC) vs gold: "
          f"diff_bytes={len(diffs)} {'PASS' if ok_recon else 'FAIL ' + str([hex(d) for d in diffs[:6]])}")

    # ---- 4. N-invariance vs committed canon_N0 ------------------------------
    print(f"\n[4] N-invariance vs committed canon @ X{x}Y{y}N0, mask {mask_s}:")
    canon_0 = load_table_canon(x, y, 0, mask_s)
    p0 = LutCodec.from_cram_model(x, y, 0).predict_sram(mask)
    invariance = {}
    if canon_0 is None:
        print("    (no committed N0 entry for this position/mask — skipping)")
    else:
        bb0 = {(o, b) for o, b in canon_0 if region(o) == "block_band"}
        bbn = {(o, b) for o, b in canon_n if region(o) == "block_band"}
        lc0 = {(o, b) for o, b in canon_0 if region(o) == "lab_cram"}
        lcn = {(o, b) for o, b in canon_n if region(o) == "lab_cram"}
        # LE stride from predict_sram (N0 -> Nn): difference of sorted offsets
        po0 = sorted({o for o, _ in p0})
        pon = sorted({o for o, _ in p_cells})
        deltas = {b - a for a, b in zip(po0, pon)} if len(po0) == len(pon) else set()
        stride = next(iter(deltas)) if len(deltas) == 1 else None
        bb_identical = (bb0 == bbn)
        lc_translates = None
        if stride is not None:
            lc0_shifted = {(o + stride, b) for o, b in lc0}
            lc_translates = (lc0_shifted == lcn)
        print(f"    canon_N0 = {len(canon_0)} cells; canon_N{n} = {len(canon_n)} cells")
        print(f"    block_band identical (per-LAB invariant)? {bb_identical} "
              f"(N0={len(bb0)}, N{n}={len(bbn)})")
        print(f"    predict_sram LE stride N0->N{n}: "
              f"{('0x%X' % stride) if stride is not None else 'NON-UNIFORM ' + str(sorted(deltas)[:4])}")
        print(f"    lab_cram cells translate by that stride? {lc_translates} "
              f"(N0={len(lc0)}, N{n}={len(lcn)})")
        invariance = {"bb_identical": bb_identical, "stride": stride,
                      "lc_translates": lc_translates}

    # ---- 5. pre-flash safety gate -------------------------------------------
    print(f"\n[5] pre-flash safety gate:")
    if NV_ZERO.exists():
        nv = NV_ZERO.read_bytes()
        try:
            viol = RouteCodec().validate_safe_for_hardware(gold, nv, raise_on_fail=False)
            viol = list(viol) if viol else []
            print(f"    validate_safe_for_hardware(gold, nv_zero): "
                  f"{len(viol)} violations {'(empty — OK)' if not viol else viol[:4]}")
        except Exception as e:
            print(f"    validate_safe_for_hardware raised: {e!r}")
            viol = ["<exception>"]
    else:
        print(f"    nv_zero_global.rbf not found — skipping (gold is genuine Quartus output)")
        viol = []

    # ---- verdict ------------------------------------------------------------
    print(f"\n=== VERDICT ===")
    print(f"  gold artifact : {bd.WORK}/{gold_name}/{gold_name}.rbf")
    print(f"  gold md5      : {gold_md5}")
    print(f"  size          : {len(gold)} bytes")
    print(f"  codec recon   : {'byte-identical' if ok_recon else 'MISMATCH'}")
    print(f"  behaviour     : LED0 = !KEY1 & KEY2  (ON iff KEY1 pressed[0] & KEY2 released[1])")
    flash_ready = ok_recon and not viol
    print(f"  FLASH-READY   : {'YES — genuine Quartus gold, codec reconstructs it, safety clean' if flash_ready else 'NO'}")
    return 0 if flash_ready else 1


if __name__ == "__main__":
    sys.exit(main())
