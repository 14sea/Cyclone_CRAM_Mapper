#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 M2 — nextpnr-generic chipdb generator for EP4CE6.

Emits two artifacts in ``results/``:

* ``chipdb_ep4ce6_data.json`` — compact data blob describing every bel,
  wire, and pip that nextpnr needs.  Produced from ``fuzz/config.py``
  geometry, ``results/route_cells_full.json`` (13,487 Plan D' sig-cache
  entries covering 95.9% of the NEORV32 edge set), and the
  ``M9K_INIT_ANCHORS`` table from ``fuzz/m9k_init_basis.py``.

* ``chipdb_ep4ce6.py`` — tiny ``nextpnr-generic --run`` entry point that
  loads the JSON blob and populates ``ctx`` via the generic Python API.
  Kept intentionally small so nextpnr's Python startup is cheap.

Usage
-----
::

    python3 fuzz/chipdb_gen.py
    nextpnr-generic --uarch generic --run results/chipdb_ep4ce6.py \\
        --json tmp/nv32_synth/neorv32.json --top neorv32_top \\
        --write tmp/nv32_synth/neorv32_routed.json

Scope / limits
--------------
* Bels: one ``EP4CE6_SLICE`` per (X, Y, N) LAB slot (``GENERIC_SLICE``
  in nextpnr terms — the packer folds LUT4+DFF into it); ``EP4CE6_IOB``
  for the AX301 pin map from ``config.ROUTE_FUZZ_PINS``; one
  ``EP4CE6_M9K`` per (X, Y, N=0) site at X in {15, 27}, Y 2..21.
* Wires: one output wire per slice (``Q``), four input wires per slice
  (``dataa..datad``), plus every unique endpoint mentioned in the
  route sig-cache (lazily created).
* Pips: exactly one per sig-cache key
  ``"sx,sy,sn->dx,dy,dn,port"``; delay is a placeholder (non-timing-
  driven P&R at this stage — NEORV32 is 46% utilised so slack should
  be ample even without STA).
* M9K bels carry an ``anchor`` attribute so np2fasm (M4) can look up
  the per-site byte anchor for ``write_init``.

This is a functional-first first pass.  Things deliberately *not* in
M2 scope: per-pip delay annotations, IO standard assignments,
carry-chain bels, PLL bels, timing-driven placement hints.  All are
follow-ups once M5/M6 prove the chain.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import config  # noqa: E402
from m9k_init_basis import M9K_INIT_ANCHORS  # noqa: E402

ROOT = HERE.parent
RESULTS = ROOT / "results"

DATA_PATH = RESULTS / "chipdb_ep4ce6_data.json"
SCRIPT_PATH = RESULTS / "chipdb_ep4ce6.py"

# Full LAB grid including the jailbreak columns/rows. The chipdb lives
# on true silicon, not the CE6 fitter whitelist — nextpnr should be
# free to place anywhere the silicon supports.
LAB_X_FULL = sorted(set(config.LAB_X) | set(config.JAILBREAK_LAB_X))
LAB_Y_FULL = sorted(set(config.LAB_Y) | set(config.JAILBREAK_LAB_Y))
LE_N = config.LE_N
M9K_X = [15, 27]
M9K_Y = list(range(2, 22))

CARRY_DELAY = 1          # cout→cin direct pip — cheapest (dedicated wire,
                         # no LI MUX, no LOCAL bus contention). Equal to
                         # SIG so the router prefers it for chain arcs.
SIG_DELAY = 1            # SIG pips (FASM-backed) — cheapest
INTRA_DELAY = 2          # intra-LAB direct pips — within-LAB
LOCAL_DELAY = 5          # LOCAL_IN / LOCAL_OUT — entering/leaving bus
HOP_DELAY = 20           # LOCAL_HOP — expensive, discourages long chains
PLACEHOLDER_DELAY = 1    # default (used for GCLK, IOB bridge)

