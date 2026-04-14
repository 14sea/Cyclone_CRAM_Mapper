# SPDX-License-Identifier: GPL-3.0-or-later
"""Parallel Quartus mining driver for IOB->SLICE route cells.

For each (src_pin, target_lab, target_port) combination, builds a
pair of Quartus RBFs via template_pairs.py, diffs them, and records
the delta cell set keyed as "IOB_<src_pin>-><dx>,<dy>,<dn>,<port>"
into a dedicated dataset (NOT merged into route_cells_full.json —
injection is a later manual-validation step).

One "zero" RBF per (src_pin, sec_src_pin, zero_lab) is shared across
all targets using the same src_pin.  Quartus builds are serialized
per process but the whole job pool runs in parallel across workers.

Usage:
    python3 mine_iob_routes.py \
        --src-pins E16,E15,M16 \
        --targets "10,4,0,dataa;10,4,0,datab;10,4,0,datac;10,4,0,datad" \
        --workers 4 \
        --outdir scripts/iob_slice_mining/work \
        --result-json results/iob_route_cells.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(HERE))

from template_pairs import (  # noqa: E402
    PairConfig, make_verilog, make_qsf,
    DEFAULT_ZERO_LAB, DEFAULT_SEC_SRC, DEFAULT_PRIMARY_SINK,
    DEFAULT_SEC_SINK, CLK_PIN,
)


def _parse_targets(s: str) -> list[tuple[int, int, int, str]]:
    out = []
    for tok in s.split(";"):
        tok = tok.strip()
        if not tok:
            continue
        parts = tok.split(",")
        if len(parts) != 4:
            raise ValueError(f"bad target {tok!r} (need dx,dy,dn,port)")
        dx, dy, dn = int(parts[0]), int(parts[1]), int(parts[2])
        port = parts[3].strip()
        out.append((dx, dy, dn, port))
    return out


def _build_job(job):
    """Worker: compile one (variant, config) into an RBF at `rbf_path`."""
    sys.path.insert(0, str(REPO / "fuzz"))
    sys.path.insert(0, str(HERE))
    from template_pairs import make_verilog, make_qsf  # noqa: F401
    from runner import make_lccomb
    from compile import compile_and_export

    cfg_dict, variant, rbf_path, work_dir = job
    cfg = PairConfig(**cfg_dict)

    if Path(rbf_path).exists():
        return (cfg.tag(variant), True, "cached", str(rbf_path))

    verilog = make_verilog(cfg, variant)
    qsf = make_qsf(cfg, variant, make_lccomb)
    tag = cfg.tag(variant)

    rbf, elapsed, err = compile_and_export(
        tag, verilog, qsf,
        rbf_output=str(rbf_path),
        work_dir=str(work_dir),
    )
    if rbf:
        return (tag, True, f"{elapsed:.1f}s", str(rbf_path))
    return (tag, False, f"FAIL: {err[:200]}", str(rbf_path))


def _diff_cells(target_rbf: bytes, zero_rbf: bytes) -> list[tuple[int, int]]:
    """CRAM-only XOR cell list. Mirrors route_signatures._diff_cells."""
    from route_signatures import (
        CRC_PREAMBLE, CRC_FRAME_SIZE, CRC_DATA_SIZE,
        CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME,
    )
    cells = []
    for n in range(CRC_FIRST_CRAM_FRAME, CRC_LAST_FRAME + 1):
        s = CRC_PREAMBLE + n * CRC_FRAME_SIZE
        for off in range(s, s + CRC_DATA_SIZE):
            x = target_rbf[off] ^ zero_rbf[off]
            if not x:
                continue
            for bp in range(8):
                if (x >> bp) & 1:
                    cells.append([off, bp])
    return sorted(cells)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src-pins", required=True,
                    help="comma-separated list, e.g. E16,E15,M16")
    ap.add_argument("--targets", required=True,
                    help="semicolon-separated list, e.g. "
                         "'10,4,0,dataa;10,4,0,datab'")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--outdir", default=str(HERE / "work"))
    ap.add_argument("--result-json",
                    default=str(REPO / "results" / "iob_route_cells.json"))
    ap.add_argument("--zero-lab", default=",".join(map(str, DEFAULT_ZERO_LAB)),
                    help="Zero-LAB as 'x,y,n' (default 28,16,0)")
    ap.add_argument("--sec-src-pin", default=DEFAULT_SEC_SRC)
    ap.add_argument("--primary-sink", default=DEFAULT_PRIMARY_SINK)
    ap.add_argument("--sec-sink", default=DEFAULT_SEC_SINK)
    args = ap.parse_args()

    src_pins = [p.strip() for p in args.src_pins.split(",") if p.strip()]
    targets = _parse_targets(args.targets)
    zero_lab = tuple(int(v) for v in args.zero_lab.split(","))
    if len(zero_lab) != 3:
        print(f"zero-lab must be x,y,n (got {args.zero_lab!r})", file=sys.stderr)
        return 1

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Build job list: one "zero" per src_pin (shared across targets),
    # one "pair" per (src_pin, target).
    configs: list[PairConfig] = []
    for src in src_pins:
        for (dx, dy, dn, port) in targets:
            configs.append(PairConfig(
                src_pin=src,
                target_lab=(dx, dy, dn),
                target_port=port,
                zero_lab=zero_lab,
                sec_src_pin=args.sec_src_pin,
                primary_sink=args.primary_sink,
                sec_sink=args.sec_sink,
            ))

    jobs = []
    seen_zero = set()
    for cfg in configs:
        zero_path = outdir / f"{cfg.tag('zero')}.rbf"
        if cfg.src_pin not in seen_zero:
            jobs.append((
                {
                    "src_pin": cfg.src_pin,
                    "target_lab": cfg.target_lab,
                    "target_port": cfg.target_port,
                    "zero_lab": cfg.zero_lab,
                    "sec_src_pin": cfg.sec_src_pin,
                    "primary_sink": cfg.primary_sink,
                    "sec_sink": cfg.sec_sink,
                },
                "zero", str(zero_path), str(outdir),
            ))
            seen_zero.add(cfg.src_pin)

        pair_path = outdir / f"{cfg.tag('pair')}.rbf"
        jobs.append((
            {
                "src_pin": cfg.src_pin,
                "target_lab": cfg.target_lab,
                "target_port": cfg.target_port,
                "zero_lab": cfg.zero_lab,
                "sec_src_pin": cfg.sec_src_pin,
                "primary_sink": cfg.primary_sink,
                "sec_sink": cfg.sec_sink,
            },
            "pair", str(pair_path), str(outdir),
        ))

    print(f"[plan] {len(configs)} routes, "
          f"{len(seen_zero)} zero builds + {len(configs)} pair builds = "
          f"{len(jobs)} total Quartus builds, {args.workers} workers",
          flush=True)

    # Run Quartus builds in parallel
    failed = 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(_build_job, j): j[0]["src_pin"] + "/" + j[1]
                   for j in jobs}
        for f in as_completed(futures):
            src = futures[f]
            try:
                tag, ok, msg, path = f.result()
                status = "OK  " if ok else "FAIL"
                print(f"[{status}] {tag:45s} {msg}", flush=True)
                if not ok:
                    failed += 1
            except Exception as e:
                print(f"[ERR ] {src:45s} {e}", flush=True)
                failed += 1

    if failed:
        print(f"\n{failed} build(s) failed; partial results below", flush=True)

    # Diff every pair vs its matching zero
    print("\n[diff] computing cell deltas...", flush=True)
    results: dict[str, list[list[int]]] = {}
    for cfg in configs:
        zero_path = outdir / f"{cfg.tag('zero')}.rbf"
        pair_path = outdir / f"{cfg.tag('pair')}.rbf"
        if not zero_path.exists() or not pair_path.exists():
            print(f"  skip {cfg.tag('pair')} (missing RBF)", flush=True)
            continue
        z = zero_path.read_bytes()
        p = pair_path.read_bytes()
        cells = _diff_cells(p, z)
        dx, dy, dn = cfg.target_lab
        key = (f"IOB_{cfg.src_pin}->{dx},{dy},{dn},{cfg.target_port}")
        results[key] = cells
        print(f"  {key:45s} {len(cells)} cells", flush=True)

    payload = {
        "meta": {
            "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "zero_lab": list(zero_lab),
            "sec_src_pin": args.sec_src_pin,
            "primary_sink": args.primary_sink,
            "sec_sink": args.sec_sink,
            "clk_pin": CLK_PIN,
            "src_pins": src_pins,
            "targets": [f"{dx},{dy},{dn},{port}"
                        for (dx, dy, dn, port) in targets],
            "note": (
                "Each entry is cells(pair) XOR cells(zero) over CRAM data "
                "bytes (excludes CRC and header). The 'zero' variant has "
                "src_pin routed to zero_lab while the 'pair' has it routed "
                "to the target LE.port — so the delta includes both "
                "routes' fabric + mux-select bits. Not directly injectable "
                "into route_cells_full.json without further decomposition."
            ),
        },
        "routes": results,
    }
    out_json = Path(args.result_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2))
    print(f"\n[ok ] wrote {out_json} ({len(results)} routes)", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
