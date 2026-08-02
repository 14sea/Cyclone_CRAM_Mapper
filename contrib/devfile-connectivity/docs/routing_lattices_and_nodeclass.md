# Routing-node lattices (C4 / R4 / R24 / C16) and node → class map

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10). All of this is proven from
the `libddb_dygr.so` decompile plus the device-file (`.ddb`) node vector, and
validated against a live gdb intercept oracle plus independent Quartus compiles.
Implementation: `scripts/node_id.py`; class finalize note: `nodeclass.md`.

## Node identity

The DYGR route-assembler identifies a routing-graph node by a 32-bit global id
`gid`, split by bit 31 into two disjoint id spaces:

- `is_router_id(gid)` = bit31 set → **router node** (interconnect wire:
  C4/R4/R24/C16/LI/LEIM/local/direct/IO/clk). These are the ids the connectivity
  table uses for both source and dest.
- `is_placer_id(gid)` = bit31 clear → **placer node** (atom: LE/IO/RAM/PLL cell).
- `node_index(gid) = gid & 0x7fffffff` is the pool ordinal — the sole join key
  into the DYGR route-asm node vector parsed by `ddb_parse.py` (the ASM node
  record carries no id field).

At runtime `node_index → (class, X, Y, S, I)` is a device-file table lookup
(`DYGR_DIE_INFO_BODY::get_location` @0x227930, `get_element_enum` @0x227aa0),
exactly reproducible from the parsed node vector. The node vector is a
concatenation of per-class contiguous blocks, which yields both the closed-form
lattices below (for the metal classes) and the exact enum-block extents.

## Closed-form lattices (metal classes)

Recovered by regressing `node_index` against `(I, X, Y)` over the device-wide
phase-2 routing tables and pinned to the enum-block extents:

```
C4  (I in [10,22]) : node = 60836 + 798*I + 24*X + Y
                   ( == 70654 + 798*(I-12) + 24*(X-10) + (Y-2) )
R4                 : node = 30925 + 760*I + 23*X + Y
R24 (I = 0)        : node = 59111 + 23*X + Y
C16                : contiguous enum-281 block, extents [82262, 83587]
```

Origin note: routing `(X,Y)` is the **same** coordinate system and origin as the
IOE/LUT `(X,Y)` — see `coordinate_reconciliation.md`. A handful of left-edge
columns (X6/X7 on R4, X8 on R24) sit a few indices off the pure lattice and are
carried as explicit exceptions in `node_id.py`; the enum-block extents are exact.

## node → class (device element enum)

`node_index → DEV_ELEMENT enum → wire class`, harvested from the compiler's own
classifier `DYGR_DIE_INFO_BODY::get_element_enum(gid)` (`libddb_dygr.so`
0x127aa0) swept live over all 135,117 routing node ids. Device-file → design
independent. **Decode-or-refuse:** a class label is emitted only where the enum
sweep grounds it; the 49 unlabeled enum blocks (26,757 nodes: clock / global /
direct-link / IO-sub / placer-adjacent) stay `null` (REFUSED), never guessed.

Validation (see `nodeclass.md` for the full table): reproduces the live enum
sweep 135117/135117 (0 mismatch); a held-out fresh compile 135117/135117;
agrees with 5339 `back_annotate` wire names, 0 conflicts.

Named classes (exact node-index extents):

| class | enum | node range | count |
|---|---:|---|---:|
| LE_BUFFER | 45 | 10320–30959 | 20,640 |
| R4 | 268 | 30971–59156 | 28,186 |
| R24 | 273 | 59157–60445 | 1,289 |
| C4 | 275 | 60446–82261 | 21,816 |
| C16 | 281 | 82262–83587 | 1,326 |
| LOCAL_INTERCONNECT | 282 | 83588–115988 | 32,401 |
| IO_DATAIN | 307 | 118799–119168 | 370 |
| BLOCK_INPUT_MUX | 540 | 122549–124880 | 2,332 |

`LE_BUFFER` is the LUT/LAB-cell **output** buffer — the source of the LUT-output
routing hop. `nodeclass.md` documents why an allocator-rotation shortcut mis-typed
these as C4/R4 metal, and why the ground-truth enum classification eliminates the
mis-tag by construction (decode-or-refuse over the broken rotation).
