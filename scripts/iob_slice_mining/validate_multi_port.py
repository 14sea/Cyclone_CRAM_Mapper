# SPDX-License-Identifier: GPL-3.0-or-later
"""Validation driver: probe Quartus port canonicalization via multi-input LUT.

Runs the 4 variants declared in `template_multi_port.VARIANTS` for ONE
(pin_under_test, control_pin, target_lab) triple, then computes pairwise
CRAM-delta differences to answer a single question:

   Does Quartus honor Verilog port binding when the LUT has two live
   inputs with an asymmetric `lut_mask`, or does it still canonicalize?

Procedure:

  1. Compile 4 variants in parallel (ThreadPoolExecutor, max_workers=4).
     Each variant is an independent Quartus full-flow build + cpf.
     Retries license-wait errors up to 3 times.

  2. For each RBF, compute CRAM-delta vs a shared baseline (the closest
     "zero"-style single-input pair RBF already on disk, or fall back to
     `results/rbf/nv_zero_global.rbf`).  The choice of baseline does NOT
     affect the pairwise diffs between variants, only the absolute cell
     counts reported per variant.

  3. Build a 4x4 pairwise symmetric-difference matrix and emit the
     VERDICT:
         SUCCESS  — every V_i vs V_j pair differs by >= 15 cells
         FAILED   — any pair differs by <= 5 cells (canonicalization
                    persists)
         AMBIGUOUS — something in between; requires inspection

Usage (defaults wire E16 as pin-under-test, E15 as control, LAB(10,4,0)):

    python3 validate_multi_port.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "fuzz"))
sys.path.insert(0, str(HERE))

from template_multi_port import (  # noqa: E402
    MultiPortConfig, MultiPort4InConfig, VARIANTS, VARIANTS_4IN,
    make_verilog, make_qsf, make_verilog_4in, make_qsf_4in,
    DEFAULT_TARGET_LAB,
)


def _build_one(job):
    """Worker: compile one variant to an RBF at `rbf_path`.  Retries
    license-wait errors up to 3 times with exponential backoff."""
    sys.path.insert(0, str(REPO / "fuzz"))
    sys.path.insert(0, str(HERE))
    from template_multi_port import (
        MultiPortConfig, MultiPort4InConfig,
        make_verilog, make_qsf, make_verilog_4in, make_qsf_4in,
    )
    from runner import make_lccomb
    from compile import compile_and_export

    cfg_dict, rbf_path, work_dir, mode = job
    if mode == "4in":
        cfg = MultiPort4InConfig(**cfg_dict)
    else:
        cfg = MultiPortConfig(**cfg_dict)

    if Path(rbf_path).exists():
        return (cfg.variant, True, "cached", str(rbf_path))

    if mode == "4in":
        verilog = make_verilog_4in(cfg)
        qsf = make_qsf_4in(cfg, make_lccomb)
    else:
        verilog = make_verilog(cfg)
        qsf = make_qsf(cfg, make_lccomb)
    tag = cfg.tag()

    last_err = ""
    for attempt in range(3):
        rbf, elapsed, err = compile_and_export(
            tag, verilog, qsf,
            rbf_output=str(rbf_path),
            work_dir=str(work_dir),
        )
        if rbf:
            return (cfg.variant, True, f"{elapsed:.1f}s", str(rbf_path))
        last_err = err or ""
        # license-wait retry heuristics
        if "license" in last_err.lower() or "ncsim" in last_err.lower():
            time.sleep(5 * (attempt + 1))
            continue
        break
    return (cfg.variant, False, f"FAIL: {last_err[:200]}", str(rbf_path))


def _diff_cells(target_rbf: bytes, zero_rbf: bytes):
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
                    cells.append((off, bp))
    return set(cells)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pin-under-test", default="E16")
    ap.add_argument("--control-pin", default="E15")
    ap.add_argument("--ctrl1-pin", default="E15",
                    help="4in mode: CTRL1 pin")
    ap.add_argument("--ctrl2-pin", default="M16",
                    help="4in mode: CTRL2 pin")
    ap.add_argument("--ctrl3-pin", default="M15",
                    help="4in mode: CTRL3 pin")
    ap.add_argument("--mode", choices=["2in", "4in"], default="2in",
                    help="2in = round 1 template, 4in = round 2 all-ports-live")
    ap.add_argument("--target-lab",
                    default=",".join(str(v) for v in DEFAULT_TARGET_LAB),
                    help="dx,dy,dn (default 10,4,0)")
    ap.add_argument("--led-pin", default="G15")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--outdir", default=str(HERE / "work_multiport"))
    ap.add_argument("--baseline-rbf",
                    default=str(REPO / "results" / "rbf" / "nv_zero_global.rbf"),
                    help="RBF to XOR against per-variant when reporting "
                         "absolute cell counts (does NOT affect pairwise "
                         "diffs, which are computed directly from RBFs).")
    ap.add_argument("--report",
                    default=str(HERE / "validate_multi_port_result.json"))
    args = ap.parse_args()

    dx, dy, dn = (int(v) for v in args.target_lab.split(","))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.mode == "4in":
        configs = [
            MultiPort4InConfig(
                variant=v,
                pin_under_test=args.pin_under_test,
                ctrl1_pin=args.ctrl1_pin,
                ctrl2_pin=args.ctrl2_pin,
                ctrl3_pin=args.ctrl3_pin,
                target_lab=(dx, dy, dn),
                led_pin=args.led_pin,
            )
            for v in VARIANTS_4IN
        ]
    else:
        configs = [
            MultiPortConfig(
                variant=v,
                pin_under_test=args.pin_under_test,
                control_pin=args.control_pin,
                target_lab=(dx, dy, dn),
                led_pin=args.led_pin,
            )
            for v in VARIANTS
        ]

    jobs = []
    for cfg in configs:
        path = outdir / f"{cfg.tag()}.rbf"
        if args.mode == "4in":
            cfg_dict = {
                "variant": cfg.variant,
                "pin_under_test": cfg.pin_under_test,
                "ctrl1_pin": cfg.ctrl1_pin,
                "ctrl2_pin": cfg.ctrl2_pin,
                "ctrl3_pin": cfg.ctrl3_pin,
                "target_lab": cfg.target_lab,
                "led_pin": cfg.led_pin,
            }
        else:
            cfg_dict = {
                "variant": cfg.variant,
                "pin_under_test": cfg.pin_under_test,
                "control_pin": cfg.control_pin,
                "target_lab": cfg.target_lab,
                "led_pin": cfg.led_pin,
            }
        jobs.append((cfg_dict, str(path), str(outdir), args.mode))

    print(f"[plan] {len(jobs)} Quartus builds, workers={args.workers}")
    t0 = time.time()
    failed = 0
    results = {}
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_build_one, j): j[0]["variant"] for j in jobs}
        for f in as_completed(futs):
            variant = futs[f]
            try:
                tag, ok, msg, path = f.result()
                status = "OK  " if ok else "FAIL"
                print(f"[{status}] {tag:20s} {msg}", flush=True)
                if ok:
                    results[variant] = path
                else:
                    failed += 1
            except Exception as e:
                print(f"[ERR ] {variant:20s} {e}", flush=True)
                failed += 1
    dt = time.time() - t0
    print(f"[time] builds finished in {dt:.1f}s ({failed} failed)")

    if len(results) < 4:
        print(f"\nOnly {len(results)}/4 variants built; "
              "not enough to decide.", flush=True)
        return 2

    # Compute absolute cell counts vs baseline + pairwise diffs.
    base = Path(args.baseline_rbf).read_bytes()
    per_variant = {}
    for v, path in sorted(results.items()):
        rbf = Path(path).read_bytes()
        cells = _diff_cells(rbf, base)
        per_variant[v] = cells
        print(f"[delta] {v:20s} |D|={len(cells):5d} vs baseline")

    variants = sorted(per_variant)
    matrix = {v: {} for v in variants}
    minp, maxp = None, None
    for i, a in enumerate(variants):
        for j, b in enumerate(variants):
            if a == b:
                matrix[a][b] = 0
                continue
            sym = per_variant[a].symmetric_difference(per_variant[b])
            matrix[a][b] = len(sym)
            if i < j:
                if minp is None or len(sym) < minp:
                    minp = len(sym)
                if maxp is None or len(sym) > maxp:
                    maxp = len(sym)

    print("\n[matrix] pairwise symmetric-difference cell counts")
    hdr = " " * 22 + "".join(f"{v:>22s}" for v in variants)
    print(hdr)
    for a in variants:
        print(f"{a:22s}" + "".join(f"{matrix[a][b]:>22d}" for b in variants))

    if minp is None:
        verdict = "FAILED"
    elif minp >= 15:
        verdict = "SUCCESS"
    elif maxp <= 5:
        verdict = "FAILED"
    else:
        verdict = "AMBIGUOUS"

    print(f"\n[verdict] min_off_diag={minp}  max_off_diag={maxp}  -> {verdict}")

    if args.mode == "4in":
        variant_meta = {
            v: {
                "put_port": VARIANTS_4IN[v][0],
                "c1_port": VARIANTS_4IN[v][1],
                "c2_port": VARIANTS_4IN[v][2],
                "c3_port": VARIANTS_4IN[v][3],
                "lut_mask": f"0x{VARIANTS_4IN[v][4]:04X}",
                "abs_cells_vs_baseline": len(per_variant[v]),
                "rbf": results[v],
            }
            for v in variants
        }
    else:
        variant_meta = {
            v: {
                "port_binding": VARIANTS[v][0],
                "control_port": VARIANTS[v][1],
                "lut_mask": f"0x{VARIANTS[v][2]:04X}",
                "abs_cells_vs_baseline": len(per_variant[v]),
                "rbf": results[v],
            }
            for v in variants
        }

    payload = {
        "mode": args.mode,
        "pin_under_test": args.pin_under_test,
        "control_pin": args.control_pin,
        "ctrl_pins_4in": [args.ctrl1_pin, args.ctrl2_pin, args.ctrl3_pin],
        "target_lab": [dx, dy, dn],
        "led_pin": args.led_pin,
        "baseline_rbf": args.baseline_rbf,
        "variants": variant_meta,
        "pairwise_diff": matrix,
        "min_pairwise": minp,
        "max_pairwise": maxp,
        "verdict": verdict,
    }
    Path(args.report).write_text(json.dumps(payload, indent=2))
    print(f"[ok ] wrote {args.report}")

    return 0 if verdict == "SUCCESS" else (1 if verdict == "FAILED" else 3)


if __name__ == "__main__":
    sys.exit(main())
