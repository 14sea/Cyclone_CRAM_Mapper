# Coordinate reconciliation: routing (X,Y) == IOE/LUT (X,Y)

Device-general (die `cycloneive1`, EP4CE6 == EP4CE10).

The routing-node lattices in `routing_lattices_and_nodeclass.md` are expressed in
an `(X,Y)` from the DYGR device-file node locations
(`DYGR_DIE_INFO_BODY::get_location`). The LUT/IOE codecs
(`lut_sigma.py`, `lut_fullgrid.py`, `atom_first` block origins, the IOE
input-mux codec) are expressed in the placer/atom `(X,Y)`.

**These are the same coordinate system with the same origin.** A routing node at
`(X,Y)` and the LAB/IOE cell at `(X,Y)` refer to the same physical column/row of
the die; there is no offset, flip, or scale between them. Concretely:

- The LOCAL_INTERCONNECT / BLOCK_INPUT_MUX taps that a LUT input consumes at cell
  `(X,Y)` carry routing node `(X,Y)` in the connectivity table — the join is a
  direct coordinate equality, which is what lets a bound routing arc be chained
  onto a LUT endpoint at the same `(X,Y)` (see `static_connectivity.py` /
  `connectivity_codec.py`).
- The device column layout is identical in both views: LAB columns
  `X ∈ {3,4,6,7,8,10,11,12,13,16,17,18,19,21,22,23,24,25,26,28,29,31}` for CE6,
  extended by the CE10 jailbreak columns `{5,9,14,30,32,33}`; rows
  `Y ∈ [2..21]` with gaps at `Y=15,20`. The routing lattices index the same
  columns/rows (the C4/R4 `X` term ranges over the same die columns).

**Why this matters for the pipeline.** Because the two models share one origin,
a net can be traced from a LUT output (placer cell `(X,Y)`), through the routing
lattice (router node `(X,Y)`), to a LUT input (placer cell `(X,Y)`) with no
coordinate translation layer. Any consumer that already speaks the repo's
`config.py` `(X,Y)` convention consumes the connectivity table and the routing
lattices directly.

Validation: the coordinate identity is what makes the LUT-output-hop bind checks
in `nodeclass.md` and the LI/LEIM tap resolution in `static_connectivity.py`
round-trip bit-exact — a wrong offset would have produced systematic bind
failures rather than the observed clean round-trips.
