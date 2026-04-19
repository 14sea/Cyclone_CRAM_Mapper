#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Post-route-mining pipeline: CLK_SEL_LE → IOB → FASM regeneration → bitgen
# Run this after mine_missing_routes.py completes.
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "=== Post-route-mining pipeline ==="
echo "Step 1: CLK_SEL_LE batch mining (437 LABs × 16 N-slots)"
python3 scripts/clk_sel_batch_mine.py \
    --fasm tmp/ax301_new.fasm \
    --parallel 12

echo ""
echo "Step 2: IOB pin mining (22 missing pins)"
python3 scripts/iob_pin_batch_mine.py \
    --fasm tmp/ax301_new.fasm \
    --parallel 12

echo ""
echo "Step 3: Regenerate FASM"
python3 synth/np2fasm.py --base pure tmp/ax301_placed.json tmp/ax301_new.fasm

echo ""
echo "Step 4: bitgen (non-lenient)"
python3 -c "
import sys
sys.path.insert(0, 'fuzz')
from fasm2rbf import bitgen
from pure_zero_rbf import make_pure_zero_rbf

fasm = open('tmp/ax301_new.fasm').read()
base = make_pure_zero_rbf()
try:
    rbf = bitgen(fasm, base, lenient=False)
    with open('tmp/ax301_full.rbf', 'wb') as f:
        f.write(rbf)
    print(f'SUCCESS: wrote tmp/ax301_full.rbf ({len(rbf)} bytes)')
except Exception as e:
    print(f'Non-lenient bitgen failed: {e}')
    print('Falling back to lenient mode...')
    rbf = bitgen(fasm, base, lenient=True)
    with open('tmp/ax301_lenient.rbf', 'wb') as f:
        f.write(rbf)
    print(f'Wrote tmp/ax301_lenient.rbf ({len(rbf)} bytes, lenient)')
" 2>&1

echo ""
echo "=== Pipeline complete ==="
