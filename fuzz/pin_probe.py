# SPDX-License-Identifier: GPL-3.0-or-later
"""T7: Hardware pin probe — compile 4 minimal designs, each binding LED0 (PIN_G15)
to one candidate KEY pin via `assign LED = K`. Flash one at a time, press all keys,
and the only key that toggles LED0 reveals which physical key sits on that pin.
"""
import os, sys, shutil, subprocess
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile import compile_and_export

LED_PIN = "PIN_G15"
CANDIDATES = [
    ("E16", "PIN_E16"),
    ("M16", "PIN_M16"),
    ("M15", "PIN_M15"),
    ("E15", "PIN_E15"),
]

VERILOG = """module probe_top(input wire K, output wire LED);
  assign LED = K;
endmodule
"""

QSF_TMPL = """set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY probe_top
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_location_assignment {kpin} -to K
set_location_assignment {lpin} -to LED
"""

OUT_DIR = f"{REPO}/results/rbf"

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for tag, kpin in CANDIDATES:
        name = f"pinprobe_{tag}"
        rbf_out = f"{OUT_DIR}/{name}.rbf"
        qsf = QSF_TMPL.format(kpin=kpin, lpin=LED_PIN)
        print(f"==> compiling {name} (K={kpin})", flush=True)
        rbf, t, err = compile_and_export(name, VERILOG, qsf, rbf_output=rbf_out)
        if rbf:
            print(f"   OK ({t:.1f}s) -> {rbf}")
        else:
            print(f"   FAIL ({t:.1f}s): {err}")

if __name__ == "__main__":
    main()
