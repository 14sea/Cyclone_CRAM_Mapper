# SPDX-License-Identifier: GPL-3.0-or-later
"""Plan D' compile factory: produce one nv_pair_*.rbf per NEORV32 edge.

Reads edge list from results/plan_d_prime_edges.json (built by
plan_d_prime_dryrun.py). For each edge, compiles a single-input clocked
two-LUT design with lut1 at the source LCCOMB and lut2 at the dst LCCOMB
feeding dst_port. Uses DEVICE=EP4CE10F17C8 so jailbreak LABs (X=5,9,14,
30,32,33 / Y=15) compile fine alongside CE6-whitelist LABs.

Per-task work dir: work/nvfac/{tag}/, wiped after success.
Checkpoint:         results/plan_d_prime_status.json (atomic write).
Failure log:        results/plan_d_prime_failures.json.
SIGINT safe:        handler dumps state + cancels pending futures.
Auto-retry:         up to 2 retries per edge with 5s backoff.
Parallelism:        WORKERS env var (default 12).

Launch:
    WORKERS=12 nohup python3 -u fuzz/plan_d_prime_factory.py \
        > tmp/nvfac.log 2>&1 &
"""
import json, os, sys, signal, shutil, time, traceback
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, wait, FIRST_COMPLETED

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from verilog_gen import gen_two_luts_single_input_clocked
from compile import compile_and_export
from config import FAMILY, FUZZ_PINS, QSF_OPTIMIZATIONS_OFF

CE10 = "EP4CE10F17C8"
JAILBREAK_X = {5, 9, 14, 30, 32, 33}
JAILBREAK_Y = {15}
# Valid LAB coordinates for the CE10 jailbreak fabric. X=15,20,27 are non-LAB
# (M9K/mult); X∈{0,1,2} are IO rings; Y∈{0,1,22} are IO/edge rows. FF_X0_* etc.
# appear in the STA dump as IO-register sources and must be filtered out.
VALID_LAB_X = set(range(3, 34)) - {15, 20, 27}
VALID_LAB_Y = set(range(2, 22))
VALID_LE_N = set(range(0, 32, 2))  # LEs use even N; odd N are FF-only or invalid

def _is_valid_le(x, y, n):
    return x in VALID_LAB_X and y in VALID_LAB_Y and n in VALID_LE_N

EDGES_FILE = ROOT / "results" / "plan_d_prime_edges.json"
STATUS_FILE = ROOT / "results" / "plan_d_prime_status.json"
FAIL_FILE = ROOT / "results" / "plan_d_prime_failures.json"
RBF_DIR = ROOT / "results" / "rbf"
WORK = ROOT / "work" / "nvfac"

WORKERS = int(os.environ.get("WORKERS", "12"))
RETRIES = 2
BACKOFF = 5.0
MIN_FREE_GB = 5.0  # pause if disk below this

# --- QSF generator (CE10 device, minimal, per-edge) ---
def gen_qsf_ce10(placement, seed=1):
    L = [
        f'set_global_assignment -name FAMILY "{FAMILY}"',
        f'set_global_assignment -name DEVICE {CE10}',
        'set_global_assignment -name TOP_LEVEL_ENTITY fuzz_top',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name MIN_CORE_JUNCTION_TEMP 0',
        'set_global_assignment -name MAX_CORE_JUNCTION_TEMP 85',
        'set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR 1',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        f'set_global_assignment -name SEED {seed}',
    ]
    for name, val in QSF_OPTIMIZATIONS_OFF:
        if val in ("OFF", "ON"):
            L.append(f'set_global_assignment -name {name} {val}')
        else:
            L.append(f'set_global_assignment -name {name} "{val}"')
    for sig, pin in FUZZ_PINS.items():
        L.append(f'set_location_assignment {pin} -to {sig}')
    L.append('set_location_assignment PIN_E1 -to CLK')
    for node, loc in placement.items():
        L.append(f'set_location_assignment {loc} -to "{node}"')
    return "\n".join(L) + "\n"


def _tag(edge):
    sx, sy, sn, kind, dx, dy, dn, port = edge
    return f"nv_pair_X{sx}Y{sy}N{sn}_to_X{dx}Y{dy}N{dn}_{port}"


