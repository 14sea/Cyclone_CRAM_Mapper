"""End-to-end route synthesis MVP for EP4CE6.

5-stage pipeline (see CLAUDE.md and the MVP planning doc):
  1. Need parse — turn (src, dst) into a Need dataclass
  2. Plan hops  — greedy Manhattan: vertical C4 first, then horizontal R4
  3. Pick LI    — look up dst column mode + pick a typical envelope
  4. Emit ops   — convert Plan to RouteCodec.apply_routing() op list
  5. Apply+vfy  — write CRAM cells, validate hardware safety, round-trip

Stage 1+2 implemented here. Stages 3-5 are stub functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from config import LAB_X, LAB_Y


# ----------------------------------------------------------------------
# Stage 1 — Need parse
# ----------------------------------------------------------------------

@dataclass(frozen=True)
class Need:
    sx: int
    sy: int
    dx: int
    dy: int
    sn: int = 0
    dn: int = 0
    src_port: str = "combout"
    dst_port: str = "datab"

    @property
    def ddx(self) -> int:
        return self.dx - self.sx

    @property
    def ddy(self) -> int:
        return self.dy - self.sy

    @property
    def same_lab(self) -> bool:
        return self.sx == self.dx and self.sy == self.dy


def parse_need(src, dst) -> Need:
    """src = (x, y, [n, [port]]), dst = (x, y, [n, [port]])."""
    sx, sy = src[0], src[1]
    sn = src[2] if len(src) > 2 else 0
    sp = src[3] if len(src) > 3 else "combout"
    dx, dy = dst[0], dst[1]
    dn = dst[2] if len(dst) > 2 else 0
    dp = dst[3] if len(dst) > 3 else "datab"
    if sx not in LAB_X or dx not in LAB_X:
        raise ValueError(f"non-LAB X: src_x={sx} dst_x={dx} (LAB_X={LAB_X})")
    if sy not in LAB_Y or dy not in LAB_Y:
        raise ValueError(f"non-LAB Y: src_y={sy} dst_y={dy}")
    return Need(sx=sx, sy=sy, dx=dx, dy=dy, sn=sn, dn=dn, src_port=sp, dst_port=dp)


# ----------------------------------------------------------------------
# Stage 2 — Plan hops
# ----------------------------------------------------------------------

HopType = Literal["C4", "R4", "R24", "LOCAL"]


@dataclass(frozen=True)
class Hop:
    type: HopType
    anchor_x: int
    anchor_y: int
    i_index: int
    span: int  # signed: + = down/right, - = up/left

    def __repr__(self):
        return f"{self.type}(@{self.anchor_x},{self.anchor_y} I={self.i_index} span={self.span:+d})"


# Verified I-indices we can actually emit (read+write supported by RouteCodec)
# Taken from CLAUDE.md and bitstream._R4_BASE_PREV / _C4_FIXED_OFFSETS
SAFE_R4_I = 0          # the universal-formula one; safest first choice
SAFE_C4_I = 0          # universal formula


def _vertical_step(remaining_dy: int) -> int:
    """How far one C4 hop should travel given remaining signed dy.
    C4 spans up to 4 LAB rows. Return signed step."""
    if remaining_dy == 0:
        return 0
    sign = 1 if remaining_dy > 0 else -1
    return sign * min(4, abs(remaining_dy))


def _horizontal_step(remaining_dx: int) -> int:
    """How far one R4 hop should travel. R4 spans up to 4 LAB columns
    in LAB-index distance (NOT raw X distance — LAB_X is sparse)."""
    if remaining_dx == 0:
        return 0
    sign = 1 if remaining_dx > 0 else -1
    return sign * min(4, abs(remaining_dx))


def _lab_step_to_x(start_x: int, n_lab_steps: int) -> int:
    """Move n_lab_steps along LAB_X starting at start_x. Returns new X."""
    idx = LAB_X.index(start_x)
    new_idx = max(0, min(len(LAB_X) - 1, idx + n_lab_steps))
    return LAB_X[new_idx]


def _y_step(start_y: int, n_steps: int) -> int:
    idx = LAB_Y.index(start_y)
    new_idx = max(0, min(len(LAB_Y) - 1, idx + n_steps))
    return LAB_Y[new_idx]


def plan_hops(need: Need) -> list[Hop]:
    """Greedy Manhattan: vertical first via C4, then horizontal via R4.

    Each hop's anchor is placed at the START of the wire span (closer to
    where the signal comes from). The wire then extends `span` LAB
    positions toward dst. The final LI MUX engagement at the dst LAB is
    NOT a Hop — it's emitted in stage 3 as li ops.
    """
    if need.same_lab:
        return []  # local interconnect only, no R/C hops needed

    hops: list[Hop] = []
    cur_x, cur_y = need.sx, need.sy

    # ---- vertical first ----
    while cur_y != need.dy:
        remaining = LAB_Y.index(need.dy) - LAB_Y.index(cur_y)
        step = _vertical_step(remaining)
        if step == 0:
            break
        # C4 anchor: start at cur (or one step in the dir? — TBD via L1)
        new_y = _y_step(cur_y, step)
        hops.append(Hop("C4", anchor_x=cur_x, anchor_y=cur_y,
                        i_index=SAFE_C4_I, span=step))
        cur_y = new_y

    # ---- then horizontal ----
    # R24 expressway: for hops spanning ≥2 LAB columns, prefer R24 over R4.
    # R24 covers up to 24 LABs in a single wire and matches Quartus's
    # actual choice for medium/long horizontal moves. R4 is the fallback
    # for the final 1-LAB step.
    while cur_x != need.dx:
        remaining = LAB_X.index(need.dx) - LAB_X.index(cur_x)
        if abs(remaining) >= 3:
            step = remaining if abs(remaining) <= 6 else (6 if remaining > 0 else -6)
            new_x = _lab_step_to_x(cur_x, step)
            hops.append(Hop("R24", anchor_x=cur_x, anchor_y=cur_y,
                            i_index=0, span=step))
            cur_x = new_x
            continue
        step = _horizontal_step(remaining)
        if step == 0:
            break
        new_x = _lab_step_to_x(cur_x, step)
        hops.append(Hop("R4", anchor_x=cur_x, anchor_y=cur_y,
                        i_index=SAFE_R4_I, span=step))
        cur_x = new_x

    return hops


# ----------------------------------------------------------------------
# Stage 3-5 — stubs (filled in next commits)
# ----------------------------------------------------------------------

_LI_VARIANT_TABLE = None
_R4_IINDEX_TABLE = None
_FP_SNAPSHOTS = {}  # (sx,sy) -> {fingerprint, per_route_delta}


def _load_fp(sx, sy):
    """Load a green-zone source-fingerprint snapshot if it exists."""
    if (sx, sy) in _FP_SNAPSHOTS:
        return _FP_SNAPSHOTS[(sx, sy)]
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "results" / f"fingerprint_{sx}_{sy}.json"
    if p.exists():
        raw = json.loads(p.read_text())
        snap = {
            "fingerprint": [tuple(c) for c in raw["fingerprint"]],
            "per_route_delta": {
                k: [tuple(c) for c in v] for k, v in raw["per_route_delta"].items()
            },
        }
    else:
        snap = None
    _FP_SNAPSHOTS[(sx, sy)] = snap
    return snap


# Backward-compat alias used by existing tests
def _load_fp_10_10():
    return _load_fp(10, 10) or {"fingerprint": [], "per_route_delta": {}}


def _load_r4_iindex_table():
    global _R4_IINDEX_TABLE
    if _R4_IINDEX_TABLE is None:
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "results" / "r4_iindex_table.json"
        if p.exists():
            raw = json.loads(p.read_text())
            _R4_IINDEX_TABLE = {k: [tuple(c) for c in v] for k, v in raw.items()}
        else:
            _R4_IINDEX_TABLE = {}
    return _R4_IINDEX_TABLE


def _load_variant_table():
    global _LI_VARIANT_TABLE
    if _LI_VARIANT_TABLE is None:
        import json
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "results" / "li_dst_variant_table.json"
        if p.exists():
            raw = json.loads(p.read_text())
            _LI_VARIANT_TABLE = {k: [tuple(c) for c in v] for k, v in raw.items()}
        else:
            _LI_VARIANT_TABLE = {}
    return _LI_VARIANT_TABLE


def pick_li_envelope(need: Need):
    """Stage 3 — return (mode, [(pair, base_idx), ...]) for the dst LAB.

    Lookup priority:
      1. Exact (src, dst, port) match in the corpus-mined variant table
      2. Fall back to the typical envelope per LI mode for dst column
    """
    from bitstream import RouteCodec
    table = _load_variant_table()
    key = f"{need.sx},{need.sy},{need.dx},{need.dy},{need.dst_port}"
    if key in table:
        cells = table[key]
        # Classify which mode this corresponds to (just for safety check)
        mode = RouteCodec.select_li_mode(need.dx)
        return mode, cells
    mode = RouteCodec.select_li_mode(need.dx)
    return mode, list(RouteCodec.LI_TYPICAL_ENVELOPE[mode])


def _hop_landing_coords(hop: Hop) -> tuple[int, int]:
    """Return the (wx, wy) the codec should be addressed with for this hop.

    MVP heuristic: use the END of the wire span (the side closer to dst).
    L1 round-trip will reveal if this convention matches CRAM addressing.
    """
    if hop.type == "C4":
        new_y = LAB_Y[LAB_Y.index(hop.anchor_y) + hop.span]
        return hop.anchor_x, new_y
    elif hop.type in ("R4", "R24"):
        new_x = LAB_X[LAB_X.index(hop.anchor_x) + hop.span]
        return new_x, hop.anchor_y
    raise ValueError(f"unknown hop type {hop.type}")


def emit_ops(plan: list[Hop], li, need: Need) -> list[dict]:
    """Stage 4 — turn the plan + LI envelope into apply_routing op dicts."""
    from bitstream import RouteCodec
    codec = RouteCodec()
    ops: list[dict] = []

    # ================================================================
    # GREEN ZONE: (10,10) source — bit-perfect snapshot mode.
    # When src is (10,10) and the dst was mined into the corpus,
    # emit fingerprint ∪ per_route_delta as raw cells. Bypasses
    # everything below for these routes.
    # ================================================================
    if not need.same_lab:
        fp = _load_fp(need.sx, need.sy)
    else:
        fp = None
    if fp is not None:
        key = f"{need.dx},{need.dy},{need.dst_port}"
        if key in fp["per_route_delta"]:
            seen = set()
            for t, off, bp in fp["fingerprint"] + fp["per_route_delta"][key]:
                if (off, bp) in seen:
                    continue
                seen.add((off, bp))
                ops.append({"type": "raw", "offset": off, "bp": bp, "value": True})
            return ops

    # Per-route exact R4 (wx,y,i_idx) lookup mined from lits_pair corpus
    # (r4_iindex_mine.py). When present, this replaces the plan's R4 hops
    # AND the universal launch driver with Quartus's exact cell list.
    r4_table = _load_r4_iindex_table()
    r4_key = f"{need.sx},{need.sy},{need.dx},{need.dy},{need.dst_port}"
    r4_exact = r4_table.get(r4_key)

    for hop in plan:
        wx, wy = _hop_landing_coords(hop)
        if hop.type == "C4":
            ops.append({"type": "c4", "x": wx, "y": wy, "i_idx": hop.i_index})
        elif hop.type == "R4":
            if r4_exact is not None:
                continue  # exact table will emit R4 below
            ops.append({"type": "r4", "wx": wx, "y": wy, "i_idx": hop.i_index})
        elif hop.type == "R24":
            # Sniper mode: pick the single fixed offset Quartus would use
            # for this (wx, y) via the R24 (block, prev_x) table.
            off, bp = codec.get_r24_offset(wx, wy, i_idx=hop.i_index)
            ops.append({
                "type": "r24",
                "wx": wx, "y": wy, "i_idx": hop.i_index,
                "cells": [(off, bp)],
            })

    mode, cells = li
    ops.append({
        "type": "li",
        "lx": need.dx,
        "ly": need.dy,
        "pair_bases": cells,
    })

    # Source-side LE driver MUX: P8B0 + P8B1 at the source LAB.
    # Quartus emits this for vertical hops AND horizontal hops ≥2 LAB,
    # but NOT for adjacent +1/-1 horizontal hops, which appear to use a
    # direct LE→LE link bypassing the source-side LI MUX entirely.
    # Confirmed via L2 mining (2026-04-07).
    needs_driver = (
        not need.same_lab and
        not (need.ddy == 0 and abs(need.ddx) <= 1)
    )
    if needs_driver:
        ops.append({
            "type": "li",
            "lx": need.sx,
            "ly": need.sy,
            "pair_bases": [(8, 0), (8, 1)],
        })

    # Universal source-column R24 broadcast hold: 5 raw bits identical
    # across all 23 lits_pair routes (broadcast_mine.py, 2026-04-07).
    # The 5 bits live at 2 bytes in prev_x=8's column and the codec reader
    # expands them into ~24 wire names (different (wx,y) → same physical
    # bit). The pri/sec choice differs from R24_OFFSET_TABLE because
    # broadcast and routing use opposite halves of the same physical pair.
    # Limitation: hard-coded for sx=10, sy=10. Need multi-(sx,sy) corpus
    # to generalize the offset formula.
    if not need.same_lab and need.sx == 10 and need.sy == 10:
        for off, bp in ((0x11077, 1), (0x11077, 6), (0x11077, 7),
                        (0x1121a, 2), (0x1121a, 3)):
            ops.append({"type": "raw", "offset": off, "bp": bp, "value": True})

    # Per-route R4 cells: prefer exact-table match, else universal launch.
    if r4_exact is not None:
        for wx, wy, ii in r4_exact:
            ops.append({"type": "r4", "wx": wx, "y": wy, "i_idx": ii})
    elif not need.same_lab:
        # Universal source-side R4 launch driver: R4_X{sx+1}_Y{sy} I=1 + I=2
        # Mined as 100% across lits_pair corpus (r4_iindex_mine.py).
        launch_wx = _lab_step_to_x(need.sx, 1)
        for ii in (1, 2):
            ops.append({"type": "r4", "wx": launch_wx, "y": need.sy, "i_idx": ii})
    return ops


def synth_route(base_rbf: bytes, src, dst) -> tuple[bytes, dict]:
    """Top-level entry. Returns (output_rbf, debug_info)."""
    from bitstream import RouteCodec
    need = parse_need(src, dst)
    plan = plan_hops(need)
    li = pick_li_envelope(need)
    ops = emit_ops(plan, li, need)

    codec = RouteCodec()
    out = codec.apply_routing(base_rbf, ops)

    # Stage 5 — L1 validation: round-trip + hardware safety
    codec.validate_safe_for_hardware(out, base_rbf)
    sw = codec.read_switches(out, base_rbf)

    debug = {"need": need, "plan": plan, "li_mode": li[0], "ops": ops, "read_back": sw}
    return out, debug
