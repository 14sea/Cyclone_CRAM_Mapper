# SPDX-License-Identifier: GPL-3.0-or-later
"""X-Ray-style specimen factory for EP4CE6 mining.

A *specimen* is a fully-frozen Quartus design:

  * Every IOB is pinned by `Harness`.
  * Every LE that must not move is pinned by `Specimen.placement`
    (LCCOMB_X{x}_Y{y}_N{n}).
  * Quartus optimizations are disabled (config.QSF_OPTIMIZATIONS_OFF).
  * SEED is fixed.

Mining campaigns then derive *perturbed* specimens that differ from a
baseline by exactly one axis (one LOC, one Verilog port, one INIT bit).
The XOR-diff between the two RBFs — restricted to CRAM cells via
`diff_cram` — is the per-axis bit set.

Quartus has no exact analog of Vivado's FIXED_ROUTE, so placement
freezing + SEED determinism are not enough on their own — Quartus may
still re-route between builds. `routing_invariance_probe` is the
empirical guard: it builds the same specimen at N different SEEDs and
asserts the CRAM cell set is identical. Any specimen used in a per-site
mining campaign MUST pass this probe; if it fails, shrink the design
or pin more IOBs until it does.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path

from compile import compile_and_export
from config import (
    DEVICE, FAMILY, FUZZ_PINS, PREAMBLE_BYTES, QSF_OPTIMIZATIONS_OFF, RBF_SIZE,
)
from rbf_diff import diff_rbf
from qsf_gen import make_lccomb


FRAME_BYTES = 210
DATA_BYTES_PER_FRAME = 208     # bytes 208,209 = CRC
N_FRAMES = 1752
HEADER_NOISE_FRAMES = 25
CRAM_OFFSET_LO = PREAMBLE_BYTES + HEADER_NOISE_FRAMES * FRAME_BYTES   # 5282
CRAM_OFFSET_HI = PREAMBLE_BYTES + N_FRAMES * FRAME_BYTES              # 367952


@dataclass(frozen=True)
class Harness:
    """Frozen IOB + clock layer shared by every Specimen built from it.

    `iob_pins` is the entire pin layout: {signal_name: "PIN_xx"}. Every
    signal listed here MUST appear as an input or output port in the
    specimen's Verilog. Conversely, the Verilog MUST NOT declare
    additional top-level ports — Quartus would auto-pin them and
    introduce variation between specimens.
    """
    iob_pins: tuple[tuple[str, str], ...]
    clk_signal: str | None = "CLK"
    seed: int = 1
    name: str = "default"
    optimizations_off: tuple[tuple[str, str], ...] = tuple(QSF_OPTIMIZATIONS_OFF)

    @classmethod
    def default(cls, seed: int = 1) -> "Harness":
        """Standard 4-input-1-output-1-clock harness from config.FUZZ_PINS."""
        return cls(
            iob_pins=tuple(FUZZ_PINS.items()),
            clk_signal="CLK",
            seed=seed,
            name="default",
        )

    @classmethod
    def minimal_combinational(cls, seed: int = 1) -> "Harness":
        """Tiny A->Q harness for routing-invariance probing.

        Single input + single output + no clock. Fits the smallest
        possible specimen so the routing-invariance probe has the
        cleanest possible signal.
        """
        return cls(
            iob_pins=(("A", FUZZ_PINS["A"]), ("Q", FUZZ_PINS["Q"])),
            clk_signal=None,
            seed=seed,
            name="minimal_comb",
        )

    def with_seed(self, seed: int) -> "Harness":
        return replace(self, seed=seed)


@dataclass
class Specimen:
    """A fully-frozen design plus its build harness."""
    name: str
    harness: Harness
    verilog: str
    placement: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    extra_pins: dict[str, str] = field(default_factory=dict)
    top_entity: str = "fuzz_top"

    def render_qsf(self) -> str:
        lines = [
            f'set_global_assignment -name FAMILY "{FAMILY}"',
            f'set_global_assignment -name DEVICE {DEVICE}',
            f'set_global_assignment -name TOP_LEVEL_ENTITY {self.top_entity}',
            'set_global_assignment -name VERILOG_FILE fuzz_top.v',
            'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files',
            'set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"',
        ]
        for opt, value in self.harness.optimizations_off:
            if value in ("OFF", "ON"):
                lines.append(f'set_global_assignment -name {opt} {value}')
            else:
                lines.append(f'set_global_assignment -name {opt} "{value}"')
        lines.append(f'set_global_assignment -name SEED {self.harness.seed}')
        for sig, pin in self.harness.iob_pins:
            lines.append(f'set_location_assignment {pin} -to {sig}')
        for sig, pin in self.extra_pins.items():
            lines.append(f'set_location_assignment {pin} -to {sig}')
        if self.harness.clk_signal:
            lines.append(
                f'set_instance_assignment -name GLOBAL_SIGNAL "GLOBAL CLOCK" '
                f'-to {self.harness.clk_signal}'
            )
        for node, (x, y, n) in self.placement.items():
            lines.append(
                f'set_location_assignment {make_lccomb(x, y, n)} -to "{node}"'
            )
        return "\n".join(lines) + "\n"

    def vary(self, **perturbation) -> "Specimen":
        """Return a copy with exactly one field changed.

        Enforced single-axis: pass exactly one keyword. The X-Ray rule
        is that baseline and perturbed differ by one *attribute*; anything
        else admits Quartus refit churn back into the diff.
        """
        if len(perturbation) != 1:
            raise ValueError(
                f"vary() requires exactly one perturbation axis, "
                f"got {sorted(perturbation)}"
            )
        return replace(self, **perturbation)

    def project_name(self) -> str:
        """Stable per-specimen project name; collision-free across seeds."""
        digest = hashlib.sha1(
            f"{self.name}|{self.harness.name}|{self.harness.seed}".encode()
        ).hexdigest()[:10]
        return f"spec_{self.name}_{digest}"

    def build(self, work_dir: str | Path) -> Path:
        """Compile through Quartus; return path to the produced RBF."""
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)
        proj = self.project_name()
        rbf_out = str(work_dir / f"{proj}.rbf")
        rbf_path, _elapsed, err = compile_and_export(
            project_name=proj,
            verilog_content=self.verilog,
            qsf_content=self.render_qsf(),
            rbf_output=rbf_out,
            full_flow=True,
            work_dir=str(work_dir),
        )
        if rbf_path is None:
            raise RuntimeError(
                f"Specimen build failed for {self.name!r}: {err}"
            )
        return Path(rbf_path)


def _is_cram_offset(off: int) -> bool:
    if off < CRAM_OFFSET_LO or off >= CRAM_OFFSET_HI:
        return False
    return ((off - PREAMBLE_BYTES) % FRAME_BYTES) < DATA_BYTES_PER_FRAME


def diff_cram(rbf_a: bytes, rbf_b: bytes) -> set[tuple[int, int]]:
    """XOR-diff two RBFs, restricted to CRAM cells.

    Returns a set of (byte_offset, bit_position) pairs. Filters out:
      * preamble (bytes 0..31)
      * header-noise frames 0..24 (4-5 bit/seed noise floor — see
        feedback_header_band_noise_floor)
      * postamble (bytes >= 32 + 1752*210)
      * per-frame CRC bytes 208,209
    """
    if len(rbf_a) != RBF_SIZE or len(rbf_b) != RBF_SIZE:
        raise ValueError(
            f"RBF size mismatch: {len(rbf_a)} / {len(rbf_b)}, expected {RBF_SIZE}"
        )
    cells: set[tuple[int, int]] = set()
    for d in diff_rbf(rbf_a, rbf_b):
        if _is_cram_offset(d.byte_offset):
            cells.add((d.byte_offset, d.bit_position))
    return cells


def diff_cram_files(path_a: str | Path, path_b: str | Path) -> set[tuple[int, int]]:
    return diff_cram(Path(path_a).read_bytes(), Path(path_b).read_bytes())


def routing_invariance_probe(
    spec: Specimen,
    work_dir: str | Path,
    *,
    n_seeds: int = 3,
    seeds: tuple[int, ...] | None = None,
) -> tuple[bool, set[tuple[int, int]]]:
    """Build the same specimen at N seeds; report whether CRAM is invariant.

    Returns (is_invariant, drift_cells). `drift_cells` is the union of
    every CRAM cell that differs between any pair of builds. An empty
    set means Quartus produced byte-identical CRAM regardless of SEED;
    a non-empty set means the harness is too loose to be used for
    per-site mining.
    """
    if seeds is None:
        seeds = tuple(range(1, n_seeds + 1))
    work_dir = Path(work_dir)
    builds: list[bytes] = []
    for s in seeds:
        s_spec = replace(spec, harness=spec.harness.with_seed(s))
        rbf = s_spec.build(work_dir)
        builds.append(rbf.read_bytes())
    drift: set[tuple[int, int]] = set()
    base = builds[0]
    for other in builds[1:]:
        drift |= diff_cram(base, other)
    return (not drift), drift


_LUT_PRIMITIVE_TMPL = """\
module {top}(
    input  wire A,
    output wire Q
);
    wire lut_out;
    cycloneive_lcell_comb #(
        .lut_mask(16'h{mask:04X}),
        .sum_lutc_input("datac"),
        .dont_touch("on")
    ) lut_inst (
        .dataa(A),
        .datab(1'b0),
        .datac(1'b0),
        .datad(1'b0),
        .combout(lut_out)
    );
    assign Q = lut_out;
endmodule
"""


def make_minimal_1le_specimen(
    target_le: tuple[int, int, int],
    *,
    lut_mask: int = 0xAAAA,
    name: str = "min_1le",
    harness: Harness | None = None,
) -> Specimen:
    """Smallest possible specimen: one LUT primitive at `target_le`.

    Used by `routing_invariance_probe` as the canonical "this should
    always be invariant" probe. If even this drifts under SEED change,
    something is structurally wrong with the harness or device.
    """
    h = harness if harness is not None else Harness.minimal_combinational()
    verilog = _LUT_PRIMITIVE_TMPL.format(top="fuzz_top", mask=lut_mask)
    return Specimen(
        name=name,
        harness=h,
        verilog=verilog,
        placement={"lut_inst": target_le},
    )
