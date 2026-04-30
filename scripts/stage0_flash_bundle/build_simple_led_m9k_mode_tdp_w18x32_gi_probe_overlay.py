# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the (TDP, w=18, d=32) M9K_MODE goldintersect HW probe by
XOR-overlaying on the known-HW-PASS w=9 d=512 SP probe RBF.

Step 1c of the 4-step zero-Quartus plan.  The TDP (w=18, d=32) shape
covers the NEORV32 cpu_regfile (2 sites: X15_Y16, X15_Y17) — Quartus
splits the logical 32×32 TDP regfile into two physical 16×32 M9Ks.
Stage C.2 mining widened to w=18 here because Yosys/libmap will infer
w=18 native through the M9K's BIDIR_DUAL_PORT mode.

Reads `cells_by_template["inferred_goldintersect_tdp"]` (mined via
`scripts/m9k_mode_width_mine.py --mode tdp --width 18 --depth 32`).

Same overlay rationale as the SP/SDP probes: stripes the TDP gi onto
a HW-validated SP w=9 d=512 base RBF so a fabric-reset clearly
distinguishes "TDP gi cells break the simple_led path" from "TDP gi
cells coexist safely with the existing fabric configuration".
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))

from bitstream import patch_rbf_crc  # noqa: E402

HW_PASS_PROBE = "scripts/stage0_flash_bundle/simple_led_m9k_mode_goldintersect.rbf"
HW_PASS_COMMIT = "cff800e"
MODE_BITS = REPO / "results" / "m9k_mode_bits.json"
OUT = HERE / "simple_led_m9k_mode_tdp_w18x32_goldintersect_HWbase.rbf"


def _load_gi(width: int, depth: int, key_name: str) -> list[tuple[int, int]]:
    d = json.loads(MODE_BITS.read_text())
    for entry in d.values():
        if entry["width"] == width and entry["depth"] == depth:
            cbt = entry["cells_by_template"]
            if key_name in cbt:
                return [tuple(c) for c in cbt[key_name]]
    raise KeyError(f"no {key_name} for {width}x{depth} in {MODE_BITS.name}")


def _xor_flip(buf: bytearray, cells) -> None:
    for off, bp in cells:
        buf[off] ^= (1 << bp)


def main() -> int:
    proc = subprocess.run(
        ["git", "show", f"{HW_PASS_COMMIT}:{HW_PASS_PROBE}"],
        cwd=REPO, check=True, stdout=subprocess.PIPE,
    )
    hw_pass = bytearray(proc.stdout)
    assert len(hw_pass) == 368011, f"unexpected RBF size {len(hw_pass)}"

    sp_base = _load_gi(9, 512, "inferred_goldintersect")
    tdp_tgt = _load_gi(18, 32, "inferred_goldintersect_tdp")
    inter = set(sp_base) & set(tdp_tgt)
    sym = set(sp_base) ^ set(tdp_tgt)
    print(f"SP  w=9  d=512 gi (HW-PASS base): {len(sp_base)} cells")
    print(f"TDP w=18 d=32  gi (target):       {len(tdp_tgt)} cells")
    print(f"overlap : {len(inter)} cells")
    print(f"sym diff: {len(sym)} cells (HW delta vs HW-PASS)")

    _xor_flip(hw_pass, sp_base)
    _xor_flip(hw_pass, tdp_tgt)
    patched = patch_rbf_crc(bytes(hw_pass))

    OUT.write_bytes(patched)
    print(f"\n[wrote] {OUT}  ({len(patched)} bytes)")
    print("Flash with:")
    print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader "
          f"-c usb-blaster {OUT.relative_to(REPO)}")
    print("\nExpected HW behavior (AX301): LED0 initially on, goes off when "
          "KEY2 (E16) is pressed — matches the HW-PASS w=9 SP probe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
