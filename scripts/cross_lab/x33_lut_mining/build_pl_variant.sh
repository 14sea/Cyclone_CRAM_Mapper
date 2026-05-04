#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build one 1-LE @ X33Y4N4 TT-variant (probe2-class corpus, M16 reserved).
# Usage: ./build_pl_variant.sh <variant>
#   variant ∈ {pl_and, pl_or, pl_xor, pl_xnor, pl_andn, pl_orn, pl_nor}
#
# Differs from build_variant.sh: uses key2 (E16) + key4 (M15), NOT key3 (M16).
# This keeps M16 reserved like probe2 — corpus is intersectable with the
# probe2 silicon-validated reference for 1-LE topology codec analysis.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"
QUARTUS_BIN="$HOME/intelFPGA_lite/21.1/quartus/bin"
export PATH="$PATH:$QUARTUS_BIN"

VARIANT="${1:?usage: build_pl_variant.sh <variant>}"
MOD="v_${VARIANT}"
WORK="$REPO/tmp/x33_lut_mining/$VARIANT"
mkdir -p "$WORK"
cp "$SCRIPT_DIR/${MOD}.v" "$WORK/${MOD}.v"

cat > "$WORK/$VARIANT.qsf" <<EOF
set_global_assignment -name FAMILY "Cyclone IV E"
set_global_assignment -name DEVICE EP4CE6F17C8
set_global_assignment -name TOP_LEVEL_ENTITY $MOD
set_global_assignment -name VERILOG_FILE ${MOD}.v
set_global_assignment -name GENERATE_RBF_FILE ON
set_location_assignment PIN_E1  -to clk
set_location_assignment PIN_E16 -to key2
set_location_assignment PIN_M16 -to key3
set_location_assignment PIN_G15 -to led0
set_global_assignment -name RESERVE_ALL_UNUSED_PINS "As input tri-stated with weak pull-up"
set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"
set_instance_assignment -name FAST_OUTPUT_REGISTER OFF -to led0
set_instance_assignment -name FAST_INPUT_REGISTER OFF -to key2
set_instance_assignment -name FAST_INPUT_REGISTER OFF -to key3
set_global_assignment -name SEED 1
set_global_assignment -name LAST_QUARTUS_VERSION "21.1.0 Lite Edition"
EOF

cat > "$WORK/$VARIANT.qpf" <<EOF
QUARTUS_VERSION = "21.1"
PROJECT_REVISION = "$VARIANT"
EOF

cd "$WORK"
echo "=== [$VARIANT] quartus_map ==="
quartus_map "$VARIANT" 2>&1 | tail -3
echo "=== [$VARIANT] quartus_fit ==="
quartus_fit "$VARIANT" 2>&1 | tail -5
echo "=== [$VARIANT] quartus_asm ==="
quartus_asm "$VARIANT" 2>&1 | tail -3
echo "=== [$VARIANT] quartus_cpf -> uncompressed RBF ==="
quartus_cpf -c -o bitstream_compression=off "$VARIANT.sof" "$VARIANT.rbf" 2>&1 | tail -3
ls -la "$VARIANT.rbf"
md5sum "$VARIANT.rbf"
