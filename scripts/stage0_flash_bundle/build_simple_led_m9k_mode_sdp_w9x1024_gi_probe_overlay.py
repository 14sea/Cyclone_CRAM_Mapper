# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the (SDP, w=9, d=1024) M9K_MODE goldintersect HW probe by
XOR-overlaying on the known-HW-PASS w=9 d=512 SP probe RBF.

Step 1b of the 4-step zero-Quartus plan.  The SDP (w=9, d=1024) shape
covers the NEORV32 IMEM/DMEM physical M9Ks (16 sites: X15 Y5..Y10,
X27 Y1..Y10) — Quartus depth-splits the logical 2048×8 SDP across two
physical 1024×8 chips, and Yosys libmap upgrades w=8 → native w=9.

Reads `cells_by_template["inferred_goldintersect_sdp"]` (mined via
patched `scripts/m9k_mode_width_mine.py --mode sdp --width 9 --depth 1024`,
gi = cross-site ∩ ∩ smoke_gold(SDP-flavoured)).
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
OUT = HERE / "simple_led_m9k_mode_sdp_w9x1024_goldintersect_HWbase.rbf"


def _load_gi_sp(width: int, depth: int) -> list[tuple[int, int]]:
    d = json.loads(MODE_BITS.read_text())
    for entry in d.values():
        if entry["width"] == width and entry["depth"] == depth:
            cbt = entry["cells_by_template"]
            if "inferred_goldintersect" in cbt:
                return [tuple(c) for c in cbt["inferred_goldintersect"]]
    raise KeyError(f"no SP inferred_goldintersect for {width}x{depth}")


def _load_gi_sdp(width: int, depth: int) -> list[tuple[int, int]]:
    d = json.loads(MODE_BITS.read_text())
    for entry in d.values():
        if entry["width"] == width and entry["depth"] == depth:
            cbt = entry["cells_by_template"]
            if "inferred_goldintersect_sdp" in cbt:
                return [tuple(c) for c in cbt["inferred_goldintersect_sdp"]]
    raise KeyError(f"no SDP inferred_goldintersect_sdp for {width}x{depth}")


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

    sp_base = _load_gi_sp(9, 512)
    sdp_tgt = _load_gi_sdp(9, 1024)
    inter = set(sp_base) & set(sdp_tgt)
    sym = set(sp_base) ^ set(sdp_tgt)
    print(f"SP   w=9 d=512   gi (HW-PASS base):   {len(sp_base)} cells")
    print(f"SDP  w=9 d=1024  gi (target):         {len(sdp_tgt)} cells")
    print(f"overlap : {len(inter)} cells")
    print(f"sym diff: {len(sym)} cells (HW delta vs HW-PASS)")

    _xor_flip(hw_pass, sp_base)
    _xor_flip(hw_pass, sdp_tgt)
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
