"""Decoupling test: is LI mode purely a function of dst_x?

Compile 3 srcs × 3 dsts = 9 designs and read the LI mode at each dst LAB.
If for fixed dst_x the mode is identical across all 3 srcs, then mode is
column-static and RouteCodec can use a flat dict.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fuzz"))

from bitstream import RouteCodec
from runner import (compile_route_pair_single_input,
                    compile_route_baseline_abcd)

RBF_DIR = ROOT / "results" / "rbf"

SRCS = [(3, 5), (17, 8), (25, 15)]
DSTS = [(7, 10), (12, 10), (21, 10)]   # expected: A, P, A
EXPECT = {(7, 10): "alternating", (12, 10): "paired", (21, 10): "alternating"}


def read_mode(codec, design, zero, dx, dy):
    li = codec.read_local_interconnect(design, zero)
    by_pair = {}
    for e in li:
        lx, ly, p, b = codec._parse_li_name(e[0])
        if (lx, ly) == (dx, dy):
            by_pair.setdefault(p, set()).add(b)
    if not by_pair:
        return "empty", 0
    mode, _ = RouteCodec._classify_li_lab(by_pair)
    n = sum(len(v) for v in by_pair.values())
    return mode, n


def main():
    codec = RouteCodec()
    results = {}  # (src, dst) -> mode

    for sx, sy in SRCS:
        zero_tag = f"litdec_zero_{sx}_{sy}"
        zero_path = RBF_DIR / f"{zero_tag}.rbf"
        if not zero_path.exists():
            print(f"baseline ({sx},{sy}) ...", flush=True)
            rbf, t, err = compile_route_baseline_abcd(zero_tag, sx, sy, 0)
            if not rbf:
                print(f"  FAIL: {err}")
                return
            print(f"  OK ({t:.1f}s)")
        zero = zero_path.read_bytes()

        for dx, dy in DSTS:
            tag = f"litdec_{sx}_{sy}_to_{dx}_{dy}"
            rbf_path = RBF_DIR / f"{tag}.rbf"
            if not rbf_path.exists():
                print(f"compile ({sx},{sy}) -> ({dx},{dy}) ...", flush=True)
                rbf, t, err = compile_route_pair_single_input(
                    tag, sx, sy, 0, dx, dy, 0, connect_port="datab")
                if not rbf:
                    print(f"  FAIL: {err}")
                    continue
                print(f"  OK ({t:.1f}s)")
            design = rbf_path.read_bytes()
            mode, n = read_mode(codec, design, zero, dx, dy)
            results[((sx, sy), (dx, dy))] = (mode, n)

    # Tabulate
    print(f"\n{'src':>10} | " + " | ".join(f"({dx:2d},{dy:2d})" for dx, dy in DSTS))
    print("-" * 60)
    for src in SRCS:
        cells = []
        for dst in DSTS:
            mode, n = results.get((src, dst), ("?", 0))
            tag = "P" if mode == "paired" else ("A" if mode == "alternating" else mode[0])
            cells.append(f"{tag}({n})")
        print(f"  ({src[0]:2d},{src[1]:2d})  | " + "  |  ".join(f"{c:>6s}" for c in cells))

    # Verdict
    print("\n=== Per-dst consistency ===")
    all_static = True
    for dst in DSTS:
        modes = {results.get((src, dst), ("?", 0))[0] for src in SRCS}
        modes.discard("empty")
        ok = (len(modes) == 1)
        if not ok:
            all_static = False
        exp = EXPECT[dst]
        match_exp = (len(modes) == 1 and modes.pop() == exp) if modes else False
        # restore for print
        modes2 = {results.get((src, dst), ("?", 0))[0] for src in SRCS}
        print(f"  dst{dst}: modes={modes2}  expected={exp}  static={ok}")
    print(f"\n{'✓ COLUMN-STATIC' if all_static else '✗ NOT static — depends on src'}")


if __name__ == "__main__":
    main()