# Number of parallel LOCAL tracks per LAB. Each wire in nextpnr is a
# single-net resource, so one LOCAL per LAB = one net per LAB — that
# starves the clock arc as soon as any data arc claims the bus.
# Keep small (8) to avoid pip-count blowup but big enough to carry
# counter-class designs (~32 nets distributed across LABs).
NUM_LOCAL_TRACKS = 4

SLICE_INPUTS = ("dataa", "datab", "datac", "datad")
# Map sig-cache port labels to nextpnr-generic SLICE pin indices.
PORT_TO_PIN_IDX = {"dataa": 0, "datab": 1, "datac": 2, "datad": 3}


def _wire_slice_cout(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_COUT"


def _wire_slice_cin(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_CIN"


def _wire_slice_out(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_Q"


def _wire_slice_in(x: int, y: int, n: int, port: str) -> str:
    return f"slice_X{x}_Y{y}_N{n}_{port}"


def _wire_m9k_port(x: int, y: int, port: str) -> str:
    return f"m9k_X{x}_Y{y}_N0_{port}"


def _wire_m9k_bit(x: int, y: int, port: str, i: int) -> str:
    return f"m9k_X{x}_Y{y}_N0_{port}_{i}"


# (port_name, width, is_output). Both ports emitted unconditionally so
# the bel's pin surface is fixed regardless of design mode (SP/SDP/TDP).
# See tmp/m9k_chipdb_expansion_plan.md §2 for rationale.
M9K_PORT_SPEC = [
    ("CLK_A", 1, False), ("WE_A", 1, False), ("RE_A", 1, False),
    ("ADDR_A", 13, False), ("DIN_A", 36, False), ("DOUT_A", 36, True),
    ("CLK_B", 1, False), ("WE_B", 1, False), ("RE_B", 1, False),
    ("ADDR_B", 13, False), ("DIN_B", 36, False), ("DOUT_B", 36, True),
]


def _wire_iob(name: str, kind: str) -> str:
    return f"iob_{name}_{kind}"


def build_chipdb() -> dict:
    bels: list[dict] = []
    wires: list[dict] = []
    belpins: list[dict] = []
    pips: list[dict] = []

    # Compute the IOB list first (merge ROUTE_FUZZ_PINS ∪ BOARD_PINS_AX301,
    # dedupe by pin_loc) so grid_w can accommodate every pin on the
    # Y=grid_h-1 border row. Without this, placing ax301_top (55 unique
    # board pins) overflows the default grid_w=35 that only fits LAB
    # columns + M9K.
    seen_locs: dict[str, str] = {}
    iob_entries: list[tuple[str, str]] = []
    for pin_name, pin_loc in {**config.ROUTE_FUZZ_PINS,
                              **config.BOARD_PINS_AX301}.items():
        if pin_loc in seen_locs:
            continue
        seen_locs[pin_loc] = pin_name
        iob_entries.append((pin_name, pin_loc))

    # Grid extents for nextpnr. Use inclusive max and add a 1-tile
    # margin for the IO ring so IOB bels can sit at (0, y) / (x, 0).
    # grid_w must also be wide enough for every IOB along the border.
    grid_w = max(max(LAB_X_FULL + M9K_X) + 2, len(iob_entries) + 1)
    grid_h = max(LAB_Y_FULL + M9K_Y) + 2

    # ---------- LAB slices ----------
    for x in LAB_X_FULL:
        for y in LAB_Y_FULL:
            if (x, y) in config.INVALID_LABS:
                continue
            for n in LE_N:
                name = f"SLICE_X{x}_Y{y}_N{n}"
                bels.append({
                    "name": name,
                    "type": "GENERIC_SLICE",
                    "x": x, "y": y, "z": n,
                })
                qw = _wire_slice_out(x, y, n)
                wires.append({"name": qw, "type": "SLICE_Q", "x": x, "y": y})
                belpins.append({
                    "bel": name, "pin": "Q", "wire": qw, "output": True,
                })
                # F = combinational LUT output; GENERIC_SLICE packer
                # requires it. Alias to the same Q wire — external
                # routing can't tell the two apart at our granularity.
                fw = f"slice_X{x}_Y{y}_N{n}_F"
                wires.append({"name": fw, "type": "SLICE_F", "x": x, "y": y})
                belpins.append({
                    "bel": name, "pin": "F", "wire": fw, "output": True,
                })
                # CLK pin — needed so nextpnr's packer can route the
                # global clock onto every FF slice.
                cw = f"slice_X{x}_Y{y}_N{n}_CLK"
                wires.append({"name": cw, "type": "SLICE_CLK",
                              "x": x, "y": y})
                belpins.append({"bel": name, "pin": "CLK",
                                "wire": cw, "output": False})
                for idx, port in enumerate(SLICE_INPUTS):
                    iw = _wire_slice_in(x, y, n, port)
                    wires.append({"name": iw, "type": "SLICE_IN",
                                  "x": x, "y": y})
                    belpins.append({"bel": name, "pin": f"I[{idx}]",
                                    "wire": iw, "output": False})
                # Carry chain pins — COUT (output) drives the next LE's
                # CIN (input) through a dedicated direct pip. No LI MUX
                # involved, so the packer must not route these through
                # LOCAL. Chain topology is declared in the pip section
                # below, per cycloneive_carry_chain_topology memory.
                cow = _wire_slice_cout(x, y, n)
                wires.append({"name": cow, "type": "SLICE_COUT",
                              "x": x, "y": y})
                belpins.append({"bel": name, "pin": "COUT",
                                "wire": cow, "output": True})
                ciw = _wire_slice_cin(x, y, n)
                wires.append({"name": ciw, "type": "SLICE_CIN",
                              "x": x, "y": y})
                belpins.append({"bel": name, "pin": "CIN",
                                "wire": ciw, "output": False})

    # ---------- M9K bels ----------
    for x in M9K_X:
        for y in M9K_Y:
            site = f"X{x}_Y{y}_N0"
            name = f"M9K_{site}"
            # anchor/bp if we've calibrated this site at 9x512 — M4 uses
            # it to emit FASM M9K.INIT directives.
            anchor = M9K_INIT_ANCHORS.get((site, 9, 512))
            bels.append({
                "name": name,
                "type": "EP4CE6_M9K",
                "x": x, "y": y, "z": 0,
                "anchor": anchor,  # [byte, bp] or None
            })
            for port, width, is_out in M9K_PORT_SPEC:
                if width == 1:
                    wn = _wire_m9k_port(x, y, port)
                    wires.append({"name": wn, "type": "M9K_" + port,
                                  "x": x, "y": y})
                    belpins.append({
                        "bel": name, "pin": port, "wire": wn,
                        "output": is_out,
                    })
                else:
                    for i in range(width):
                        wn = _wire_m9k_bit(x, y, port, i)
                        wires.append({"name": wn, "type": "M9K_" + port,
                                      "x": x, "y": y})
                        belpins.append({
                            "bel": name, "pin": f"{port}[{i}]", "wire": wn,
                            "output": is_out,
                        })

    # ---------- IOBs (AX301 pin map + routing-fuzz pins) ----------
    # Put IOBs on the border row Y=grid_h-1 and spread along X so
    # nextpnr has distinct (x,y,z) locations. They don't carry routing
    # at M2 — np2fasm will emit BIT lines for them later.
    #
    # iob_entries is the merged ROUTE_FUZZ_PINS ∪ BOARD_PINS_AX301 list
    # (deduped by pin_loc) computed at the top of build_chipdb so grid_w
    # can size to fit. PIN_E1 appears once even though it's labelled
    # "CLK" by the fuzz pins and "CLOCK" by the AX301 wrapper.
    for i, (pin_name, pin_loc) in enumerate(iob_entries):
        # Bel/wire/pip identifiers must be filename-safe — '[' / ']' in
        # bus signal names like "S_DB[0]" trip nextpnr's name-validator.
        safe = pin_name.replace("[", "_").replace("]", "")
        name = f"IOB_{safe}_{pin_loc}"
        bels.append({
            "name": name, "type": "GENERIC_IOB",
            "x": i, "y": grid_h - 1, "z": 0,
            "pin": pin_loc,
        })
        wi = _wire_iob(safe, "I")
        wo = _wire_iob(safe, "O")
        we = _wire_iob(safe, "EN")
        wires.extend([
            {"name": wi, "type": "IOB_I", "x": i, "y": grid_h - 1},
            {"name": wo, "type": "IOB_O", "x": i, "y": grid_h - 1},
            {"name": we, "type": "IOB_EN", "x": i, "y": grid_h - 1},
        ])
        belpins.extend([
            {"bel": name, "pin": "I", "wire": wi, "output": False},
            {"bel": name, "pin": "O", "wire": wo, "output": True},
            {"bel": name, "pin": "EN", "wire": we, "output": False},
        ])
    # Defer IOB<->LOCAL bridge pips until LOCAL wires exist (below).

    # ---------- Synthetic LOCAL-bus overlay (densification) ----------
    # Plan D' sig-cache only covers NEORV32-observed edges; it's too
    # sparse for arbitrary small-design routing (the counter smoke
    # test exposed this). Mimic Cyclone IV LOCAL_INTERCONNECT + LAB-
    # neighbor hops with a hierarchical bus: per LAB one LOCAL wire
    # that every slice Q/F drives and every slice I reads, plus 8
    # Moore-neighbour LOCAL->LOCAL pips.  Linear cost (~100 pips/LAB
    # instead of O(N^2)) and gives the router full connectivity.
    # These pips have NO FASM backing — np2fasm will either fall back
    # to route_synth or flag unroutable FASM. Marked type="LOCAL" so
    # M4 can distinguish them from the "SIG" sig-cache pips.
    local_wires: set[tuple[int, int]] = set()
    valid_labs = [(x, y) for x in LAB_X_FULL for y in LAB_Y_FULL
                  if (x, y) not in config.INVALID_LABS]
    valid_lab_set = set(valid_labs)

    # ---------- Carry chain direct pips ----------
    # cout→cin is a dedicated silicon wire, not routed via LI MUX or
    # LOCAL. Within LAB: N→N+2 for N in [0,2,...,28]. Between LABs:
    # N30 of (x,y) → N0 of (x, y-1) in the same column, only when
    # Y-1 is physically adjacent (no gap). See memory
    # cycloneive_carry_chain_topology.md for the two-fit verification.
    n_pips_carry = 0
    for (x, y) in valid_labs:
        # Within-LAB chain (LE_N ascending; N=30 is terminal).
        for i in range(len(LE_N) - 1):
            n_src, n_dst = LE_N[i], LE_N[i + 1]
            pips.append({
                "name": f"pip_carry_X{x}_Y{y}_N{n_src}__N{n_dst}",
                "type": "CARRY",
                "src": _wire_slice_cout(x, y, n_src),
                "dst": _wire_slice_cin(x, y, n_dst),
                "delay": CARRY_DELAY,
                "x": x, "y": y,
            })
            n_pips_carry += 1
        # Between-LAB chain: N30 → (x, y-1).N0 if the LAB directly
        # below is also valid. INVALID_LABS gaps break the chain.
        if (x, y - 1) in valid_lab_set:
            pips.append({
                "name": f"pip_carry_X{x}_Y{y}_N30__X{x}_Y{y - 1}_N0",
                "type": "CARRY",
                "src": _wire_slice_cout(x, y, 30),
                "dst": _wire_slice_cin(x, y - 1, 0),
                "delay": CARRY_DELAY,
                "x": x, "y": y - 1,
            })
            n_pips_carry += 1

    for (x, y) in valid_labs:
        for t in range(NUM_LOCAL_TRACKS):
            wires.append({
                "name": f"LOCAL_X{x}_Y{y}_T{t}",
                "type": "LOCAL", "x": x, "y": y,
            })
        local_wires.add((x, y))
    n_local_pips = 0
    for (x, y) in valid_labs:
        xi = LAB_X_FULL.index(x)
        yi = LAB_Y_FULL.index(y)

        # ----- Intra-LAB direct pips (Q/F → I[0..3]) -----
        # Within the same LAB, slices connect via the LOCAL bus
        # hardware, but we model it as direct pips to avoid track
        # contention. 16×16×4 = 1024 pips per LAB.
        for n_src in LE_N:
            for out_pin in ("Q", "F"):
                src = (_wire_slice_out(x, y, n_src) if out_pin == "Q"
                       else f"slice_X{x}_Y{y}_N{n_src}_F")
                for n_dst in LE_N:
                    for port in SLICE_INPUTS:
                        dst = _wire_slice_in(x, y, n_dst, port)
                        pips.append({
                            "name": f"pip_{src}__{dst}",
                            "type": "INTRA_LAB",
                            "src": src, "dst": dst,
                            "delay": INTRA_DELAY,
                            "x": x, "y": y,
                        })
                        n_local_pips += 1

        # ----- LOCAL tracks for inter-LAB routing -----
        for t in range(NUM_LOCAL_TRACKS):
            lw = f"LOCAL_X{x}_Y{y}_T{t}"
            # slice outputs -> LOCAL track
            for n in LE_N:
                for src in (_wire_slice_out(x, y, n),
                            f"slice_X{x}_Y{y}_N{n}_F"):
                    pips.append({
                        "name": f"pip_{src}__{lw}",
                        "type": "LOCAL_IN",
                        "src": src, "dst": lw,
                        "delay": LOCAL_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1
            # LOCAL track -> slice inputs (I[0..3] and CLK)
            for n in LE_N:
                dsts = [_wire_slice_in(x, y, n, port)
                        for port in SLICE_INPUTS]
                dsts.append(f"slice_X{x}_Y{y}_N{n}_CLK")
                for dw in dsts:
                    pips.append({
                        "name": f"pip_{lw}__{dw}",
                        "type": "LOCAL_OUT",
                        "src": lw, "dst": dw,
                        "delay": LOCAL_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1
            # Same-track 4-neighbour hops (N/S/E/W only, no diagonals
            # — reduces fan-out from 8 to 4 per wire, halving
            # pathfinder search space).
            for dxi, dyi in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nxi, nyi = xi + dxi, yi + dyi
                    if not (0 <= nxi < len(LAB_X_FULL)):
                        continue
                    if not (0 <= nyi < len(LAB_Y_FULL)):
                        continue
                    nx, ny = LAB_X_FULL[nxi], LAB_Y_FULL[nyi]
                    if (nx, ny) not in local_wires:
                        continue
                    dst = f"LOCAL_X{nx}_Y{ny}_T{t}"
                    pips.append({
                        "name": f"pip_{lw}__{dst}",
                        "type": "LOCAL_HOP",
                        "src": lw, "dst": dst,
                        "delay": HOP_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1

    # ---------- Dedicated global clock network ----------
    # A single GCLK wire carries one clock net with direct fanout to
    # every slice CLK pin. Bypasses LOCAL so the clock never competes
    # with data arcs for track allocation. Any IOB_O can drive it.
    wires.append({"name": "GCLK", "type": "GCLK", "x": 0, "y": 0})
    for (pin_name, _pl) in iob_entries:
        safe = pin_name.replace("[", "_").replace("]", "")
        wo = _wire_iob(safe, "O")
        pips.append({
            "name": f"pip_iob_{safe}_O__GCLK",
            "type": "IOB_TO_GCLK",
            "src": wo, "dst": "GCLK",
            "delay": PLACEHOLDER_DELAY, "x": 0, "y": 0,
        })
        n_local_pips += 1
    for (x, y) in valid_labs:
        for n in LE_N:
            cw = f"slice_X{x}_Y{y}_N{n}_CLK"
            pips.append({
                "name": f"pip_GCLK__{cw}",
                "type": "GCLK_TO_CLK",
                "src": "GCLK", "dst": cw,
                "delay": PLACEHOLDER_DELAY, "x": x, "y": y,
            })
            n_local_pips += 1

    # ---------- IOB <-> LOCAL bridge ----------
    # Every IOB output (driver into fabric, e.g. clock input pad) gets
    # a pip into every LOCAL bus so clock/reset/input signals can
    # reach any LAB. Every IOB input (pad-driver from fabric) is
    # reachable from every LOCAL so outputs can land anywhere. Cost:
    # ~9 IOBs × 392 LABs × 2 = ~7k pips, linear and tiny.
    # Single-entry IOB bridge: each IOB pads into ONE "gateway" LAB
    # LOCAL (and reads from the same one). Propagation to the rest of
    # the fabric uses LOCAL-hop chains. Avoids the combinatorial
    # explosion of an all-LABs-per-IOB fanout that hung the router.
    # One entry per IOB, but onto every track at the gateway LAB so
    # different IOB nets can pick different tracks and not collide.
    # Inputs (pad->fabric, non-clock): single gateway LAB LOCAL entry.
    # Outputs (fabric->pad): direct slice-Q->IOB_I fanout, symmetric
    # to GCLK. Each IOB_I is one wire carrying one net, so direct
    # fanout is safe (no track contention) and pathfinder cost is
    # a single hop instead of exploring LOCAL.
    gx, gy = valid_labs[len(valid_labs) // 2]
    for (pin_name, _pin_loc) in iob_entries:
        safe = pin_name.replace("[", "_").replace("]", "")
        wi = _wire_iob(safe, "I")  # fabric -> pad
        wo = _wire_iob(safe, "O")  # pad -> fabric
        for t in range(NUM_LOCAL_TRACKS):
            gw = f"LOCAL_X{gx}_Y{gy}_T{t}"
            pips.append({
                "name": f"pip_iob_{safe}_O__{gw}",
                "type": "IOB_TO_LOCAL",
                "src": wo, "dst": gw,
                "delay": PLACEHOLDER_DELAY, "x": gx, "y": gy,
            })
            n_local_pips += 1
        we = _wire_iob(safe, "EN")  # OE from fabric
        for (x, y) in valid_labs:
            for n in LE_N:
                src = _wire_slice_out(x, y, n)
                pips.append({
                    "name": f"pip_{src}__iob_{safe}_I",
                    "type": "SLICE_TO_IOB",
                    "src": src, "dst": wi,
                    "delay": PLACEHOLDER_DELAY, "x": x, "y": y,
                })
                pips.append({
                    "name": f"pip_{src}__iob_{safe}_EN",
                    "type": "SLICE_TO_IOB",
                    "src": src, "dst": we,
                    "delay": PLACEHOLDER_DELAY, "x": x, "y": y,
                })
                n_local_pips += 2

    # ---------- M9K <-> LOCAL bridge + GCLK -> CLK ----------
    # Mirrors the IOB gateway-LAB pattern above. For each M9K site,
    # pick the nearest valid LAB column on the same row (or closest Y
    # if the row has no LAB) as the gateway: every M9K input bit reads
    # from the gateway's LOCAL tracks; every M9K output bit drives
    # them; CLK_A/CLK_B come from the global GCLK wire. See
    # tmp/m9k_chipdb_expansion_plan.md §3 for topology + budget.
    n_pips_m9k = 0
    for x in M9K_X:
        for y in M9K_Y:
            gx, gy = min(
                valid_labs,
                key=lambda lab: (abs(lab[0] - x), abs(lab[1] - y)),
            )
            for port, width, is_out in M9K_PORT_SPEC:
                if port.startswith("CLK"):
                    # Feed CLK directly from GCLK, not LOCAL.
                    cw = _wire_m9k_port(x, y, port)
                    pips.append({
                        "name": f"pip_GCLK__{cw}",
                        "type": "GCLK_TO_M9K_CLK",
                        "src": "GCLK", "dst": cw,
                        "delay": PLACEHOLDER_DELAY, "x": x, "y": y,
                    })
                    n_pips_m9k += 1
                    continue
                bits = [_wire_m9k_port(x, y, port)] if width == 1 else \
                       [_wire_m9k_bit(x, y, port, i) for i in range(width)]
                for w in bits:
                    for t in range(NUM_LOCAL_TRACKS):
                        gw = f"LOCAL_X{gx}_Y{gy}_T{t}"
                        if is_out:
                            pips.append({
                                "name": f"pip_{w}__{gw}",
                                "type": "M9K_OUT",
                                "src": w, "dst": gw,
                                "delay": LOCAL_DELAY, "x": gx, "y": gy,
                            })
                        else:
                            pips.append({
                                "name": f"pip_{gw}__{w}",
                                "type": "M9K_IN",
                                "src": gw, "dst": w,
                                "delay": LOCAL_DELAY, "x": gx, "y": gy,
                            })
                        n_pips_m9k += 1

    # ---------- Pips from Plan D' sig-cache (overlay) ----------
    cache_path = RESULTS / "route_cells_full.json"
    cache = json.loads(cache_path.read_text())
    known_wires = {w["name"] for w in wires}
    pip_count = 0
    skipped_unknown_src = 0
    skipped_unknown_dst = 0
    for key in cache.keys():
        try:
            left, right = key.split("->")
            sx, sy, sn = (int(v) for v in left.split(","))
            dx_s, dy_s, dn_s, port = right.split(",")
            dx, dy, dn = int(dx_s), int(dy_s), int(dn_s)
        except ValueError:
            continue
        src_wire = _wire_slice_out(sx, sy, sn)
        dst_wire = _wire_slice_in(dx, dy, dn, port)
        if src_wire not in known_wires:
            skipped_unknown_src += 1
            continue
        if dst_wire not in known_wires:
            skipped_unknown_dst += 1
            continue
        pips.append({
            "name": f"pip_{sx}_{sy}_{sn}__{dx}_{dy}_{dn}_{port}",
            "type": "SIG",
            "src": src_wire,
            "dst": dst_wire,
            "delay": SIG_DELAY,
            "x": dx, "y": dy,
        })
        pip_count += 1

    return {
        "grid_w": grid_w,
        "grid_h": grid_h,
        "bels": bels,
        "wires": wires,
        "belpins": belpins,
        "pips": pips,
        "stats": {
            "n_bels": len(bels),
            "n_wires": len(wires),
            "n_belpins": len(belpins),
            "n_pips_total": len(pips),
            "n_pips_sig": pip_count,
            "n_pips_local": n_local_pips,
            "n_pips_carry": n_pips_carry,
            "n_pips_m9k": n_pips_m9k,
            "pips_skipped_unknown_src": skipped_unknown_src,
            "pips_skipped_unknown_dst": skipped_unknown_dst,
        },
    }


_RUNNER_TEMPLATE = '''\
# SPDX-License-Identifier: GPL-3.0-or-later
"""nextpnr-generic --run entry point for EP4CE6 (auto-generated).

Do not edit by hand; regenerate with ``python3 fuzz/chipdb_gen.py``.
"""
import json, os
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DATA = json.loads((_HERE / "chipdb_ep4ce6_data.json").read_text())

# ctx is injected by nextpnr-generic when invoked with --run.
# Loc is exposed under the generic Python API.
try:
    from nextpnrpy_generic import Loc  # type: ignore
except ImportError:
    Loc = globals().get("Loc")  # provided by --run environment

_delays = {}
for cost in set(p["delay"] for p in _DATA["pips"]):
    _delays[cost] = ctx.getDelayFromNS(cost * 0.5)

for w in _DATA["wires"]:
    ctx.addWire(name=w["name"], type=w["type"], x=w["x"], y=w["y"])

for b in _DATA["bels"]:
    ctx.addBel(name=b["name"], type=b["type"],
               loc=Loc(b["x"], b["y"], b["z"]),
               gb=False, hidden=False)

for bp in _DATA["belpins"]:
    if bp["output"]:
        ctx.addBelOutput(bel=bp["bel"], name=bp["pin"], wire=bp["wire"])
    else:
        ctx.addBelInput(bel=bp["bel"], name=bp["pin"], wire=bp["wire"])

for p in _DATA["pips"]:
    ctx.addPip(name=p["name"], type=p["type"],
               srcWire=p["src"], dstWire=p["dst"],
               delay=_delays[p["delay"]],
               loc=Loc(p["x"], p["y"], 0))

print("[chipdb_ep4ce6] loaded:",
      _DATA["stats"]["n_bels"], "bels,",
      _DATA["stats"]["n_wires"], "wires,",
      _DATA["stats"]["n_pips_total"], "pips")
'''


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Generate nextpnr-generic chipdb for EP4CE6")
    ap.add_argument("--region", metavar="X0,Y0,X1,Y1",
                    help="Restrict SLICE placement to bounding box "
                         "(e.g. --region 13,6,18,14)")
    ap.add_argument("--no-jailbreak", action="store_true",
                    help="Exclude jailbreak columns/rows (CE6 whitelist only)")
    args = ap.parse_args()

    global LAB_X_FULL, LAB_Y_FULL

    if args.no_jailbreak:
        LAB_X_FULL = sorted(config.LAB_X)
        LAB_Y_FULL = sorted(config.LAB_Y)
        print(f"[no-jailbreak] CE6 whitelist only: {len(LAB_X_FULL)} cols × {len(LAB_Y_FULL)} rows")

    if args.region:
        x0, y0, x1, y1 = (int(v) for v in args.region.split(","))
        LAB_X_FULL = [x for x in LAB_X_FULL if x0 <= x <= x1]
        LAB_Y_FULL = [y for y in LAB_Y_FULL if y0 <= y <= y1]
        print(f"[region] placement restricted to X=[{x0},{x1}] Y=[{y0},{y1}]"
              f" → {len(LAB_X_FULL)} cols × {len(LAB_Y_FULL)} rows")

    data = build_chipdb()
    DATA_PATH.write_text(json.dumps(data, indent=1))
    SCRIPT_PATH.write_text(_RUNNER_TEMPLATE)

    s = data["stats"]
    print(f"wrote {DATA_PATH.name}")
    print(f"wrote {SCRIPT_PATH.name}")
    print(f"grid: {data['grid_w']} x {data['grid_h']}")
    print(f"bels:    {s['n_bels']:>7d}")
    print(f"wires:   {s['n_wires']:>7d}")
    print(f"belpins: {s['n_belpins']:>7d}")
    print(f"pips total: {s['n_pips_total']:>7d} "
          f"(sig {s['n_pips_sig']} + local {s['n_pips_local']} "
          f"+ carry {s['n_pips_carry']})")
    print(f"pips skipped (unknown src slice): "
          f"{s['pips_skipped_unknown_src']}")
    print(f"pips skipped (unknown dst slice): "
          f"{s['pips_skipped_unknown_dst']}")


if __name__ == "__main__":
    main()
