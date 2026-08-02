#!/usr/bin/env python3
"""
SA2 node-id model helper  (Cyclone IV E, die base ``cycloneive1``; EP4CE6 == EP4CE10,
same 368011-B rbf, same routing-graph node space).

WHAT A "NODE ID" IS  (proven from libddb_dygr.so decompile + live trace)
-----------------------------------------------------------------------
The assembler / DYGR route-asm resolver identifies a routing-graph node by a
32-bit GLOBAL ID (gid).  Two disjoint id spaces share the 32-bit word, split by
bit 31:

    is_router_id(gid) :  (gid + 0x80000000) < 0x7fffffff        # DYGR_DIE_INFO_BODY::is_router_id @0x227920
    is_placer_id(gid) :  (~gid) >> 31                           # DYGR_DIE_INFO_BODY::is_placer_id @0x227910
    node_index(gid)   :  gid & 0x7fffffff  (0xffffffff stays)   # DYGR_DIE_INFO_BODY::get_node_index_of_id @0x228120
    DEV_ILLEGAL_GLOBAL_ID = 0xffffffff

  * bit31 SET  -> ROUTER node  (interconnect wire: C4/R4/R24/C16/LI/LEIM/local/
                  direct/IO/clk...).  These are the ids the DYGR route-asm
                  connectivity table uses for BOTH src and dest.
  * bit31 CLEAR-> PLACER node   (atom: LE/IO/RAM/PLL cell).

  node_index = gid & 0x7fffffff is the POOL INDEX: the positional ordinal into
  the routing-graph node vector.  The DYGR_ROUTE_ASM node vector parsed by
  ddb_parse.py is indexed by exactly this ordinal (the ASM node record carries NO
  id field -> ordinal is the sole join key).  The live trace stores it as `id`
  (raw = id | 0x80000000, e.g. raw 2147510387 -> id 26739).

HOW node_index -> (class, X, Y, S, I)   (proven from decompile)
--------------------------------------------------------------
At runtime the map is a device-file LOOKUP, not a formula (DYGR_ROUTE_INFO_BODY,
loaded from ddb_cycloneive1_routing.ddb):
  DYGR_DIE_INFO_BODY::get_location(gid, DEV_LOCATION&) @0x227930  reads a 0x10-byte
    per-node record at  base + node_index*0x10:  X = *(short)(rec+0),
    Y = *(short)(rec+2), and via a pointer at (rec+8) the third dim S = ptr[+4]
    and the wire index I = ptr[+6].
  DYGR_DIE_INFO_BODY::get_element_enum(gid) @0x227aa0  reads the class
    (DEV_ELEMENT enum) = *ushort at *(rec+8).
The node vector is a CONCATENATION of per-element (per-class) contiguous blocks
(get_global_id_of_element(elem,i)=base[elem]+i ; get_num_element(elem)=count), so
the id -> class -> (I,X,Y) map is exactly reproducible by that table read.  This
module reconstructs the (I,X,Y)->ordinal map for the classes we have grounded, and
REFUSES (class-only / UNMAPPED) where it cannot ground the answer -- decode-or-refuse.

GROUNDING  (device-file, non-fuzz)
----------------------------------
Two sources, both grounded via quartus_cdb --back_annotate=routing naming a wire
`TYPE:XxYySsIi` and joining that name to a DYGR node ordinal:
  * phase2 devwide codec tables (C4 n=3153, R4 n=1782, R24 n=363, C16 n=13) --
    these turned out to be a HIGH-I SUBSET of each class (C4 I=12..17, R4 I=17..22,
    R24 I=0), which is why an earlier revision of this model mis-ranged the blocks.
  * the READ-ONLY live-trace ground truth (traceA/B.json) -- names 53 more nodes
    and, crucially, extends the observed I-domains DOWN (C4 to I=0, R4 to I=5,
    LOCAL_INTERCONNECT to I=25), exposing that low-I nodes earlier flagged
    "UNMAPPED" are simply the low-I part of C4 / R4 / LOCAL_INTERCONNECT.

VALIDATED FITS (this module's __main__ reproduces these against the tables above):
  C4  : TWO affine regimes, both sX=24, sY=1 -- 3153/3153 EXACT
          I in [0,9]  : node = 60444 + 832*I + 24*X + Y
          I in [10,22]: node = 60836 + 798*I + 24*X + Y   (== mission 70654+798*(I-12)+24*(X-10)+(Y-2))
  R4  : node = 30925 + 760*I + 23*X + Y   (single regime; a few left-edge X6/X7 off by 10..15)
  R24 : node = 59111 + 23*X + Y (I=0)     (2 left-edge X8 off by 5)
"""
import os, json, re

