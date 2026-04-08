# SPDX-License-Identifier: GPL-3.0-or-later
"""Port coverage mining — dataa / datac / datad across the 15 green islands.

The existing `route_cells.json` has 1050/1050 routes on **datab only**, which
means FASM can only emit designs where every LUT reads its "live" signal on
datab. Any real 2/3/4-input LUT design needs dataa/datac/datad routed cells
in the signature table too.

This driver:
  1. Loads the 15 canonical green-island sources.
  2. For each source, picks up to MAX_DSTS_PER_SRC destinations from its
     existing datab corpus (so the new ports land on already-proven legal
     geometries — no yellow-zone surprises).
  3. Fans out Quartus compiles across N parallel workers, each with its own
     work directory to avoid `db/` lockfile collisions.
  4. Writes into results/rbf/lits_pair_...{port}.rbf using the same naming
     pattern as the datab corpus, so `route_signatures.py` can ingest the
     new files with no code changes.

Usage:
    python3 fuzz/port_mine.py              # all 3 ports, 8 workers
    python3 fuzz/port_mine.py --ports dataa --workers 12
"""
import argparse
import json
import multiprocessing as mp
import os
import shutil
import sys
import time
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)

# The 15 silicon-validated green islands.
GREEN_SOURCES = [
    (4, 4), (10, 4), (10, 10), (10, 14), (13, 10),
    (16, 4), (16, 8), (16, 14), (19, 14), (22, 12),
    (22, 16), (25, 6), (28, 10), (28, 18), (31, 12),
]

MAX_DSTS_PER_SRC = 15  # cap compiles per (src, port); covers ~225 routes/port
DEFAULT_PORTS = ("dataa", "datac", "datad")


def load_datab_dsts_per_source():
    """Return {(sx,sy): [(dx,dy,dn), ...]} from the existing datab corpus."""
    cells = json.loads((Path(REPO) / "results" / "route_cells.json").read_text())
    by_src = {}
    for rk in cells:
        lhs, rhs = rk.split("->")
        sx, sy = map(int, lhs.split(","))
        dx, dy, dn, port = rhs.split(",")
        if port != "datab":
            continue
        by_src.setdefault((sx, sy), []).append((int(dx), int(dy), int(dn)))
    return by_src


def worker_init(worker_id):
    """Each worker gets a private work dir to avoid Quartus db/ collisions."""
    work_root = Path(REPO) / "work" / f"port_mine_w{worker_id}"
    work_root.mkdir(parents=True, exist_ok=True)
    # Stash on module so worker_compile can see it.
    import builtins
    builtins._PORT_MINE_WORK = str(work_root)


def worker_compile(task):
    """task = (sx, sy, dx, dy, dn, port). Runs one compile, returns status."""
    sx, sy, dx, dy, dn, port = task
    import builtins
    work_dir = getattr(builtins, "_PORT_MINE_WORK", None)

    # Lazy imports so each worker has its own module state.
    from verilog_gen import gen_two_luts_single_input
    from qsf_gen import gen_qsf, make_lccomb
    from compile import compile_and_export

    tag = f"lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N{dn}_{port}"
    out = Path(REPO) / "results" / "rbf" / f"{tag}.rbf"
    if out.exists():
        return ("SKIP", tag, 0.0, "exists")

    # mask2 MUST depend on the connect_port, otherwise Quartus sees lut2's
    # truth table as a function of a 1'b0-tied input and collapses the route
    # into whatever port it prefers (usually datab). Use the identity TT per
    # input: dataa=0xAAAA, datab=0xCCCC, datac=0xF0F0, datad=0xFF00.
    mask2_by_port = {"dataa": 0xAAAA, "datab": 0xCCCC, "datac": 0xF0F0, "datad": 0xFF00}
    mask2 = mask2_by_port[port]
    verilog = gen_two_luts_single_input(0x8888, mask2, connect_port=port)
    placement = {
        "lut1": make_lccomb(sx, sy, 0),
        "lut2": make_lccomb(dx, dy, dn),
    }
    qsf = gen_qsf(placement=placement, seed=1)

    t0 = time.time()
    try:
        rbf, elapsed, err = compile_and_export(
            tag, verilog, qsf, rbf_output=str(out), work_dir=work_dir
        )
    except Exception as e:
        return ("ERR", tag, time.time() - t0, str(e))
    if rbf:
        return ("OK", tag, elapsed, "")
    return ("FAIL", tag, elapsed, err or "no rbf")


def _worker_loop(wid, qin, qout):
    worker_init(wid)
    while True:
        t = qin.get()
        if t is None:
            return
        qout.put(worker_compile(t))


def build_tasks(ports, max_dsts):
    by_src = load_datab_dsts_per_source()
    tasks = []
    for (sx, sy) in GREEN_SOURCES:
        dsts = by_src.get((sx, sy), [])[:max_dsts]
        if not dsts:
            print(f"  WARN: no datab corpus for ({sx},{sy}), skipping", flush=True)
            continue
        for port in ports:
            for (dx, dy, dn) in dsts:
                tasks.append((sx, sy, dx, dy, dn, port))
    return tasks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ports", nargs="+", default=list(DEFAULT_PORTS),
                    choices=["dataa", "datab", "datac", "datad"])
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-dsts", type=int, default=MAX_DSTS_PER_SRC)
    args = ap.parse_args()

    tasks = build_tasks(args.ports, args.max_dsts)
    total = len(tasks)
    print(f"port_mine: {len(args.ports)} port(s) × {len(GREEN_SOURCES)} src "
          f"× up to {args.max_dsts} dst = {total} compiles, "
          f"{args.workers} workers", flush=True)

    t0 = time.time()
    ok = fail = skip = err = 0
    # Spawn N workers directly; each gets a private work dir via its wid.
    ctx = mp.get_context("spawn")
    q_in = ctx.Queue()
    q_out = ctx.Queue()
    for t in tasks:
        q_in.put(t)
    for _ in range(args.workers):
        q_in.put(None)  # sentinel

    procs = [ctx.Process(target=_worker_loop, args=(i, q_in, q_out))
             for i in range(args.workers)]
    for p in procs:
        p.start()

    done = 0
    while done < total:
        status, tag, elapsed, msg = q_out.get()
        done += 1
        if status == "OK":
            ok += 1
        elif status == "SKIP":
            skip += 1
        elif status == "FAIL":
            fail += 1
        else:
            err += 1
        if done % 10 == 0 or status not in ("OK", "SKIP"):
            print(f"  [{done:4d}/{total}] {status:4s} {tag} ({elapsed:.1f}s) {msg}",
                  flush=True)

    for p in procs:
        p.join()

    wall = time.time() - t0
    print(f"\ndone in {wall:.1f}s: {ok} ok / {skip} skip / {fail} fail / {err} err",
          flush=True)

    # Clean per-worker work dirs (keep the RBFs, not the Quartus scratch).
    for i in range(args.workers):
        scratch = Path(REPO) / "work" / f"port_mine_w{i}"
        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)
    print("cleaned work/port_mine_w*", flush=True)
    return 0 if fail == 0 and err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
