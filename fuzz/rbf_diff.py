"""Binary diff engine for RBF bitstream comparison."""

from dataclasses import dataclass

from config import RBF_SIZE


@dataclass
class BitDiff:
    """A single bit difference between two RBF files."""
    byte_offset: int
    bit_position: int  # 0=LSB, 7=MSB
    direction: int     # +1 = 0->1 (a->b), -1 = 1->0 (a->b)

    @property
    def abs_bit(self) -> int:
        """Absolute bit position in the file."""
        return self.byte_offset * 8 + self.bit_position

    def __repr__(self):
        d = "0->1" if self.direction > 0 else "1->0"
        return f"BitDiff(0x{self.byte_offset:05X}:{self.bit_position}, {d})"


def diff_rbf(rbf_a: bytes, rbf_b: bytes) -> list[BitDiff]:
    """Compare two RBF files bit-by-bit.

    Args:
        rbf_a: Reference/baseline RBF
        rbf_b: Modified RBF

    Returns:
        List of BitDiff for each differing bit.
    """
    if len(rbf_a) != RBF_SIZE or len(rbf_b) != RBF_SIZE:
        raise ValueError(
            f"RBF size mismatch: {len(rbf_a)} / {len(rbf_b)}, expected {RBF_SIZE}"
        )

    diffs = []
    for i in range(RBF_SIZE):
        xor = rbf_a[i] ^ rbf_b[i]
        if xor:
            for bit in range(8):
                if xor & (1 << bit):
                    direction = 1 if (rbf_b[i] >> bit) & 1 else -1
                    diffs.append(BitDiff(i, bit, direction))
    return diffs


def diff_rbf_files(path_a: str, path_b: str) -> list[BitDiff]:
    """Compare two RBF files from disk."""
    with open(path_a, "rb") as f:
        a = f.read()
    with open(path_b, "rb") as f:
        b = f.read()
    return diff_rbf(a, b)


def diff_summary(diffs: list[BitDiff]) -> dict:
    """Generate summary statistics for a diff."""
    if not diffs:
        return {"total_bits": 0, "set_bits": 0, "clear_bits": 0,
                "byte_range": (0, 0), "regions": []}

    set_bits = sum(1 for d in diffs if d.direction > 0)
    clear_bits = sum(1 for d in diffs if d.direction < 0)
    min_byte = min(d.byte_offset for d in diffs)
    max_byte = max(d.byte_offset for d in diffs)

    # Find contiguous regions
    regions = []
    sorted_offsets = sorted(set(d.byte_offset for d in diffs))
    if sorted_offsets:
        start = sorted_offsets[0]
        end = sorted_offsets[0]
        for off in sorted_offsets[1:]:
            if off <= end + 4:  # gap tolerance of 4 bytes
                end = off
            else:
                regions.append((start, end))
                start = off
                end = off
        regions.append((start, end))

    return {
        "total_bits": len(diffs),
        "set_bits": set_bits,
        "clear_bits": clear_bits,
        "byte_range": (min_byte, max_byte),
        "regions": regions,
    }


def print_diff(diffs: list[BitDiff], max_lines: int = 50):
    """Pretty-print a diff."""
    summary = diff_summary(diffs)
    print(f"Total differing bits: {summary['total_bits']}")
    print(f"  Set (0->1): {summary['set_bits']}")
    print(f"  Clear (1->0): {summary['clear_bits']}")
    print(f"  Byte range: 0x{summary['byte_range'][0]:05X} - 0x{summary['byte_range'][1]:05X}")
    print(f"  Regions: {len(summary['regions'])}")
    for start, end in summary['regions']:
        print(f"    0x{start:05X} - 0x{end:05X} ({end - start + 1} bytes)")
    print()

    for i, d in enumerate(diffs[:max_lines]):
        print(f"  {d}")
    if len(diffs) > max_lines:
        print(f"  ... ({len(diffs) - max_lines} more)")
