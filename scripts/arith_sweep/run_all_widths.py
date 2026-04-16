#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Python driver for the full arith sweep (widths 2..8 lo/up + 9..15 xh + 17..32 ml).

Spawns up to 8 concurrent Quartus runs (quartus_map -> quartus_fit ->
quartus_asm -> quartus_cpf) per design dir under tmp/arith_sweep/.  Skips
dirs that already have output_files/top.rbf so partial reruns are cheap.

Mirrors the behaviour of run_all_widths.sh; provided because the launching
shell sandbox refuses to spawn shell-script wrappers but allows direct
Python + subprocess.

Usage (from repo root):
    python3 scripts/arith_sweep/run_all_widths.py
"""
from __future__ import annotations
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "tmp" / "arith_sweep"
QUARTUS_BIN = Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin"

CMDS = [
    ["quartus_map", "top"],
    ["quartus_fit", "top"],
    ["quartus_asm", "top"],
    [
        "quartus_cpf",
        "-c",
        "-o",
        "bitstream_compression=off",
        "output_files/top.sof",
        "output_files/top.rbf",
    ],
]


def build_one(d: Path) -> tuple[str, int, str]:
    """Run all four Quartus stages in d.  Returns (tag, rc, last_log_tail)."""
    env = os.environ.copy()
    env["PATH"] = f"{QUARTUS_BIN}:" + env.get("PATH", "")
    last_tail = ""
    for cmd in CMDS:
        log = d / f"{cmd[0].replace('quartus_', '')}.log"
        with log.open("w") as fh:
            r = subprocess.run(cmd, cwd=d, stdout=fh, stderr=subprocess.STDOUT, env=env)
        if r.returncode != 0:
            try:
                last_tail = log.read_text(errors="replace")[-400:]
            except Exception:
                last_tail = "(log read failed)"
            return d.name, r.returncode, f"{cmd[0]} FAILED: {last_tail}"
    return d.name, 0, "ok"


def candidate_dirs() -> list[Path]:
    out: list[Path] = []
    for child in sorted(WORK.iterdir()):
        if not child.is_dir():
            continue
        # tag patterns: c{w}_lo / c{w}_up / i{w}_lo / i{w}_up,
        #               c{w}_xh / i{w}_xh, c{w}_ml / i{w}_ml
        name = child.name
        if not (name.startswith("c") or name.startswith("i")):
            continue
        if not (name.endswith("_lo") or name.endswith("_up") or
                name.endswith("_xh") or name.endswith("_ml")):
            continue
        if not (child / "top.qsf").exists():
            continue
        out.append(child)
    return out


def main() -> int:
    dirs = candidate_dirs()
    todo = []
    for d in dirs:
        if (d / "output_files" / "top.rbf").exists():
            print(f"SKIP {d.name} (already built)")
            continue
        todo.append(d)
    print(f"Launching {len(todo)} builds (parallel cap 8)...", flush=True)

    failures = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(build_one, d): d for d in todo}
        for f in as_completed(futs):
            tag, rc, msg = f.result()
            if rc == 0:
                print(f"DONE {tag}", flush=True)
            else:
                print(f"FAIL {tag} rc={rc} :: {msg}", flush=True)
                failures.append(tag)
    print(f"ALL_BUILDS_DONE failures={len(failures)}")
    if failures:
        print("Failed tags:", " ".join(failures))
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
