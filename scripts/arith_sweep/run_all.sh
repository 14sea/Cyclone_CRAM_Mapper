#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Launch all 24 builds with parallelism cap
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
cd /tmp/arith_sweep
ls -d c?_lo c?_up i?_lo i?_up 2>/dev/null | \
    xargs -I {} -P 8 bash -c 'bash /tmp/arith_sweep/build_one.sh /tmp/arith_sweep/{}'
echo "ALL_BUILDS_DONE"
