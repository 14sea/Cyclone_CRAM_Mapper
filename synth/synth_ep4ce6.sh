#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Wrapper for synth_ep4ce6.ys.
#
# Why this exists: Yosys .ys scripts do NOT expand $HOME or other shell
# variables, so absolute paths to the NEORV32 VHDL tree would have to be
# hard-coded — which breaks on every other machine. This wrapper expands
# env vars in the .ys via `envsubst`, drops the result in tmp/, and runs
# yosys on the expanded script. Paths inside the .ys therefore stay
# portable (`$HOME/neorv32_rot/...`) and no one has to hand-edit.
#
# Usage:
#   ./synth/synth_ep4ce6.sh                 # uses $HOME/neorv32_rot
#   NEORV32_ROOT=/path/to/neorv32 ./synth/synth_ep4ce6.sh
#
# Requirements: yosys (with ghdl-yosys-plugin), envsubst (gettext-base).

set -euo pipefail

# Resolve repo root from this script's location so the wrapper works
# whether invoked from the repo root or anywhere else.
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

# Default NEORV32 checkout location; override by exporting NEORV32_ROOT.
export NEORV32_ROOT="${NEORV32_ROOT:-$HOME/neorv32_rot}"

# The .ys references $HOME (not $NEORV32_ROOT) for backwards compat with
# the existing convention; remap if the user pointed NEORV32_ROOT elsewhere.
if [[ "$NEORV32_ROOT" != "$HOME/neorv32_rot" ]]; then
    echo "[synth_ep4ce6] NEORV32_ROOT=$NEORV32_ROOT (overriding default)"
    # Rewrite $HOME/neorv32_rot references to the custom root before envsubst.
    SRC="$(sed "s#\$HOME/neorv32_rot#$NEORV32_ROOT#g" synth/synth_ep4ce6.ys)"
else
    SRC="$(cat synth/synth_ep4ce6.ys)"
fi

mkdir -p tmp/nv32_synth
EXPANDED="tmp/nv32_synth/synth_ep4ce6.expanded.ys"
printf '%s\n' "$SRC" | envsubst '$HOME' > "$EXPANDED"

echo "[synth_ep4ce6] running: yosys -s $EXPANDED"
yosys -s "$EXPANDED"