def _is_jailbreak(edge):
    sx, sy, sn, kind, dx, dy, dn, port = edge
    return (sx in JAILBREAK_X or dx in JAILBREAK_X
            or sy in JAILBREAK_Y or dy in JAILBREAK_Y)


# --- Worker (top-level for pickling) ---
def compile_edge(edge):
    sx, sy, sn, kind, dx, dy, dn, port = edge
    tag = _tag(edge)
    out_rbf = str(RBF_DIR / f"{tag}.rbf")
    if os.path.exists(out_rbf) and os.path.getsize(out_rbf) == 368011:
        return {"tag": tag, "ok": True, "elapsed": 0.0, "skipped": True}

    verilog = gen_two_luts_single_input_clocked(0x8888, 0xAAAA, connect_port=port)
    placement = {
        "lut1": f"LCCOMB_X{sx}_Y{sy}_N{sn}",
        "lut2": f"LCCOMB_X{dx}_Y{dy}_N{dn}",
    }
    qsf = gen_qsf_ce10(placement, seed=1)
    work_sub = str(WORK / tag)
    # wipe any stale dir from a prior retry
    if os.path.exists(work_sub):
        shutil.rmtree(work_sub, ignore_errors=True)

    last_err = ""
    t0 = time.time()
    for attempt in range(RETRIES + 1):
        try:
            rbf, elapsed, err = compile_and_export(
                tag, verilog, qsf, rbf_output=out_rbf, work_dir=str(WORK)
            )
            if rbf and os.path.getsize(rbf) == 368011:
                shutil.rmtree(work_sub, ignore_errors=True)
                return {"tag": tag, "ok": True, "elapsed": time.time() - t0,
                        "attempts": attempt + 1, "jailbreak": _is_jailbreak(edge)}
            last_err = err or "rbf size mismatch"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-400:]}"
        # cleanup before retry
        shutil.rmtree(work_sub, ignore_errors=True)
        if attempt < RETRIES:
            time.sleep(BACKOFF)
    return {"tag": tag, "ok": False, "elapsed": time.time() - t0,
            "err": last_err[:1000], "attempts": RETRIES + 1,
            "jailbreak": _is_jailbreak(edge), "edge": list(edge)}


# --- Main loop ---
def _load_json(p, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return default
    return default


def _atomic_write(p, obj):
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1))
    os.replace(tmp, p)


def _free_gb(path):
    st = shutil.disk_usage(str(path))
    return st.free / (1024 ** 3)


STOP = {"flag": False}

def _sigint(signum, frame):
    if STOP["flag"]:
        print("\n[!!] second SIGINT — hard exit", flush=True)
        sys.exit(130)
    STOP["flag"] = True
    print("\n[!] SIGINT received — draining workers, will checkpoint then exit",
          flush=True)


