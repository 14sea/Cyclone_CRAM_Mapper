# SPDX-License-Identifier: GPL-3.0-or-later
"""Functional demo: write LUT TT 0x0357 onto minterm_0 baseline.
Function: LED0 = (K1 & K2) | (K3 & K4)  — active-low keys.

A=K2(E16) B=K3(M16) C=K4(M15) D=K1(E15), all active-low.
Default (no key pressed): A=B=C=D=1 -> Q=0 -> LED OFF.
Press K1+K2 or K3+K4 -> Q=1 -> LED ON.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bitstream import LutCodec, patch_rbf_crc
from database import get_db

BASE = "/home/test/EP4CE6/results/rbf/minterm_0_X10_Y10_N0.rbf"
OUT  = "/home/test/EP4CE6/results/rbf/demo_keys_to_led0.rbf"
# minterm_0 baseline already has TT[0]=1, so XOR-mask to land on 0x0357 absolute
TARGET = 0x0357
MASK = TARGET ^ 0x0001  # 0x0356
X, Y, N = 10, 10, 0

def main():
    base = open(BASE, "rb").read()
    db = get_db()
    lcodec = LutCodec.from_db(db, X, Y, N)
    out = lcodec.write_tt(base, MASK)
    rb = lcodec.read_tt(out, base)
    print(f"wrote 0x{MASK:04X}, read back 0x{rb:04X}", "OK" if rb == MASK else "FAIL")
    out = patch_rbf_crc(out)
    open(OUT, "wb").write(out)
    print(f"-> {OUT}")

if __name__ == "__main__":
    main()
