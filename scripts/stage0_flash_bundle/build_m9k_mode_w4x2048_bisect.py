# SPDX-License-Identifier: GPL-3.0-or-later
"""M9K_MODE (4, 2048) silicon bisection harness.

The 24-cell inferred_goldintersect bucket for (w=4, d=2048) FAILs silicon
(LED0 stuck on, KEY2 inert) when overlaid on the HW-PASS w=9 probe.  This
script bisects that bucket: flash each output RBF on AX301, watch LED0
respond to KEY2 (E16, active-low) -> PASS means that subset is safe, FAIL
means a leaky cell is inside.

Subsets are defined as sorted-offset index lists over the 24-cell bucket.
Pass any combination on the CLI; omit to build Layer 1 (H0=idx 0..11,
H1=idx 12..23).

    python3 build_m9k_mode_w4x2048_bisect.py           # Layer 1: H0 + H1
    python3 build_m9k_mode_w4x2048_bisect.py 0-5       # label 0_5
    python3 build_m9k_mode_w4x2048_bisect.py 0,2,5,7   # label 0_2_5_7
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


def _load_gi(width: int, depth: int) -> list[tuple[int, int]]:
    d = json.loads(MODE_BITS.read_text())
    for entry in d.values():
        if entry["width"] == width and entry["depth"] == depth:
            return [tuple(c) for c in entry["cells_by_template"]["inferred_goldintersect"]]
    raise KeyError(f"no site for {width}x{depth}")


def _hw_pass_bytes() -> bytearray:
    proc = subprocess.run(
        ["git", "show", f"{HW_PASS_COMMIT}:{HW_PASS_PROBE}"],
        cwd=REPO, check=True, stdout=subprocess.PIPE,
    )
    buf = bytearray(proc.stdout)
    assert len(buf) == 368011, f"unexpected RBF size {len(buf)}"
    return buf


def _xor_flip(buf: bytearray, cells) -> None:
    for off, bp in cells:
        buf[off] ^= (1 << bp)


def _parse_spec(spec: str, n: int) -> list[int]:
    out: set[int] = set()
    for tok in spec.split(","):
        tok = tok.strip()
        if "-" in tok:
            lo, hi = tok.split("-")
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(tok))
    for i in out:
        assert 0 <= i < n, f"idx {i} out of range 0..{n-1}"
    return sorted(out)


def _label(idxs: list[int]) -> str:
    if not idxs:
        return "empty"
    runs = []
    s = e = idxs[0]
    for i in idxs[1:]:
        if i == e + 1:
            e = i
        else:
            runs.append((s, e))
            s = e = i
    runs.append((s, e))
    return "_".join(f"{a}-{b}" if a != b else str(a) for a, b in runs)


def build(idxs: list[int], w9_off: list, w4_all: list,
          hw_pass: bytearray) -> Path:
    selected = [w4_all[i] for i in idxs]
    buf = bytearray(hw_pass)
    _xor_flip(buf, w9_off)
    _xor_flip(buf, selected)
    patched = patch_rbf_crc(bytes(buf))
    out = HERE / f"simple_led_m9k_mode_w4x2048_bisect_{_label(idxs)}.rbf"
    out.write_bytes(patched)
    print(f"[wrote] {out.name}  ({len(selected)} cells: idx {_label(idxs)})")
    return out


def main(argv: list[str]) -> int:
    hw_pass = _hw_pass_bytes()
    w9_off = _load_gi(9, 512)
    w4_all = sorted(_load_gi(4, 2048))
    print(f"w=9x512 OFF delta: {len(w9_off)} cells")
    print(f"w=4x2048 candidates: {len(w4_all)} cells")

    specs = argv[1:]
    if not specs:
        specs = [f"0-{len(w4_all)//2 - 1}", f"{len(w4_all)//2}-{len(w4_all)-1}"]
        print(f"\n[Layer 1 default] {specs}")

    built = []
    for spec in specs:
        idxs = _parse_spec(spec, len(w4_all))
        built.append(build(idxs, w9_off, w4_all, hw_pass))

    print("\nFlash with:")
    for p in built:
        print(f"  $HOME/see_neorv32_run_linux/tools/openFPGALoader/build/"
              f"openFPGALoader -c usb-blaster {p.relative_to(REPO)}")
    print("\nObserve KEY2 (E16, active-low) -> LED0 (G15). "
          "PASS = LED responds; FAIL = stuck/inert.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
