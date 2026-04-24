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
from m9k_init_basis import M9K_INIT_ANCHORS
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

print(f"[preplace_ax301] IOB: bound={bound} already={already} "
      f"unmapped={len(unmapped)} unavailable={len(unavailable)}",
      file=sys.stderr, flush=True)
if unmapped:
    print(f"[preplace_ax301] unmapped cells: {unmapped}",
          file=sys.stderr, flush=True)
if unavailable:
    print(f"[preplace_ax301] unavailable bels: {unavailable}",
          file=sys.stderr, flush=True)

# --- M9K pre-placement: bind EP4CE6_M9K cells to calibrated sites ---
def _yosys_int(val):
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        s = val.strip()
        if not s:
            return None
        try:
            return int(s, 2)
        except ValueError:
            try:
                return int(s, 0)
            except ValueError:
                return None
    return None

_m9k_sites_by_geom = {}
for (site, w, d) in M9K_INIT_ANCHORS:
    _m9k_sites_by_geom.setdefault((w, d), []).append(site)
for k in _m9k_sites_by_geom:
    _m9k_sites_by_geom[k] = sorted(set(_m9k_sites_by_geom[k]))

_m9k_cells_by_geom = {}
for _kv in ctx.cells:
    _cell = _kv.second
    _name = _kv.first
    if _cell.type != "EP4CE6_M9K":
        continue
    try:
        _w = _yosys_int(str(_cell.params["WIDTH_A"]))
    except (KeyError, IndexError):
        _w = None
    try:
        _d = _yosys_int(str(_cell.params["DEPTH"]))
    except (KeyError, IndexError):
        _d = None
    if _w is None or _d is None:
        continue
    _m9k_cells_by_geom.setdefault((_w, _d), []).append((_name, _cell))

_m9k_used = set()
_m9k_bound = 0
_m9k_err = []
for (_w, _d), _group in _m9k_cells_by_geom.items():
    _avail = [s for s in _m9k_sites_by_geom.get((_w, _d), [])
              if s not in _m9k_used]
    if len(_avail) < len(_group):
        _m9k_err.append(f"{len(_group)} EP4CE6_M9K at {_w}x{_d} but "
                        f"only {len(_avail)} sites")
        continue
    for (_cname, _ccell), _site in zip(sorted(_group), _avail):
        _bel_name = f"M9K_{_site}"
        if _ccell.bel is not None:
            continue
        if not ctx.checkBelAvail(_bel_name):
            _m9k_err.append(f"{_cname}: bel {_bel_name} unavailable")
            continue
        ctx.bindBel(_bel_name, _ccell, PlaceStrength.STRENGTH_LOCKED)
        _m9k_used.add(_site)
        _m9k_bound += 1

print(f"[preplace_ax301] M9K: bound={_m9k_bound} errors={len(_m9k_err)}",
      file=sys.stderr, flush=True)
for _e in _m9k_err:
    print(f"[preplace_ax301] M9K ERROR: {_e}",
          file=sys.stderr, flush=True)
