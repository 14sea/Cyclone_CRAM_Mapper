# SPDX-License-Identifier: GPL-3.0-or-later
"""Memory-safe Quartus compile scheduler — general fuzzing infrastructure.

Running hundreds/thousands of Quartus flows to mine CRAM bits will OOM and hang a
small box: one `quartus_map`+`quartus_fit`+`quartus_asm` flow peaks ~1.5 GiB, and
launching a compile into low memory swap-thrashes the whole machine to a halt.
This module is the guard rail — the piece that let a 3.8 GiB box grind 500+
compiles unattended overnight without a single OOM:

  * `guarded_compile(thunk)` runs ONE compile under two watchdogs — it won't START
    unless there's enough free RAM (`MemCfg.start_mb`), and it KILLS the flow if
    free RAM crosses a danger floor (`MemCfg.critical_mb`) or a wall-clock cap
    (`MemCfg.max_wall_s`) mid-compile, so the box always survives.
  * `kill_quartus()` SIGKILLs only the Quartus flow, via /proc (no fork — safe
    under memory pressure) and matching the executable name exactly (won't kill
    `vim quartus_fit.rpt`).
  * `block_qsf(...)` builds a minimal, known-good QSF for a single-design probe.
  * `_atomic(path, obj)` is a crash-safe JSON writer (tmp+rename) that tolerates a
    transient drvfs/9p/AV-lock hiccup instead of dying mid multi-day run.
  * SIGINT/SIGTERM set `STOP["flag"]`; long loops poll it to checkpoint & exit.

Usage:
    import quartus_grind as G, signal
    signal.signal(signal.SIGINT,  G._sigint)
    signal.signal(signal.SIGTERM, G._sigint)
    G.setup_quartus_env()                       # optional PATH/env setup
    rbf, transient = G.guarded_compile(lambda: my_compile(tag, verilog, qsf))
    if transient:   # STOP or watchdog-abort -> do NOT retire the job (resume later)
        ...

Tune the thresholds for your box via `MemCfg` (defaults suit ~3.8 GiB). This is
device-agnostic; the shipped `block_qsf` defaults target Cyclone IV E but take the
device string as an argument.
"""
from __future__ import annotations
import json, os, re, signal, threading, time
from pathlib import Path

# SIGINT/SIGTERM cooperative-stop flag (poll STOP["flag"] in long loops).
STOP = {"flag": False}


def _sigint(sig, frm):
    STOP["flag"] = True
    print("\n[!] stop requested — checkpointing then exiting", flush=True)


def setup_quartus_env(rootdir: str | None = None):
    """Put Quartus on PATH and set QUARTUS_ROOTDIR. `rootdir` defaults to
    $QUARTUS_ROOTDIR, else ~/intelFPGA_lite/21.1/quartus. LC_ALL=C avoids
    locale-dependent report parsing."""
    root = rootdir or os.environ.get("QUARTUS_ROOTDIR") \
        or os.path.expanduser("~/intelFPGA_lite/21.1/quartus")
    os.environ["QUARTUS_ROOTDIR"] = root
    os.environ["PATH"] = root + "/bin:" + os.environ.get("PATH", "")
    os.environ.setdefault("LC_ALL", "C")
    return root


# ----------------------------------------------------------------------
# persistence — crash-safe atomic JSON write
# ----------------------------------------------------------------------
def _atomic(path, obj):
    """tmp+rename atomic write. A transient drvfs/9p/AV-lock hiccup must NOT kill a
    multi-day run, so on OSError we warn and carry on rather than raise."""
    path = Path(path)
    try:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(obj))
        os.replace(tmp, path)
    except OSError as e:
        print(f"  [io] persist {path.name} failed: {e} (continuing)", flush=True)


# ----------------------------------------------------------------------
# minimal single-design QSF
# ----------------------------------------------------------------------
def block_qsf(device, top, pins, loc_node=None, loc=None):
    """A minimal known-good QSF for a one-design probe. `pins` = {signal: PIN_ball}.
    Optional (loc_node, loc) pins a hierarchical node to a chip location."""
    L = [
        'set_global_assignment -name FAMILY "Cyclone IV E"',
        f'set_global_assignment -name DEVICE {device}',
        f'set_global_assignment -name TOP_LEVEL_ENTITY {top}',
        'set_global_assignment -name VERILOG_FILE fuzz_top.v',
        'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
        'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        'set_global_assignment -name SEED 1',
    ]
    for sig, pin in pins.items():
        L.append(f'set_location_assignment PIN_{pin} -to {sig}')
    if loc_node and loc:
        L.append(f'set_location_assignment {loc} -to "{loc_node}"')
    return "\n".join(L) + "\n"


