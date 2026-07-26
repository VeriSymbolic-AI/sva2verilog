#!/usr/bin/env python3
"""Validate built artifacts and compile one SVA outside the source checkout."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
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

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = [Path(name) for name in archive.getnames()]
    forbidden_roots = {"tests", "tools", ".github", ".planning", ".gsd"}
    leaked = sorted(
        str(path)
        for path in sdist_names
        if len(path.parts) > 1 and path.parts[1] in forbidden_roots
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
