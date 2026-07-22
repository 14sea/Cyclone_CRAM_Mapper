# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine the IOB I/O-standard / drive / slew CRAM codec (Cyclone IV, Quartus).

Which CRAM cells encode a pin's electrical settings (I/O standard, drive strength,
slew, weak pull-up, registered-IOB)? Isolate them by building the SAME pin with a
matrix of IOB settings and diffing each variant against a fixed REFERENCE build on
that pin -> because the pin + route are identical, the routing cancels and only the
electrical bits remain. Repeating on several anchor pins in different banks and
intersecting the (base-normalised) deltas keeps the position-invariant core.

  python3 iostd_codec_mine.py --pilot     # reference + a few variants, ONE pin
  python3 iostd_codec_mine.py --mine       # full matrix on 3 anchor pins (3 banks)
  python3 iostd_codec_mine.py --analyze    # (re)build the codec from existing specimens

RESULT on EP4CE10F17C8 (honest negative, so you don't repeat the dead end): each
I/O-standard change moves ~26-122 CRAM cells per pin, but the cross-pin invariant
intersection is SMALL — lvcmos33=3, io25=1, drive_min=2, pullup=2 cells; drive_max /
slew / fast_oreg came out as no-ops (0 cells) because the shipped default (3.3-V
LVTTL) is already max-drive/default-slew and a combinational buffer has no output
register. WORSE: the min-offset normalisation below trivially maps each pin's lowest
changed cell to [0,0], so [0,0] appears "invariant" in every non-empty setting — the
1-3 "invariant" cells are largely that anchor artifact, and pairwise Jaccard
~0.02-0.16 means the true cross-pin overlap is ~zero. So the electrical bits are NOT
cleanly position-invariant under this normalisation; the per-pin deltas are
placement-noise-dominated. The value here is the METHOD (variant-vs-ref diff cancels
routing) + this documented dead end. The raw specimens are shipped
(results/iostd_specimens.jsonl) so a better alignment (per-bank, or anchoring to the
IOB base rather than the delta min) can be retried WITHOUT re-mining.

Depends on `quartus_grind` (memory-safe compile scheduler), `fuzz/compile.py`
(`compile_and_export`), and a zero `baseline.rbf` (`python3 fuzz/runner.py
baseline`). Memory-safe, resumable. Device is `config.DEVICE` (EP4CE6F17C8); the
shipped specimens were mined on its CE10 sibling (same die, same F17 256-ball
package). Anchor pins are F17 — change them for another package.
"""
from __future__ import annotations
import json, os, shutil, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quartus_grind as G                       # memory-safe compile scheduler
from compile import compile_and_export          # noqa: E402
from config import DEVICE, RBF_DIR, RESULTS_DIR, WORK_DIR  # noqa: E402

G.setup_quartus_env()
WORK = Path(WORK_DIR) / "iostd"                 # honors $FUZZ_WORK_DIR (see config.py)
WORK.mkdir(parents=True, exist_ok=True)

_BASE = None
def _base():
    """Lazy zero baseline (`fuzz/runner.py baseline`) — only --mine needs it, so
    --analyze runs on the shipped specimens without it present."""
    global _BASE
    if _BASE is None:
        _BASE = (Path(RBF_DIR) / "baseline.rbf").read_bytes()
    return _BASE

SPEC = Path(RESULTS_DIR) / "iostd_specimens.jsonl"   # raw variant-vs-ref specimens (shipped)
CODEC = Path(RESULTS_DIR) / "iostd_codec.json"       # regenerated summary (NOT shipped — content-free)

# buffer design: OUT = IN. We vary the OUT pin's IOB electrical settings; the input
# anchor + route are held fixed so they cancel in the variant-vs-ref diff.
VERILOG = "module fuzz_top(input K, output LED);\n  assign LED = K;\nendmodule\n"
IN_ANCHOR = "E15"             # a plain input ball, proven to build (F17)
# 3 OUT anchors in different regions/banks so the cross-pin intersection actually
# tests position-invariance rather than one edge (all valid F17 output balls):
OUT_PIN_A = "G15"
OUT_PIN_B = "C15"
OUT_PIN_C = "L6"
OUT_PINS = [OUT_PIN_A, OUT_PIN_B, OUT_PIN_C]

# label -> extra QSF assignment lines on the OUT pin (LED). "ref" = default = base.
VARIANTS = {
    "ref":       [],
    "lvcmos33":  ['set_instance_assignment -name IO_STANDARD "3.3-V LVCMOS" -to LED'],
    "io25":      ['set_instance_assignment -name IO_STANDARD "2.5 V" -to LED'],
    "io18":      ['set_instance_assignment -name IO_STANDARD "1.8 V" -to LED'],
    "drive_min": ['set_instance_assignment -name CURRENT_STRENGTH_NEW "MINIMUM CURRENT" -to LED'],
    "drive_max": ['set_instance_assignment -name CURRENT_STRENGTH_NEW "MAXIMUM CURRENT" -to LED'],
    "slew_fast": ['set_instance_assignment -name SLEW_RATE 2 -to LED'],
    "pullup":    ['set_instance_assignment -name WEAK_PULL_UP_RESISTOR ON -to LED'],
    "fast_oreg": ['set_instance_assignment -name FAST_OUTPUT_REGISTER ON -to LED'],
}
PILOT = ["ref", "lvcmos33", "io25", "drive_min", "drive_max", "pullup"]


def qsf(out_pin, extra):
    base = G.block_qsf(DEVICE, "fuzz_top", {"K": IN_ANCHOR, "LED": out_pin})
    return base + "\n" + "\n".join(extra) + ("\n" if extra else "")


def full_diff(rbf: bytes):
    """All changed cells vs the zero baseline over the full config (IOB config lives
    in the header band, so we do NOT restrict to the LAB data band)."""
    b = _base(); n = len(b)
    cells = set()
    for off in range(32, n - 59):
        v = rbf[off] ^ b[off]
        if v:
            for bp in range(8):
                if (v >> bp) & 1:
                    cells.add((off, bp))
    return cells


def build(tag, out_pin, extra):
    proj = WORK / tag
    shutil.rmtree(proj, ignore_errors=True)
    out = str(WORK / f"{tag}.rbf")
    try:
        rbf, _el, err = compile_and_export(tag, VERILOG, qsf(out_pin, extra),
                                           rbf_output=out, work_dir=str(WORK))
        if rbf and os.path.getsize(rbf) == len(_base()):
            return full_diff(Path(rbf).read_bytes()), "ok"
        return None, (err or "fail")[:80]
    except Exception as e:
        return None, f"exc:{type(e).__name__}"
    finally:
        shutil.rmtree(proj, ignore_errors=True)
        try: os.unlink(out)
        except OSError: pass


def run(labels, pins):
    done = {}
    if SPEC.exists():
        for ln in open(SPEC):
            ln = ln.strip()
            if ln:
                s = json.loads(ln); done[s["tag"]] = s
    for pin in pins:
        for lab in labels:
            tag = f"iostd_{pin}_{lab}"
            if tag in done:
                print(f"  {tag}: cached ({len(done[tag]['cells'])} cells)"); continue
            if G.STOP["flag"]: return
            t0 = time.time()
            res, transient = G.guarded_compile(lambda: build(tag, pin, VARIANTS[lab]))
            if transient:
                if G.STOP["flag"]: return
                continue
            cells, status = res if isinstance(res, tuple) else (None, "fail")
            if cells is not None:
                rec = {"tag": tag, "pin": pin, "label": lab,
                       "cells": [list(c) for c in sorted(cells)]}
                with open(SPEC, "a") as f:
                    f.write(json.dumps(rec) + "\n"); f.flush(); os.fsync(f.fileno())
                done[tag] = rec
            print(f"  {tag}: {status} ({len(cells) if cells else 0} cells) "
                  f"[{time.time()-t0:.0f}s]", flush=True)
            for _ in range(G.MemCfg.cooldown_s):
                if G.STOP["flag"]: return
                time.sleep(1)


def _is_crc(off):
    # per-frame CRC bytes live at frame offsets 208/209 (RBF has a 32B preamble);
    # they differ between any two builds -> pure noise, drop them.
    return (off - 32) % 210 >= 208


def analyze(pins):
    """variant - ref per pin -> the setting's cells; intersect the (base-normalised)
    deltas across pins -> position-invariant codec bits. CRC bytes dropped."""
    specs = {}
    for ln in open(SPEC):
        ln = ln.strip()
        if ln:
            s = json.loads(ln)
            specs[s["tag"]] = set((o, bp) for o, bp in map(tuple, s["cells"]) if not _is_crc(o))
    print("\n=== per-setting delta vs ref (route cancels; electrical bits remain) ===")
    per_setting = defaultdict(list)
    for pin in pins:
        ref = specs.get(f"iostd_{pin}_ref")
        if ref is None:
            print(f"  {pin}: no ref build"); continue
        for lab in VARIANTS:
            if lab == "ref": continue
            v = specs.get(f"iostd_{pin}_{lab}")
            if v is None: continue
            delta = v ^ ref                      # symmetric diff = the setting's cells
            per_setting[lab].append((pin, delta))
            print(f"  {pin} {lab:10s}: {len(delta)} delta cells")
    print("\n=== position-invariant codec (intersection across pins, base-normalised) ===")
    codec = {}
    for lab, lst in per_setting.items():
        if len(lst) < 2:
            codec[lab] = {"n_pins": 1, "delta_example": len(lst[0][1]) if lst else 0}
            print(f"  {lab:10s}: {codec[lab]['delta_example']} cells (1 pin only)")
            continue
        norm = []
        for pin, delta in lst:
            if not delta: norm.append(set()); continue
            b = min(o for o, _ in delta)
            norm.append(set((o - b, bp) for o, bp in delta))
        inv = set.intersection(*norm) if norm else set()
        jac = []
        for i in range(len(norm)):
            for j in range(i + 1, len(norm)):
                u = norm[i] | norm[j]
                jac.append(round(len(norm[i] & norm[j]) / len(u), 2) if u else 1.0)
        codec[lab] = {"n_pins": len(lst), "invariant_cells": sorted(map(list, inv)),
                      "per_pin_sizes": [len(d) for _, d in lst], "pairwise_jaccard": jac}
        print(f"  {lab:10s}: {len(inv)} invariant cells across {len(lst)} pins "
              f"(sizes {codec[lab]['per_pin_sizes']}, pairwise-J {jac})")
    json.dump(codec, open(CODEC, "w"), indent=1)
    print(f"\nwrote {CODEC.name}")


def main():
    import argparse, signal
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--mine", action="store_true")
    ap.add_argument("--analyze", action="store_true")
    a = ap.parse_args()
    signal.signal(signal.SIGINT, G._sigint)
    signal.signal(signal.SIGTERM, G._sigint)
    if a.pilot:
        run(PILOT, [OUT_PIN_A]); analyze([OUT_PIN_A])
    if a.mine:
        run(list(VARIANTS), OUT_PINS); analyze(OUT_PINS)
    if a.analyze:
        analyze(OUT_PINS)
    if not (a.pilot or a.mine or a.analyze):
        ap.print_help()


if __name__ == "__main__":
    main()
