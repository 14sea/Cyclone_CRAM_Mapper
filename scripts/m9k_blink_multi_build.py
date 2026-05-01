# SPDX-License-Identifier: GPL-3.0-or-later
r"""Multi-M9K Quartus reference builder.

Generates a single-module Verilog with N independent altsyncram
instances, LOCs each to a distinct M9K site, and runs the standard
Quartus flow.  The resulting RBF lets us isolate inter-M9K shared
configuration cells (M9K_MULTI_INFRA) from per-site mode cells:

  multi_diff_nv = (multi_M9K.rbf XOR nv_zero_global) ∩ block_band
  per_site_diff = union of solo single-M9K diff_nv buckets at the
                  same (mode, w, d, X, Y) tuples
  M9K_MULTI_INFRA candidate = multi_diff_nv \ per_site_diff
                              (cells that emerge only with co-residency)
  solo_isolation_artifacts = per_site_diff \ multi_diff_nv
                             (cells solo emits but multi doesn't —
                              probably "isolated M9K" markers)

Step A scope: SP 9×512 only, N=2.  Future steps extend to mixed
modes and larger N.

Usage:
    python3 scripts/m9k_blink_multi_build.py \\
        --instances "sp,9,512,15,4;sp,9,512,15,10" \\
        --tag 2m9k_x15_y4_y10_sp9x512
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from m9k_blink_modes import _addr_bits, _din_expr  # noqa: E402

WORK_ROOT = ROOT / "tmp"


def parse_instances(spec: str) -> list[tuple[str, int, int, int, int, int]]:
    """Parse 'mode,w,d,x,y[,n];...' → list of (mode, w, d, x, y, n)."""
    out: list[tuple[str, int, int, int, int, int]] = []
    for chunk in spec.split(";"):
        parts = chunk.strip().split(",")
        if len(parts) < 5:
            raise SystemExit(f"bad instance spec {chunk!r}")
        mode = parts[0]
        w, d, x, y = (int(parts[i]) for i in (1, 2, 3, 4))
        n = int(parts[5]) if len(parts) >= 6 else 0
        out.append((mode, w, d, x, y, n))
    return out


def render_sp_block(idx: int, w: int, d: int, addr_lo_bit: int) -> str:
    """Verilog snippet for one SP 9×512-style M9K instance.

    addr_lo_bit picks a different counter slice per instance so the
    runtime addr buses don't merge logically (forcing Quartus to keep
    independent altsyncram instances).
    """
    ab = _addr_bits(d)
    din = _din_expr(w)
    return f"""\
    // ---- M9K instance {idx}: SP {w}×{d} ----
    wire [{ab-1}:0] addr{idx} = counter[{addr_lo_bit + ab - 1} -: {ab}];
    (* ramstyle = "M9K" *) reg [{w-1}:0] mem{idx} [0:{d-1}];
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem{idx}[i] = (i < {d//2}) ? {{{w}{{1'b0}}}} : {{{w}{{1'b1}}}};
    end
    reg [{w-1}:0] dout{idx}_r;
    always @(posedge CLK) begin
        if (we) mem{idx}[addr{idx}] <= din{idx};
        dout{idx}_r <= mem{idx}[addr{idx}];
    end
"""


def render_verilog(instances: list[tuple[str, int, int, int, int, int]]) -> str:
    """Generate the multi-M9K Verilog module (Step A: SP-only)."""
    body_blocks: list[str] = []
    led_terms: list[str] = []
    din_decls: list[str] = []
    for idx, (mode, w, d, x, y, n) in enumerate(instances):
        if mode != "sp":
            raise SystemExit(f"Step A scope is sp-only; got {mode}")
        # Stagger addr bits so each RAM picks distinct counter slices.
        addr_lo = max(0, 27 - _addr_bits(d) - idx)
        body_blocks.append(render_sp_block(idx, w, d, addr_lo))
        led_terms.append(f"^dout{idx}_r")
        din_decls.append(f"    wire [{w-1}:0] din{idx} = {_din_expr(w)};")
    return f"""\
module m9k_multi(
    input  wire CLK,
    input  wire KEY2,
    input  wire KEY3,
    output wire LED0
);
    reg [27:0] counter = 28'd0;
    always @(posedge CLK) counter <= counter + 1'b1;

    wire we = ~KEY2;
{chr(10).join(din_decls)}

    integer i;
{chr(10).join(body_blocks)}
    assign LED0 = {' ^ '.join(led_terms)};
endmodule
"""


def render_qsf(instances: list[tuple[str, int, int, int, int, int]]) -> str:
    head = """\
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY m9k_multi
set_global_assignment -name VERILOG_FILE fuzz_top.v
set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_global_assignment -name SEED 1
set_location_assignment PIN_E1  -to CLK
set_location_assignment PIN_E16 -to KEY2
set_location_assignment PIN_M16 -to KEY3
set_location_assignment PIN_G15 -to LED0
"""
    locs: list[str] = []
    for idx, (mode, w, d, x, y, n) in enumerate(instances):
        # Variable name `mem{idx}` → inferred altsyncram instance
        # `altsyncram:mem{idx}_rtl_0`.
        locs.append(
            f'set_location_assignment M9K_X{x}_Y{y}_N{n} '
            f'-to "altsyncram:mem{idx}_rtl_0"'
        )
    return head + "\n".join(locs) + "\n"


def build_multi(instances: list[tuple[str, int, int, int, int, int]],
                tag: str) -> Path | None:
    work = WORK_ROOT / f"m9k_multi_{tag}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "fuzz_top.v").write_text(render_verilog(instances))
    (work / "fuzz_top.qsf").write_text(render_qsf(instances))
    rbf = work / f"m9k_multi_{tag}.rbf"
    if rbf.exists():
        print(f"  exists: {rbf.relative_to(ROOT)}")
        return rbf
    qbin = Path.home() / "intelFPGA_lite/21.1/quartus/bin"
    env = {**os.environ, "PATH": f"{qbin}:" + os.environ.get("PATH", "")}
    for tool in ("quartus_map", "quartus_fit", "quartus_asm"):
        r = subprocess.run([str(qbin / tool), "fuzz_top",
                            "--read_settings_files=on",
                            "--write_settings_files=off"],
                           cwd=work, env=env, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"  FAIL {tool}: {r.stderr[-300:]}")
            return None
    r = subprocess.run([str(qbin / "quartus_cpf"), "-c",
                        "-o", "bitstream_compression=off",
                        "output_files/fuzz_top.sof", str(rbf)],
                       cwd=work, env=env, capture_output=True, text=True)
    if r.returncode != 0 or not rbf.exists():
        print(f"  FAIL cpf: {r.stderr[-300:]}")
        return None
    return rbf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", required=True,
                    help="semicolon-separated mode,w,d,x,y[,n] tuples")
    ap.add_argument("--tag", required=True,
                    help="label for the build dir (tmp/m9k_multi_<tag>/)")
    args = ap.parse_args()
    instances = parse_instances(args.instances)
    print(f"=== building {len(instances)}-M9K reference: {args.tag} ===")
    for mode, w, d, x, y, n in instances:
        print(f"  {mode} {w}x{d} @ M9K_X{x}_Y{y}_N{n}")
    rbf = build_multi(instances, args.tag)
    if rbf:
        print(f"  OK -> {rbf.relative_to(ROOT)}")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