# ---------------------------------------------------------------- gid layer ---
DEV_ILLEGAL_GLOBAL_ID = 0xFFFFFFFF
ROUTER_FLAG = 0x80000000

def is_router_id(gid):
    gid &= 0xFFFFFFFF
    return ((gid + 0x80000000) & 0xFFFFFFFF) < 0x7FFFFFFF   # bit31 set, != 0xffffffff

def is_placer_id(gid):
    gid &= 0xFFFFFFFF
    return (gid >> 31) == 0                                  # bit31 clear

def node_index(gid):
    gid &= 0xFFFFFFFF
    return DEV_ILLEGAL_GLOBAL_ID if gid == DEV_ILLEGAL_GLOBAL_ID else (gid & 0x7FFFFFFF)

def router_gid(idx):
    """node_index (pool ordinal) -> router global id (bit31 set)."""
    return (idx & 0x7FFFFFFF) | ROUTER_FLAG

# ------------------------------------------------- per-class affine lattices ---
# Simple single-regime classes: node_index = base + sI*I + sX*X + Y  (Y stride 1).
LATTICE = {
    'R4' : dict(base=30925, sI=760, sX=23, I=(5, 22),  X=(6, 25),  Y=(2, 21)),
    'R24': dict(base=59111, sI=0,   sX=23, I=(0, 0),   X=(3, 31),  Y=(2, 21)),
}
# C4 is piecewise in I (both regimes share sX=24, sY=1).
C4_LO = dict(base=60444, sI=832, sX=24, I=(0, 9),   X=(8, 36), Y=(0, 23))
C4_HI = dict(base=60836, sI=798, sX=24, I=(10, 22), X=(8, 36), Y=(0, 23))
C4_DOM = dict(I=(0, 22), X=(8, 36), Y=(0, 23))

def _c4_regime(I):
    return C4_LO if I <= 9 else C4_HI

def encode(cls, I, X, Y):
    """(class,I,X,Y) -> node_index (affine; edge cells may differ by a few)."""
    if cls == 'C4':
        L = _c4_regime(I)
        return L['base'] + L['sI'] * I + L['sX'] * X + Y
    L = LATTICE[cls]
    return L['base'] + L['sI'] * I + L['sX'] * X + Y

def _decode_one(L, n):
    cands = []
    for I in range(L['I'][0], L['I'][1] + 1):
        r = n - L['base'] - L['sI'] * I
        if r < 0:
            continue
        X, Y = divmod(r, L['sX'])
        if L['X'][0] <= X <= L['X'][1] and L['Y'][0] <= Y <= L['Y'][1]:
            cands.append((I, X, Y))
    return cands

def decode_lattice(cls, n):
    """node_index -> list of in-domain (I,X,Y) candidates for one class.
    Iterates the small I domain (bands overlap because X starts >0), so this is
    the CORRECT inverse -- a plain divmod is wrong.  For C4 both I-regimes are
    tried.  Normally returns 0 or 1 candidate."""
    if cls == 'C4':
        return _decode_one(C4_LO, n) + _decode_one(C4_HI, n)
    return _decode_one(LATTICE[cls], n)

