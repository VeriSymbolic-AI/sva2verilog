#!/usr/bin/env python3
"""Validate built artifacts and compile one SVA outside the source checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

APACHE_2_LICENSE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"


def _run(
    command: list[str],
    *,
    cwd: Path,
    expected_returncodes: frozenset[int] = frozenset({0}),
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in expected_returncodes:
        rendered = " ".join(command)
        raise RuntimeError(
            f"command failed ({result.returncode}): {rendered}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def inspect_artifacts(wheel: Path, sdist: Path) -> None:
    """Check template inclusion and reject development-only sdist payloads."""

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    required_wheel_members = {
        "sva2rtl/__init__.py",
        "sva2rtl/emitter.py",
        "sva2rtl/templates/bool_expr.sv.j2",
        "sva2rtl/templates/_macros.sv.j2",
    }
    missing = sorted(required_wheel_members - wheel_names)
    if missing:
        raise RuntimeError(f"wheel is missing required members: {missing}")

    metadata_members = [name for name in wheel_names if name.endswith(".dist-info/METADATA")]
    license_members = [name for name in wheel_names if name.endswith(".dist-info/licenses/LICENSE")]
    if len(metadata_members) != 1 or len(license_members) != 1:
        raise RuntimeError("wheel must contain one METADATA file and one licensed LICENSE file")
    with zipfile.ZipFile(wheel) as archive:
        metadata = archive.read(metadata_members[0]).decode("utf-8")
        wheel_license = archive.read(license_members[0])
    if "License-Expression: Apache-2.0" not in metadata:
        raise RuntimeError("wheel metadata does not declare Apache-2.0")
    if hashlib.sha256(wheel_license).hexdigest() != APACHE_2_LICENSE_SHA256:
        raise RuntimeError("wheel LICENSE does not match the official Apache-2.0 text")

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = [Path(name) for name in archive.getnames()]
        required_docs = {
            "LICENSE",
            "README.md",
            "FORMAL_VERIFICATION.md",
            "SUPPORTED_CONSTRUCTS.md",
            "SUPPORT_MATRIX.md",
        }
        present_docs = {path.name for path in sdist_names}
        missing_docs = sorted(required_docs - present_docs)
        if missing_docs:
            raise RuntimeError(f"sdist is missing public license/support docs: {missing_docs}")
        license_member = next(path for path in sdist_names if path.name == "LICENSE")
        extracted_license = archive.extractfile(license_member.as_posix())
        if extracted_license is None:
            raise RuntimeError("sdist LICENSE could not be read")
        if hashlib.sha256(extracted_license.read()).hexdigest() != APACHE_2_LICENSE_SHA256:
            raise RuntimeError("sdist LICENSE does not match the official Apache-2.0 text")
    forbidden_roots = {"tests", ".github", ".planning", ".gsd"}
    leaked = sorted(
        str(path)
        for path in sdist_names
        if len(path.parts) > 1
        and (
            path.parts[1] in forbidden_roots
            or (
                path.parts[1] == "tools"
                and (len(path.parts) < 3 or path.parts[2] != "formal")
            )
        )
    )
    if leaked:
        raise RuntimeError(f"sdist includes development-only paths: {leaked[:10]}")


def smoke_installed_wheel(wheel: Path) -> None:
    """Install the wheel into a fresh venv and invoke it from a temporary cwd."""

    slang = shutil.which("slang")
    iverilog = shutil.which("iverilog")
    if slang is None or iverilog is None:
        raise RuntimeError("slang and iverilog are required for distribution smoke")

    with tempfile.TemporaryDirectory(prefix="sva2rtl-dist-smoke-") as temp:
        work = Path(temp)
        venv = work / "venv"
        _run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=work)
        python = venv / "bin" / "python"
        cli = venv / "bin" / "sva2rtl"
        formal_cli = venv / "bin" / "sva2rtl-formal"
        _run(
            ["uv", "pip", "install", "--python", str(python), str(wheel.resolve())],
            cwd=work,
        )

        source = work / "smoke.sv"
        output = work / "monitor.sv"
        source.write_text(
            "module smoke(input logic clk, rst_n, a);\n"
            "  p_smoke: assert property (@(posedge clk) a);\n"
            "endmodule\n",
            encoding="utf-8",
        )
        _run(
            [
                str(cli),
                str(source),
                "--slang-path",
                slang,
                "--output",
                str(output),
            ],
            cwd=work,
        )
        generated = output.read_text(encoding="utf-8")
        if "module sva_p_smoke" not in generated or "attempt_fired" not in generated:
            raise RuntimeError("installed CLI generated an incomplete checker")
        _run([iverilog, "-g2012", "-tnull", str(output)], cwd=work)

        formal_help = _run([str(formal_cli), "--help"], cwd=work).stdout
        if "--logic-semantics" not in formal_help or "--property-file" not in formal_help:
            raise RuntimeError("installed formal CLI is missing required semantic inputs")
        dut = work / "dut.sv"
        prop = work / "property.sv"
        evidence = work / "formal-evidence"
        dut.write_text(
            "module smoke_formal(input logic clk, rst_n, a, output logic ack);\n"
            "  assign ack = a;\n"
            "endmodule\n",
            encoding="utf-8",
        )
        prop.write_text(
            "module smoke_spec(input logic clk, rst_n, a, ack);\n"
            "  p: assert property (@(posedge clk) (!a) || ack);\n"
            "endmodule\n",
            encoding="utf-8",
        )
        _run(
            [
                str(formal_cli),
                "--dut",
                str(dut),
                "--property-file",
                str(prop),
                "--property",
                "p",
                "--top",
                "smoke_formal",
                "--slang-path",
                slang,
                "--output",
                str(evidence),
                "--compile-only",
            ],
            cwd=work,
            expected_returncodes=frozenset({11}),
        )
        result_payload = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
        if result_payload["status"] != "UNKNOWN":
            raise RuntimeError("installed formal compile-only command hid UNKNOWN status")
        manifest = json.loads((evidence / "manifest.json").read_text(encoding="utf-8"))
        if manifest["config"]["logic_semantics"] != "two-state":
            raise RuntimeError("installed formal CLI omitted the semantic profile")
        if "evidence/property.sv" in manifest["yosys_inputs"]:
            raise RuntimeError("installed formal CLI leaked original SVA into Yosys inputs")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args(argv)

    inspect_artifacts(args.wheel, args.sdist)
    smoke_installed_wheel(args.wheel)
    print(f"distribution smoke passed: {args.wheel.name}, {args.sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
