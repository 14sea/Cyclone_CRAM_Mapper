# SPDX-License-Identifier: GPL-3.0-or-later
"""Task B — global baseline + plain sig extractor.

Compiles a single nv_zero_global.rbf (empty 2-LUT dummy under CE10), then
XOR-diffs every nv_pair_*.rbf against it to populate
results/nv_route_cells.json. No per-source intersection; the diff cell
list contains src LUT TT + dst LUT TT + routing. Downstream consumers
can strip known LUT bits via LutCodec.

Runs continuously (polls every 5 min) until the factory finishes.
"""
import os, sys, json, time, re, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from verilog_gen import gen_two_luts_single_input_clocked
from compile import compile_and_export
from plan_d_prime_factory import gen_qsf_ce10

RBF = ROOT / 'results' / 'rbf'
BASE = RBF / 'nv_zero_global.rbf'
OUT = ROOT / 'results' / 'nv_route_cells.json'
WORK = ROOT / 'work' / 'nvbase'

POLL_SEC = 300
NAME_RE = re.compile(
    r'nv_pair_X(\d+)Y(\d+)N(\d+)_to_X(\d+)Y(\d+)N(\d+)_(\w+)\.rbf$'
)


def build_baseline():
    if BASE.exists() and BASE.stat().st_size == 368011:
        print(f'[base] reusing {BASE.name}', flush=True)
        return
    print('[base] compiling nv_zero_global...', flush=True)
    WORK.mkdir(parents=True, exist_ok=True)
    verilog = gen_two_luts_single_input_clocked(0x0000, 0x0000, connect_port='datab')
    # Park lut1/lut2 at safe CE6-legal LE positions we already know compile.
    placement = {
        'lut1': 'LCCOMB_X10_Y10_N0',
        'lut2': 'LCCOMB_X10_Y11_N0',
    }
    qsf = gen_qsf_ce10(placement, seed=1)
    rbf, elapsed, err = compile_and_export(
        'nv_zero_global', verilog, qsf,
        rbf_output=str(BASE), work_dir=str(WORK),
    )
    if not rbf:
        raise RuntimeError(f'baseline compile failed: {err}')
    print(f'[base] built in {elapsed:.1f}s', flush=True)


def diff_cells(target, zero):
    cells = []
    for n in range(25, 1752):
        s = 32 + n * 210
        for off in range(s, s + 208):
            x = target[off] ^ zero[off]
            if x:
                for bp in range(8):
                    if (x >> bp) & 1:
                        cells.append((off, bp))
    return cells


def factory_alive():
    try:
        subprocess.check_output(['pgrep', '-f', 'plan_d_prime_factory'])
        return True
    except subprocess.CalledProcessError:
        return False


def load_existing():
    if OUT.exists():
        try:
            return json.loads(OUT.read_text())
        except Exception:
            return {}
    return {}


def main():
    build_baseline()
    zero = BASE.read_bytes()

    table = load_existing()
    print(f'[extract] starting with {len(table)} existing entries', flush=True)

    idle_rounds = 0
    while True:
        added = 0
        for p in RBF.glob('nv_pair_*.rbf'):
            m = NAME_RE.match(p.name)
            if not m:
                continue
            sx, sy, sn = int(m[1]), int(m[2]), int(m[3])
            dx, dy, dn, port = int(m[4]), int(m[5]), int(m[6]), m[7]
            key = f'{sx},{sy},{sn}->{dx},{dy},{dn},{port}'
            if key in table:
                continue
            try:
                cells = diff_cells(p.read_bytes(), zero)
                table[key] = cells
                added += 1
            except Exception as e:
                print(f'  ERR {key}: {e}', flush=True)
            if added and added % 500 == 0:
                ts = time.strftime('%H:%M:%S')
                print(f'[extract {ts}] +{added} (total {len(table)})', flush=True)
                tmp = OUT.with_suffix('.tmp')
                tmp.write_text(json.dumps(table))
                os.replace(tmp, OUT)

        if added:
            tmp = OUT.with_suffix('.tmp')
            tmp.write_text(json.dumps(table))
            os.replace(tmp, OUT)
            ts = time.strftime('%H:%M:%S')
            print(f'[extract {ts}] round done +{added} new, total {len(table)}',
                  flush=True)
            idle_rounds = 0
        else:
            idle_rounds += 1

        if not factory_alive() and idle_rounds >= 2:
            print(f'[extract] factory done + no new files — exit. '
                  f'Final: {len(table)} entries.', flush=True)
            break
        time.sleep(POLL_SEC)


if __name__ == '__main__':
    main()
