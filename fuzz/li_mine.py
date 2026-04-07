#!/usr/bin/env python3
"""LI activation key-space analysis (Phase 1: pure path_json mining).

Goal: characterize the (src_type, src_I, dst_N, dst_port) keyspace from
existing routing_paths, in service of building a Quartus-faithful LI pair
activation lookup table.

Outputs:
  - distinct (src_type, src_I, dst_N, dst_port) tuples observed
  - distribution of dst_port values
  - distribution of source wire types
  - LAB-level LI step counts per experiment (to find isolation candidates)
"""
import sqlite3
import json
import re
import os
from collections import Counter, defaultdict

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "results", "ep4ce6_bitdb.sqlite")

# Wire types we care about as LI sources
SRC_TYPES = ("R4", "C4", "R24", "C16", "LE_BUFFER", "GEN_CORE_BUF",
             "CLK_BUFFER", "LOCAL_INTERCONNECT", "BLOCK_INPUT_MUX")

WIRE_RE = re.compile(r"^([A-Z_]+?)_X(\d+)_Y(\d+)_N(\d+)_I(\d+)$")
LCCOMB_RE = re.compile(r"^LCCOMB_X(\d+)_Y(\d+)_N(\d+)$")
LUT_PORT_RE = re.compile(r"^lut\d+\|(data[a-d])$", re.IGNORECASE)


def parse_wire(loc):
    m = WIRE_RE.match(loc or "")
    if not m:
        return None
    return {
        "type": m.group(1),
        "x": int(m.group(2)),
        "y": int(m.group(3)),
        "n": int(m.group(4)),
        "i": int(m.group(5)),
    }


def parse_lccomb(loc):
    m = LCCOMB_RE.match(loc or "")
    if not m:
        return None
    return {"x": int(m.group(1)), "y": int(m.group(2)), "n": int(m.group(3))}


def extract_li_records(path):
    """Walk a path step list, return list of LI activation records.

    Each record: dict with src_type, src_i, li_lx, li_ly, li_i, dst_n, dst_port
    """
    records = []
    n = len(path)
    for i in range(n):
        step = path[i]
        loc = step.get("location", "")
        w = parse_wire(loc)
        if not w or w["type"] != "LOCAL_INTERCONNECT":
            continue

        # source = the step immediately before with a wire-shaped location
        src = None
        for j in range(i - 1, -1, -1):
            prev_loc = path[j].get("location", "")
            pw = parse_wire(prev_loc)
            if pw and pw["type"] != "LOCAL_INTERCONNECT":
                src = pw
                break

        # destination = the next LCCOMB step + the IC step right after that
        # carries the lut|port element
        dst_lc = None
        dst_port = None
        for j in range(i + 1, n):
            nxt = path[j]
            lc = parse_lccomb(nxt.get("location", ""))
            if lc:
                dst_lc = lc
                # The IC step pointing into LCCOMB usually IS this very step
                el = nxt.get("element", "")
                pm = LUT_PORT_RE.match(el)
                if pm:
                    dst_port = pm.group(1).lower()
                else:
                    # Look one further for the port info
                    if j + 1 < n:
                        el2 = path[j + 1].get("element", "")
                        pm2 = LUT_PORT_RE.match(el2)
                        if pm2:
                            dst_port = pm2.group(1).lower()
                break

        if not src or not dst_lc:
            continue

        records.append({
            "src_type": src["type"],
            "src_i": src["i"],
            "li_lx": w["x"],
            "li_ly": w["y"],
            "li_i": w["i"],
            "dst_n": dst_lc["n"],
            "dst_port": dst_port,
            # Bonus: keep source coords for later (lx,ly) consistency check
            "src_x": src["x"],
            "src_y": src["y"],
        })
    return records


