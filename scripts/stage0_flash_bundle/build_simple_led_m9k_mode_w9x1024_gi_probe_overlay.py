# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the w=9 depth=1024 M9K_MODE goldintersect HW probe by
XOR-overlaying on the known-HW-PASS w=9 depth=512 probe RBF.

See build_simple_led_m9k_mode_w18_gi_probe_overlay.py for the rationale
(sidesteps directive-stack drift in the simple_led baseline).

Only delta vs HW-PASS RBF: sym_diff(w9x512_gi, w9x1024_gi) = 59 cells
at block band frames 1717..1738. Everything else (IOB, GCLK, CLK_SEL,
LE) is byte-identical to the silicon-safe baseline.
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
OUT = HERE / "simple_led_m9k_mode_w9x1024_goldintersect_HWbase.rbf"

TARGET_WIDTH = 9
TARGET_DEPTH = 1024


def _load_gi(width: int, depth: int) -> list[tuple[int, int]]:
    """gi cells are site-invariant within (w,d); use the first available site."""
    d = json.loads(MODE_BITS.read_text())
    for key, entry in d.items():
        if entry["width"] == width and entry["depth"] == depth:
            return [tuple(c) for c in entry["cells_by_template"]["inferred_goldintersect"]]
    raise KeyError(f"no site for {width}x{depth} in {MODE_BITS.name}")


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
    print(f"w=9x512   gi (base): {len(w9_base)} cells")
    print(f"w={TARGET_WIDTH}x{TARGET_DEPTH} gi (target): {len(w_tgt)} cells")
    print(f"overlap: {len(set(w9_base) & set(w_tgt))} cells")
    print(f"sym diff: {len(set(w9_base) ^ set(w_tgt))} cells (minimal HW delta)")

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
