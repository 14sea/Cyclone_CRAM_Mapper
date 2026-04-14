#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Launch all 24 builds with parallelism cap
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
# Resolve directories relative to the script's own location so this works
# whether invoked from the repo root or anywhere else.
HERE="$(cd "$(dirname "$0")" && pwd)"           # scripts/arith_sweep
WORK="$(cd "$HERE/../.." && pwd)/tmp/arith_sweep"  # repo-root/tmp/arith_sweep
cd "$WORK"
ls -d c?_lo c?_up i?_lo i?_up 2>/dev/null | \
    xargs -I {} -P 8 bash -c 'bash "$0" "$1"' "$HERE/build_one.sh" "$WORK/{}"
echo "ALL_BUILDS_DONE"
