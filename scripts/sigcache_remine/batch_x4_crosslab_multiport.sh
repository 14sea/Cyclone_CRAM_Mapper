#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Batch driver — fills X=4 cross-LAB R4 sigcache port-coverage gaps.
#
# Background: Pitfall #14 — formula-fallback for cross-LAB ROUTE emits
# silicon-hostile cells.  Pre-2026-05-10 the X=4 cross-LAB sigcache had
# 37 entries; only the X4Y4N0 → X4Y{near}N0.datab "base table" was
# coverage-systematic, all other ports/sources were ad-hoc per-design.
#
# This script systematically extends with two batches:
#
#   Batch A  39 entries  X4Y4N0 → X4Y{2,3,5..11,17..21}N0.{a,c,d}
#                        (datab already covered; fills 3 missing ports
#                         per dst Y for the base table)
#   Batch B  33 entries  X4Y17N{0,14,16} → X4Y{4,21}N{0,16}.{a,b,c,d}
#                        (Path B-relevant: chain-start / mid / chain-end
#                         LE @ X4Y17 to common Y4 / Y21 destinations)
#
# Mining methodology: each invocation calls
#   scripts/sigcache_remine/mine_x4_cross_lab_route.py
# which builds a 2-LUT pair via Quartus CE10 (~10s) + diffs vs
# nv_zero_global.rbf + writes both nv_route_cells.json (canonical) and
# route_cells_full.json (runtime).  Resumable: cached pair RBFs are
# skipped on re-run.
#
# Total wall time: Batch A ~7 min, Batch B ~6 min.  Total ~13 min for
# 72 entries on a 4-core dev box.
#
# Cell-count note: dataa/datac/datad share the same R4 backbone and
# differ by only ~8 cells (LE-input MUX); datab is structurally
# different (~60 cells, direct C4-style) for vertical hops.  Both are
# real and serve different Quartus router decisions.
#
# Re-run safety: if an entry already exists, the underlying script
# warns and overwrites — but that overwrite is byte-identical for the
# same Quartus version.
#
# Usage:  ./scripts/sigcache_remine/batch_x4_crosslab_multiport.sh
#
# Pre-req: PATH must include $HOME/intelFPGA_lite/21.1/quartus/bin

set -u  # do NOT set -e — continue past Quartus failures

PASS=0; FAIL=0; SKIP=0
LOG=tmp/batch_x4_crosslab_multiport.log
mkdir -p tmp
: > "$LOG"

mine() {
    local src="$1" dst="$2" port="$3"
    echo "------ $src -> $dst.$port ------" >> "$LOG"
    if python3 scripts/sigcache_remine/mine_x4_cross_lab_route.py \
            --src "$src" --dst "$dst" --port "$port" >> "$LOG" 2>&1; then
        PASS=$((PASS+1))
        echo "  OK $src -> $dst.$port"
    else
        rc=$?
        if [ $rc -eq 1 ]; then
            FAIL=$((FAIL+1))
            echo "  FAIL (Quartus) $src -> $dst.$port"
        else
            SKIP=$((SKIP+1))
            echo "  SKIP (no diff) $src -> $dst.$port"
        fi
    fi
}

echo "=== Batch A: X4Y4N0 multi-port (datab already covered) ==="
for dy in 2 3 5 6 7 8 9 10 11 17 18 19 21; do
    for port in dataa datac datad; do
        mine "4,4,0" "4,${dy},0" "$port"
    done
done

echo
echo "=== Batch B: X4Y17N{0,14,16} → Y4/Y21 destinations ==="
for sn in 0 16; do
    for dst in "4,4,0" "4,4,16" "4,21,0"; do
        for port in dataa datab datac datad; do
            mine "4,17,${sn}" "${dst}" "${port}"
        done
    done
done
# Fill missing ports for X4Y17N14 (which already had .dataa for 4,4,0 / 4,4,16 / 4,21,0)
for dst in "4,4,0" "4,4,16" "4,21,0"; do
    for port in datab datac datad; do
        mine "4,17,14" "${dst}" "${port}"
    done
done

echo
echo "=== Batch totals: PASS=$PASS FAIL=$FAIL SKIP=$SKIP ==="
echo "Full log: $LOG"
