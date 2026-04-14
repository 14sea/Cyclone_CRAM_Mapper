#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build one design: quartus_map -> quartus_fit -> quartus_asm -> quartus_cpf
set -e
export PATH=$PATH:$HOME/intelFPGA_lite/21.1/quartus/bin
cd "$1"
quartus_map top  >  map.log 2>&1
quartus_fit top  >  fit.log 2>&1
quartus_asm top  >  asm.log 2>&1
quartus_cpf -c -o bitstream_compression=off output_files/top.sof output_files/top.rbf > cpf.log 2>&1
echo "DONE $1"
