# SPDX-License-Identifier: GPL-3.0-or-later
"""Do the codec's XOR-DELTAS survive the F17->E22 package change?

The codecs in this repo are all XOR-delta based (Pitfall #5): what matters is
not whether two devices' absolute RBFs match, but whether

    delta = design_A ^ design_B

is the same cell set on both packages.  This builds a pair of designs
(y = a&b  and  y = a^b, both LOC'd to the same LE, all ports VIRTUAL_PIN)
under EP4CE6F17C8 and EP4CE6E22C8 and compares the two deltas cell-for-cell.

Equal deltas => LutCodec / the mined dictionary transfer to the new board
unchanged, and only the IOB / header layer needs re-mining.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "fuzz"))

import compile as qcompile  # noqa: E402

FAMILY = "Cyclone IV E"
TX, TY, TN = 10, 10, 0
WORK = ROOT / "tmp" / "pkg_port"
OUT = WORK / "rbf"
PRE = 32

DEVICES = {"f17c8": "EP4CE6F17C8", "e22c8": "EP4CE6E22C8"}
EXPRS = {"and": "a & b", "xor": "a ^ b"}


def verilog(expr: str) -> str:
    return f"""\
module fuzz_top(input wire a, input wire b, input wire c, input wire d,
                output wire y);
    lut_inst_mod lut_inst(.a(a), .b(b), .c(c), .d(d), .y(y));
endmodule

module lut_inst_mod(input wire a, input wire b, input wire c, input wire d,
                    output wire y);
    assign y = {expr};
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


def build(dev_tag: str, expr_tag: str) -> Path | None:
    OUT.mkdir(parents=True, exist_ok=True)
    rbf = OUT / f"d_{dev_tag}_{expr_tag}.rbf"
    path, elapsed, err = qcompile.compile_and_export(
        f"d_{dev_tag}_{expr_tag}", verilog(EXPRS[expr_tag]),
        gen_qsf(DEVICES[dev_tag]), rbf_output=str(rbf), work_dir=str(WORK),
    )
    print(f"[build] {DEVICES[dev_tag]:<12} {expr_tag:<4} "
          f"{'ok' if path else 'FAIL'} ({elapsed:.1f}s)"
          + ("" if path else f" {err[:200]}"), flush=True)
    return Path(path) if path else None


def cells(p: Path, q: Path) -> set[tuple[int, int]]:
    """XOR delta as a {(byte_offset, bit_position)} set, CRC bytes excluded."""
    a, b = p.read_bytes(), q.read_bytes()
    out = set()
    for off, (x, y) in enumerate(zip(a, b)):
        if x == y or (off - PRE) % 210 >= 208:   # skip frame CRC bytes
            continue
        for bp in range(8):
            if (x ^ y) & (1 << bp):
                out.add((off, bp))
    return out


def main() -> int:
    rbfs = {}
    for dev in DEVICES:
        for ex in EXPRS:
            r = build(dev, ex)
            if r is None:
                return 1
            rbfs[(dev, ex)] = r

    d17 = cells(rbfs[("f17c8", "and")], rbfs[("f17c8", "xor")])
    d22 = cells(rbfs[("e22c8", "and")], rbfs[("e22c8", "xor")])

    print(f"\ndelta F17C8 (and^xor): {len(d17)} cells")
    print(f"delta E22C8 (and^xor): {len(d22)} cells")
    only17, only22 = d17 - d22, d22 - d17
    print(f"shared: {len(d17 & d22)}   F17-only: {len(only17)}   "
          f"E22-only: {len(only22)}")

    if d17 == d22:
        print("\n*** DELTAS IDENTICAL — LutCodec transfers to EQFP-144 "
              "unchanged. ***")
        return 0
    print("\n!!! deltas differ !!!")
    for tag, s in (("F17-only", only17), ("E22-only", only22)):
        for off, bp in sorted(s)[:20]:
            print(f"  {tag}: off={off} (0x{off:X}) bp={bp} "
                  f"frame={(off - PRE) // 210}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
