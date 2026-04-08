# SPDX-License-Identifier: GPL-3.0-or-later
"""δ expansion — push (22,12) past 60 routes to test if fp=1 is small-N too."""
import sys, os
import os as _os
REPO = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runner import compile_route_pair_single_input, compile_route_baseline_abcd

SX, SY = 22, 12
DSTS = [
    (22,2),(22,4),(22,6),(22,9),(22,16),(22,19),(22,21),
    (3,12),(7,12),(11,12),(17,12),(25,12),(29,12),(31,12),
    (16,4),(28,4),(13,16),(19,16),(25,16),(28,9),
    (4,21),(31,21),(4,2),(31,2),(16,8),(7,17),
    (10,14),(13,8),(19,4),(25,21),
]

def main():
    ztag = f"lits_zero_{SX}_{SY}"
    if not os.path.exists(f"{REPO}/results/rbf/{ztag}.rbf"):
        compile_route_baseline_abcd(ztag, SX, SY, 0)
    ok=fail=0
    for dx,dy in DSTS:
        tag=f"lits_pair_X{SX}Y{SY}_to_X{dx}Y{dy}N0_datab"
        path=f"{REPO}/results/rbf/{tag}.rbf"
        if os.path.exists(path):
            ok+=1; continue
        rbf,t,err=compile_route_pair_single_input(tag,SX,SY,0,dx,dy,0,connect_port="datab")
        if rbf: ok+=1
        else: fail+=1; print(f"FAIL {tag}: {(err or '').split(';')[0][:60]}")
    print(f"summary: {ok} OK, {fail} fail")

if __name__=="__main__": main()
