# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the w=8 depth=64 M9K_MODE goldintersect HW probe by
XOR-overlaying on the known-HW-PASS w=9 depth=512 probe RBF.

Step 1a of the 4-step zero-Quartus plan
(`memory/quartus_independence_4step_plan_2026_04_28.md`):
the (w=8, d=64) shape covers the NEORV32 icache site at X15_Y11_N0
(4 SP ways, libmap-upgraded to native w=9 at runtime).  Mining
landed 2026-04-28 via `scripts/m9k_mode_width_mine.py --width 8
--depth 64 --workers 4 --sites 8`: 58 cells per site, perfect
site-invariance across 16 mined sites (X15 Y4..Y11, X27 Y3..Y10).

Same overlay rationale as the w=18/w=36/w=4×2048 probes —
isolates the (w=8, d=64) gi-bucket question from baseline drift.
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
OUT = HERE / "simple_led_m9k_mode_w8x64_goldintersect_HWbase.rbf"

TARGET_WIDTH = 8
TARGET_DEPTH = 64


def _load_gi(width: int, depth: int) -> list[tuple[int, int]]:
    d = json.loads(MODE_BITS.read_text())
    for key, entry in d.items():
        if entry["width"] == width and entry["depth"] == depth:
            cbt = entry["cells_by_template"]
            if "inferred_goldintersect" not in cbt:
                continue
            return [tuple(c) for c in cbt["inferred_goldintersect"]]
    raise KeyError(f"no inferred_goldintersect entry for {width}x{depth} in {MODE_BITS.name}")


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

    w9_base = _load_gi(9, 512)
    w_tgt = _load_gi(TARGET_WIDTH, TARGET_DEPTH)
    print(f"w=9x512   gi (base):   {len(w9_base)} cells")
    print(f"w={TARGET_WIDTH}x{TARGET_DEPTH} gi (target): {len(w_tgt)} cells")
    inter = set(w9_base) & set(w_tgt)
    sym = set(w9_base) ^ set(w_tgt)
    print(f"overlap : {len(inter)} cells")
    print(f"sym diff: {len(sym)} cells (HW delta vs HW-PASS)")

    _xor_flip(hw_pass, w9_base)
    _xor_flip(hw_pass, w_tgt)
    patched = patch_rbf_crc(bytes(hw_pass))

    OUT.write_bytes(patched)
    print(f"\n[wrote] {OUT}  ({len(patched)} bytes)")
    print("Flash with:")
    print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/openFPGALoader "
          f"-c usb-blaster {OUT.relative_to(REPO)}")
    print("\nExpected HW behavior (AX301): LED0 initially on, goes off when "
          "KEY2 (E16) is pressed — matches the HW-PASS w=9 probe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
