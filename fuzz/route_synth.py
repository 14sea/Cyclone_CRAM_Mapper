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
    while cur_x != need.dx:
        remaining = LAB_X.index(need.dx) - LAB_X.index(cur_x)
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

def pick_li_envelope(need: Need):
    """Stage 3 — return (mode, [(pair, base_idx), ...]) for the dst LAB."""
    from bitstream import RouteCodec
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
    ops: list[dict] = []
    for hop in plan:
        wx, wy = _hop_landing_coords(hop)
        if hop.type == "C4":
            ops.append({"type": "c4", "x": wx, "y": wy, "i_idx": hop.i_index})
        elif hop.type == "R4":
            ops.append({"type": "r4", "wx": wx, "y": wy, "i_idx": hop.i_index})
        elif hop.type == "R24":
            ops.append({"type": "r24", "wx": wx, "y": wy, "i_idx": hop.i_index})

    mode, cells = li
    ops.append({
        "type": "li",
        "lx": need.dx,
        "ly": need.dy,
        "pair_bases": cells,
    })
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