# ----------------------------------------------------------------------
# MEMORY SAFETY — one Quartus flow peaks ~1.5 GiB. Launching into low memory
# OOM/swap-thrashes and HANGS the box. Two guards: (1) don't START a compile
# unless there's enough free RAM; (2) if free RAM crosses a danger floor DURING
# a compile, kill Quartus so the compile fails but the box survives.
# ----------------------------------------------------------------------
def mem_available_mb():
    """Free RAM in MB, or -1 if unreadable (never 0 — 0 would make the gate wait
    forever)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        return -1
    return -1


_QTOOL_RE = re.compile(r"^quartus_(map|fit|asm|cpf|sh|sta|cdb)$")


def kill_quartus():
    """SIGKILL our Quartus flow via /proc (no fork — safe under memory pressure),
    matching only the executable name (not an arg substring, so it can't kill
    `vim quartus_fit.rpt`). Never raises."""
    me = os.getpid()
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return
    for p in pids:
        if int(p) == me:
            continue
        try:
            with open(f"/proc/{p}/cmdline", "rb") as f:
                argv0 = f.read().split(b"\0", 1)[0].decode("utf8", "replace")
        except OSError:
            continue
        if _QTOOL_RE.match(argv0.rsplit("/", 1)[-1]):
            try:
                os.kill(int(p), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass


class MemCfg:
    start_mb = 2200      # need this much free to START a compile
    critical_mb = 350    # abort a running compile if free drops below this
    cooldown_s = 8       # settle time between compiles
    poll_s = 3
    max_wall_s = 900     # hard wall-clock cap per compile (kills a hung Quartus)


def wait_for_memory():
    """Block until free RAM >= MemCfg.start_mb (or STOP). Returns True if clear to
    compile, False only if STOP was requested. If meminfo is unreadable we proceed
    (better than deadlocking forever)."""
    warned = False
    while not STOP["flag"]:
        m = mem_available_mb()
        if m < 0:
            print("  [mem] cannot read /proc/meminfo — proceeding cautiously", flush=True)
            return True
        if m >= MemCfg.start_mb:
            return True
        if not warned:
            print(f"  [mem] waiting: {m}MB free (< {MemCfg.start_mb}MB) — holding compile",
                  flush=True)
            warned = True
        time.sleep(5)
    return False


def guarded_compile(thunk):
    """Run one compile `thunk` under the memory + wall-clock watchdog.
    Returns (result_or_None, transient); transient=True means we stopped or
    watchdog-aborted (env issue) and the job must NOT be retired — resume it later.
    `thunk`'s own return value is passed through as the result on success."""
    if not wait_for_memory():
        return None, True                      # STOP during wait -> transient
    result = {}

    def run():
        try:
            result["rbf"] = thunk()
        except Exception as e:
            result["err"] = e

    th = threading.Thread(target=run, daemon=True)
    th.start()
    t0 = time.time()
    aborted = False
    while th.is_alive():
        th.join(MemCfg.poll_s)
        if not th.is_alive():
            break
        m = mem_available_mb()
        over = (time.time() - t0) > MemCfg.max_wall_s
        if (0 <= m < MemCfg.critical_mb) or over or STOP["flag"]:
            why = "STOP" if STOP["flag"] else ("timeout" if over else f"{m}MB")
            print(f"  [mem] aborting compile ({why})", flush=True)
            aborted = True
            # keep killing until the compile thread dies — one shot can miss the
            # next Quartus stage started right after the kill snapshot.
            for _ in range(10):
                kill_quartus()
                th.join(3)
                if not th.is_alive():
                    break
            break
    if "err" in result:
        print(f"  [compile-exc] {result['err']!r}", flush=True)
    if aborted:
        return None, True
    return result.get("rbf"), False
