# SPDX-License-Identifier: GPL-3.0-or-later
"""Cross-device equivalence: compile the SAME design with DEVICE=EP4CE6F17C8
and DEVICE=EP4CE10F17C8, byte-diff the resulting RBFs.

Hypothesis: EP4CE6 and EP4CE10 share the same physical die; EP4CE6 is just
EP4CE10 with software-imposed resource limits in Quartus. If true, the two
RBFs will be byte-identical.
"""
import sys, os, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export

VERILOG = """module probe_top(input wire K, output wire LED);
  assign LED = K;
endmodule
"""

QSF_TMPL = """set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE {device}
set_global_assignment -name TOP_LEVEL_ENTITY probe_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_location_assignment PIN_E16 -to K
set_location_assignment PIN_G15 -to LED
"""

OUT = "/home/test/EP4CE6/results/rbf"

def main():
    rbfs = {}
    for tag, dev in [("ce6", "EP4CE6F17C8"), ("ce10", "EP4CE10F17C8")]:
        name = f"xdev_{tag}"
        path = f"{OUT}/{name}.rbf"
        print(f"==> compiling {name} ({dev})")
        rbf, t, err = compile_and_export(name, VERILOG, QSF_TMPL.format(device=dev), rbf_output=path)
        if not rbf:
            print(f"   FAIL: {err}"); return
        data = open(path, "rb").read()
        rbfs[tag] = data
        print(f"   OK ({t:.1f}s) size={len(data)} sha1={hashlib.sha1(data).hexdigest()[:16]}")

    a, b = rbfs["ce6"], rbfs["ce10"]
    print(f"\nlen ce6 = {len(a)}, len ce10 = {len(b)}, same_len = {len(a)==len(b)}")
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        print(f"byte differences: {len(diffs)}")
        if diffs:
            for i in diffs[:20]:
                print(f"  off=0x{i:06X}  ce6=0x{a[i]:02X}  ce10=0x{b[i]:02X}")
            # Localize: header (off<32+25*210=5282) vs CRAM
            hdr = sum(1 for i in diffs if i < 32 + 25*210)
            cram = len(diffs) - hdr
            print(f"  header diffs: {hdr}, cram diffs: {cram}")
        else:
            print("  >>> RBFs are BYTE-IDENTICAL <<<")

if __name__ == "__main__":
    main()
