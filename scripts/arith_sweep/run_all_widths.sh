#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Launch the full arith sweep (widths 2..8 lo/up, 9..15 xh, 17..32 ml).
# Parallelism cap -P 8.  Skips dirs whose output_files/top.rbf already exists
# so partial reruns are safe.
#
# Usage: bash scripts/arith_sweep/run_all_widths.sh
set -e
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="$(cd "$HERE/../.." && pwd)/tmp/arith_sweep"
cd "$WORK"

# Enumerate all candidate design dirs.
mapfile -t DIRS < <(ls -d \
    c?_lo c?_up i?_lo i?_up \
    c??_xh i??_xh \
    c??_ml i??_ml \
    c?_xh i?_xh \
    2>/dev/null | sort -u)

TODO=()
for d in "${DIRS[@]}"; do
    if [ -f "$WORK/$d/output_files/top.rbf" ]; then
        echo "SKIP $d (already built)"
        continue
    fi
    TODO+=("$d")
done

echo "Launching ${#TODO[@]} builds..."
if [ ${#TODO[@]} -gt 0 ]; then
    printf '%s\n' "${TODO[@]}" | \
        xargs -I {} -P 8 bash -c 'bash "$0" "$1"' "$HERE/build_one.sh" "$WORK/{}"
fi
echo "ALL_BUILDS_DONE"
