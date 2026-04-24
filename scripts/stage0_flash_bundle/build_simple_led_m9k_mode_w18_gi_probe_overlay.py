# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the w=18 M9K_MODE goldintersect HW probe by XOR-overlaying on
the known-HW-PASS w=9 probe RBF.

Why this exists:
  `build_simple_led_m9k_mode_w18_gi_probe.py` regenerates the full
  simple_led stack from scratch via `NV_BASELINE_PACK + IOB_BASELINE_NV
  + IOB_IN/OUT + IOB_ROUTE + GCLK_PIN + LAB_CLK_SEL + LAB_CLK_SEL_LE`.
  That FASM stack has silently drifted since the w=9 probe HW-PASS of
  2026-04-17 (443 byte delta vs the checked-in w=9 probe RBF) — flashing
  today's fresh build leaves LED0 stuck on, independent of the M9K_MODE
  line.  Investigating that drift is a separate task.

  This overlay path side-steps the drift.  It starts from the w=9 probe
  RBF committed at cff800e (HW-verified on AX301 2026-04-17), XOR-flips
  the 38 w=9 gi cells OFF (returning the bitstream to "simple_led only"
  at the M9K block band), then XOR-flips the 74 w=18 gi cells ON.  The
  only delta vs the HW-PASS RBF is:

    42 block-band bits (frames 1720..1738, bp=2)
      = sym_diff(w9_gi, w18_gi)
      = 3 cells unique to w=9 ∪ 39 cells unique to w=18

  Everything else (IOB, GCLK, CLK_SEL, LE) is byte-identical to the
  known-silicon-safe baseline.  If this RBF behaves like the HW-PASS
  w=9 probe on silicon, the w=18 gi bucket is silicon-validated.

HW result (2026-04-24 on AX301): LED0 initial on, goes off when KEY2
pressed — identical to the HW-PASS w=9 probe.  **w=18 gi PASSed.**
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
HW_PASS_COMMIT = "cff800e"   # HW-verified on AX301 2026-04-17
MODE_BITS = REPO / "results" / "m9k_mode_bits.json"
OUT = HERE / "simple_led_m9k_mode_w18_goldintersect_HWbase.rbf"


def _load_gi(width: int, depth: int = 512) -> list[tuple[int, int]]:
    d = json.loads(MODE_BITS.read_text())
    key = f"X15_Y10_N0_{width}x{depth}"
    return [tuple(c) for c in d[key]["cells_by_template"]["inferred_goldintersect"]]


def _xor_flip(buf: bytearray, cells) -> None:
    for off, bp in cells:
        buf[off] ^= (1 << bp)


def main() -> int:
    # Grab the committed HW-PASS RBF straight from git so the build is
    # independent of any currently-checked-out tree state.
    proc = subprocess.run(
        ["git", "show", f"{HW_PASS_COMMIT}:{HW_PASS_PROBE}"],
        cwd=REPO, check=True, stdout=subprocess.PIPE,
    )
    hw_pass = bytearray(proc.stdout)
    assert len(hw_pass) == 368011, f"unexpected RBF size {len(hw_pass)}"

    w9 = _load_gi(9)
    w18 = _load_gi(18)
    print(f"w=9  gi: {len(w9)} cells")
    print(f"w=18 gi: {len(w18)} cells")
    print(f"overlap: {len(set(w9) & set(w18))} cells")
    print(f"sym diff: {len(set(w9) ^ set(w18))} cells (minimal HW delta)")

    _xor_flip(hw_pass, w9)   # remove w=9 gi (restore simple_led M9K band)
    _xor_flip(hw_pass, w18)  # add w=18 gi
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