def main():
    RBF_DIR.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    ef = Path(os.environ.get("EDGES_FILE", EDGES_FILE))
    data = json.loads(ef.read_text())
    raw = [tuple(e) for e in data["strict_edges_sorted"]]
    # Normalize: FF_X*_N{odd} shares its LE with LCCOMB at N-1 (Cyclone IV
    # LE layout). Map odd N → N-1 so the placement lands on the LCCOMB.
    def _norm(e):
        sx, sy, sn, kind, dx, dy, dn, port = e
        if sn % 2: sn -= 1
        if dn % 2: dn -= 1
        return (sx, sy, sn, kind, dx, dy, dn, port)
    normed = {_norm(e) for e in raw}
    # Drop self-loops: our two-LUT template can't place both LUTs at the same LE.
    # Self-loops are legitimate NEORV32 FF→LCCOMB feedback but unrepresentable
    # in this compile strategy (would need a 1-LUT reflexive variant).
    edges = [e for e in sorted(normed)
             if _is_valid_le(e[0], e[1], e[2]) and _is_valid_le(e[4], e[5], e[6])
             and (e[0], e[1], e[2]) != (e[4], e[5], e[6])]
    print(f"loaded {len(raw)} raw → {len(normed)} after N-normalize → "
          f"{len(edges)} placeable after LAB+self-loop filter", flush=True)

    status = _load_json(STATUS_FILE, {"done": [], "failed_tags": []})
    done = set(status.get("done", []))
    failures = _load_json(FAIL_FILE, [])
    failed_tags = {f["tag"] for f in failures}

    todo = [e for e in edges if _tag(e) not in done and _tag(e) not in failed_tags]
    # pre-filter: anything already on disk counts as done
    already = 0
    for e in list(todo):
        p = RBF_DIR / f"{_tag(e)}.rbf"
        if p.exists() and p.stat().st_size == 368011:
            done.add(_tag(e))
            todo.remove(e)
            already += 1
    if already:
        print(f"  {already} edges already on disk → counted done", flush=True)
    print(f"  done={len(done)}  failed={len(failed_tags)}  todo={len(todo)}", flush=True)

    if not todo:
        print("nothing to do", flush=True)
        return

    signal.signal(signal.SIGINT, _sigint)
    signal.signal(signal.SIGTERM, _sigint)

    n_total = len(todo)
    n_ok = n_fail = n_jail_fail = 0
    t_start = time.time()

    def checkpoint():
        _atomic_write(STATUS_FILE, {
            "done": sorted(done),
            "failed_tags": sorted(failed_tags),
            "n_total_planned": len(edges),
            "n_done": len(done),
            "n_failed": len(failed_tags),
            "updated": time.time(),
        })
        _atomic_write(FAIL_FILE, failures)

    with ProcessPoolExecutor(max_workers=WORKERS) as ex:
        # feeder: submit in bounded waves so SIGINT cancels cleanly
        pending = {}
        it = iter(todo)
        # prime the pool
        for _ in range(min(WORKERS * 3, len(todo))):
            try:
                e = next(it)
            except StopIteration:
                break
            pending[ex.submit(compile_edge, e)] = e

        n_checkpoint_since = 0
        while pending:
            done_now, _ = wait(pending.keys(), return_when=FIRST_COMPLETED)
            for fut in done_now:
                e = pending.pop(fut)
                try:
                    r = fut.result()
                except Exception as ex_e:
                    r = {"tag": _tag(e), "ok": False, "err": str(ex_e),
                         "edge": list(e), "jailbreak": _is_jailbreak(e)}
                if r.get("ok"):
                    done.add(r["tag"])
                    n_ok += 1
                else:
                    failed_tags.add(r["tag"])
                    failures.append(r)
                    n_fail += 1
                    if r.get("jailbreak"):
                        n_jail_fail += 1
                    print(f"  [FAIL{'*JB' if r.get('jailbreak') else ''}] "
                          f"{r['tag']}: {r.get('err','?')[:200]}", flush=True)

                n_checkpoint_since += 1
                processed = n_ok + n_fail
                if processed % 20 == 0 or n_checkpoint_since >= 50:
                    elapsed = time.time() - t_start
                    rate = processed / elapsed if elapsed else 0
                    eta_min = (n_total - processed) / rate / 60 if rate else 0
                    free = _free_gb(ROOT)
                    print(f"  [{processed}/{n_total}] ok={n_ok} fail={n_fail} "
                          f"jb_fail={n_jail_fail} rate={rate:.2f}/s "
                          f"eta={eta_min:.1f}min free={free:.1f}GB",
                          flush=True)
                    checkpoint()
                    n_checkpoint_since = 0

                if _free_gb(ROOT) < MIN_FREE_GB:
                    print(f"[!] low disk ({_free_gb(ROOT):.1f}GB) — pausing 30s",
                          flush=True)
                    checkpoint()
                    time.sleep(30)

                if not STOP["flag"]:
                    try:
                        ne = next(it)
                        pending[ex.submit(compile_edge, ne)] = ne
                    except StopIteration:
                        pass

            if STOP["flag"]:
                print("  draining: cancelling pending futures", flush=True)
                for f in list(pending):
                    f.cancel()
                break

        checkpoint()

    elapsed = time.time() - t_start
    print(f"\n== done ==  ok={n_ok}  fail={n_fail}  jb_fail={n_jail_fail}  "
          f"elapsed={elapsed/60:.1f}min", flush=True)
    print(f"status: {STATUS_FILE}")
    print(f"failures: {FAIL_FILE}")


if __name__ == "__main__":
    main()
