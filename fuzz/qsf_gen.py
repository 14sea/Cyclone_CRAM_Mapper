"""Generate QSF (Quartus Settings File) for fuzzing experiments."""

from config import (
    FAMILY, DEVICE, FUZZ_PINS, QSF_OPTIMIZATIONS_OFF,
)


def gen_qsf(
    verilog_file: str = "fuzz_top.v",
    top_entity: str = "fuzz_top",
    placement: dict | None = None,
    extra_pins: dict | None = None,
    seed: int = 1,
) -> str:
    """Generate a complete QSF file.

    Args:
        verilog_file: Path to the Verilog source file
        top_entity: Top-level entity name
        placement: Dict of {node_name: "LCCOMB_X{x}_Y{y}_N{n}"} for forced placement
        extra_pins: Additional pin assignments {signal: "PIN_XX"}
        seed: Fitter random seed for deterministic routing
    """
    lines = []

    # Device settings
    lines.append(f'set_global_assignment -name FAMILY "{FAMILY}"')
    lines.append(f'set_global_assignment -name DEVICE {DEVICE}')
    lines.append(f'set_global_assignment -name TOP_LEVEL_ENTITY {top_entity}')
    lines.append(f'set_global_assignment -name VERILOG_FILE {verilog_file}')
    lines.append('set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output_files')
    lines.append('')

    # Standard settings
    lines.append('set_global_assignment -name MIN_CORE_JUNCTION_TEMP 0')
    lines.append('set_global_assignment -name MAX_CORE_JUNCTION_TEMP 85')
    lines.append('set_global_assignment -name ERROR_CHECK_FREQUENCY_DIVISOR 1')
    lines.append('set_global_assignment -name STRATIX_DEVICE_IO_STANDARD "3.3-V LVTTL"')
    lines.append('')

    # Disable all optimizations
    lines.append('# Disable optimizations for deterministic fuzzing')
    for name, value in QSF_OPTIMIZATIONS_OFF:
        if value in ('OFF', 'ON'):
            lines.append(f'set_global_assignment -name {name} {value}')
        else:
            lines.append(f'set_global_assignment -name {name} "{value}"')
    lines.append('')

    # Fitter seed for deterministic routing
    lines.append(f'set_global_assignment -name SEED {seed}')
    lines.append('')

    # Pin assignments
    lines.append('# Pin assignments')
    for signal, pin in FUZZ_PINS.items():
        lines.append(f'set_location_assignment {pin} -to {signal}')
    if extra_pins:
        for signal, pin in extra_pins.items():
            lines.append(f'set_location_assignment {pin} -to {signal}')
    lines.append('')

    # Placement constraints
    if placement:
        lines.append('# Forced LE placement')
        for node_name, location in placement.items():
            lines.append(f'set_location_assignment {location} -to "{node_name}"')
        lines.append('')

    return '\n'.join(lines) + '\n'


def make_lccomb(x: int, y: int, n: int) -> str:
    """Format a LCCOMB placement string."""
    return f"LCCOMB_X{x}_Y{y}_N{n}"


def make_lcff(x: int, y: int, n: int) -> str:
    """Format a LCFF placement string."""
    return f"LCFF_X{x}_Y{y}_N{n}"
