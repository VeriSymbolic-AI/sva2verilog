"""Emitter: renders a CheckerNode to SystemVerilog text via Jinja2.

Design decisions:
- ``FileSystemLoader`` is used (not ``PackageLoader``) so that templates live in
  the project-root ``templates/`` directory and are easily editable by RTL
  engineers without touching Python code.
- ``trim_blocks=True, lstrip_blocks=True`` ensure that Jinja2 block tags
  (``{% for %}``, ``{% endfor %}``, etc.) do not produce extra blank lines in
  the rendered SV.
- ``keep_trailing_newline=True`` ensures the rendered file ends with exactly one
  newline, which is required by most SV tools.
- ``_get_template_dir()`` resolves the templates directory relative to this
  source file using the ``src/`` layout convention, so it works in both editable
  installs and direct ``python -m`` invocations.
- ``emit_all()`` recursively renders all sub-modules for hierarchical checkers
  (Phase 2+) and returns a ``{module_name: sv_text}`` dict.
"""

from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from sva2rtl.ir import CheckerNode

# ── Template directory resolution ─────────────────────────────────────────


def _get_template_dir() -> Path:
    """Locate the ``templates/`` directory relative to this source file.

    Development / editable-install layout::

        <repo_root>/
            src/
                sva2rtl/
                    emitter.py   ← this file  (parent = src/sva2rtl/)
            templates/           ← target     (parent.parent.parent / "templates")

    Returns the resolved path, whether or not it exists (caller must validate
    before constructing the Jinja2 environment).
    """
    candidate = Path(__file__).parent.parent.parent / "templates"
    if candidate.is_dir():
        return candidate
    # Fallback: templates installed alongside the package as package data.
    return Path(__file__).parent / "templates"


def _make_env(template_dir: Path | None = None) -> Environment:
    """Create a Jinja2 ``Environment`` configured for SV template rendering.

    Parameters
    ----------
    template_dir:
        Override the templates directory.  ``None`` delegates to
        ``_get_template_dir()``.
    """
    td = template_dir if template_dir is not None else _get_template_dir()
    return Environment(
        loader=FileSystemLoader(str(td)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        # Disable auto-escaping: SV is not HTML; escaping would corrupt identifiers.
        autoescape=False,
    )


# ── Public API ────────────────────────────────────────────────────────────


def emit(
    checker: CheckerNode,
    template_dir: Path | None = None,
    *,
    verilog_mode: bool = False,
) -> str:
    """Render a ``CheckerNode`` to a SystemVerilog string via Jinja2.

    Parameters
    ----------
    checker:
        The populated ``CheckerNode`` to render.  ``checker.template_name``
        selects the Jinja2 template file (``<name>.sv.j2``).
    template_dir:
        Override for the templates directory.  ``None`` resolves to the
        project-root ``templates/`` directory relative to this file.
    verilog_mode:
        When ``True``, templates emit Verilog-2001 compatible output
        (no ``logic``, ``always_ff``, or ``'0`` literals).

    Returns
    -------
    str
        Full SystemVerilog source text for the generated monitor module,
        ending with a newline character.
    """
    env = _make_env(template_dir)
    template_file = checker.template_name + ".sv.j2"
    tmpl = env.get_template(template_file)

    # Build render context: start from the string params dict, then add
    # non-string values (observed_signals, children) that the template iterates.
    ctx: dict[str, object] = dict(checker.params)
    ctx["observed_signals"] = checker.observed_signals
    ctx["children"] = checker.children
    ctx["verilog_mode"] = verilog_mode

    return str(tmpl.render(**ctx))


def emit_all(
    checker: CheckerNode,
    template_dir: Path | None = None,
    *,
    verilog_mode: bool = False,
) -> dict[str, str]:
    """Render a hierarchical ``CheckerNode`` tree into one SV string per module.

    Recursively visits all descendant sub-modules depth-first, rendering each
    unique module exactly once.  Returns a mapping of ``module_name → sv_text``
    in dependency order (children before parents).

    Parameters
    ----------
    checker:
        The root ``CheckerNode`` to render (typically the top-level wrapper).
    template_dir:
        Override for the templates directory.  ``None`` uses the default.
    verilog_mode:
        When ``True``, templates emit Verilog-2001 compatible output
        (no ``logic``, ``always_ff``, or ``'0`` literals).

    Returns
    -------
    dict[str, str]
        Ordered mapping of ``{module_name: sv_text}`` for every unique module
        in the hierarchy.  The top-level checker is last.
    """
    env = _make_env(template_dir)
    results: dict[str, str] = {}
    _emit_recursive(checker, env, results, verilog_mode=verilog_mode)

    # Auto-include transitive dependencies: if any sync_2dff module is emitted,
    # the lfsr_8bit library module MUST also be emitted (sync_2dff instantiates
    # it when META_ENABLE=1; iverilog needs the module definition present).
    _ensure_deps(checker, env, results, verilog_mode=verilog_mode)

    return results


def _ensure_deps(
    checker: CheckerNode,
    env: Environment,
    results: dict[str, str],
    *,
    verilog_mode: bool = False,
) -> None:
    """Ensure transitive library modules are present in *results*.

    Currently the only dependency is ``lfsr_8bit``, required by ``sync_2dff``.
    """
    _ensure_lfsr_8bit(checker, env, results, verilog_mode=verilog_mode)


def _ensure_lfsr_8bit(
    checker: CheckerNode,
    env: Environment,
    results: dict[str, str],
    *,
    verilog_mode: bool = False,
) -> None:
    """If any ``sync_2dff`` module is emitted, emit ``lfsr_8bit`` as well."""
    def _has_sync(node: CheckerNode) -> bool:
        if node.template_name == "sync_2dff":
            return True
        for child in node.children:
            if _has_sync(child):
                return True
        return False

    if _has_sync(checker) and "lfsr_8bit" not in results:
        ctx: dict[str, object] = {
            "module_name": "lfsr_8bit",
            "verilog_mode": verilog_mode,
        }
        results["lfsr_8bit"] = env.get_template("lfsr_8bit.sv.j2").render(**ctx)


def _emit_recursive(
    checker: CheckerNode,
    env: Environment,
    results: dict[str, str],
    *,
    verilog_mode: bool = False,
) -> None:
    """Depth-first recursive renderer; populates *results* in-place."""
    for child in checker.children:
        if child.module_name not in results:
            _emit_recursive(child, env, results, verilog_mode=verilog_mode)

    if checker.module_name not in results:
        template_file = checker.template_name + ".sv.j2"
        tmpl = env.get_template(template_file)
        ctx: dict[str, object] = dict(checker.params)
        ctx["observed_signals"] = checker.observed_signals
        ctx["children"] = checker.children
        ctx["verilog_mode"] = verilog_mode
        results[checker.module_name] = str(tmpl.render(**ctx))


def write_output(sv_text: str, output_path: Path | None) -> None:
    """Write SystemVerilog text to a file or stdout.

    Parameters
    ----------
    sv_text:
        The rendered SystemVerilog text to write.
    output_path:
        If ``None``, write to stdout.  Otherwise write to this path, creating
        parent directories as needed.  The file is written with UTF-8 encoding
        and no BOM.
    """
    if output_path is None:
        sys.stdout.write(sv_text)
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sv_text, encoding="utf-8")


