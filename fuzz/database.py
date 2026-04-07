# SPDX-License-Identifier: GPL-3.0-or-later
"""SQLite database for storing bitstream bit mappings."""

import sqlite3
import os
import json

from config import DB_PATH
from rbf_diff import BitDiff


def get_db(db_path: str | None = None) -> sqlite3.Connection:
    """Open or create the bit mapping database."""
    path = db_path or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    _init_tables(conn)
    return conn


def _init_tables(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            verilog TEXT,
            qsf_placement TEXT,
            compile_time REAL,
            rbf_path TEXT
        );

        CREATE TABLE IF NOT EXISTS bit_mapping (
            x INTEGER NOT NULL,
            y INTEGER NOT NULL,
            n INTEGER NOT NULL,
            feature TEXT NOT NULL,
            byte_offset INTEGER NOT NULL,
            bit_position INTEGER NOT NULL,
            direction INTEGER NOT NULL DEFAULT 1,
            experiment_id INTEGER REFERENCES experiments(id),
            PRIMARY KEY (x, y, n, feature, byte_offset, bit_position)
        );

        CREATE INDEX IF NOT EXISTS idx_bit_mapping_location
            ON bit_mapping(x, y, n);

        CREATE INDEX IF NOT EXISTS idx_bit_mapping_offset
            ON bit_mapping(byte_offset, bit_position);

        CREATE INDEX IF NOT EXISTS idx_bit_mapping_feature
            ON bit_mapping(feature);

        CREATE TABLE IF NOT EXISTS rbf_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            path TEXT NOT NULL,
            description TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS routing_paths (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER REFERENCES experiments(id),
            src_x INTEGER, src_y INTEGER, src_n INTEGER,
            dst_x INTEGER, dst_y INTEGER, dst_n INTEGER,
            path_json TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_routing_src
            ON routing_paths(src_x, src_y, src_n);
        CREATE INDEX IF NOT EXISTS idx_routing_dst
            ON routing_paths(dst_x, dst_y, dst_n);
    """)
    conn.commit()


def register_rbf(conn: sqlite3.Connection, name: str, path: str, description: str = ""):
    """Register an RBF file in the registry."""
    conn.execute(
        "INSERT OR REPLACE INTO rbf_registry (name, path, description) VALUES (?, ?, ?)",
        (name, path, description),
    )
    conn.commit()


def log_experiment(
    conn: sqlite3.Connection,
    name: str,
    description: str = "",
    verilog: str = "",
    qsf_placement: str = "",
    compile_time: float = 0,
    rbf_path: str = "",
) -> int:
    """Log a fuzzing experiment. Returns the experiment ID."""
    cur = conn.execute(
        """INSERT INTO experiments (name, description, verilog, qsf_placement, compile_time, rbf_path)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (name, description, verilog, qsf_placement, compile_time, rbf_path),
    )
    conn.commit()
    return cur.lastrowid


def store_bit_diffs(
    conn: sqlite3.Connection,
    x: int, y: int, n: int,
    feature: str,
    diffs: list[BitDiff],
    experiment_id: int | None = None,
):
    """Store bit differences for a specific feature at a specific LE location."""
    conn.executemany(
        """INSERT OR IGNORE INTO bit_mapping
           (x, y, n, feature, byte_offset, bit_position, direction, experiment_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        [(x, y, n, feature, d.byte_offset, d.bit_position, d.direction, experiment_id)
         for d in diffs],
    )
    conn.commit()


def get_feature_bits(
    conn: sqlite3.Connection,
    x: int, y: int, n: int,
    feature: str,
) -> list[tuple[int, int, int]]:
    """Get all bits for a feature at a location.

    Returns list of (byte_offset, bit_position, direction).
    """
    rows = conn.execute(
        """SELECT byte_offset, bit_position, direction FROM bit_mapping
           WHERE x=? AND y=? AND n=? AND feature=?
           ORDER BY byte_offset, bit_position""",
        (x, y, n, feature),
    ).fetchall()
    return rows


def get_le_features(
    conn: sqlite3.Connection,
    x: int, y: int, n: int,
) -> dict[str, list[tuple[int, int]]]:
    """Get all features and their bits for a specific LE."""
    rows = conn.execute(
        """SELECT feature, byte_offset, bit_position FROM bit_mapping
           WHERE x=? AND y=? AND n=?
           ORDER BY feature, byte_offset, bit_position""",
        (x, y, n),
    ).fetchall()
    result = {}
    for feature, byte_off, bit_pos in rows:
        result.setdefault(feature, []).append((byte_off, bit_pos))
    return result


def get_all_locations(conn: sqlite3.Connection) -> list[tuple[int, int, int]]:
    """Get all (x, y, n) locations that have mappings."""
    return conn.execute(
        "SELECT DISTINCT x, y, n FROM bit_mapping ORDER BY x, y, n"
    ).fetchall()


def store_routing_path(
    conn: sqlite3.Connection,
    experiment_id: int,
    src: tuple[int, int, int],
    dst: tuple[int, int, int],
    segments: list[dict],
):
    """Store a routing path (list of wire segments) for a route."""
    conn.execute(
        """INSERT INTO routing_paths
           (experiment_id, src_x, src_y, src_n, dst_x, dst_y, dst_n, path_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (experiment_id, *src, *dst, json.dumps(segments)),
    )
    conn.commit()


def export_json(conn: sqlite3.Connection, output_path: str):
    """Export the full database to JSON."""
    data = {}
    for x, y, n in get_all_locations(conn):
        key = f"{x}_{y}_{n}"
        data[key] = get_le_features(conn, x, y, n)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
