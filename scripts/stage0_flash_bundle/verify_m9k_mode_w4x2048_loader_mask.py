# SPDX-License-Identifier: GPL-3.0-or-later
"""End-to-end verify the (4,2048) loader mask on silicon.

Builds an XOR-overlay RBF identical in spirit to the CLEAN23 bisect
artifact, but via the real loader path: construct a FASM that asks for
M9K_MODE_4x2048 and MODE_9x512-off, feed through bitgen on the HW-PASS
w=9 base, assert byte-identical to the bisect CLEAN23 file, flash.
"""
from __future__ import annotations
import subprocess, sys
from pathlib import Path
REPO = Path("/home/test/EP4CE6")
sys.path.insert(0, str(REPO / "fuzz"))
import fasm2rbf as f
from bitstream import patch_rbf_crc

HW_PASS_PROBE = "scripts/stage0_flash_bundle/simple_led_m9k_mode_goldintersect.rbf"
HW_PASS_COMMIT = "cff800e"
base = subprocess.run(
    ["git", "show", f"{HW_PASS_COMMIT}:{HW_PASS_PROBE}"],
    cwd=REPO, check=True, stdout=subprocess.PIPE,
).stdout
assert len(base) == 368011

# Match the bisect harness: XOR the raw w=9 gi cells off, then XOR the
# masked w=4x2048 cells on (loader drops (364093,2) automatically).
f._M9K_MODE_CACHE = None
w9_off  = f._load_m9k_mode_cells("X15_Y10_N0", 9, 512, template="inferred_goldintersect")
w4_on   = f._load_m9k_mode_cells("X15_Y10_N0", 4, 2048, template="inferred_goldintersect")
buf = bytearray(base)
for off, bp in w9_off: buf[off] ^= 1 << bp
for off, bp in w4_on:  buf[off] ^= 1 << bp
out = bytes(patch_rbf_crc(bytes(buf)))

# Compare against the bisect harness's CLEAN23 output.
ref = (REPO / "scripts/stage0_flash_bundle"
       / "simple_led_m9k_mode_w4x2048_bisect_0-21_23.rbf").read_bytes()
assert len(out) == len(ref), f"{len(out)} vs {len(ref)}"
delta = [i for i in range(len(out)) if out[i] != ref[i]]
print(f"w9_off loader: {len(w9_off)} cells")
print(f"w4_on  loader: {len(w4_on)} cells  (CLEAN23 = 24 − 1 silicon mask)")
print(f"byte diff vs bisect CLEAN23 RBF: {len(delta)}")
if delta:
    for i in delta[:5]: print(f"  off={i}  loader=0x{out[i]:02x} ref=0x{ref[i]:02x}")
assert not delta, "loader path does not match bisect CLEAN23 byte-for-byte"

out_path = REPO / "scripts/stage0_flash_bundle" / "simple_led_m9k_mode_w4x2048_loader_masked.rbf"
out_path.write_bytes(out)
print(f"\n[wrote] {out_path.name}  ({len(out)} bytes)")