# ----------------------------------------------- grounded block partition ------
# R1 CORRECTED CODEC (device-file EXACT).  Superseded the earlier "min..max node
# id SEEN" blocks (which undershot every block on both edges).  These ranges are
# the EXACT contiguous DEV_ELEMENT enum runs from the R1 DEBUG oracle
# (R1_oracle_1.jsonl): a full get_element_enum(gid) sweep over ALL 135,117 router
# ids, captured live from the tool's own device-file classifier and reproduced
# tool-free here.  Validated bit-exact vs the oracle (135117/135117, 0 mismatch)
# AND held-out on an independent compile (specimenR1: 135117/135117, 0 mismatch).
# The map is design-independent (device-file), so it holds for every EP4CE6/EP4CE10
# bitstream incl. target.rbf.
#   `class` present => that node RANGE is a single grounded wire class (exact extent).
#   `class` None    => a real device element block (clock/global/direct-link/IO-sub/
#                      placer-adjacent) whose class label is not yet grounded -- do
#                      NOT guess (decode-or-refuse).  Range/enum are still exact.
# Codec artifact: out/loop/R1_corrected_node_class_codec.json.
BLOCKS = [
 (     0,  10319, None                  , 'enum 43 device class UNKNOWN; decode-or-refuse'),
 ( 10320,  30959, 'LE_BUFFER'           , 'enum 45 LE_BUFFER (device-file exact extent, R1 oracle)'),
 ( 30960,  30960, None                  , 'enum 57 device class UNKNOWN; decode-or-refuse'),
 ( 30961,  30970, None                  , 'enum 69 device class UNKNOWN; decode-or-refuse'),
 ( 30971,  59156, 'R4'                  , 'enum 268 R4 (device-file exact extent, R1 oracle)'),
 ( 59157,  60445, 'R24'                 , 'enum 273 R24 (device-file exact extent, R1 oracle)'),
 ( 60446,  82261, 'C4'                  , 'enum 275 C4 (device-file exact extent, R1 oracle)'),
 ( 82262,  83587, 'C16'                 , 'enum 281 C16 (device-file exact extent, R1 oracle)'),
 ( 83588, 115988, 'LOCAL_INTERCONNECT'  , 'enum 282 LOCAL_INTERCONNECT (device-file exact extent, R1 oracle)'),
 (115989, 117644, None                  , 'enum 284 device class UNKNOWN; decode-or-refuse'),
 (117645, 118472, None                  , 'enum 286 device class UNKNOWN; decode-or-refuse'),
 (118473, 118480, None                  , 'enum 295 device class UNKNOWN; decode-or-refuse'),
 (118481, 118490, None                  , 'enum 298 device class UNKNOWN; decode-or-refuse'),
 (118491, 118510, None                  , 'enum 299 device class UNKNOWN; decode-or-refuse'),
 (118511, 118786, None                  , 'enum 300 device class UNKNOWN; decode-or-refuse (incl. 118745=SCLK_TO_ROWCLK_BUF trace anchor)'),
 (118787, 118798, None                  , 'enum 304 device class UNKNOWN; decode-or-refuse'),
 (118799, 119168, 'IO_DATAIN'           , 'enum 307 IO_DATAIN (device-file exact extent, R1 oracle)'),
 (119169, 119176, None                  , 'enum 308 device class UNKNOWN; decode-or-refuse'),
 (119177, 119180, None                  , 'enum 309 device class UNKNOWN; decode-or-refuse'),
 (119181, 119184, None                  , 'enum 335 device class UNKNOWN; decode-or-refuse'),
 (119185, 119186, None                  , 'enum 336 device class UNKNOWN; decode-or-refuse'),
 (119187, 119188, None                  , 'enum 343 device class UNKNOWN; decode-or-refuse'),
 (119189, 119190, None                  , 'enum 346 device class UNKNOWN; decode-or-refuse'),
 (119191, 119194, None                  , 'enum 350 device class UNKNOWN; decode-or-refuse'),
 (119195, 119196, None                  , 'enum 351 device class UNKNOWN; decode-or-refuse'),
 (119197, 119198, None                  , 'enum 353 device class UNKNOWN; decode-or-refuse'),
 (119199, 119200, None                  , 'enum 356 device class UNKNOWN; decode-or-refuse'),
 (119201, 119202, None                  , 'enum 357 device class UNKNOWN; decode-or-refuse'),
 (119203, 119204, None                  , 'enum 358 device class UNKNOWN; decode-or-refuse'),
 (119205, 119206, None                  , 'enum 359 device class UNKNOWN; decode-or-refuse'),
 (119207, 121786, None                  , 'enum 364 device class UNKNOWN; decode-or-refuse'),
 (121787, 121787, None                  , 'enum 367 device class UNKNOWN; decode-or-refuse'),
 (121788, 121788, None                  , 'enum 368 device class UNKNOWN; decode-or-refuse'),
 (121789, 121789, None                  , 'enum 369 device class UNKNOWN; decode-or-refuse'),
 (121790, 121790, None                  , 'enum 370 device class UNKNOWN; decode-or-refuse'),
 (121791, 121791, None                  , 'enum 371 device class UNKNOWN; decode-or-refuse'),
 (121792, 121792, None                  , 'enum 372 device class UNKNOWN; decode-or-refuse'),
 (121793, 121793, None                  , 'enum 373 device class UNKNOWN; decode-or-refuse'),
 (121794, 121794, None                  , 'enum 374 device class UNKNOWN; decode-or-refuse'),
 (121795, 122346, None                  , 'enum 377 device class UNKNOWN; decode-or-refuse'),
 (122347, 122461, None                  , 'enum 380 device class UNKNOWN; decode-or-refuse'),
 (122462, 122462, None                  , 'enum 408 device class UNKNOWN; decode-or-refuse'),
 (122463, 122463, None                  , 'enum 409 device class UNKNOWN; decode-or-refuse'),
 (122464, 122464, None                  , 'enum 416 device class UNKNOWN; decode-or-refuse'),
 (122465, 122536, None                  , 'enum 521 device class UNKNOWN; decode-or-refuse'),
 (122537, 122548, None                  , 'enum 523 device class UNKNOWN; decode-or-refuse'),
 (122549, 124880, 'BLOCK_INPUT_MUX'     , 'enum 540 BLOCK_INPUT_MUX (device-file exact extent, R1 oracle)'),
 (124881, 124888, None                  , 'enum 541 device class UNKNOWN; decode-or-refuse'),
 (124889, 124892, None                  , 'enum 564 device class UNKNOWN; decode-or-refuse'),
 (124893, 124896, None                  , 'enum 566 device class UNKNOWN; decode-or-refuse'),
 (124897, 129636, None                  , 'enum 568 device class UNKNOWN; decode-or-refuse'),
 (129637, 129637, None                  , 'enum 650 device class UNKNOWN; decode-or-refuse'),
 (129638, 129638, None                  , 'enum 651 device class UNKNOWN; decode-or-refuse'),
 (129639, 129642, None                  , 'enum 659 device class UNKNOWN; decode-or-refuse'),
 (129643, 129646, None                  , 'enum 664 device class UNKNOWN; decode-or-refuse'),
 (129647, 134386, None                  , 'enum 665 device class UNKNOWN; decode-or-refuse'),
 (134387, 135116, None                  , 'enum 667 device class UNKNOWN; decode-or-refuse'),
]

