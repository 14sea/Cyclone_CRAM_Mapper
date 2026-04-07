# SPDX-License-Identifier: GPL-3.0-or-later
"""T9-followup: Orthogonal grid corpus for LI mode-selection rule mining.

The natural-bias corpus from li_mode_corpus_mine.py confounded dx with sx
(decision tree stalled at 66% acc with mush in middle leaves). Fix: force
every source to attempt the SAME relative-dx grid {-10,-5,-1,+1,+5,+10}
crossed with the same relative-dy grid, so dx-effect and sx-effect can be
disentangled by the tree.
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

LAB_X = [3, 4, 6, 7, 8, 10, 11, 12, 13, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 28, 29, 31]
LAB_Y = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19, 21]

# Sources spread across the chip so the same relative grid samples
# different absolute neighborhoods (corner / interior / M9K boundary / right edge).
SRCS = [(4, 4), (10, 10), (13, 8), (17, 10), (19, 14), (25, 8), (28, 12)]

# Forced relative offsets — break Quartus' natural-routing bias.
DREL = [-10, -5, -2, -1, 1, 2, 5, 10]


def nearest_lab_x(x):
    return min(LAB_X, key=lambda v: abs(v - x))


def nearest_lab_y(y):
    return min(LAB_Y, key=lambda v: abs(v - y))


def dsts_for(sx, sy):
    out = []
    # Pure column moves: hold dx=sx, sweep dy
    for ddy in DREL:
        ty = sy + ddy
        if ty in LAB_Y and ty != sy and sx in LAB_X:
            out.append((sx, ty))
    # Pure row moves: hold dy=sy, sweep dx (snap to LAB if forced dx is non-LAB)
    for ddx in DREL:
        tx = sx + ddx
        if tx not in LAB_X:
            tx = nearest_lab_x(sx + ddx)
        if tx == sx:
            continue
        out.append((tx, sy))
    # Diagonal grid: every (ddx,ddy) combo
    for ddx in DREL:
        for ddy in DREL:
            tx = sx + ddx
            ty = sy + ddy
            if tx not in LAB_X:
                tx = nearest_lab_x(tx)
            if ty not in LAB_Y:
                ty = nearest_lab_y(ty)
            if (tx, ty) == (sx, sy):
                continue
            out.append((tx, ty))
    seen, uniq = set(), []
    for k in out:
        if k not in seen:
            seen.add(k); uniq.append(k)
    return uniq


OUT = "/home/test/EP4CE6/results/rbf"


def main():
    log = open("/home/test/EP4CE6/results/li_mode_grid.log", "w")
    def say(s):
        print(s, flush=True); log.write(s + "\n"); log.flush()

    t0 = time.time()
    n_done = n_skip = n_fail = 0
    plan = [(sx, sy, dx, dy) for (sx, sy) in SRCS for (dx, dy) in dsts_for(sx, sy)]
    say(f"=== orthogonal grid mine: {len(SRCS)} srcs × ~{len(plan)//len(SRCS)} dsts = {len(plan)} compiles ===")

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
    say(f"=== grid mine done: done={n_done} skip={n_skip} fail={n_fail} elapsed={time.time()-t0:.0f}s ===")
    log.close()


if __name__ == "__main__":
    main()
