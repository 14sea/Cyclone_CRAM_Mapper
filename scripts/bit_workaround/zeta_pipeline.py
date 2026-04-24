# SPDX-License-Identifier: GPL-3.0-or-later
"""ζ production pipeline: Quartus project / gold RBF → BIT FASM → rebuilt RBF → flash → UART verify.

Chains the steps that previously had to be run by hand:

    .qpf  →  quartus_map/fit/asm/cpf           (optional; skipped for .rbf input)
           →  quartus_gold_to_bit_fasm.py      (BIT FASM)
           →  fasm2rbf.py                       (rebuilt RBF)
           →  cmp -s rebuilt gold               (byte-identity gate — HARD FAIL if diff)
           →  openFPGALoader                    (--flash)
           →  uart_observe.py + regex match    (--uart-seconds, --expect)

Exit code 0 iff every requested gate passed. A single command suitable for CI
or an end-user "build-and-verify" flow.

Usage:
    # RBF input + round-trip verify only (no hardware):
    python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf

    # Quartus project input:
    python3 scripts/bit_workaround/zeta_pipeline.py path/to/design.qpf

    # Full end-to-end with hardware:
    python3 scripts/bit_workaround/zeta_pipeline.py gold.rbf \\
        --flash --uart-seconds 10 --baud 19200 --expect "NEORV32"
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZETA = ROOT / "scripts" / "bit_workaround" / "quartus_gold_to_bit_fasm.py"
FASM2RBF = ROOT / "fuzz" / "fasm2rbf.py"
DEFAULT_BASE = ROOT / "results" / "rbf" / "nv_zero_global.rbf"
UART_OBSERVE = ROOT / "scripts" / "uart_observe.py"
DEFAULT_LOADER = Path.home() / "see_neorv32_run_linux" / "tools" / "openFPGALoader" / "build" / "openFPGALoader"

sys.path.insert(0, str(ROOT / "scripts" / "bit_workaround"))
from zeta_rbf_diff import categorize as _rbf_categorize  # noqa: E402


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str | None:
    try:
        rc = subprocess.run(["git", "rev-parse", "HEAD"],
                            cwd=ROOT, capture_output=True, text=True, timeout=3)
        if rc.returncode == 0:
            return rc.stdout.strip()
    except Exception:
        pass
    return None


class Gate:
    """One pipeline step with its pass/fail result and a short log line."""
    def __init__(self, name: str):
        self.name = name
        self.ok: bool | None = None
        self.message: str = ""
        self.seconds: float = 0.0

    def as_dict(self):
        return {"name": self.name, "ok": self.ok, "message": self.message,
                "seconds": round(self.seconds, 3)}


def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                       timeout=timeout, errors="replace")
    return p.returncode, p.stdout, p.stderr


def quartus_project_to_rbf(qpf: Path, gate: Gate) -> Path | None:
    """Run quartus_map→fit→asm→cpf for a .qpf and return the produced .rbf."""
    proj_dir = qpf.parent
    revision = qpf.stem
    quartus_bin = os.environ.get("QUARTUS_BIN") or str(Path.home() / "intelFPGA_lite" / "21.1" / "quartus" / "bin")

    t0 = time.time()
    for tool in ("quartus_map", "quartus_fit", "quartus_asm"):
        rc, out, err = _run([os.path.join(quartus_bin, tool),
                             "--read_settings_files=on",
                             "--write_settings_files=off",
                             revision, "-c", revision],
                            cwd=proj_dir, timeout=1800)
        if rc != 0:
            gate.ok = False
            errs = [l for l in out.split("\n") if "Error" in l][:3]
            gate.message = f"{tool} rc={rc}: {'; '.join(errs)}"
            gate.seconds = time.time() - t0
            return None

    sof = proj_dir / "output_files" / f"{revision}.sof"
    if not sof.exists():
        gate.ok = False
        gate.message = f"no .sof at {sof}"
        gate.seconds = time.time() - t0
        return None

    rbf = proj_dir / "output_files" / f"{revision}.rbf"
    rc, out, err = _run([os.path.join(quartus_bin, "quartus_cpf"),
                         "-c", "-o", "bitstream_compression=off",
                         str(sof), str(rbf)], timeout=60)
    gate.seconds = time.time() - t0
    if rc != 0 or not rbf.exists():
        gate.ok = False
        gate.message = f"quartus_cpf rc={rc}: {err[:200]}"
        return None
    gate.ok = True
    gate.message = f"built {rbf.name} ({rbf.stat().st_size} B)"
    return rbf


def run_zeta(gold: Path, out_fasm: Path, base: Path, gate: Gate) -> bool:
    t0 = time.time()
    rc, out, err = _run(["python3", str(ZETA), str(gold), str(out_fasm),
                         "--base", str(base)], timeout=120)
    gate.seconds = time.time() - t0
    if rc != 0:
        gate.ok = False
        gate.message = f"ζ rc={rc}: {(err or out)[:200]}"
        return False
    gate.ok = True
    gate.message = out.strip().split("\n")[0]
    return True


def run_fasm2rbf(fasm: Path, base: Path, out_rbf: Path, gate: Gate) -> bool:
    t0 = time.time()
    rc, out, err = _run(["python3", str(FASM2RBF), str(fasm), str(base), str(out_rbf)],
                        timeout=300)
    gate.seconds = time.time() - t0
    if rc != 0:
        gate.ok = False
        gate.message = f"fasm2rbf rc={rc}: {(err or out)[:200]}"
        return False
    if not out_rbf.exists():
        gate.ok = False
        gate.message = "fasm2rbf produced no output"
        return False
    gate.ok = True
    gate.message = f"rebuilt {out_rbf.name} ({out_rbf.stat().st_size} B)"
    return True


def byte_identity(gold: Path, rebuilt: Path, gate: Gate) -> bool:
    t0 = time.time()
    g = gold.read_bytes()
    r = rebuilt.read_bytes()
    gate.seconds = time.time() - t0
    if len(g) != len(r):
        gate.ok = False
        gate.message = f"size mismatch gold={len(g)} rebuilt={len(r)}"
        return False
    diffs = sum(1 for i in range(len(g)) if g[i] != r[i])
    if diffs:
        first = next(i for i in range(len(g)) if g[i] != r[i])
        gate.ok = False
        gate.message = f"{diffs} byte diffs (first at offset {first})"
        return False
    gate.ok = True
    gate.message = f"byte-identical ({len(g)} B)"
    return True


def flash(rbf: Path, loader: Path, gate: Gate) -> bool:
    if not loader.exists():
        gate.ok = False
        gate.message = f"openFPGALoader not found at {loader}"
        return False
    t0 = time.time()
    rc, out, err = _run([str(loader), "-c", "usb-blaster", str(rbf)], timeout=120)
    gate.seconds = time.time() - t0
    if rc != 0:
        gate.ok = False
        tail = (err or out).strip().split("\n")[-1][:200]
        gate.message = f"loader rc={rc}: {tail}"
        return False
    gate.ok = True
    gate.message = "flashed"
    return True


def uart_verify(seconds: float, baud: int, port: str, expect: str | None, gate: Gate,
                log_dir: Path) -> bool:
    if not UART_OBSERVE.exists():
        gate.ok = False
        gate.message = f"uart_observe not found at {UART_OBSERVE}"
        return False
    log_dir.mkdir(parents=True, exist_ok=True)
    out_log = log_dir / "uart_log.txt"
    raw_log = log_dir / "uart_raw.bin"
    t0 = time.time()
    rc, out, err = _run(["python3", str(UART_OBSERVE),
                         "--port", port, "--baud", str(baud),
                         "--seconds", str(seconds),
                         "--out", str(out_log), "--raw", str(raw_log)],
                        timeout=int(seconds) + 30)
    gate.seconds = time.time() - t0
    if rc == 2:
        gate.ok = False
        gate.message = f"no UART bytes received in {seconds}s"
        return False
    if rc != 0:
        gate.ok = False
        gate.message = f"uart_observe rc={rc}: {(err or out)[:200]}"
        return False

    if expect is None:
        gate.ok = True
        gate.message = f"captured {raw_log.stat().st_size} B (no --expect given)"
        return True

    try:
        raw = raw_log.read_bytes().decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    if re.search(expect, raw):
        gate.ok = True
        gate.message = f"matched /{expect}/ in {raw_log.stat().st_size} B"
        return True
    gate.ok = False
    gate.message = f"no match for /{expect}/ in {raw_log.stat().st_size} B"
    return False


def emit_manifest(manifest_path: Path, *, input_path: Path, gold: Path,
                  rebuilt: Path, base: Path, gates: list) -> dict:
    """Write a sidecar JSON manifest alongside the rebuilt RBF.

    Fields chosen so that manifest-diffing two ζ builds (e.g. bootloader
    v1 vs v2) tells you what changed without re-reading either RBF.
    """
    bits = bytes_ = region_bits = region_bytes = None
    try:
        a = base.read_bytes(); b = gold.read_bytes()
        rep = _rbf_categorize(a, b)
        names = ("preamble", "header_data", "header_crc",
                 "fabric_data", "fabric_crc", "postamble")
        region_bits = {n: rep[n]["bits"] for n in names}
        region_bytes = {n: rep[n]["bytes"] for n in names}
        bits = rep["total"]["bits"]
        bytes_ = rep["total"]["bytes"]
    except Exception as exc:
        region_bits = {"error": str(exc)}

    manifest = {
        "schema_version": 1,
        "kind": "zeta_pipeline_manifest",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_head": _git_head(),
        "input":   {"path": str(input_path), "suffix": input_path.suffix},
        "gold":    {"path": str(gold),    "sha256": _sha256(gold),
                    "size": gold.stat().st_size},
        "rebuilt": {"path": str(rebuilt), "sha256": _sha256(rebuilt),
                    "size": rebuilt.stat().st_size},
        "base":    {"path": str(base),    "sha256": _sha256(base),
                    "size": base.stat().st_size},
        "zeta_bits_total": bits,
        "zeta_bytes_total": bytes_,
        "region_bits": region_bits,
        "region_bytes": region_bytes,
        "gates": [g.as_dict() for g in gates],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", type=Path, help="Quartus .qpf OR .rbf")
    ap.add_argument("--base", type=Path, default=DEFAULT_BASE,
                    help=f"baseline RBF for ζ XOR (default: {DEFAULT_BASE})")
    ap.add_argument("--workdir", type=Path, default=None,
                    help="scratch dir for intermediates (default: tmp/zeta_pipe/<stem>/)")
    ap.add_argument("--flash", action="store_true", help="flash rebuilt RBF via openFPGALoader")
    ap.add_argument("--loader", type=Path, default=DEFAULT_LOADER)
    ap.add_argument("--uart-seconds", type=float, default=0,
                    help="seconds to observe UART after flash (0 = skip)")
    ap.add_argument("--baud", type=int, default=None,
                    help="UART baud (required if --uart-seconds > 0)")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--expect", default=None,
                    help="regex; uart gate passes iff it matches the captured stream")
    ap.add_argument("--json", type=Path, default=None, help="write JSON report here")
    ap.add_argument("--manifest", type=Path, default=None,
                    help="sidecar manifest path (default: <workdir>/<stem>.manifest.json; "
                         "pass '-' to disable)")
    ap.add_argument("--rebuild-check", action="store_true",
                    help="for .qpf input: run Quartus twice and require both RBFs to be "
                         "byte-identical (catches non-deterministic builds)")
    args = ap.parse_args()

    if args.uart_seconds > 0 and args.baud is None:
        ap.error("--baud is required when --uart-seconds > 0")

    stem = args.input.stem
    workdir = args.workdir or (ROOT / "tmp" / "zeta_pipe" / stem)
    workdir.mkdir(parents=True, exist_ok=True)

    report: dict = {"input": str(args.input), "workdir": str(workdir), "gates": []}
    gates: list[Gate] = []

    # Stage 0: resolve input → gold RBF
    if args.input.suffix == ".qpf":
        g0 = Gate("quartus_build")
        gates.append(g0)
        print(f"[stage] {g0.name}: running quartus_map/fit/asm/cpf on {args.input}")
        gold = quartus_project_to_rbf(args.input, g0)
        if gold is None:
            print(f"  FAIL: {g0.message}")
            _finish(report, gates, args, ok=False)
            sys.exit(1)
        print(f"  OK: {g0.message} ({g0.seconds:.1f}s)")

        if args.rebuild_check:
            g0b = Gate("quartus_rebuild_check"); gates.append(g0b)
            print(f"[stage] {g0b.name}: re-running Quartus on {args.input} "
                  "and byte-comparing RBFs")
            v1_copy = workdir / f"{stem}.rbf.v1"
            shutil.copyfile(gold, v1_copy)
            # re-run; Quartus overwrites the same output_files/<rev>.rbf
            gold2 = quartus_project_to_rbf(args.input, g0b)
            if gold2 is None:
                print(f"  FAIL: {g0b.message}")
                _finish(report, gates, args, ok=False); sys.exit(1)
            a = v1_copy.read_bytes(); b = gold2.read_bytes()
            if a != b:
                diffs = sum(1 for i in range(len(a)) if a[i] != b[i])
                g0b.ok = False
                g0b.message = (f"Quartus non-deterministic: {diffs} byte diffs "
                               f"between v1 and v2 builds")
                print(f"  FAIL: {g0b.message}")
                _finish(report, gates, args, ok=False); sys.exit(1)
            g0b.ok = True
            g0b.message = "Quartus deterministic: v1 == v2 byte-identical"
            print(f"  OK: {g0b.message} ({g0b.seconds:.1f}s)")
            # keep gold = first build
    elif args.input.suffix == ".rbf":
        gold = args.input
        if args.rebuild_check:
            print("[warn] --rebuild-check ignored for .rbf input (no Quartus build to re-run)")
    else:
        ap.error(f"unrecognized input extension: {args.input.suffix} (want .qpf or .rbf)")

    if gold.stat().st_size != 368011:
        print(f"gold {gold} size {gold.stat().st_size} != 368011")
        sys.exit(1)

    # Stage 1: ζ — gold RBF → BIT FASM
    g1 = Gate("zeta_to_fasm"); gates.append(g1)
    fasm_path = workdir / f"{stem}.bit.fasm"
    print(f"[stage] {g1.name}: {gold.name} → {fasm_path.name}")
    if not run_zeta(gold, fasm_path, args.base, g1):
        print(f"  FAIL: {g1.message}")
        _finish(report, gates, args, ok=False); sys.exit(1)
    print(f"  OK: {g1.message} ({g1.seconds:.1f}s)")

    # Stage 2: fasm2rbf
    g2 = Gate("fasm_to_rbf"); gates.append(g2)
    rebuilt = workdir / f"{stem}.rebuilt.rbf"
    print(f"[stage] {g2.name}: {fasm_path.name} → {rebuilt.name}")
    if not run_fasm2rbf(fasm_path, args.base, rebuilt, g2):
        print(f"  FAIL: {g2.message}")
        _finish(report, gates, args, ok=False); sys.exit(1)
    print(f"  OK: {g2.message} ({g2.seconds:.1f}s)")

    # Stage 3: byte-identity gate (the hard safety rail)
    g3 = Gate("byte_identity"); gates.append(g3)
    print(f"[stage] {g3.name}: cmp rebuilt vs gold")
    if not byte_identity(gold, rebuilt, g3):
        print(f"  FAIL: {g3.message}")
        _finish(report, gates, args, ok=False); sys.exit(1)
    print(f"  OK: {g3.message}")

    # Stage 4: flash
    if args.flash:
        g4 = Gate("flash"); gates.append(g4)
        print(f"[stage] {g4.name}: openFPGALoader -c usb-blaster {rebuilt.name}")
        if not flash(rebuilt, args.loader, g4):
            print(f"  FAIL: {g4.message}")
            _finish(report, gates, args, ok=False); sys.exit(1)
        print(f"  OK: {g4.message} ({g4.seconds:.1f}s)")

    # Stage 5: uart observe / regex match
    if args.uart_seconds > 0:
        g5 = Gate("uart_verify"); gates.append(g5)
        print(f"[stage] {g5.name}: {args.port}@{args.baud} for {args.uart_seconds}s"
              + (f", expect /{args.expect}/" if args.expect else ""))
        if not uart_verify(args.uart_seconds, args.baud, args.port, args.expect, g5, workdir):
            print(f"  FAIL: {g5.message}")
            _finish(report, gates, args, ok=False); sys.exit(1)
        print(f"  OK: {g5.message} ({g5.seconds:.1f}s)")

    # Sidecar manifest — default on, `--manifest -` disables
    if str(args.manifest) != "-":
        mpath = args.manifest or (workdir / f"{stem}.manifest.json")
        try:
            emit_manifest(mpath, input_path=args.input, gold=gold,
                          rebuilt=rebuilt, base=args.base, gates=gates)
            print(f"[manifest] wrote {mpath}")
        except Exception as exc:
            print(f"[manifest] WARN: failed to emit sidecar: {exc}")

    _finish(report, gates, args, ok=True)
    print(f"\n[OK] all {len(gates)} gates passed. rebuilt={rebuilt}")


def _finish(report, gates, args, ok: bool):
    report["gates"] = [g.as_dict() for g in gates]
    report["ok"] = ok
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
