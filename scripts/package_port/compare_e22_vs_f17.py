# SPDX-License-Identifier: GPL-3.0-or-later
"""Does the EP4CE6 CRAM dictionary survive a package change?

Builds the *same* logic (one LUT4 at LCCOMB_X10_Y10_N0, all top-level ports
VIRTUAL_PIN so no package pad is involved) under two devices:

    EP4CE6F17C8   -- FBGA-256, the package every mined table was built on
    EP4CE6E22C8   -- EQFP-144, the user's new minimal-system board

and diffs the two uncompressed RBFs.

Interpretation:
  * byte-identical            -> package is a pure bonding change; the whole
                                 CRAM bit dictionary transfers untouched.
  * differs only in hdr/IOB   -> fabric model transfers, IOB_* layer must be
                                 re-mined for the new package.
  * fabric_data differs       -> STOP; the fabric model does not transfer.

Also dumps the fitter's .pin file for the EQFP-144 part, which is the
ground-truth pin table for the new board (there is no AX301.tcl for it).
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fuzz"))

import compile as qcompile  # noqa: E402

FAMILY = "Cyclone IV E"
TX, TY, TN = 10, 10, 0
WORK = ROOT / "tmp" / "pkg_port"
OUT = ROOT / "tmp" / "pkg_port" / "rbf"

VERILOG = """\
module fuzz_top(
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire y
);
    lut_inst_mod lut_inst(.a(a), .b(b), .c(c), .d(d), .y(y));
endmodule

module lut_inst_mod(
    input  wire a,
    input  wire b,
    input  wire c,
    input  wire d,
    output wire y
);
    // 0x8888 = a & b  (the pipeline's canonical 2-input probe mask)
    assign y = a & b;
endmodule
"""


def gen_qsf(device: str) -> str:
    lines = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f"set_global_assignment -name DEVICE {device}",
        "set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top",
        "set_global_assignment -name VERILOG_FILE fuzz_top.v",
        "set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files",
        "set_global_assignment -name MIN_CORE_JUNCTION_TEMP 0",
        "set_global_assignment -name MAX_CORE_JUNCTION_TEMP 85",
        "set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR 1",
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        "set_global_assignment -name SEED 1",
        f'set_location_assignment LCCOMB_X{TX}_Y{TY}_N{TN} -to "lut_inst"',
    ]
    for p in ("a", "b", "c", "d", "y"):
        lines.append(f"set_instance_assignment -name VIRTUAL_PIN ON -to {p}")
    return "\n".join(lines) + "\n"


def build(device: str, tag: str) -> Path | None:
    OUT.mkdir(parents=True, exist_ok=True)
    rbf = OUT / f"{tag}.rbf"
    print(f"[build] {device:<14} -> {rbf.name}", flush=True)
    path, elapsed, err = qcompile.compile_and_export(
        f"pkg_{tag}", VERILOG, gen_qsf(device),
        rbf_output=str(rbf), work_dir=str(WORK),
    )
    if path is None:
        print(f"  FAIL after {elapsed:.1f}s: {err[:400]}")
        return None
    print(f"  ok ({elapsed:.1f}s, {os.path.getsize(path)} B)")
    return Path(path)


def main() -> int:
    f17 = build("EP4CE6F17C8", "f17c8")
    e22 = build("EP4CE6E22C8", "e22c8")
    if f17 is None or e22 is None:
        return 1

    a, b = f17.read_bytes(), e22.read_bytes()
    print(f"\nsize  F17={len(a)}  E22={len(b)}  "
          f"{'SAME' if len(a) == len(b) else 'DIFFERENT'}")
    if a == b:
        print("\n*** RBFs are BYTE-IDENTICAL ***")
        print("    -> package change is pure bonding; whole dictionary transfers.")
    else:
        n = sum(1 for x, y in zip(a, b) if x != y)
        print(f"differing bytes: {n} / {min(len(a), len(b))}")
        print("\n--- region breakdown (zeta_rbf_diff) ---", flush=True)
        subprocess.run(
            [sys.executable,
             str(ROOT / "scripts" / "bit_workaround" / "zeta_rbf_diff.py"),
             str(f17), str(e22)],
            check=False,
        )

    # ground-truth pin table for the new package
    pin = WORK / "pkg_e22c8" / "output_files" / "pkg_e22c8.pin"
    if pin.exists():
        dest = ROOT / "results" / "ep4ce6e22c8.pin"
        dest.write_text(pin.read_text(errors="replace"))
        print(f"\n[pin] EQFP-144 pin table -> {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