def block_of(n):
    for lo, hi, cls, note in BLOCKS:
        if lo <= n <= hi:
            return cls, note
    return None, 'above highest grounded block'

# -------------------------------------- exact device-file table (grounded) -----
# Loaded lazily from the authoritative device-file-grounded sources.
_PHASE2 = '<repo>/devfile/phase2'
_DEBUG  = '<repo>/devfile/re_workflows/out/debugger'
_DEVWIDE = {
    'C4':  os.path.join(_PHASE2, 'c4_codec_table_devwide.json'),
    'R4':  os.path.join(_PHASE2, 'r4/r4_codec_table_devwide.json'),
    'R24': os.path.join(_PHASE2, 'r24/r24_codec_table_devwide.json'),
    'C16': os.path.join(_PHASE2, 'c16/c16_codec_table_devwide.json'),
}
_TRACES = [os.path.join(_DEBUG, 'traceA.json'), os.path.join(_DEBUG, 'traceB.json')]
_NAME_RE = re.compile(r'^[A-Z0-9_]+:X(-?\d+)Y(-?\d+)(?:S(-?\d+))?(?:I(-?\d+))?')
_EXACT = None

def _load_exact():
    global _EXACT
    if _EXACT is not None:
        return _EXACT
    _EXACT = {}
    def add(nid, nm):
        if isinstance(nid, int) and isinstance(nm, str) and _NAME_RE.match(nm):
            _EXACT.setdefault(nid, nm)
    for path in _DEVWIDE.values():
        try:
            d = json.load(open(path))
        except Exception:
            continue
        for r in (d if isinstance(d, list) else d.get('nodes', [])):
            if isinstance(r, dict):
                add(r.get('dest_node'), r.get('dest') or r.get('name'))
    for path in _TRACES:
        try:
            for r in json.load(open(path)):
                add(r.get('dest_node'), r.get('dest_wire'))
                add(r.get('source_node'), r.get('source_wire'))
        except Exception:
            continue
    return _EXACT

