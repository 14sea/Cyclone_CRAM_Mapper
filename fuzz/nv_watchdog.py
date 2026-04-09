# SPDX-License-Identifier: GPL-3.0-or-later
"""Task C — factory watchdog. Tails status.json + work dir every 5 min,
prints rate / failure / disk metrics, alerts on stalls (no new RBF in 30
min) or disk pressure (work/ > 20 GB).
"""
import json, time, os, sys, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS = ROOT / 'results' / 'plan_d_prime_status.json'
FAIL = ROOT / 'results' / 'plan_d_prime_failures.json'
RBF = ROOT / 'results' / 'rbf'
WORK = ROOT / 'work' / 'nvfac'

INTERVAL = 300   # 5 min
STALL_MIN = 30   # stall alert threshold
WORK_CAP_GB = 20


def _du(path):
    if not path.exists():
        return 0.0
    try:
        out = subprocess.check_output(['du', '-sb', str(path)], stderr=subprocess.DEVNULL)
        return int(out.split()[0]) / (1024**3)
    except Exception:
        return 0.0


def _rbf_count():
    return sum(1 for _ in RBF.glob('nv_pair_*.rbf'))


def _factory_alive():
    try:
        out = subprocess.check_output(['pgrep', '-f', 'plan_d_prime_factory'])
        return bool(out.strip())
    except subprocess.CalledProcessError:
        return False


def main():
    t0 = time.time()
    last_count = _rbf_count()
    last_count_at = time.time()
    print(f'[watchdog] start — {last_count} RBFs present', flush=True)
    while True:
        time.sleep(INTERVAL)
        now = time.time()
        alive = _factory_alive()
        n = _rbf_count()
        work_gb = _du(WORK)
        fails = 0
        if FAIL.exists():
            try:
                fails = len(json.loads(FAIL.read_text()))
            except Exception:
                pass
        status = {}
        if STATUS.exists():
            try:
                status = json.loads(STATUS.read_text())
            except Exception:
                pass
        done = status.get('n_done', 0)
        planned = status.get('n_total_planned', 0)
        if n > last_count:
            last_count_at = now
            last_count = n
        stall_min = (now - last_count_at) / 60
        rate = (n - 0) / max(now - t0, 1)  # this-session rate
        eta_h = (planned - done) / rate / 3600 if rate > 0 and planned else 0
        elapsed_h = (now - t0) / 3600

        alerts = []
        if not alive:
            alerts.append('FACTORY DEAD')
        if stall_min > STALL_MIN:
            alerts.append(f'STALL {stall_min:.0f}min')
        if work_gb > WORK_CAP_GB:
            alerts.append(f'WORK {work_gb:.1f}GB > cap')

        flag = '!!' if alerts else '  '
        ts = time.strftime('%H:%M:%S')
        line = (f'[wd {ts}] {flag} rbf={n} done={done}/{planned} fail={fails} '
                f'work={work_gb:.1f}GB rate={rate:.2f}/s eta={eta_h:.1f}h '
                f'alive={alive} stall={stall_min:.0f}m elapsed={elapsed_h:.1f}h')
        if alerts:
            line += ' ALERTS=' + ','.join(alerts)
        print(line, flush=True)

        if not alive and done >= planned - 5:
            print('[watchdog] factory clean-exit detected — stopping watchdog')
            break


if __name__ == '__main__':
    main()
