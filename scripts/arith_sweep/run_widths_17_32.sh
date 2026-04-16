#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Launch all multi-LAB (widths 17..32) builds in parallel (cap -P 8).
# Usage: bash scripts/arith_sweep/run_widths_17_32.sh
set -e
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin

HERE="$(cd "$(dirname "$0")" && pwd)"           # scripts/arith_sweep
WORK="$(cd "$HERE/../.." && pwd)/tmp/arith_sweep"  # repo-root/tmp/arith_sweep
cd "$WORK"

# Match c{w}_ml and i{w}_ml tag forms (widths 17..32).
ls -d c??_ml i??_ml 2>/dev/null | \
    xargs -I {} -P 8 bash -c 'bash "$0" "$1"' "$HERE/build_one.sh" "$WORK/{}"
echo "ALL_MULTILAB_BUILDS_DONE"
