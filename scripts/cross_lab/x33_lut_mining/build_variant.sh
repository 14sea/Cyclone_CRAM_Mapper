#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Build one X=33 LUT TT mining variant via Quartus.
# Usage: ./build_variant.sh <variant>
#   variant ∈ {and2, or2, xor2, andn2, ...}
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"
QUARTUS_BIN="$HOME/intelFPGA_lite/21.1/quartus/bin"
export PATH="$PATH:$QUARTUS_BIN"

VARIANT="${1:?usage: build_variant.sh <variant>}"
# Variants prefixed with "cl_" use cross_lab.v 2-LE structure (forces X=33 placement).
MOD="v_${VARIANT}"
WORK="$REPO/tmp/x33_lut_mining/$VARIANT"
mkdir -p "$WORK"
cp "$SCRIPT_DIR/${MOD}.v" "$WORK/${MOD}.v"

# Generate qsf
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
echo "=== quartus_map ==="
quartus_map "$VARIANT" 2>&1 | tail -10
echo "=== quartus_fit ==="
quartus_fit "$VARIANT" 2>&1 | tail -20
echo "=== quartus_asm ==="
quartus_asm "$VARIANT" 2>&1 | tail -10
echo "=== quartus_cpf -> uncompressed RBF ==="
quartus_cpf -c -o bitstream_compression=off "$VARIANT.sof" "$VARIANT.rbf" 2>&1 | tail -5
ls -la "$VARIANT.rbf"
md5sum "$VARIANT.rbf"

# Show placement summary
echo "=== fit summary ==="
grep -E "Total logic|Total combinational|Dedicated logic|Total registers" "$VARIANT.fit.summary" || true
echo "=== resource section ==="
awk '/^Loc/,/^$/' "$VARIANT.fit.rpt" | head -30 || true
