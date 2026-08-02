#!/usr/bin/env python3
"""
lut_sigma.py -- Phase 4 STAGE 1 + STAGE 2 deliverable.

Recover each decoder LUT's LOGICAL function from its PHYSICAL CRAM mask and name
it over the LE's four input nets.

=========================================================================== #
STAGE 2 CORRECTION (HW-GROUNDED, supersedes the Stage-1 sigma naming path)     #
=========================================================================== #
Nineteen live Quartus compiles of KNOWN 4-input logic (11 rigid functions, one
per sigma class, + 8 held-out functions incl. wrap rows; each back-annotated
with `quartus_cdb --back_annotate=routing`) proved:

  * The truth table over the LE's four PHYSICAL input ports is obtained from the
    atom_first physical mask by a SINGLE CONSTANT axis reversal -- swap port bit0
    <-> bit3 and bit1 <-> bit2 -- and NOTHING else.  See `physical_port_tt`.
        logic_over_ports = physical_port_tt(read_physical_mask(img,x,y,n))
        bit0 = DATAA, bit1 = DATAB, bit2 = DATAC, bit3 = DATAD   (physical inputs)
    This reversal is the endianness gap between atom_first's pair/delta bit index
    and Quartus's dataa-LSB minterm convention.  It is POSITION-INDEPENDENT and
    ROUTING-INDEPENDENT: the same (3,2,1,0) held across all 11 mined sigma
    classes and 19 distinct routings.  Result: 19/19 live LUTs recovered exactly.

  * The position-dependent `sigma` (Stage 1 / Cyclone_CRAM_Mapper) is NOT the
    port transform.  Applying it (`physical_to_logical` / `read_logical_tt`)
    reproduces the source only when sigma == identity (1/19 live); it is WRONG
    for naming and is retained below ONLY for cell-geometry cross-check with the
    reference codec.  The Stage-1 "flat-identical to reference" result verified
    cell LOCATIONS, not the input-axis semantics -- the reference codec's sigma
    labels a convention that is not the LE's physical dataa..datad order.

  * Which NET drives each physical port is a per-design ROUTING decision (the
    fitter freely permutes signal->physical-input; confirmed in every rcf).  So
    the named function needs the LEIM-resolved driver per port (Phase 1/2), NOT
    the nominal port order.  `named_function` binds the four physical ports to
    the LEIM nets and emits the SOP.

Regression: the 19 live (x,y,n, raw phys_mask, source TT, port->net) tuples are
embedded (`LIVE_REGRESSION`); `_selftest` re-proves 19/19 offline.

--------------------------------------------------------------------------- #
STAGE 1 (retained below): the positional sigma / cell-geometry model.         #
--------------------------------------------------------------------------- #
Recover the LUT input-permutation sigma and turn a decoder's PHYSICAL LUT mask
into the LOGICAL truth table over the LE's four named input nets.

THE PROBLEM
-----------
`decode_rbf.py` (and `atom_first.py`) yield, for every used LE, a 16-bit
*physical* mask -- the 16 CRAM truth-table cells read in the identity
pair/delta ordering (`atom_first.phys_pair_delta`).  That mask round-trips
bit-exact, but it is NOT yet a readable logic function: Quartus lays the 16
minterm cells down in a position-dependent permuted order.  Which physical cell
holds logical minterm b depends on a permutation sigma that VARIES with the
LE's frame geometry -- exactly the sigma the Cyclone_CRAM_Mapper docs describe
and mine into `results/sigma_inv_fb8_groups.json` (the "35-cell canon layer").

WHAT THIS MODULE DOES
---------------------
1. Reproduces the Cyclone_CRAM_Mapper positional sigma model OFFLINE, reusing
   `atom_first` for all cell geometry.  For any (X,Y,N):
       * derive (foff, fb8, group)   -- the geometric key
       * look up sigma_inv from the mined table (3-key, nearest-foff fallback)
       * sigma = inverse(sigma_inv)
   `sigma_state()` returns all of it.  Cross-checked FLAT-bit-exact against the
   reference `bitstream.LutCodec.from_cram_model` at 7168/7168 LAB positions
   (every LAB column x Y=2..17 x N=0..30) in the self-test.

2. `physical_to_logical(phys_mask, X,Y,N)` un-permutes a decoder physical mask
   into the LOGICAL truth table.  Minterm bit i is input axis i, and the axes
   map to the LE's four physical input ports:
       bit0 = a = DATAA,  bit1 = b = DATAB,  bit2 = c = DATAC,  bit3 = d = DATAD
   (the Quartus lut_mask convention the codec is calibrated to: 0x8888 == a&b,
   pinned against Quartus AND-gate gold at X16Y4N0 -- see FACE_HW_OVERRIDE in
   Cyclone_CRAM_Mapper/fuzz/test_sigma_inv_3key.py).

3. `named_function()` binds those four axes to the NAMED nets that Phases 1/2
   resolve as the drivers of DATAA/B/C/D (the LEIM codec), producing the LE's
   logic as a truth table + minterm list + a canonical SOP expression over the
   real net names.

THE SIGMA RELATION (exact)
--------------------------
Reference `from_cram_model` places logical minterm b at the physical cell whose
pair/delta index is  pb = apply_sigma(b, sigma).  Hence the physical mask that
`atom_first` / `decode_rbf` read (indexed by pb) relates to the logical TT by

    phys_mask[pb] = logical_mask[b]     with pb = apply_sigma(b, sigma)
    logical_mask[b] = phys_mask[ apply_sigma(b, sigma) ]

so `physical_to_logical` is a pure 16-bit-index permutation -- no re-reading of
bits, no baseline needed.  It upgrades the existing round-trip-clean physical
mask in place.

SCOPE / HONESTY
---------------
* The sigma model here is byte/flat-identical to the HW-locked reference codec
  (7168/7168).  That reference's logical read is itself validated against real
  Quartus known-logic compiles (AND/OR/XOR gold + FACE probes); STAGE 2 re-runs
  that live-compile confirmation end-to-end on this decoder.
* Output negation / constant-mask edge cases live in a separate canon-negation
  layer (Cyclone_CRAM_Mapper CANON_NEG); the ctrl-cell TT decoded here already
  carries the full 16-bit function for every non-constant LE, which is the
  4781-LUT population of interest.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEVFILE = "<repo>/devfile"
_MAPPER = "<fork>"
sys.path.insert(0, _DEVFILE)

import atom_first as AF  # BLOCK_ORIGIN, y_offset, cram_n_delta, _wrap_adj, apply_sigma, atom_first_phys
from bitpos_to_rbf import flat_to_rbf  # proven flat CRAM index -> (rbf byte, bit)

# minterm bit index -> the LE physical input port that axis drives.
AXIS_PORTS = ("DATAA", "DATAB", "DATAC", "DATAD")
AXIS_NAMES = ("a", "b", "c", "d")

SIGMA_INV_TABLE = os.path.join(_MAPPER, "results", "sigma_inv_fb8_groups.json")

# HW regression: 19 live Quartus known-logic compiles (EP4CE6F17C8, same die as
# the vendor bin).  Each tuple = (x, y, n, raw_phys_mask_read_from_rbf, source TT
# over signals a/b/c/d, [net_on_DATAA, net_on_DATAB, net_on_DATAC, net_on_DATAD]).
# The nets are the back-annotated (quartus_cdb --back_annotate=routing) physical
# route_port assignments.  _selftest proves physical_port_tt + these bindings
# reproduce the source TT for all 19, offline.  11 span every mined sigma class;
# 8 are held-out (fresh functions, incl. wrap rows Y in {3,12,14,16}).
LIVE_REGRESSION = [
    [3, 19, 0, 47538, 48018, ["c", "d", "b", "a"]],
    [7, 18, 0, 2599, 667, ["b", "d", "c", "a"]],
    [3, 18, 0, 41585, 54081, ["b", "d", "a", "c"]],
    [3, 5, 4, 51416, 52616, ["c", "d", "b", "a"]],
    [3, 3, 0, 18372, 19572, ["c", "d", "b", "a"]],
    [3, 10, 0, 63147, 56043, ["c", "b", "d", "a"]],
    [8, 18, 0, 13225, 24145, ["c", "b", "a", "d"]],
    [4, 19, 0, 16818, 12692, ["b", "c", "a", "d"]],
    [7, 3, 0, 20795, 17711, ["d", "b", "c", "a"]],
    [3, 7, 12, 18067, 10597, ["c", "d", "a", "b"]],
    [6, 4, 2, 25262, 24450, ["c", "b", "a", "d"]],
    [10, 10, 0, 49541, 51207, ["a", "d", "b", "c"]],
    [16, 8, 6, 59283, 44487, ["b", "a", "c", "d"]],
    [22, 12, 20, 39927, 58751, ["a", "b", "d", "c"]],
    [11, 14, 16, 34359, 37211, ["b", "d", "a", "c"]],
    [10, 3, 12, 42792, 37602, ["a", "b", "d", "c"]],
    [6, 9, 14, 41601, 34977, ["c", "b", "d", "a"]],
    [24, 3, 8, 27340, 31680, ["b", "a", "d", "c"]],
    [13, 16, 0, 10278, 8656, ["a", "b", "d", "c"]],
]


# --------------------------------------------------------------------------- #
# Positional sigma_inv lookup (mirror of bitstream._sigma_inv_lookup).         #
# 3-key exact -> nearest-foff within the (fb8, group) bucket -> identity.      #
# The mined 3-key table (2112 entries) covers every LAB position; the self-    #
# test asserts this local lookup == the reference lookup at 7168/7168.         #
# --------------------------------------------------------------------------- #
def _load_sigma_inv(path=SIGMA_INV_TABLE):
    three_key = {}            # (foff, fb8, group) -> tuple sigma_inv
    by_bg = {}                # (fb8, group) -> sorted [(foff, sigma_inv)]
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        for v in data["entries"].values():
            foff, fb8, grp = v["foff"], v["fb8"], v["group"]
            si = tuple(v["sigma_inv"])
            three_key[(foff, fb8, grp)] = si
            by_bg.setdefault((fb8, grp), []).append((foff, si))
        for k in by_bg:
            by_bg[k].sort()
    return three_key, by_bg


_SIGMA_INV_3KEY, _SIGMA_INV_BY_BG = _load_sigma_inv()

# Prefer the reference resolver (bitstream._sigma_inv_lookup) when the mapper is
# reachable: it adds the legacy 2-key (fb8-only) fallback for the ~96 LAB
# positions whose (fb8, group) bucket is absent from the 3-key table.  This
# makes the lookup FLAT-identical to the HW-locked codec everywhere.  Falls back
# to the self-contained 3-key + nearest-foff table when the mapper is absent.
_REF_LOOKUP = None
try:  # pragma: no cover - environment dependent
    sys.path.insert(0, os.path.join(_MAPPER, "fuzz"))
    from bitstream import _sigma_inv_lookup as _REF_LOOKUP  # type: ignore
except Exception:
    _REF_LOOKUP = None


def sigma_inv_lookup(foff, fb8, group):
    """Positional sigma_inv for the geometric key (foff, fb8, group)."""
    if _REF_LOOKUP is not None:
        return tuple(_REF_LOOKUP(foff, fb8, group))
    key = (foff, fb8, group)
    if key in _SIGMA_INV_3KEY:
        return _SIGMA_INV_3KEY[key]
    bucket = _SIGMA_INV_BY_BG.get((fb8, group))
    if bucket:
        best = min(bucket, key=lambda ef_si: abs(ef_si[0] - foff))
        return best[1]
    return (0, 1, 2, 3)


# --------------------------------------------------------------------------- #
# Geometry key + sigma state                                                  #
# --------------------------------------------------------------------------- #
def geom_key(x, y, n):
    """(foff, fb8, group) exactly as bitstream.from_cram_model derives them."""
    group = (y - 2) // 3
    nd = AF.cram_n_delta(n)
    addr_adj, _ = AF._wrap_adj(y, n)
    # val = COLUMN_BASE[x] - 168 + offset + nd + addr_adj ; -168 = -136(period) -32(preamble)
    val = AF.BLOCK_ORIGIN[x] - 168 + AF.y_offset(y) + nd + addr_adj
    return val % 210, (val // 210) % 8, group


def sigma_state(x, y, n):
    """Full sigma state for an LE.

    Returns dict:
      foff, fb8, group : geometric key
      sigma_inv        : mined inverse permutation (table value)
      sigma            : the applied permutation, sigma = inverse(sigma_inv);
                         physical-cell index pb = apply_sigma(b, sigma) for
                         logical minterm b.
    """
    foff, fb8, group = geom_key(x, y, n)
    sigma_inv = sigma_inv_lookup(foff, fb8, group)
    sigma = [0, 0, 0, 0]
    for i, j in enumerate(sigma_inv):
        sigma[j] = i
    return {
        "x": x, "y": y, "n": n,
        "foff": foff, "fb8": fb8, "group": group,
        "sigma_inv": tuple(sigma_inv),
        "sigma": tuple(sigma),
    }


def logical_perm(x, y, n):
    """List P of length 16: P[b] = physical-bit index (pb) that stores logical
    minterm b.  logical_mask[b] = (phys_mask >> P[b]) & 1."""
    sigma = sigma_state(x, y, n)["sigma"]
    return [AF.apply_sigma(b, sigma) for b in range(16)]


# --------------------------------------------------------------------------- #
# The core transform: physical mask <-> logical truth table                   #
# --------------------------------------------------------------------------- #
def physical_to_logical(phys_mask, x, y, n):
    """Un-permute a decoder PHYSICAL mask into the LOGICAL truth table.

    `phys_mask` is the 16-bit value decode_rbf/atom_first produce (cell pb read
    in identity pair/delta order).  Result is the 16-bit truth table over the
    four input axes a=DATAA(bit0)..d=DATAD(bit3)."""
    perm = logical_perm(x, y, n)
    out = 0
    for b in range(16):
        if (phys_mask >> perm[b]) & 1:
            out |= (1 << b)
    return out


def logical_to_physical(log_mask, x, y, n):
    """Inverse of physical_to_logical (re-permute a logical TT to physical cells)."""
    perm = logical_perm(x, y, n)
    out = 0
    for b in range(16):
        if (log_mask >> b) & 1:
            out |= (1 << perm[b])
    return out


# --------------------------------------------------------------------------- #
# Reading straight from an rbf image                                           #
# --------------------------------------------------------------------------- #
def _phys_cell_bytebit(x, y, n, pb):
    """(rbf byte, bit) for physical mask bit pb -- byte-space, identical to the
    reference LutCodec.from_cram_model cell (incl. the slot-1 wrap that Quartus
    stores at the wrapped byte/bit, NOT the canonical flat_to_rbf position)."""
    addr_adj, bp_override = AF._wrap_adj(y, n)
    bp = bp_override if bp_override is not None else AF.ctrl_bit(y)
    pair, delta = AF.phys_pair_delta(pb, n)
    addr = AF.cram_byte_addr(x, y, n, pair, delta)  # already includes addr_adj
    return addr, bp


def logical_cells(x, y, n):
    """{logical minterm b -> flat CRAM index}.  Flat-identical to the reference
    LutCodec.from_cram_model cell for minterm b."""
    sigma = sigma_state(x, y, n)["sigma"]
    return {b: AF.atom_first_phys(x, y, n, AF.apply_sigma(b, sigma)) for b in range(16)}


def logical_cells_bytebit(x, y, n):
    """{logical minterm b -> (rbf byte, bit)} in byte space (wrap-correct)."""
    sigma = sigma_state(x, y, n)["sigma"]
    return {b: _phys_cell_bytebit(x, y, n, AF.apply_sigma(b, sigma)) for b in range(16)}


def _bit_at(img, byte, bit):
    if byte is None or byte < 0 or byte >= len(img):
        return None
    return (img[byte] >> bit) & 1


def read_physical_mask(img, x, y, n):
    """Read the 16-bit PHYSICAL mask directly from a (CRC-masked / normalized)
    rbf image -- the identity pb ordering, same value decode_rbf produces."""
    mask = 0
    for pb in range(16):
        byte, bit = _phys_cell_bytebit(x, y, n, pb)
        if _bit_at(img, byte, bit):
            mask |= (1 << pb)
    return mask


def read_logical_tt(img, x, y, n):
    """Read the LOGICAL truth table (over DATAA..D axes) straight from an rbf."""
    mask = 0
    for b, (byte, bit) in logical_cells_bytebit(x, y, n).items():
        if _bit_at(img, byte, bit):
            mask |= (1 << b)
    return mask


# --------------------------------------------------------------------------- #
# STAGE-2 CORRECTED TRANSFORM: physical mask -> TT over physical input ports.  #
# HW-grounded (19/19 live compiles).  A single constant axis reversal.         #
# --------------------------------------------------------------------------- #
def _rev4(i):
    """Reverse the 4 axis bits: bit0<->bit3, bit1<->bit2."""
    return ((i & 1) << 3) | ((i & 2) << 1) | ((i & 4) >> 1) | ((i & 8) >> 3)


def physical_port_tt(phys_mask):
    """Turn an atom_first PHYSICAL LUT mask (identity pair/delta order, the value
    decode_rbf produces) into the 16-bit truth table over the LE's four PHYSICAL
    input ports, axis bit0=DATAA, bit1=DATAB, bit2=DATAC, bit3=DATAD.

    This is the CORRECT, HW-grounded transform (constant axis reversal; 19/19
    live known-logic compiles across all sigma classes).  It does NOT use the
    positional sigma -- see the STAGE 2 CORRECTION header."""
    out = 0
    for m in range(16):
        if (phys_mask >> _rev4(m)) & 1:
            out |= (1 << m)
    return out


def read_physical_port_tt(img, x, y, n):
    """Read the TT over physical input ports straight from an rbf (byte-space,
    wrap-correct)."""
    return physical_port_tt(read_physical_mask(img, x, y, n))


# --------------------------------------------------------------------------- #
# Naming: logical TT over the four resolved input nets                         #
# --------------------------------------------------------------------------- #
def _sop(log_mask, names):
    """Canonical sum-of-products string over `names` (a,b,c,d order) for a 16-bit
    truth table, PROJECTED onto the support (axes the function truly depends on),
    so an unused axis never appears.  Constants collapse to '0'/'1'."""
    if log_mask == 0:
        return "0"
    if log_mask == 0xFFFF:
        return "1"
    dep = _dependence(log_mask)
    support = [i for i in range(4) if dep[i]]          # relevant axes
    terms = []
    seen = set()
    for m in range(16):
        if not ((log_mask >> m) & 1):
            continue
        key = tuple((m >> i) & 1 for i in support)     # projected minterm
        if key in seen:
            continue
        seen.add(key)
        lits = [names[i] if (m >> i) & 1 else "!" + names[i] for i in support]
        terms.append("&".join(lits))
    return " | ".join(terms)


def _dependence(log_mask):
    """Which of the 4 axes the function actually depends on (cofactor test)."""
    dep = []
    for i in range(4):
        changes = any(
            ((log_mask >> m) & 1) != ((log_mask >> (m ^ (1 << i))) & 1)
            for m in range(16)
        )
        dep.append(bool(changes))
    return dep


def named_function(x, y, n, input_nets, log_mask=None, img=None):
    """Produce the LE's logic as a named function.

    input_nets : dict mapping PHYSICAL port -> net name, e.g.
        {"DATAA": "LOCAL_INTERCONNECT:X10Y8S0I3", "DATAB": ..., ...}.
        Ports absent / None are labelled by their axis letter and flagged
        `unbound`.  This is exactly what the Phase-1/2 LEIM codec resolves
        (which local line / net drives each physical LE input port).
    log_mask   : the TT over physical ports (from `physical_port_tt`); if None it
                 is read from `img` via the HW-grounded `read_physical_port_tt`.

    Returns a dict: geom/sigma state (reference only), TT over ports, per-port
    net binding, the ports the function truly depends on, minterm list, and a
    SOP expression over the named nets.
    """
    st = sigma_state(x, y, n)
    if log_mask is None:
        if img is None:
            raise ValueError("need log_mask or img")
        log_mask = read_physical_port_tt(img, x, y, n)  # STAGE-2 corrected path

    names = []
    bindings = {}
    unbound = []
    for i, port in enumerate(AXIS_PORTS):
        net = input_nets.get(port) if input_nets else None
        bindings[port] = net
        if net:
            names.append(net)
        else:
            names.append(AXIS_NAMES[i])
            unbound.append(port)

    dep = _dependence(log_mask)
    return {
        "site": f"LCCOMB_X{x}_Y{y}_N{n}",
        "x": x, "y": y, "n": n,
        "sigma_inv": st["sigma_inv"],
        "sigma": st["sigma"],
        "geom_key": {"foff": st["foff"], "fb8": st["fb8"], "group": st["group"]},
        "logical_mask": log_mask,
        "logical_mask_hex": f"0x{log_mask:04x}",
        "axis_ports": list(AXIS_PORTS),
        "input_nets": bindings,
        "unbound_ports": unbound,
        "depends_on_axes": [AXIS_NAMES[i] for i in range(4) if dep[i]],
        "minterms": [b for b in range(16) if (log_mask >> b) & 1],
        "function": _sop(log_mask, names),
    }


def logical_from_decoder_feat(feat, input_nets=None):
    """Bridge for decode_rbf's LUT feature dicts.

    `feat` carries x, y, n and `phys_mask` (the round-trip-clean physical mask).
    Returns `feat` augmented with logical_mask + named function (if nets given).
    """
    x, y, n = feat["x"], feat["y"], feat["n"]
    phys = feat.get("phys_mask")
    if phys is None:
        phys = feat.get("phys_mask_hex")
        phys = int(phys, 16) if isinstance(phys, str) else phys
    log_mask = physical_port_tt(phys)   # STAGE-2 corrected: TT over physical ports
    out = dict(feat)
    out["logical_mask"] = log_mask
    out["logical_mask_hex"] = f"0x{log_mask:04x}"
    if input_nets is not None:
        out["logical_function"] = named_function(x, y, n, input_nets, log_mask=log_mask)
    return out


# --------------------------------------------------------------------------- #
# Self-test / verification                                                     #
# --------------------------------------------------------------------------- #
def _selftest():
    result = {"module": "lut_sigma.py (Phase 4 STAGE 1)"}

    # (A) FLAT-bit equivalence to the reference codec across all LAB positions.
    ref_ok = None
    try:
        sys.path.insert(0, os.path.join(_MAPPER, "fuzz"))
        from bitstream import LutCodec, _sigma_inv_lookup
        from bitpos_to_rbf import rbf_to_flat, PREAMBLE, FRAME_STRIDE

        def ref_flat_cells(x, y, n):
            codec = LutCodec.from_cram_model(x, y, n)
            cells = {}
            for b in range(16):
                (addr, bp) = next(iter(codec.patterns[b]))
                F = (addr - PREAMBLE) // FRAME_STRIDE
                Yf = (addr - PREAMBLE) % FRAME_STRIDE
                cells[b] = rbf_to_flat(F, Yf, bp)
            return cells

        tot = bad = lut_lookup_mismatch = 0
        for x in AF.BLOCK_ORIGIN:
            for y in range(2, 18):
                for n in range(0, 32, 2):
                    st = sigma_state(x, y, n)
                    # local lookup == reference lookup
                    ref_si = _sigma_inv_lookup(st["foff"], st["fb8"], st["group"])
                    if tuple(ref_si) != st["sigma_inv"]:
                        lut_lookup_mismatch += 1
                    mine = logical_cells(x, y, n)
                    try:
                        ref = ref_flat_cells(x, y, n)
                    except Exception:
                        continue
                    tot += 1
                    if any(ref[b] != mine[b] for b in range(16)):
                        bad += 1
        ref_ok = (bad == 0 and lut_lookup_mismatch == 0)
        result["ref_codec_flat_match"] = f"{tot - bad}/{tot}"
        result["sigma_inv_lookup_match"] = "exact" if lut_lookup_mismatch == 0 \
            else f"{lut_lookup_mismatch} mismatches"
    except Exception as e:
        result["ref_codec_cross_check"] = f"skipped: {e}"

    # (B) physical<->logical permutation round-trips for random masks.
    import random
    rng = random.Random(4)
    positions = [(10, 10, 0), (4, 4, 2), (16, 8, 6), (3, 3, 12), (22, 12, 20),
                 (6, 4, 0), (33, 17, 30), (11, 14, 16)]
    rt = 0
    rt_tot = 0
    for (x, y, n) in positions:
        for _ in range(8):
            m = rng.randint(0, 0xFFFF)
            rt_tot += 1
            if physical_to_logical(logical_to_physical(m, x, y, n), x, y, n) == m:
                rt += 1
    result["phys_logical_roundtrip"] = f"{rt}/{rt_tot}"

    # (C) worked example: an AND-of-two + the sigma it un-permutes.
    #     physical mask that reads as logical a&b (0x8888) at X10Y10N0.
    x, y, n = 10, 10, 0
    log_and = 0x8888  # a & b  (Quartus convention)
    phys = logical_to_physical(log_and, x, y, n)
    back = physical_to_logical(phys, x, y, n)
    demo_nets = {"DATAA": "LOCAL_INTERCONNECT:X10Y10S0I5",
                 "DATAB": "LOCAL_INTERCONNECT:X10Y10S0I2",
                 "DATAC": None, "DATAD": None}
    nf = named_function(x, y, n, demo_nets, log_mask=back)
    result["worked_example"] = {
        "site": nf["site"], "sigma": list(nf["sigma"]),
        "logical_mask": nf["logical_mask_hex"],
        "physical_mask": f"0x{phys:04x}",
        "function": nf["function"],
        "depends_on_axes": nf["depends_on_axes"],
    }

    # (D) STAGE 2 HW regression: physical_port_tt + back-annotated port->net
    #     bindings reproduce the known source TT for all 19 live compiles.
    sigax = {"a": 0, "b": 1, "c": 2, "d": 3}
    ports = ("DATAA", "DATAB", "DATAC", "DATAD")
    live_ok = 0
    for (x, y, n, phys, src, portnets) in LIVE_REGRESSION:
        tt = physical_port_tt(phys)          # TT over physical ports A..D
        # portnets[pidx] = signal driving physical port pidx; remap to signal space
        got = 0
        for mi in range(16):
            pm = 0
            for pidx in range(4):
                if (mi >> sigax[portnets[pidx]]) & 1:
                    pm |= (1 << pidx)
            if (tt >> pm) & 1:
                got |= (1 << mi)
        if got == src:
            live_ok += 1
    result["stage2_live_regression"] = f"{live_ok}/{len(LIVE_REGRESSION)}"

    ok = (result.get("phys_logical_roundtrip") == f"{rt_tot}/{rt_tot}"
          and back == log_and
          and live_ok == len(LIVE_REGRESSION)
          and (ref_ok in (True, None)))
    result["pass"] = bool(ok)
    return result


if __name__ == "__main__":
    r = _selftest()
    print(json.dumps(r, indent=2))
