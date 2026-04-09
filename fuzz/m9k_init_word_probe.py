#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stage B word-axis probe — after Stage A locked the bit axis
(byte(bit) = 261142 - 2*bit, bp=6 at word=0), this script sweeps a
handful of words with bit=0 only, to fit the word-axis stride of
the 2D CRAM formula:

    byte(word, bit) = B0 + dW*word + dB*bit
    bp              = const

Compiles: baseline + word∈{0,1,2,3,255,511} at bit=0. 7 total.
Parallelism: 4 workers. Wall ~35-50s.

Output: prints the fitted (B0, dW, dB, bp) and archives
results/m9k_init_word_probe.json for Stage B basis writer.
"""
import json, os, sys, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from m9k_init_harness import build, DEPTH, WIDTH
from rbf_diff import diff_rbf_files

def diff_bits(a, b):
    return [(d.byte_offset, d.bit_position) for d in diff_rbf_files(a, b)]

ROOT = HERE.parent
RBF_DIR = ROOT / "results" / "rbf"

WORDS_TO_PROBE = [0, 1, 2, 3, 255, 511]  # corners + small-address
BIT = 0                                  # single bit flipped per probe


def _compile(tag, overrides):
    rbf, elapsed, err = build(tag, overrides=overrides,
                              rbf_output=str(RBF_DIR / f"{tag}.rbf"))
    return tag, rbf, elapsed, err


def main():
    tasks = [("m9k_wp_base", None)]
    for w in WORDS_TO_PROBE:
        tasks.append((f"m9k_wp_w{w}_b{BIT}", {w: 1 << BIT}))

    print(f"dispatching {len(tasks)} compiles across 4 workers...")
    t0 = time.time()
    results = {}
    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_compile, tag, ov): tag for tag, ov in tasks}
        for fut in as_completed(futs):
            tag, rbf, elapsed, err = fut.result()
            if rbf is None:
                print(f"  {tag:25s} FAIL ({elapsed:.1f}s): {err[:200]}")
                results[tag] = None
            else:
                print(f"  {tag:25s} OK   ({elapsed:.1f}s)")
                results[tag] = rbf
    print(f"total wall: {time.time()-t0:.1f}s\n")

    if any(v is None for v in results.values()):
        print("ABORT: at least one compile failed")
        sys.exit(1)

    base_rbf = results["m9k_wp_base"]
    per_word = {}
    for w in WORDS_TO_PROBE:
        rbf = results[f"m9k_wp_w{w}_b{BIT}"]
        cells = sorted(diff_bits(base_rbf, rbf))
        per_word[w] = cells
        if len(cells) == 1:
            byte, bp = cells[0]
            frame = (byte - 32) // 210
            off = (byte - 32) % 210
            print(f"  word={w:3d}  bit={BIT}  ->  byte={byte:6d} bp={bp}  "
                  f"(frame={frame} off_in_frame={off})")
        else:
            print(f"  word={w:3d}  bit={BIT}  ->  {len(cells)} cells: {cells[:5]}")

    # Fit linear model: byte(word) = B0 + dW * word
    singletons = [(w, per_word[w][0][0]) for w in WORDS_TO_PROBE
                  if len(per_word[w]) == 1]
    if len(singletons) >= 2:
        w_vals = [s[0] for s in singletons]
        b_vals = [s[1] for s in singletons]
        # Simple two-point slope using 0 and 1 if available, else first two
        try:
            b0 = next(b for w, b in singletons if w == 0)
            b1 = next(b for w, b in singletons if w == 1)
            dW = b1 - b0
            print(f"\n=== linear fit ===")
            print(f"  B0 (word=0 bit=0) = {b0}")
            print(f"  dW (word stride)  = {dW}")
            print(f"  dB (bit stride)   = -2  (from Stage A sweep)")
            # Verify against other samples
            print(f"\n=== verify against samples ===")
            all_ok = True
            for w, b in singletons:
                pred = b0 + dW * w
                ok = (pred == b)
                print(f"  word={w:3d}: predicted={pred:6d} actual={b:6d}  "
                      f"{'OK' if ok else 'MISMATCH'}")
                all_ok = all_ok and ok
            if all_ok:
                print("\n>>> 2D linear model confirmed: "
                      f"byte(w, b) = {b0} + {dW}*word + -2*bit, bp=6")
            else:
                print("\n>>> MISMATCH — word axis is NOT simple linear, "
                      "may be block-interleaved or scrambled")
        except StopIteration:
            print("missing word=0 or word=1 singleton")

    out = {
        "words_probed": WORDS_TO_PROBE,
        "bit": BIT,
        "per_word": {str(w): c for w, c in per_word.items()},
    }
    (ROOT / "results" / "m9k_init_word_probe.json").write_text(
        json.dumps(out, indent=1))
    print(f"\narchived results/m9k_init_word_probe.json")


if __name__ == "__main__":
    main()
