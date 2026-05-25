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


def emit(checker: CheckerNode, template_dir: Path | None = None) -> str:
    """Render a ``CheckerNode`` to a SystemVerilog string via Jinja2.

    Parameters
    ----------
    checker:
        The populated ``CheckerNode`` to render.  ``checker.template_name``
        selects the Jinja2 template file (``<name>.sv.j2``).
    template_dir:
        Override for the templates directory.  ``None`` resolves to the
        project-root ``templates/`` directory relative to this file.

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
    # non-string values (observed_signals) that the template iterates over.
    ctx: dict[str, object] = dict(checker.params)
    ctx["observed_signals"] = checker.observed_signals

    return str(tmpl.render(**ctx))


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
