# SPDX-License-Identifier: GPL-3.0-or-later
"""Drive Quartus headless compilation for fuzzing."""

import os
import subprocess
import shutil
import time
from pathlib import Path

from config import QUARTUS_BIN, WORK_DIR


def _quartus_cmd(tool: str) -> str:
    return os.path.join(QUARTUS_BIN, tool)


def setup_project(
    project_name: str,
    verilog_content: str,
    qsf_content: str,
    work_dir: str | None = None,
) -> str:
    """Set up a Quartus project directory.

    Returns the project directory path.
    """
    work = work_dir or WORK_DIR
    proj_dir = os.path.join(work, project_name)
    os.makedirs(proj_dir, exist_ok=True)

    # Write Verilog source
    with open(os.path.join(proj_dir, "fuzz_top.v"), "w") as f:
        f.write(verilog_content)

    # Write QSF
    with open(os.path.join(proj_dir, f"{project_name}.qsf"), "w") as f:
        f.write(qsf_content)

    # Write QPF (minimal project file)
    with open(os.path.join(proj_dir, f"{project_name}.qpf"), "w") as f:
        f.write(f'PROJECT_REVISION = "{project_name}"\n')

    return proj_dir


def run_quartus(
    tool: str,
    project_name: str,
    proj_dir: str,
    extra_args: list[str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """Run a Quartus tool headlessly.

    Args:
        tool: Tool name (e.g. 'quartus_map')
        project_name: Quartus project/revision name
        proj_dir: Project directory
        extra_args: Additional command-line arguments
        timeout: Timeout in seconds
    """
    cmd = [
        _quartus_cmd(tool),
        "--read_settings_files=on",
        "--write_settings_files=off",
        project_name,
        "-c", project_name,
    ]
    if extra_args:
        cmd.extend(extra_args)

    result = subprocess.run(
        cmd,
        cwd=proj_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result


def compile_full(
    project_name: str,
    proj_dir: str,
    timeout: int = 120,
) -> tuple[bool, float, str]:
    """Run full Quartus flow: map -> fit -> asm.

    Returns (success, elapsed_seconds, error_message).
    """
    t0 = time.time()

    for tool in ["quartus_map", "quartus_fit", "quartus_asm"]:
        result = run_quartus(tool, project_name, proj_dir, timeout=timeout)
        if result.returncode != 0:
            elapsed = time.time() - t0
            # Extract error lines
            errors = [l for l in result.stdout.split('\n') if 'Error' in l]
            err_msg = f"{tool} failed: {'; '.join(errors[:5])}"
            return False, elapsed, err_msg

    elapsed = time.time() - t0
    return True, elapsed, ""


def compile_fit_only(
    project_name: str,
    proj_dir: str,
    timeout: int = 120,
) -> tuple[bool, float, str]:
    """Run fit -> asm only (skip map when Verilog unchanged).

    Returns (success, elapsed_seconds, error_message).
    """
    t0 = time.time()

    for tool in ["quartus_fit", "quartus_asm"]:
        result = run_quartus(tool, project_name, proj_dir, timeout=timeout)
        if result.returncode != 0:
            elapsed = time.time() - t0
            errors = [l for l in result.stdout.split('\n') if 'Error' in l]
            err_msg = f"{tool} failed: {'; '.join(errors[:5])}"
            return False, elapsed, err_msg

    elapsed = time.time() - t0
    return True, elapsed, ""


def generate_rbf(
    project_name: str,
    proj_dir: str,
    output_path: str | None = None,
) -> str | None:
    """Convert .sof to uncompressed .rbf.

    Returns the path to the .rbf file, or None on failure.
    """
    sof_path = os.path.join(proj_dir, "output_files", f"{project_name}.sof")
    if not os.path.exists(sof_path):
        return None

    rbf_path = output_path or os.path.join(proj_dir, f"{project_name}.rbf")

    result = subprocess.run(
        [
            _quartus_cmd("quartus_cpf"),
            "-c",
            "-o", "bitstream_compression=off",
            sof_path,
            rbf_path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode == 0 and os.path.exists(rbf_path):
        return rbf_path
    return None


def compile_and_export(
    project_name: str,
    verilog_content: str,
    qsf_content: str,
    rbf_output: str | None = None,
    full_flow: bool = True,
    work_dir: str | None = None,
) -> tuple[str | None, float, str]:
    """One-shot: setup project, compile, export RBF.

    Returns (rbf_path, elapsed_seconds, error_message).
    """
    proj_dir = setup_project(project_name, verilog_content, qsf_content, work_dir)

    if full_flow:
        ok, elapsed, err = compile_full(project_name, proj_dir)
    else:
        ok, elapsed, err = compile_fit_only(project_name, proj_dir)

    if not ok:
        return None, elapsed, err

    rbf = generate_rbf(project_name, proj_dir, rbf_output)
    if rbf is None:
        return None, elapsed, "RBF generation failed"

    return rbf, elapsed, ""


def extract_routing(project_name: str, proj_dir: str,
                     timeout: int = 60) -> list[dict]:
    """Extract routing path segments from a fitted design via STA.

    Returns list of dicts with keys: src, dst, segments.
    Each segment has: element_type, location, delay_incr.
    """
    tcl = f'''project_open {project_name}
load_package sta
create_timing_netlist
create_clock -name vclk -period 100
set_input_delay -clock vclk 0 [get_ports {{A B C D E F G}}]
set_output_delay -clock vclk 0 [get_ports Q]
report_timing -from {{A}} -to {{Q}} -detail full_path -show_routing -npaths 1 -file _route_out.txt
delete_timing_netlist
project_close
'''
    tcl_path = os.path.join(proj_dir, "_extract_route.tcl")
    with open(tcl_path, "w") as f:
        f.write(tcl)

    result = subprocess.run(
        [_quartus_cmd("quartus_sta"), "-t", "_extract_route.tcl"],
        cwd=proj_dir, capture_output=True, text=True, timeout=timeout,
    )

    route_file = os.path.join(proj_dir, "_route_out.txt")
    if not os.path.exists(route_file):
        return []

    return _parse_route_file(route_file)


def _parse_route_file(path: str) -> list[dict]:
    """Parse a report_timing -show_routing output file.

    Returns list of routing segments in the data arrival path:
    [{type, location, element, delay_incr}, ...]
    """
    import re
    segments = []
    in_data = False

    with open(path, "r", errors="replace") as f:
        for line in f:
            line = line.rstrip()
            # Detect data arrival path table
            if "Data Arrival Path" in line:
                in_data = True
                continue
            if in_data and "Data Required Path" in line:
                break
            if not in_data:
                continue

            # Parse table rows: ; total ; incr ; RF ; Type ; Fanout ; Location ; Element ;
            m = re.match(
                r';\s*([\d.\-]+)\s*;\s*([\d.\-]+)\s*;\s*(\S*)\s*;\s*(\S*)\s*;\s*(\d*)\s*;\s*(\S*)\s*;\s*(.*?)\s*;',
                line
            )
            if m:
                seg = {
                    "total_ns": float(m.group(1)),
                    "incr_ns": float(m.group(2)),
                    "rf": m.group(3),
                    "type": m.group(4),
                    "fanout": m.group(5),
                    "location": m.group(6),
                    "element": m.group(7).strip(),
                }
                segments.append(seg)

    return segments


def clean_work_dir(work_dir: str | None = None):
    """Remove the work directory to save disk space."""
    work = work_dir or WORK_DIR
    if os.path.exists(work):
        shutil.rmtree(work)
