"""Stage 1+2 unit tests: parse_need + plan_hops on 8 hand-traced cases."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from route_synth import parse_need, plan_hops, Hop


def fmt(plan):
    return " ; ".join(repr(h) for h in plan) or "(no hops)"


CASES = [
    ("1 R4 east",                     (10, 10), (11, 10)),
    ("1 R4 east LAB-step 2",          (10, 10), (12, 10)),
    ("1 C4 down",                     (10, 10), (10, 11)),
    ("C4 up only, multi-hop",         (10, 10), (10,  4)),
    ("C4 up then R4 east",            (10, 10), (16,  8)),
    ("C4 down + R4 east multi",       (10, 10), (28, 21)),
    ("src(4,5)→dst(16,8) far row",    ( 4,  5), (16,  8)),
    ("src(21,12)→dst(8,16) westwd",   (21, 12), ( 8, 16)),
]

# Note: (5,5),(15,8),(20,12),(8,16) — verify they exist in LAB_X/LAB_Y
from config import LAB_X, LAB_Y
print(f"LAB_X = {LAB_X}")
print(f"LAB_Y = {LAB_Y}")
print()


def main():
    fails = 0
    for label, src, dst in CASES:
        try:
            need = parse_need(src, dst)
        except ValueError as e:
            print(f"  SKIP {label} src={src} dst={dst}: {e}")
            continue
        plan = plan_hops(need)
        print(f"  {src} → {dst}  (ddx={need.ddx:+d} ddy={need.ddy:+d})")
        print(f"    plan: {fmt(plan)}")

        # Sanity: cumulative span should reach dst
        cur_x, cur_y = need.sx, need.sy
        for h in plan:
            if h.type == "C4":
                cur_y = LAB_Y[LAB_Y.index(cur_y) + h.span]
            elif h.type in ("R4", "R24"):
                cur_x = LAB_X[LAB_X.index(cur_x) + h.span]
        ok = (cur_x == need.dx and cur_y == need.dy) or need.same_lab
        marker = "✓" if ok else "✗"
        print(f"    landed at ({cur_x},{cur_y})  expected ({need.dx},{need.dy})  {marker}")
        if not ok:
            fails += 1
        print()

    print(f"=== {len(CASES)-fails}/{len(CASES)} cases land correctly ===")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