def _parse_name(nm):
    m = _NAME_RE.match(nm)
    if not m:
        return None
    return dict(X=int(m.group(1)), Y=int(m.group(2)),
                S=int(m.group(3)) if m.group(3) is not None else None,
                I=int(m.group(4)) if m.group(4) is not None else None)

# ---------------------------------------------------------- classify -----------
def classify(gid_or_index, use_table=True):
    """Resolve a router gid OR a bare node_index to the best (class, coords, name).
    Order: (1) exact device-file table, (2) affine lattice inverse (correct
    domains, C4 two-regime), (3) grounded block bucket, else refuse.
    confidence in {exact, lattice, lattice-ambiguous, class-only, none}."""
    g = gid_or_index & 0xFFFFFFFF
    flag_present = bool(g & ROUTER_FLAG)
    idx = node_index(g) if flag_present else g
    if idx == DEV_ILLEGAL_GLOBAL_ID:
        return dict(node_index=idx, is_router=False, flag_present=flag_present,
                    block='ILLEGAL', **{'class': None}, coords=None, name=None,
                    confidence='none', note='DEV_ILLEGAL_GLOBAL_ID')
    out = dict(node_index=idx, is_router=True, flag_present=flag_present)
    blk_cls, note = block_of(idx)
    out['block'] = blk_cls or 'UNBOUND_GAP'
    # 1) exact device-file table lookup
    if use_table:
        nm = _load_exact().get(idx)
        if nm:
            out.update({'class': nm.split(':')[0], 'coords': _parse_name(nm), 'name': nm,
                        'confidence': 'exact', 'note': 'device-file grounded (cdb name <-> ddb node)'})
            return out
    # 2) affine lattice inverse
    for cls in ('C4', 'R4', 'R24'):
        cands = decode_lattice(cls, idx)
        if cands:
            if len(cands) == 1:
                I, X, Y = cands[0]
                out.update({'class': cls, 'coords': dict(I=I, X=X, Y=Y, S=0),
                            'name': f'{cls}:X{X}Y{Y}S0I{I}', 'confidence': 'lattice',
                            'note': 'affine inverse (edge cells may be off a few)'})
            else:
                out.update({'class': cls,
                            'coords': [dict(I=I, X=X, Y=Y, S=0) for I, X, Y in cands],
                            'name': None, 'confidence': 'lattice-ambiguous',
                            'note': f'{len(cands)} in-domain candidates'})
            return out
    # 3) grounded block bucket, else refuse
    if blk_cls:
        out.update({'class': blk_cls, 'coords': None, 'name': None,
                    'confidence': 'class-only', 'note': note})
    else:
        out.update({'class': None, 'coords': None, 'name': None,
                    'confidence': 'none', 'note': note})
    return out

# ------------------------------------------------------------- self-test -------
if __name__ == '__main__':
    print('== lattice validation against ALL grounded points (device-file + trace) ==')
    ex = _load_exact()
    per = {}
    for nid, nm in ex.items():
        cls = nm.split(':')[0]
        c = _parse_name(nm)
        if cls in ('C4', 'R4', 'R24') and c and c.get('I') is not None:
            per.setdefault(cls, []).append((nid, c['I'], c['X'], c['Y']))
    for cls in ('C4', 'R4', 'R24'):
        rows = per.get(cls, [])
        enc = sum(1 for nid, I, X, Y in rows if encode(cls, I, X, Y) == nid)
        dec = sum(1 for nid, I, X, Y in rows if decode_lattice(cls, nid) == [(I, X, Y)])
        print(f'  {cls}: n={len(rows):4d}  encode {enc}/{len(rows)} exact  decode {dec}/{len(rows)} unique-correct')

    print('\n== classify observed live-trace node ids ==')
    OBS = [10618, 26739, 34950, 38082, 39602, 40270, 60851, 68335, 68339, 70813,
           71614, 82372, 82373, 82931, 83384, 83520, 83957, 84783, 91337, 91368,
           93801, 94621, 103953, 118896, 118902, 119088, 119145, 122603, 123131]
    for n in OBS:
        r = classify(n)
        print(f"  {n:7d}  block={str(r['block']):19s} conf={r['confidence']:16s} {r['name'] or ''}")
