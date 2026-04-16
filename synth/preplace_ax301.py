# SPDX-License-Identifier: GPL-3.0-or-later
"""nextpnr-generic --pre-place hook for ax301_top.

Binds every GENERIC_IOB cell created by the IO packer to its pinned IOB bel
based on the AX301 board pin map (BOARD_PINS_AX301 in fuzz/config.py).
Without this, nextpnr picks an arbitrary IOB per port and the chipdb's
single LOCAL gateway can't always bridge that IOB to the placed fabric LE
(see Stage A.5 PROBE 3 SD_NCS / iob_S_A_11_I single-arc routing failure).

Usage:
    nextpnr-generic --pre-pack results/chipdb_ep4ce6.py \
                    --pre-place synth/preplace_ax301.py \
                    --json tmp/ax301_synth/ax301.json --router router2
"""
import sys
sys.path.insert(0, "/home/test/EP4CE6/fuzz")

from config import BOARD_PINS_AX301
from nextpnrpy_generic import PlaceStrength

# cell-name (post-pack: <port>$iob) -> bel-name.
# chipdb keeps legacy single-letter names (IOB_A_PIN_E16, IOB_F_PIN_L16, ...)
# for the original 9 IOBs even after the 55-bel expansion, so we look up the
# bel by its PIN_<loc> suffix rather than by the port-derived "safe" name.
# Walk the chipdb via ctx.getBels(): BelId is a str, and every IOB bel name
# contains "_PIN_<loc>". Build pin_loc -> bel_name map.
_bel_by_pin = {}
for _bel in ctx.getBels():
    # _bel is a BelId (str). Only IOB bels carry GENERIC_IOB type.
    if ctx.getBelType(_bel) != "GENERIC_IOB":
        continue
    _idx = _bel.rfind("_PIN_")
    if _idx < 0:
        continue
    _pin = _bel[_idx + 1:]  # "PIN_xxx"
    _bel_by_pin[_pin] = _bel

_pin_map = {}
for _port, _pin_loc in BOARD_PINS_AX301.items():
    _bel_name = _bel_by_pin.get(_pin_loc)
    if _bel_name is None:
        raise RuntimeError(
            f"[preplace_ax301] chipdb has no IOB bel at {_pin_loc} "
            f"(port {_port}) — check chipdb_gen.py expansion"
        )
    _pin_map[_port + "$iob"] = _bel_name

bound = 0
already = 0
unmapped = []
unavailable = []
for _kv in ctx.cells:
    _cell = _kv.second
    _name = _kv.first
    if _cell.type != "GENERIC_IOB":
        continue
    _bel_name = _pin_map.get(_name)
    if _bel_name is None:
        unmapped.append(_name)
        continue
    if _cell.bel is not None:
        already += 1
        continue
    if not ctx.checkBelAvail(_bel_name):
        unavailable.append((_name, _bel_name))
        continue
    ctx.bindBel(_bel_name, _cell, PlaceStrength.STRENGTH_LOCKED)
    bound += 1

print(f"[preplace_ax301] bound={bound} already={already} "
      f"unmapped={len(unmapped)} unavailable={len(unavailable)}")
if unmapped:
    print(f"[preplace_ax301] unmapped cells: {unmapped}")
if unavailable:
    print(f"[preplace_ax301] unavailable bels: {unavailable}")
