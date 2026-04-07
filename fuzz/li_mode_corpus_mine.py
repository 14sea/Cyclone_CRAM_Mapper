# SPDX-License-Identifier: GPL-3.0-or-later
"""Mine LI mode-selection rule: compile a broad src×dst sweep so we can
later derive when Quartus picks paired vs alternating mode.

Sources span corner, interior, M9K boundary, edge.
Destinations span dx in {3..31} crossing non-LAB columns (5,9,14,15,20,27,30)
to test the "near non-LAB → alternating" hypothesis.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

LAB_X = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 31]
LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]

SRCS = [(4, 4), (10, 10), (10, 14), (17, 8), (25, 15)]

def dsts_for(sx, sy):
    out = []
    # Sweep dx across LAB columns at sy (horizontal) — tests column-x dependency
    for dx in LAB_X:
        if dx == sx:
            continue
        out.append((dx, sy))
    # Sweep dy across LAB rows at sx (vertical) — tests row dependency
    for dy in LAB_Y:
        if dy == sy:
            continue
        out.append((sx, dy))
    # Diagonals near non-LAB columns
    for dx in (6, 8, 10, 13, 16, 19, 21, 26, 28):
        for dy in (sy + 2, sy - 2):
            if dy in LAB_Y and dx in LAB_X and (dx, dy) != (sx, sy):
                out.append((dx, dy))
    # de-dup, preserve order
    seen, uniq = set(), []
    for k in out:
        if k not in seen:
            seen.add(k); uniq.append(k)
    return uniq

OUT = "/home/test/EP4CE6/results/rbf"

def main():
    log = open("/home/test/EP4CE6/results/li_mode_mine.log", "w")
    def say(s):
        print(s, flush=True); log.write(s + "\n"); log.flush()

    t0 = time.time()
    n_done = n_skip = n_fail = 0
    for sx, sy in SRCS:
        ztag = f"lits_zero_{sx}_{sy}"
        zpath = f"{OUT}/{ztag}.rbf"
        if not os.path.exists(zpath):
            say(f"[{time.time()-t0:6.1f}s] compiling {ztag}")
            rbf, t, err = compile_route_baseline_abcd(ztag, sx, sy, 0)
            say(f"   {'OK' if rbf else 'FAIL'} ({t:.1f}s) {err or ''}")
            if not rbf:
                continue
        for dx, dy in dsts_for(sx, sy):
            tag = f"lits_pair_X{sx}Y{sy}_to_X{dx}Y{dy}N0_datab"
            p = f"{OUT}/{tag}.rbf"
            if os.path.exists(p):
                n_skip += 1
                continue
            say(f"[{time.time()-t0:6.1f}s] {tag}")
            rbf, t, err = compile_route_pair_single_input(
                tag, sx, sy, 0, dx, dy, 0, connect_port="datab")
            if rbf:
                n_done += 1
                say(f"   OK ({t:.1f}s)  done={n_done} skip={n_skip} fail={n_fail}")
            else:
                n_fail += 1
                say(f"   FAIL ({t:.1f}s) {err}")
    say(f"=== mining done: done={n_done} skip={n_skip} fail={n_fail} elapsed={time.time()-t0:.0f}s ===")
    log.close()

if __name__ == "__main__":
    main()
