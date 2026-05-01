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


def _addr_slice(idx: int, ab: int) -> tuple[int, int]:
    """Return (hi, ab) so the addr expression is counter[hi -: ab].
    Stagger by idx so each RAM picks a different slice (prevents merging).
    """
    hi = max(ab - 1, 27 - idx)
    return hi, ab


def render_sp_block(idx: int, w: int, d: int) -> str:
    """SP: 1 read+write port, address shared."""
    ab = _addr_bits(d)
    hi, _ = _addr_slice(idx, ab)
    return f"""\
    // ---- M9K instance {idx}: SP {w}×{d} ----
    wire [{ab-1}:0] addr{idx} = counter[{hi} -: {ab}];
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


def render_sdp_block(idx: int, w: int, d: int) -> str:
    """SDP: separate read/write addresses, single clock."""
    ab = _addr_bits(d)
    hi_w, _ = _addr_slice(idx, ab)
    hi_r = max(ab - 1, hi_w - 1)
    return f"""\
    // ---- M9K instance {idx}: SDP {w}×{d} ----
    wire [{ab-1}:0] waddr{idx} = counter[{hi_w} -: {ab}];
    wire [{ab-1}:0] raddr{idx} = counter[{hi_r} -: {ab}];
    (* ramstyle = "M9K" *) reg [{w-1}:0] mem{idx} [0:{d-1}];
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem{idx}[i] = (i < {d//2}) ? {{{w}{{1'b0}}}} : {{{w}{{1'b1}}}};
    end
    reg [{w-1}:0] dout{idx}_r;
    always @(posedge CLK) begin
        if (we) mem{idx}[waddr{idx}] <= din{idx};
        dout{idx}_r <= mem{idx}[raddr{idx}];
    end
"""


def render_tdp_block(idx: int, w: int, d: int) -> str:
    """TDP: two independent read/write ports, single clock."""
    ab = _addr_bits(d)
    hi_a, _ = _addr_slice(idx, ab)
    hi_b = max(ab - 1, hi_a - 1)
    return f"""\
    // ---- M9K instance {idx}: TDP {w}×{d} ----
    wire [{ab-1}:0] addr{idx}_a = counter[{hi_a} -: {ab}];
    wire [{ab-1}:0] addr{idx}_b = counter[{hi_b} -: {ab}];
    wire we{idx}_b = ~we;
    (* ramstyle = "M9K" *) reg [{w-1}:0] mem{idx} [0:{d-1}];
    initial begin
        for (i = 0; i < {d}; i = i + 1)
            mem{idx}[i] = (i < {d//2}) ? {{{w}{{1'b0}}}} : {{{w}{{1'b1}}}};
    end
    reg [{w-1}:0] dout{idx}_a, dout{idx}_b;
    always @(posedge CLK) begin
        if (we)        mem{idx}[addr{idx}_a] <= din{idx};
        dout{idx}_a <= mem{idx}[addr{idx}_a];
    end
    always @(posedge CLK) begin
        if (we{idx}_b) mem{idx}[addr{idx}_b] <= ~din{idx};
        dout{idx}_b <= mem{idx}[addr{idx}_b];
    end
"""


def render_rom_block(idx: int, w: int, d: int) -> str:
    """ROM: read-only with init data."""
    ab = _addr_bits(d)
    hi, _ = _addr_slice(idx, ab)
    return f"""\
    // ---- M9K instance {idx}: ROM {w}×{d} ----
    wire [{ab-1}:0] addr{idx} = counter[{hi} -: {ab}] ^ {{{ab}{{KEY3}}}};
    (* ramstyle = "M9K" *) reg [{w-1}:0] mem{idx} [0:{d-1}];
    integer j{idx};
    initial begin
        for (j{idx} = 0; j{idx} < {d}; j{idx} = j{idx} + 1)
            mem{idx}[j{idx}] = j{idx}[{w-1}:0] ^ {{{w}{{1'b1}}}};
    end
    reg [{w-1}:0] dout{idx}_r;
    always @(posedge CLK) dout{idx}_r <= mem{idx}[addr{idx}];
"""


_BLOCK_RENDERERS = {
    "sp":  (render_sp_block,  False),  # has dout{idx}_r
    "sdp": (render_sdp_block, False),
    "tdp": (render_tdp_block, True),   # has dout{idx}_a + dout{idx}_b
    "rom": (render_rom_block, False),
}


def render_verilog(instances: list[tuple[str, int, int, int, int, int]]) -> str:
    """Generate the multi-M9K Verilog module (any mix of sp/sdp/tdp/rom)."""
    body_blocks: list[str] = []
    led_terms: list[str] = []
    din_decls: list[str] = []
    for idx, (mode, w, d, x, y, n) in enumerate(instances):
        if mode not in _BLOCK_RENDERERS:
            raise SystemExit(f"unknown mode {mode!r}; "
                             f"expected one of {list(_BLOCK_RENDERERS)}")
        renderer, has_b_port = _BLOCK_RENDERERS[mode]
        body_blocks.append(renderer(idx, w, d))
        if mode == "rom":
            led_terms.append(f"^dout{idx}_r")
        elif has_b_port:
            led_terms.append(f"^dout{idx}_a ^ ^dout{idx}_b")
        else:
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