def main():
    db = sqlite3.connect(DB)
    cur = db.cursor()
    rows = cur.execute(
        "SELECT id, experiment_id, src_x, src_y, src_n, dst_x, dst_y, dst_n, path_json "
        "FROM routing_paths"
    ).fetchall()
    print(f"Loaded {len(rows)} routing_paths rows")

    all_records = []
    li_per_lab_per_exp = defaultdict(lambda: defaultdict(set))  # exp -> (lx,ly) -> set of li_i
    for rid, exp, sx, sy, sn, dx, dy, dn, pj in rows:
        try:
            path = json.loads(pj)
        except Exception:
            continue
        recs = extract_li_records(path)
        for r in recs:
            r["exp_id"] = exp
            r["row_id"] = rid
            all_records.append(r)
            li_per_lab_per_exp[exp][(r["li_lx"], r["li_ly"])].add(
                (r["li_i"], r["dst_n"], r["dst_port"])
            )

    print(f"\nExtracted {len(all_records)} LI records")
    # Distributions
    src_type_ct = Counter(r["src_type"] for r in all_records)
    print(f"\nSource wire types:")
    for t, c in src_type_ct.most_common():
        print(f"  {t:20s} {c}")

    dst_port_ct = Counter(r["dst_port"] for r in all_records)
    print(f"\nDest LUT input ports:")
    for p, c in dst_port_ct.most_common():
        print(f"  {p}: {c}")

    dst_n_ct = Counter(r["dst_n"] for r in all_records)
    print(f"\nDest LE N values: "
          f"{sorted(dst_n_ct.keys())}  ({len(dst_n_ct)} distinct)")

    # Distinct keys (the proposed lookup table key shape)
    keys = set((r["src_type"], r["src_i"], r["dst_n"], r["dst_port"])
               for r in all_records if r["dst_port"] is not None)
    print(f"\nDistinct (src_type, src_I, dst_N, dst_port) keys: {len(keys)}")

    # The same key might map to multiple li_path_I values across different LABs
    # If the LAB-topology-replication hypothesis holds, the SAME key should
    # appear with the SAME li_i regardless of (lx, ly). Verify:
    key_to_li_i = defaultdict(set)
    key_to_labs = defaultdict(set)
    for r in all_records:
        if r["dst_port"] is None:
            continue
        k = (r["src_type"], r["src_i"], r["dst_n"], r["dst_port"])
        key_to_li_i[k].add(r["li_i"])
        key_to_labs[k].add((r["li_lx"], r["li_ly"]))

    multi_li_i_keys = [(k, lis, len(key_to_labs[k]))
                       for k, lis in key_to_li_i.items() if len(lis) > 1]
    print(f"\nKeys observed with >1 distinct li_i value: {len(multi_li_i_keys)}/{len(key_to_li_i)}")
    print("First 10 such collisions:")
    for k, lis, nlabs in multi_li_i_keys[:10]:
        print(f"  {k}: li_i={sorted(lis)}  across {nlabs} LABs")

    # Single-LAB isolation: how many (experiment, LAB) had exactly 1 LI activation?
    # Those are the gold-standard records where CRAM bits = exactly one key's pairs.
    iso_count = 0
    iso_keys = set()
    iso_examples = []
    for exp, labs in li_per_lab_per_exp.items():
        for (lx, ly), recs in labs.items():
            if len(recs) == 1:
                iso_count += 1
                li_i, dst_n, dst_port = next(iter(recs))
                # Find the matching record to get the source
                for r in all_records:
                    if (r["exp_id"] == exp and r["li_lx"] == lx
                            and r["li_ly"] == ly and r["li_i"] == li_i):
                        k = (r["src_type"], r["src_i"], dst_n, dst_port)
                        iso_keys.add(k)
                        if len(iso_examples) < 5:
                            iso_examples.append((exp, lx, ly, k))
                        break
    print(f"\nIsolation candidates (LABs with exactly 1 LI activation in their path):")
    print(f"  total such (exp, LAB) instances: {iso_count}")
    print(f"  distinct keys covered:           {len(iso_keys)}")
    print(f"  examples:")
    for exp, lx, ly, k in iso_examples:
        print(f"    exp={exp} LAB(X{lx},Y{ly}): key={k}")


if __name__ == "__main__":
    main()
