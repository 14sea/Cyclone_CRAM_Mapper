# SPDX-License-Identifier: GPL-3.0-or-later
"""Y=15 ghost-row hardware demo: same (K1&K2)|(K3&K4) function as
demo_keys2leds.py but placed in the previously CE6-illegal Y=15 row at
LCCOMB_X10_Y15_N0. Validates Phase 3.25 jailbreak Y axis on silicon.

Default LED OFF; press K1+K2 or K3+K4 -> LED ON.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bitstream import LutCodec, patch_rbf_crc
from database import get_db

BASE = "/home/test/EP4CE6/results/rbf/minterm_0_X10_Y15_N0.rbf"
OUT  = "/home/test/EP4CE6/results/rbf/demo_y15_keys_to_led0.rbf"
TARGET = 0x0357
MASK = TARGET ^ 0x0001  # XOR-delta vs minterm_0 baseline (TT[0]=1)
X, Y, N = 10, 15, 0

def main():
    base = open(BASE, "rb").read()
    db = get_db()
    lcodec = LutCodec.from_db(db, X, Y, N)
    out = lcodec.write_tt(base, MASK)
    rb = lcodec.read_tt(out, base)
    print(f"wrote 0x{MASK:04X}, read back 0x{rb:04X}",
          "OK" if rb == MASK else "FAIL")
    out = patch_rbf_crc(out)
    open(OUT, "wb").write(out)
    print(f"-> {OUT}")
    print("Flash with: openFPGALoader -c usb-blaster", OUT)


if __name__ == "__main__":
    main()