def write_output_dir(modules: dict[str, str], output_dir: Path) -> None:
    """Write each module SV text to ``<output_dir>/<module_name>.sv``.

    Parameters
    ----------
    modules:
        Mapping of ``{module_name: sv_text}`` as returned by ``emit_all()``.
    output_dir:
        Target directory.  Created (with parents) if it does not yet exist.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    for module_name, sv_text in modules.items():
        out_file = output_dir / f"{module_name}.sv"
        out_file.write_text(sv_text, encoding="utf-8")


def emit_bind(
    checker: CheckerNode,
    dut_module: str,
    template_dir: Path | None = None,
    *,
    verilog_mode: bool = False,
) -> str:
    """Render a SystemVerilog ``bind`` statement for a generated monitor module.

    The bind statement wires the monitor's ports to the DUT's signals using
    ``bind <dut_module> <monitor_module> u_<monitor_module> (...)`` syntax,
    making the DUT's internal signals directly visible to the monitor without
    modifying the DUT source.

    Parameters
    ----------
    checker:
        The root ``CheckerNode`` of the compiled property (as returned by
        ``compose()``).  ``checker.module_name`` and ``checker.observed_signals``
        are used to generate the port connection list.
    dut_module:
        Name of the DUT module to bind into, e.g. ``"my_cpu_core"``.
    template_dir:
        Override for the templates directory.  ``None`` uses the project-root
        ``templates/`` directory.
    verilog_mode:
        Accepted for API consistency; bind template does not vary between
        SystemVerilog and Verilog-2001.

    Returns
    -------
    str
        SystemVerilog bind statement text, ending with a newline.
    """
    env = _make_env(template_dir)
    tmpl = env.get_template("bind.sv.j2")

    ctx: dict[str, object] = dict(checker.params)
    ctx["observed_signals"] = checker.observed_signals
    ctx["dut_module"] = dut_module
    ctx["verilog_mode"] = verilog_mode

    return str(tmpl.render(**ctx))
