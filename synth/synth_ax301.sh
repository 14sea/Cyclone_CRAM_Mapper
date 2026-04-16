#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Wrapper for synth_ax301.ys (board-level NEORV32 SoC + SDRAM
# controller, top entity = ax301_top, exposes 51 pins).
#
# Why this exists: same reason as synth_ep4ce6.sh — Yosys .ys scripts
# don't expand $HOME, so we envsubst before invoking yosys.
#
# Usage:
#   ./synth/synth_ax301.sh                            # uses defaults
#   NEORV32_ROOT=/path/to/neorv32 \
#   AX301_RTL=/path/to/see_neorv32_run_linux/rtl \
#       ./synth/synth_ax301.sh
#
# Requirements: yosys (with ghdl-yosys-plugin), envsubst (gettext-base).

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

export NEORV32_ROOT="${NEORV32_ROOT:-$HOME/neorv32_rot}"
export AX301_RTL="${AX301_RTL:-$HOME/see_neorv32_run_linux/rtl}"

SRC="$(cat synth/synth_ax301.ys)"
if [[ "$NEORV32_ROOT" != "$HOME/neorv32_rot" ]]; then
    echo "[synth_ax301] NEORV32_ROOT=$NEORV32_ROOT (overriding default)"
    SRC="$(printf '%s' "$SRC" | sed "s#\$HOME/neorv32_rot#$NEORV32_ROOT#g")"
fi
if [[ "$AX301_RTL" != "$HOME/see_neorv32_run_linux/rtl" ]]; then
    echo "[synth_ax301] AX301_RTL=$AX301_RTL (overriding default)"
    SRC="$(printf '%s' "$SRC" | sed "s#\$HOME/see_neorv32_run_linux/rtl#$AX301_RTL#g")"
fi

mkdir -p tmp/ax301_synth

# GHDL 7.0.0-dev (oss-cad-suite Apr 2026) crashes with
# "Exception SYSTEM.ASSERTIONS.ASSERT_FAILURE : no field Actual" when
# elaborating individual element associations of an unconstrained
# output slice with `open` (the spi_csn_o(1..7) => open lines in
# ax301_top.vhd). Patch the source on-the-fly to use a slice
# association instead, which GHDL handles fine.
PATCHED="tmp/ax301_synth/ax301_top.patched.vhd"
python3 - "$AX301_RTL/ax301_top.vhd" "$PATCHED" <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
# Strip the seven `spi_csn_o(N) => open[,]` lines and rewrite the
# spi_csn_o(0) line to associate the whole slice with a sink signal
# `spi_csn_dump_sig` (declared just before `begin`). GHDL 7.0.0-dev's
# elaborator crashes ("no field Actual") on ANY individual element /
# slice association with `open`, so we route the unused bits to a
# real signal instead.
for n in range(1, 8):
    text = re.sub(
        rf'^\s*spi_csn_o\({n}\)\s*=>\s*open,?\s*$\n', '', text,
        flags=re.MULTILINE,
    )
text = text.replace(
    'spi_csn_o(0) => SD_NCS,',
    'spi_csn_o    => spi_csn_dump_sig',
)
# Inject the sink signal declaration. Architecture uses
# `architecture rtl of ax301_top is` — place the signal just before
# the matching `begin` of the architecture. Simpler: append after the
# first `architecture rtl of ax301_top is\n` line.
text = re.sub(
    r'(architecture\s+rtl\s+of\s+ax301_top\s+is\s*\n)',
    r'\1  signal spi_csn_dump_sig : std_ulogic_vector(7 downto 0);\n',
    text, count=1, flags=re.IGNORECASE,
)
# And drive SD_NCS from spi_csn_dump_sig(0) with a concurrent assign.
# Insert just before `end architecture rtl;` (or `end rtl;`).
text = re.sub(
    r'(\n\s*end\s+(?:architecture\s+)?rtl\s*;)',
    r'\n  SD_NCS <= spi_csn_dump_sig(0);\1',
    text, count=1, flags=re.IGNORECASE,
)
open(dst, 'w').write(text)
PY

# Rewrite the .ys reference to ax301_top.vhd to point at the patched copy.
SRC="$(printf '%s' "$SRC" | sed "s#\$HOME/see_neorv32_run_linux/rtl/ax301_top.vhd#$ROOT/$PATCHED#g")"

EXPANDED="tmp/ax301_synth/synth_ax301.expanded.ys"
printf '%s\n' "$SRC" | envsubst '$HOME' > "$EXPANDED"

echo "[synth_ax301] running: yosys -s $EXPANDED"
yosys -s "$EXPANDED"
