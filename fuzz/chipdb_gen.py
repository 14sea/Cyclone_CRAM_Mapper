#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Phase 5.3 M2 — nextpnr-generic chipdb generator for EP4CE6.

Emits two artifacts in ``results/``:

* ``chipdb_ep4ce6_data.json`` — compact data blob describing every bel,
  wire, and pip that nextpnr needs.  Produced from ``fuzz/config.py``
  geometry, ``results/route_cells_full.json`` (38,683 sig-cache entries
  from demand mining), and the ``M9K_INIT_ANCHORS`` table from
  ``fuzz/m9k_init_basis.py``.

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

import gzip
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

DATA_PATH = RESULTS / "chipdb_ep4ce6_data.json.gz"
SCRIPT_PATH = RESULTS / "chipdb_ep4ce6.py"

# Full LAB grid including the jailbreak columns/rows. The chipdb lives
# on true silicon, not the CE6 fitter whitelist — nextpnr should be
# free to place anywhere the silicon supports.
LAB_X_FULL = sorted(set(config.LAB_X) | set(config.JAILBREAK_LAB_X))
LAB_Y_FULL = sorted(set(config.LAB_Y) | set(config.JAILBREAK_LAB_Y))
LE_N = config.LE_N
M9K_X = [15, 27]
M9K_Y = list(range(2, 24))

CARRY_DELAY = 1          # cout→cin direct pip — cheapest (dedicated wire,
                         # no LI MUX, no LOCAL bus contention). Equal to
                         # SIG so the router prefers it for chain arcs.
SIG_DELAY = 1            # SIG pips (FASM-backed) — cheapest
INTRA_DELAY = 2          # intra-LAB direct pips — within-LAB
LOCAL_DELAY = 5          # LOCAL_IN / LOCAL_OUT — entering/leaving bus
HOP_DELAY = 15           # LOCAL_HOP — base cost (scaled ×distance)
MAX_HOP_DIST = 8         # Reach 8 valid neighbours per direction
PLACEHOLDER_DELAY = 1    # default (used for IOB bridge)
DEDICATED_DELAY = 0      # GCLK_BUS / GND_BUS — zero-delay dedicated
                         # networks (silicon-accurate); pips cost 0 so
                         # router2 prefers them over LOCAL for their
                         # exclusive fan-out (CLOCK, constant-0).

# Number of parallel LOCAL tracks per LAB.  Real Cyclone IV has 26 LI
# wires per LAB; match that so the router has realistic capacity for
# NEORV32-class designs (~6600 LUTs).  SIG pips handle most long-range
# routes; LOCAL carries the remainder.
NUM_LOCAL_TRACKS = 26

SLICE_INPUTS = ("dataa", "datab", "datac", "datad")
# Map sig-cache port labels to nextpnr-generic SLICE pin indices.
PORT_TO_PIN_IDX = {"dataa": 0, "datab": 1, "datac": 2, "datad": 3}

# Cyclone IV has 4 dedicated global clock networks (GCLK_BUS). Only the
# 12 F17-package dedicated clock pins can drive them. Source of truth:
# clk_pins_full_f17_coverage.md (A14/B14/M1 not on AX301 board, but
# valid silicon-level GCLK sources so included here for completeness).
F17_GCLK_PINS = frozenset([
    "PIN_E1", "PIN_R8", "PIN_N1", "PIN_M1", "PIN_M2",
    "PIN_T4", "PIN_R4", "PIN_M16", "PIN_M15", "PIN_E15",
    "PIN_A14", "PIN_B14",
])
NUM_GCLK_TRACKS = 4


def _wire_slice_cout(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_COUT"


def _wire_slice_cin(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_CIN"


def _wire_slice_out(x: int, y: int, n: int) -> str:
    return f"slice_X{x}_Y{y}_N{n}_Q"


def _wire_slice_in(x: int, y: int, n: int, port: str) -> str:
    return f"slice_X{x}_Y{y}_N{n}_{port}"


def _wire_carry_in(x: int, y: int, n: int, port: str) -> str:
    """CE6_CARRY's dedicated A/B input wires.

    Distinct from `slice_X{x}_Y{y}_N{n}_{dataa,datab}` so CE6_CARRY and
    GENERIC_SLICE can co-exist at the same LE position without two
    different nets (e.g. PACKER_GND on CE6_CARRY.A and a real D-net on
    SLICE.I[0]) ending up on the same physical wire.

    Silicon truth: A/B inputs to the carry primitive enter through the
    same LAB local interconnect as the LUT inputs, but carry has its
    own selection MUX inside the LE.  We model that as a separate wire
    fed by the same drivers (LOCAL tracks, intra-LAB Q/F/carry_S).

    See `path_alpha_progress_2026_05_03_night.md` and the X4_Y21_N28
    collision diagnosis in the 2026-05-04 session log for the bug this
    fixes.
    """
    return f"carry_X{x}_Y{y}_N{n}_{port}"


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


def build_chipdb(*, num_local_tracks: int = NUM_LOCAL_TRACKS,
                 max_hop_dist: int = MAX_HOP_DIST,
                 sig_routing_only: bool = False) -> dict:
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

                # CE6_CARRY bel — co-located with GENERIC_SLICE at each
                # LE position. Shares the CIN/COUT carry wires and reuses
                # I[0]/I[1] for the A/B data inputs.  S (sum output) gets
                # its own wire so CE6_CARRY.S and GENERIC_SLICE.Q don't
                # collide — they're logically the same LE output but
                # nextpnr needs distinct driver belpins to avoid
                # multi-driver errors when only one cell type is placed.
                carry_name = f"CARRY_X{x}_Y{y}_N{n}"
                carry_z = n + 100
                bels.append({
                    "name": carry_name,
                    "type": "CE6_CARRY",
                    "x": x, "y": y, "z": carry_z,
                })
                # S output — drives a dedicated wire that feeds into the
                # same LOCAL bus the SLICE Q wire feeds into, so
                # downstream sinks can reach it via the same LOCAL pips.
                sw = f"carry_X{x}_Y{y}_N{n}_S"
                wires.append({"name": sw, "type": "CARRY_S",
                              "x": x, "y": y})
                belpins.append({
                    "bel": carry_name, "pin": "S", "wire": sw,
                    "output": True,
                })
                # CO — reuse existing COUT wire
                belpins.append({
                    "bel": carry_name, "pin": "CO", "wire": cow,
                    "output": True,
                })
                # CI — reuse existing CIN wire
                belpins.append({
                    "bel": carry_name, "pin": "CI", "wire": ciw,
                    "output": False,
                })
                # A, B — dedicated carry-input wires distinct from
                # GENERIC_SLICE's I[0]/I[1] (= dataa/datab).  Sharing
                # the wires causes router2 to fail with
                #
                #   attempting to reserve sink input path wire
                #   'slice_X{x}_Y{y}_N{n}_dataa' for nets '...' and
                #   '$PACKER_GND_NET'
                #
                # whenever a CE6_CARRY and a co-located GENERIC_SLICE
                # both place at the same LE — the packer ties one's
                # unused input to PACKER_GND while the other carries a
                # real net.  Driver pips below feed the new wires from
                # the same sources as I[0..3] so routing capacity is
                # preserved.
                aw = _wire_carry_in(x, y, n, "A")
                bw = _wire_carry_in(x, y, n, "B")
                wires.append({"name": aw, "type": "CARRY_IN",
                              "x": x, "y": y})
                wires.append({"name": bw, "type": "CARRY_IN",
                              "x": x, "y": y})
                belpins.append({
                    "bel": carry_name, "pin": "A",
                    "wire": aw, "output": False,
                })
                belpins.append({
                    "bel": carry_name, "pin": "B",
                    "wire": bw, "output": False,
                })

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
    # 26 LOCAL tracks per LAB matches real Cyclone IV LI wire count.
    # SIG pips (38k FASM-backed routes) handle most inter-LAB routing;
    # LOCAL carries whatever SIG doesn't cover.  np2fasm independently
    # queries the sig-cache by (src,dst) pair — it doesn't care which
    # chipdb pip type the router chose.  Marked type="LOCAL" so np2fasm
    # can distinguish from "SIG" sig-cache pips.
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
        for t in range(num_local_tracks):
            wires.append({
                "name": f"LOCAL_X{x}_Y{y}_T{t}",
                "type": "LOCAL", "x": x, "y": y,
            })
        local_wires.add((x, y))
    n_local_pips = 0
    for (x, y) in valid_labs:
        xi = LAB_X_FULL.index(x)
        yi = LAB_Y_FULL.index(y)

        # ----- Intra-LAB direct pips (Q/F → I[0..3] + carry_A/B) -----
        # Within the same LAB, slices connect via the LOCAL bus
        # hardware, but we model it as direct pips to avoid track
        # contention. 16×16×6 = 1536 pips per LAB.  carry_A/B are now
        # their own wires (see _wire_carry_in) so the same Q/F driver
        # can independently feed both a SLICE input and a co-located
        # CE6_CARRY input.
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
                    for cport in ("A", "B"):
                        dst = _wire_carry_in(x, y, n_dst, cport)
                        pips.append({
                            "name": f"pip_{src}__{dst}",
                            "type": "INTRA_LAB",
                            "src": src, "dst": dst,
                            "delay": INTRA_DELAY,
                            "x": x, "y": y,
                        })
                        n_local_pips += 1

        # ----- CE6_CARRY S → intra-LAB SLICE + co-located CARRY -----
        for n_src in LE_N:
            carry_s = f"carry_X{x}_Y{y}_N{n_src}_S"
            for n_dst in LE_N:
                for port in SLICE_INPUTS:
                    dst = _wire_slice_in(x, y, n_dst, port)
                    pips.append({
                        "name": f"pip_{carry_s}__{dst}",
                        "type": "INTRA_LAB",
                        "src": carry_s, "dst": dst,
                        "delay": INTRA_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1
                for cport in ("A", "B"):
                    dst = _wire_carry_in(x, y, n_dst, cport)
                    pips.append({
                        "name": f"pip_{carry_s}__{dst}",
                        "type": "INTRA_LAB",
                        "src": carry_s, "dst": dst,
                        "delay": INTRA_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1

        # ----- LE-internal feedback: SLICE.Q → co-located CARRY.B -----
        # On Cyclone IV silicon, the DFF.Q at one LE drives the same
        # LE's CE6_CARRY.B input directly through an internal MUX, no
        # external routing.  Quartus carry counters emit ZERO route
        # cells for this feedback (memory `phase54_first_flash_lab418`).
        # Model it as a zero-delay pip so nextpnr-generic's router can
        # legalise a placed-CARRY-and-DFF-at-same-N pattern; np2fasm's
        # carry-chain walker recognises the same-LE pair and emits a
        # single LUT_ARITH directive without a sig-cache ROUTE.
        for n in LE_N:
            qw = _wire_slice_out(x, y, n)
            for cport in ("A", "B"):
                dst = _wire_carry_in(x, y, n, cport)
                pips.append({
                    "name": f"pip_{qw}__{dst}_internal",
                    "type": "LE_INTERNAL",
                    "src": qw, "dst": dst,
                    "delay": 0,
                    "x": x, "y": y,
                })
                n_local_pips += 1

        # ----- LOCAL tracks for inter-LAB routing -----
        for t in range(num_local_tracks):
            lw = f"LOCAL_X{x}_Y{y}_T{t}"
            # slice outputs -> LOCAL track
            for n in LE_N:
                for src in (_wire_slice_out(x, y, n),
                            f"slice_X{x}_Y{y}_N{n}_F",
                            f"carry_X{x}_Y{y}_N{n}_S"):
                    pips.append({
                        "name": f"pip_{src}__{lw}",
                        "type": "LOCAL_IN",
                        "src": src, "dst": lw,
                        "delay": LOCAL_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1
            # LOCAL track -> slice data inputs (I[0..3]) and carry A/B.
            # slice_CLK is reachable ONLY via the GCLK_BUS/LAB_CLK tree
            # (see "Dedicated global clock network" section below) so
            # the router can't waste LOCAL bandwidth on clock nets.
            for n in LE_N:
                dsts = [_wire_slice_in(x, y, n, port)
                        for port in SLICE_INPUTS]
                dsts += [_wire_carry_in(x, y, n, cport)
                         for cport in ("A", "B")]
                for dw in dsts:
                    pips.append({
                        "name": f"pip_{lw}__{dw}",
                        "type": "LOCAL_OUT",
                        "src": lw, "dst": dw,
                        "delay": LOCAL_DELAY,
                        "x": x, "y": y,
                    })
                    n_local_pips += 1
            if not sig_routing_only:
                # Multi-distance hops (N/S/E/W, distance 1..max_hop_dist).
                # Longer hops carry higher delay so the router prefers
                # short hops when LOCAL capacity allows, but can skip
                # intermediate LABs to reduce transit wire pressure.
                for dxi, dyi in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nxi, nyi = xi + dxi, yi + dyi
                    hops_found = 0
                    while (0 <= nxi < len(LAB_X_FULL)
                           and 0 <= nyi < len(LAB_Y_FULL)
                           and hops_found < max_hop_dist):
                        nx, ny = LAB_X_FULL[nxi], LAB_Y_FULL[nyi]
                        if (nx, ny) in local_wires:
                            hops_found += 1
                            dst = f"LOCAL_X{nx}_Y{ny}_T{t}"
                            pips.append({
                                "name": f"pip_{lw}__{dst}",
                                "type": "LOCAL_HOP",
                                "src": lw, "dst": dst,
                                "delay": HOP_DELAY * hops_found,
                                "x": x, "y": y,
                            })
                            n_local_pips += 1
                        nxi += dxi
                        nyi += dyi

    # ---------- Dedicated global clock network (GCLK_BUS) ----------
    # 4 silicon GCLK tracks, drivable only by the 12 F17 clock pins, fan
    # out through a per-LAB LAB_CLK intermediate wire to every slice's
    # CLK pin. Matches the FASM directive hierarchy the FASM side
    # already emits:
    #   GCLK_PIN        — which pin drives which GCLK_BUS track
    #   LAB_CLK_SEL     — per-LAB CLK source select (N-invariant)
    #   LAB_CLK_SEL_LE  — per-LE CLK enable
    # Topology:
    #   IOB(clkpin).O -> GCLK_BUS[t]             (12 pins × 4 tracks)
    #   GCLK_BUS[t]   -> LAB_CLK[x,y]            (4 tracks × #LABs)
    #   LAB_CLK[x,y]  -> slice_CLK[x,y,n]        (16 slices / LAB)
    # Non-clock IOBs do NOT get a GCLK source pip — matches silicon and
    # keeps the router from using GCLK as a general fabric shortcut.
    n_pips_gclk = 0
    for t in range(NUM_GCLK_TRACKS):
        wires.append({"name": f"GCLK_BUS_{t}", "type": "GCLK_BUS",
                      "x": 0, "y": 0})
    # 12 F17 clock pins → 4 GCLK_BUS tracks
    for (pin_name, pin_loc) in iob_entries:
        if pin_loc not in F17_GCLK_PINS:
            continue
        safe = pin_name.replace("[", "_").replace("]", "")
        wo = _wire_iob(safe, "O")
        for t in range(NUM_GCLK_TRACKS):
            pips.append({
                "name": f"pip_iob_{safe}_O__GCLK_BUS_{t}",
                "type": "IOB_TO_GCLK",
                "src": wo, "dst": f"GCLK_BUS_{t}",
                "delay": DEDICATED_DELAY, "x": 0, "y": 0,
            })
            n_pips_gclk += 1
    # Per-LAB CLK wire + GCLK_BUS → LAB_CLK → slice_CLK fanout
    for (x, y) in valid_labs:
        lab_clk = f"LAB_CLK_X{x}_Y{y}"
        wires.append({"name": lab_clk, "type": "LAB_CLK", "x": x, "y": y})
        for t in range(NUM_GCLK_TRACKS):
            pips.append({
                "name": f"pip_GCLK_BUS_{t}__{lab_clk}",
                "type": "GCLK_TO_LAB_CLK",
                "src": f"GCLK_BUS_{t}", "dst": lab_clk,
                "delay": DEDICATED_DELAY, "x": x, "y": y,
            })
            n_pips_gclk += 1
        for n in LE_N:
            cw = f"slice_X{x}_Y{y}_N{n}_CLK"
            pips.append({
                "name": f"pip_{lab_clk}__{cw}",
                "type": "LAB_CLK_TO_SLICE",
                "src": lab_clk, "dst": cw,
                "delay": DEDICATED_DELAY, "x": x, "y": y,
            })
            n_pips_gclk += 1

    # ---------- IOB <-> LOCAL bridge (per-bank gateways, rev 7) ----------
    # Each IOB connects to the fabric through a LOCAL gateway LAB near
    # its IO bank.  Signals propagate through LOCAL-hop chains between
    # the gateway and the rest of the chip.
    #
    # Rev 4 used ONE gateway for all 55 IOBs → 4 LOCAL tracks × 55 IOBs
    # = massive congestion, router thrash.  Rev 5/6 tried adding direct
    # slice→IOB pips (Q+F) → doubled pip count caused negotiated
    # congestion divergence (~2040 overused wires).
    #
    # Rev 7: per-bank gateways (7 gateways for 7 IO banks).  Both
    # directions (pad→fabric, fabric→pad) go through LOCAL at the
    # bank's gateway.  No direct SLICE→IOB pips — signals reach IOBs
    # only via LOCAL_HOP → gateway → IOB.  This works because both Q
    # and F outputs already drive LOCAL_IN (line ~367).
    #
    # Pin-letter → IO bank mapping (EP4CE6F17C8 F17 package):
    #   A-D → bank 1 (top), E-G → bank 2 (upper-left),
    #   J-K → bank 3 (mid-left), L-N → bank 4 (lower-left),
    #   P → bank 5 (bottom-mid), R → bank 6 (bottom-right),
    #   T → bank 7 (right)

    def _pin_bank(pin_loc: str) -> int:
        letter = pin_loc.replace("PIN_", "")[0]
        return {"A":1,"B":1,"C":1,"D":1,
                "E":2,"F":2,"G":2,
                "J":3,"K":3,
                "L":4,"M":4,"N":4,
                "P":5,
                "R":6,
                "T":7}.get(letter, 2)

    bank_gateway_targets = {
        1: (4, 19),   2: (6, 12),  3: (10, 8),
        4: (17, 4),   5: (22, 4),  6: (28, 8),
        7: (31, 12),
    }

    def _nearest_valid(tx, ty):
        best = None
        best_d = 1e9
        for (lx, ly) in valid_labs:
            d = abs(lx - tx) + abs(ly - ty)
            if d < best_d:
                best_d = d
                best = (lx, ly)
        return best

    bank_gateways = {b: _nearest_valid(tx, ty)
                     for b, (tx, ty) in bank_gateway_targets.items()}

    for (pin_name, pin_loc) in iob_entries:
        safe = pin_name.replace("[", "_").replace("]", "")
        wi = _wire_iob(safe, "I")   # fabric -> pad
        wo = _wire_iob(safe, "O")   # pad -> fabric
        we = _wire_iob(safe, "EN")  # OE from fabric
        bank = _pin_bank(pin_loc)
        gx, gy = bank_gateways[bank]
        for t in range(num_local_tracks):
            gw = f"LOCAL_X{gx}_Y{gy}_T{t}"
            pips.append({
                "name": f"pip_iob_{safe}_O__{gw}",
                "type": "IOB_TO_LOCAL",
                "src": wo, "dst": gw,
                "delay": PLACEHOLDER_DELAY, "x": gx, "y": gy,
            })
            pips.append({
                "name": f"pip_{gw}__iob_{safe}_I",
                "type": "LOCAL_TO_IOB",
                "src": gw, "dst": wi,
                "delay": PLACEHOLDER_DELAY, "x": gx, "y": gy,
            })
            pips.append({
                "name": f"pip_{gw}__iob_{safe}_EN",
                "type": "LOCAL_TO_IOB",
                "src": gw, "dst": we,
                "delay": PLACEHOLDER_DELAY, "x": gx, "y": gy,
            })
            n_local_pips += 3

    # ---------- Dedicated GND (constant-0) network ----------
    # nextpnr-generic's packer materialises $PACKER_GND as a SLICE cell
    # whose F output drives every constant-0 sink in the design. In
    # NEORV32 the vast majority (~1066) of those sinks are unused M9K
    # DIN bits — routing that fanout through LOCAL saturates fabric
    # tracks identically to how CLOCK would without GCLK_BUS.
    #
    # Mirror the GCLK treatment: one dedicated GND_BUS wire; any
    # SLICE.F can drive it (so whichever slice the packer places
    # $PACKER_GND on becomes the driver); GND_BUS fans out directly
    # to every M9K_DIN bit. Real data bits still reach M9K_DIN via
    # LOCAL → M9K_IN pips (below) — router chooses GND_BUS only for
    # the PACKER_GND net since that's the only cost-efficient user.
    n_pips_gnd = 0
    # 4 GND_BUS wires distributed at quadrant centres so every sink's
    # per-arc bounding box includes at least one. router2's BB filter
    # excludes a single global wire from half the arcs when it sits at
    # one corner of the die; a quadrant set costs only 4× pips while
    # ensuring GND_BUS is always considered. Each SLICE.F can drive any
    # of the 4 wires; each M9K DIN/ADDR bit can read from any. Router
    # picks whichever the PACKER_GND net already occupies.
    xmax = max(LAB_X_FULL)
    ymax = max(LAB_Y_FULL)
    GND_BUS_LOCS = [
        (xmax // 4,       ymax // 4),       # NW
        (xmax * 3 // 4,   ymax // 4),       # NE
        (xmax // 4,       ymax * 3 // 4),   # SW
        (xmax * 3 // 4,   ymax * 3 // 4),   # SE
    ]
    for i, (gx, gy) in enumerate(GND_BUS_LOCS):
        wires.append({"name": f"GND_BUS_{i}", "type": "GND_BUS",
                      "x": gx, "y": gy})
    # Zero-delay chain pips between every GND_BUS pair so once
    # $PACKER_GND binds one quadrant wire the router can extend the
    # tree to the other three for free. Without this, only sinks
    # within the bound wire's arc-BB can use GND_BUS.
    for i, (ix, iy) in enumerate(GND_BUS_LOCS):
        for j, (jx, jy) in enumerate(GND_BUS_LOCS):
            if i == j:
                continue
            pips.append({
                "name": f"pip_GND_BUS_{i}__GND_BUS_{j}",
                "type": "GND_CHAIN",
                "src": f"GND_BUS_{i}", "dst": f"GND_BUS_{j}",
                "delay": DEDICATED_DELAY, "x": jx, "y": jy,
            })
            n_pips_gnd += 1
    for (x, y) in valid_labs:
        for n in LE_N:
            fw = f"slice_X{x}_Y{y}_N{n}_F"
            for i, (gx, gy) in enumerate(GND_BUS_LOCS):
                pips.append({
                    "name": f"pip_{fw}__GND_BUS_{i}",
                    "type": "SLICE_F_TO_GND",
                    "src": fw, "dst": f"GND_BUS_{i}",
                    "delay": DEDICATED_DELAY, "x": gx, "y": gy,
                })
                n_pips_gnd += 1

    # Chain-start CIN tie-off.  CE6_CARRY[0].CI is a Verilog constant
    # (1'b0 for $add, 1'b1 for $sub) and Yosys / nextpnr-generic
    # routes it through $PACKER_GND_NET / $PACKER_VCC_NET.  On silicon
    # the chain-start CRAM bit (LUT_ARITH blob) handles the constant,
    # not external routing — but the router still wants a pip from
    # whichever cell holds $PACKER_GND to the CIN of the chain-start
    # LE.  Restrict the GND→CIN pip set to N=0 of every valid LAB,
    # since prepack_carry pins chain bit 0 to N=0.  Adding pips for
    # every N=0..30 explodes router2 search space (24-bit chain
    # exceeds 10 minutes wallclock).
    for (x, y) in valid_labs:
        ciw = _wire_slice_cin(x, y, 0)
        for i in range(len(GND_BUS_LOCS)):
            pips.append({
                "name": f"pip_GND_BUS_{i}__{ciw}",
                "type": "GND_TO_CIN",
                "src": f"GND_BUS_{i}", "dst": ciw,
                "delay": DEDICATED_DELAY, "x": x, "y": y,
            })
            n_pips_gnd += 1

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
                    # Feed CLK_A/CLK_B from any of the 4 GCLK_BUS tracks,
                    # not LOCAL. Matches silicon M9K clock-fanin.
                    cw = _wire_m9k_port(x, y, port)
                    for t in range(NUM_GCLK_TRACKS):
                        pips.append({
                            "name": f"pip_GCLK_BUS_{t}__{cw}",
                            "type": "GCLK_TO_M9K_CLK",
                            "src": f"GCLK_BUS_{t}", "dst": cw,
                            "delay": DEDICATED_DELAY, "x": x, "y": y,
                        })
                        n_pips_m9k += 1
                    continue
                bits = [_wire_m9k_port(x, y, port)] if width == 1 else \
                       [_wire_m9k_bit(x, y, port, i) for i in range(width)]
                # GND_BUS → DIN/ADDR bit: gives PACKER_GND a direct
                # cheap path to M9K inputs that would otherwise
                # saturate LOCAL. Matches the NEORV32 sink profile:
                # 1002 DIN bits + 64 ADDR_A[0..1] bits from
                # $PACKER_GND. Output ports (DOUT) skipped.
                if port.startswith("DIN") or port.startswith("ADDR"):
                    for w in bits:
                        for i in range(len(GND_BUS_LOCS)):
                            pips.append({
                                "name": f"pip_GND_BUS_{i}__{w}",
                                "type": "GND_TO_M9K_IN",
                                "src": f"GND_BUS_{i}", "dst": w,
                                "delay": DEDICATED_DELAY, "x": x, "y": y,
                            })
                            n_pips_gnd += 1
                for w in bits:
                    for t in range(num_local_tracks):
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

    # ---------- Pips from sig-cache (FASM-backed overlay) ----------
    # Each sig-cache entry is a bit-perfect verified (src_LE → dst_LE.port)
    # route.  These bypass the synthetic LOCAL model entirely — the router
    # can one-hop from any source Q wire to any destination datax wire that
    # has a sig-cache entry, and np2fasm emits the ROUTE directive.
    cache_path = RESULTS / "route_cells_full.json"
    cache = json.loads(cache_path.read_text())
    known_wires = {w["name"] for w in wires}
    pip_count = 0
    skipped_unknown_src = 0
    skipped_unknown_dst = 0
    sig_src_labs: set[tuple[int, int]] = set()
    sig_dst_labs: set[tuple[int, int]] = set()
    sig_lab_pairs: set[tuple[int, int, int, int]] = set()
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
        sig_src_labs.add((sx, sy))
        sig_dst_labs.add((dx, dy))
        sig_lab_pairs.add((sx, sy, dx, dy))

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
            "n_pips_gclk": n_pips_gclk,
            "n_pips_gnd": n_pips_gnd,
            "n_sig_cache_total": len(cache),
            "n_sig_src_labs": len(sig_src_labs),
            "n_sig_dst_labs": len(sig_dst_labs),
            "n_sig_lab_pairs": len(sig_lab_pairs),
            "pips_skipped_unknown_src": skipped_unknown_src,
            "pips_skipped_unknown_dst": skipped_unknown_dst,
        },
    }


_RUNNER_TEMPLATE = '''\
# SPDX-License-Identifier: GPL-3.0-or-later
"""nextpnr-generic --run entry point for EP4CE6 (auto-generated).

Do not edit by hand; regenerate with ``python3 fuzz/chipdb_gen.py``.
"""
import gzip, json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
# Match data file to script stem so sidecar variants
# (chipdb_ep4ce6_nojb.py / _data_nojb.json.gz) auto-pair.
_STEM = Path(__file__).stem.replace("chipdb_ep4ce6", "chipdb_ep4ce6_data")
_DATA = json.loads(gzip.decompress((_HERE / f"{_STEM}.json.gz").read_bytes()))

try:
    from nextpnrpy_generic import Loc  # type: ignore
except ImportError:
    Loc = globals().get("Loc")

_delays = {}
for cost in set(p[4] for p in _DATA["pips"]):
    _delays[cost] = ctx.getDelayFromNS(cost * 0.5)

for w in _DATA["wires"]:
    ctx.addWire(name=w[0], type=w[1], x=w[2], y=w[3])

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
    ctx.addPip(name=p[0], type=p[1],
               srcWire=p[2], dstWire=p[3],
               delay=_delays[p[4]],
               loc=Loc(p[5], p[6], 0))

print("[chipdb_ep4ce6] loaded:",
      _DATA["stats"]["n_bels"], "bels,",
      _DATA["stats"]["n_wires"], "wires,",
      _DATA["stats"]["n_pips_total"], "pips")

# --run replaces the default flow, so we must drive pack/place/route
# ourselves.  sys.argv inside --run only has the binary path, so read
# the real command line from /proc/self/cmdline.  When invoked via
# --pre-pack instead, nextpnr runs its own pack/place/route flow and
# the hooks below would re-exec this script, double-adding wires and
# tripping the assertion in nextpnr-generic 0.10+.  Detect the
# invocation mode and skip the flow-driver block in --pre-pack mode.
def _run_hook(flag):
    """Execute a --flag script if the user passed one."""
    try:
        args = open("/proc/self/cmdline").read().split(chr(0))
    except OSError:
        return
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            path = args[i + 1]
            exec(compile(open(path).read(), path, "exec"), globals())
            return


def _invoked_as(flag):
    """True if /proc/self/cmdline contains `flag <this-file>`."""
    try:
        args = open("/proc/self/cmdline").read().split(chr(0))
    except OSError:
        return False
    me = str(Path(__file__).resolve())
    for i, a in enumerate(args):
        if a == flag and i + 1 < len(args):
            try:
                if str(Path(args[i + 1]).resolve()) == me:
                    return True
            except (OSError, ValueError):
                pass
    return False


# Only drive the flow when invoked as --run (this script is the
# entry point).  In --pre-pack mode, nextpnr drives the default flow
# and the hooks below would cause recursion.
if _invoked_as("--run"):
    _run_hook("--pre-pack")
    ctx.pack()
    _run_hook("--pre-place")
    ctx.place()
    _run_hook("--pre-route")
    ctx.route()
    _run_hook("--post-route")
'''


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Generate nextpnr-generic chipdb for EP4CE6")
    ap.add_argument("--region", metavar="X0,Y0,X1,Y1",
                    help="Restrict SLICE placement to bounding box "
                         "(e.g. --region 13,6,18,14)")
    ap.add_argument("--no-jailbreak", action="store_true",
                    help="Exclude jailbreak columns/rows (CE6 whitelist only)")
    ap.add_argument("--local-tracks", type=int, default=NUM_LOCAL_TRACKS,
                    metavar="N",
                    help=f"LOCAL bus tracks per LAB (default {NUM_LOCAL_TRACKS})")
    ap.add_argument("--max-hop-dist", type=int, default=MAX_HOP_DIST,
                    metavar="N",
                    help=f"Max hop distance per direction (default {MAX_HOP_DIST})")
    ap.add_argument("--sig-routing-only", action="store_true",
                    help="Inter-LAB routing via SIG pips only (no LOCAL_HOP)")
    ap.add_argument("--out-tag", metavar="TAG",
                    help="Suffix output paths with `_TAG` to produce a "
                         "sidecar variant (e.g. --out-tag nojb writes "
                         "chipdb_ep4ce6_nojb.py / _data_nojb.json.gz)")
    args = ap.parse_args()

    global DATA_PATH, SCRIPT_PATH
    if args.out_tag:
        DATA_PATH = RESULTS / f"chipdb_ep4ce6_data_{args.out_tag}.json.gz"
        SCRIPT_PATH = RESULTS / f"chipdb_ep4ce6_{args.out_tag}.py"

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

    data = build_chipdb(num_local_tracks=args.local_tracks,
                        max_hop_dist=args.max_hop_dist,
                        sig_routing_only=args.sig_routing_only)
    data["wires"] = [[w["name"], w["type"], w["x"], w["y"]]
                     for w in data["wires"]]
    data["pips"] = [[p["name"], p["type"], p["src"], p["dst"],
                     p["delay"], p["x"], p["y"]]
                    for p in data["pips"]]
    blob = json.dumps(data, separators=(",", ":")).encode()
    DATA_PATH.write_bytes(gzip.compress(blob, compresslevel=6))
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
          f"+ carry {s['n_pips_carry']} + m9k {s['n_pips_m9k']} "
          f"+ gclk {s['n_pips_gclk']} + gnd {s['n_pips_gnd']})")
    print(f"sig-cache: {s['n_sig_cache_total']} total, "
          f"{s['n_pips_sig']} injected, "
          f"{s['pips_skipped_unknown_src']}+{s['pips_skipped_unknown_dst']} skipped")
    print(f"sig topology: {s['n_sig_src_labs']} src LABs, "
          f"{s['n_sig_dst_labs']} dst LABs, "
          f"{s['n_sig_lab_pairs']} LAB-pairs")


if __name__ == "__main__":
    main()
