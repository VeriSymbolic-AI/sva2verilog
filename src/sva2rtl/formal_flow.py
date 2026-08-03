"""User-DUT open formal verification workflow.

This module deliberately keeps two compiler boundaries separate:

* slang parses the original SVA property for sva2rtl;
* Yosys/SymbiYosys receive only the DUT and generated formal RTL.

The separation is the key workaround for open Yosys frontends that cannot parse
advanced concurrent SVA.  Result classification is fail-closed: a bounded BMC
run with no counterexample is ``UNKNOWN`` and only a successful unbounded
``prove`` run is ``PROVEN``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from sva2rtl import ir as sva_ir
from sva2rtl.ast_importer import import_all_assertions
from sva2rtl.composer import compose
from sva2rtl.emitter import (
    emit_all,
    observed_signal_signedness,
    observed_signal_widths,
)
from sva2rtl.errors import PropertyNotFound, SvaCompileError, UnsupportedConstruct
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_TOOL_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_PASS_RE = re.compile(r"(?:DONE\s*\(PASS|STATUS:\s*PASS(?:ED)?)", re.IGNORECASE)
_FAIL_RE = re.compile(
    r"(?:DONE\s*\(FAIL|STATUS:\s*FAIL(?:ED)?|counterexample)", re.IGNORECASE
)


class FormalMode(StrEnum):
    """Supported SBY execution modes for the initial safety workflow."""

    PROVE = "prove"
    BMC = "bmc"


class FormalStatus(StrEnum):
    """Externally visible, fail-closed formal result states."""

    PROVEN = "PROVEN"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class PropertyClass(StrEnum):
    """Semantic class used to choose a sound formal backend."""

    FINITE_VERDICT = "finite-verdict"
    SAFETY = "safety"
    BOUNDED_LIVENESS = "bounded-liveness"
    LIVENESS = "liveness"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FormalRunConfig:
    """Validated inputs for one user-DUT formal run."""

    dut_sources: tuple[Path, ...]
    property_file: Path
    top: str
    output_dir: Path
    property_name: str | None = None
    clock: str = "clk"
    reset: str = "rst_n"
    mode: FormalMode = FormalMode.PROVE
    depth: int = 20
    timeout_seconds: int = 120
    engine: str = "smtbmc"
    solver: str = "yices"
    slang_path: str = "slang"
    sby_path: str = "sby"
    force: bool = False

    def __post_init__(self) -> None:
        """Reject unsafe or ambiguous configuration before running tools."""
        if not self.dut_sources:
            raise ValueError("at least one DUT source is required")
        for label, value in (
            ("top", self.top),
            ("clock", self.clock),
            ("reset", self.reset),
        ):
            if _IDENTIFIER_RE.fullmatch(value) is None:
                raise ValueError(f"invalid {label} identifier: {value!r}")
        if self.property_name is not None:
            selector = self.property_name
            is_index = selector.isdigit() or (
                selector.startswith("@") and selector[1:].isdigit()
            )
            if not is_index and _IDENTIFIER_RE.fullmatch(selector) is None:
                raise ValueError(f"invalid property identifier: {selector!r}")
        if self.depth <= 0:
            raise ValueError("depth must be positive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout must be positive")
        for label, value in (
            ("engine", self.engine),
            ("solver", self.solver),
            ("slang path", self.slang_path),
            ("sby path", self.sby_path),
        ):
            if not value or any(char in value for char in ("\x00", "\n", "\r")):
                raise ValueError(f"invalid {label}: {value!r}")
        if _TOOL_TOKEN_RE.fullmatch(self.engine) is None:
            raise ValueError(f"invalid engine token: {self.engine!r}")
        if _TOOL_TOKEN_RE.fullmatch(self.solver) is None:
            raise ValueError(f"invalid solver token: {self.solver!r}")
        for source in (*self.dut_sources, self.property_file):
            if not source.is_file():
                raise ValueError(f"input source does not exist: {source}")


@dataclass(frozen=True)
class FormalEvidence:
    """A compiled, replayable formal evidence bundle."""

    bundle_dir: Path
    config: FormalRunConfig
    checker_module: str
    property_class: PropertyClass
    manifest: dict[str, Any]


@dataclass(frozen=True)
class FormalCompilation:
    """Backend-selected property ready for formal source emission."""

    checker: CheckerNode
    property_class: PropertyClass
    backend: str


@dataclass(frozen=True)
class FormalResult:
    """Machine-readable result of running one evidence bundle."""

    status: FormalStatus
    mode: FormalMode
    message: str
    returncode: int | None
    duration_seconds: float
    tool_versions: dict[str, str]
    log_path: str
    trace_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        return {
            "schema_version": 1,
            "status": self.status.value,
            "mode": self.mode.value,
            "message": self.message,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration_seconds, 6),
            "tool_versions": dict(sorted(self.tool_versions.items())),
            "log_path": self.log_path,
            "trace_paths": list(self.trace_paths),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _select_assertion(
    assertions: list[tuple[Any, Any, str, str | None]],
    selector: str | None,
) -> tuple[Any, Any, str, str | None]:
    if selector is None:
        if len(assertions) != 1:
            raise SvaCompileError(
                message=(
                    f"formal workflow requires exactly one property, found {len(assertions)}; "
                    "use --property"
                )
            )
        return assertions[0]
    if selector.isdigit():
        index = int(selector)
        if 1 <= index <= len(assertions):
            return assertions[index - 1]
    elif selector.startswith("@") and selector[1:].isdigit():
        line = int(selector[1:])
        matches = [
            assertion
            for assertion in assertions
            if getattr(assertion[0], "source_loc", None) is not None
            and assertion[0].source_loc.line == line
        ]
        if len(matches) == 1:
            return matches[0]
    else:
        matches = [assertion for assertion in assertions if assertion[3] == selector]
        if len(matches) == 1:
            return matches[0]
    raise PropertyNotFound(
        message=f"property selector {selector!r} did not select exactly one assertion",
        property_name=selector,
        available=[label for _, _, _, label in assertions if label is not None],
    )


def _join_property_classes(classes: tuple[PropertyClass, ...]) -> PropertyClass:
    """Join child classes conservatively for a composed property."""
    if PropertyClass.UNSUPPORTED in classes:
        return PropertyClass.UNSUPPORTED
    if PropertyClass.LIVENESS in classes:
        return PropertyClass.LIVENESS
    if PropertyClass.SAFETY in classes:
        return PropertyClass.SAFETY
    if PropertyClass.BOUNDED_LIVENESS in classes:
        return PropertyClass.BOUNDED_LIVENESS
    return PropertyClass.FINITE_VERDICT


def classify_property(node: sva_ir.SVANode) -> PropertyClass:
    """Classify temporal semantics before selecting a formal backend.

    The classifier is deliberately conservative.  In particular, a nested
    clock is unsupported by the initial single-clock formal backend and the
    negation of an unbounded safety property is true liveness.
    """
    if isinstance(node, (sva_ir.BoolExpr, sva_ir.SignalFunc)):
        return PropertyClass.FINITE_VERDICT
    if isinstance(node, sva_ir.PropBoundedEventually):
        return PropertyClass.BOUNDED_LIVENESS
    if isinstance(node, sva_ir.PropBoundedAlways):
        return PropertyClass.FINITE_VERDICT
    if isinstance(node, sva_ir.PropAlways):
        return PropertyClass.SAFETY
    if isinstance(node, sva_ir.PropNexttime):
        return PropertyClass.FINITE_VERDICT
    if isinstance(node, sva_ir.PropUntil):
        return PropertyClass.SAFETY
    if isinstance(node, (sva_ir.SeqGotoRep, sva_ir.SeqNonconsecRep)):
        # Occurrence count is finite but the wait for those occurrences has no
        # deadline, so successful discharge is a true eventuality obligation.
        return PropertyClass.LIVENESS
    if isinstance(node, sva_ir.ClockedSeq):
        return PropertyClass.UNSUPPORTED
    if isinstance(node, (sva_ir.DisableIff, sva_ir.SeqFirstMatch)):
        return classify_property(node.body)
    if isinstance(node, sva_ir.PropNot):
        inner = classify_property(node.body)
        if inner is PropertyClass.SAFETY:
            return PropertyClass.LIVENESS
        if inner is PropertyClass.LIVENESS:
            return PropertyClass.SAFETY
        if inner is PropertyClass.UNSUPPORTED:
            return inner
        return PropertyClass.FINITE_VERDICT
    if isinstance(node, sva_ir.PropIfElse):
        branches = [classify_property(node.condition), classify_property(node.true_branch)]
        if node.false_branch is not None:
            branches.append(classify_property(node.false_branch))
        return _join_property_classes(tuple(branches))
    if isinstance(
        node,
        (
            sva_ir.SeqConcat,
            sva_ir.SeqRepetition,
        ),
    ):
        children = node.elements if isinstance(node, sva_ir.SeqConcat) else (node.expr,)
        return _join_property_classes(tuple(classify_property(child) for child in children))
    if isinstance(
        node,
        (
            sva_ir.PropImplication,
            sva_ir.SeqOr,
            sva_ir.SeqAnd,
            sva_ir.SeqIntersect,
        ),
    ):
        left = node.antecedent if isinstance(node, sva_ir.PropImplication) else node.left
        right = node.consequent if isinstance(node, sva_ir.PropImplication) else node.right
        return _join_property_classes((classify_property(left), classify_property(right)))
    if isinstance(node, sva_ir.SeqWithin):
        return _join_property_classes(
            (classify_property(node.inner), classify_property(node.outer))
        )
    if isinstance(node, sva_ir.SeqThroughout):
        return _join_property_classes(
            (classify_property(node.condition), classify_property(node.body))
        )
    return PropertyClass.UNSUPPORTED


def select_formal_backend(property_class: PropertyClass) -> str:
    """Select the currently qualified backend or reject without weakening."""
    if property_class in {
        PropertyClass.FINITE_VERDICT,
        PropertyClass.SAFETY,
        PropertyClass.BOUNDED_LIVENESS,
    }:
        return "generated-monitor-safety"
    if property_class is PropertyClass.LIVENESS:
        raise UnsupportedConstruct(
            message=(
                "this property needs an open live backend or a checked "
                "liveness-to-safety reduction; bounded truncation is unsound"
            ),
            construct_name="open live backend",
        )
    raise UnsupportedConstruct(
        message=(
            "the initial formal backend accepts one clock domain only; split the "
            "property and state handoff assumptions explicitly"
        ),
        construct_name="single-clock formal backend",
    )


def _direct_invariant(node: sva_ir.SVANode) -> sva_ir.BoolExpr | None:
    """Return the effective invariant body, including disable semantics."""
    disable: sva_ir.BoolExpr | None = None
    body = node
    if isinstance(body, sva_ir.DisableIff):
        if not isinstance(body.condition, sva_ir.BoolExpr):
            return None
        disable = body.condition
        body = body.body
    if not isinstance(body, sva_ir.PropAlways) or not isinstance(body.body, sva_ir.BoolExpr):
        return None
    invariant = body.body
    if disable is None:
        return invariant
    if disable.expr is None or invariant.expr is None:
        return sva_ir.BoolExpr(
            text=f"(({disable.text}) || ({invariant.text}))",
            source_loc=body.source_loc,
        )
    combined = sva_ir.BoolBinary(
        op="or",
        left=disable.expr,
        right=invariant.expr,
        source_loc=body.source_loc,
    )
    return sva_ir.BoolExpr(
        text=f"(({disable.text}) || ({invariant.text}))",
        expr=combined,
        source_loc=body.source_loc,
    )


def _is_bare_sequence_property(node: sva_ir.SVANode) -> bool:
    """Detect sequence roots whose no-match output is not assertion failure."""
    body = node.body if isinstance(node, sva_ir.DisableIff) else node
    return isinstance(
        body,
        (
            sva_ir.SeqConcat,
            sva_ir.SeqRepetition,
            sva_ir.SeqFirstMatch,
            sva_ir.SeqGotoRep,
            sva_ir.SeqNonconsecRep,
            sva_ir.SeqOr,
            sva_ir.SeqAnd,
            sva_ir.SeqIntersect,
            sva_ir.SeqWithin,
            sva_ir.SeqThroughout,
        ),
    )


def _compile_checker(config: FormalRunConfig) -> FormalCompilation:
    """Compile the selected SVA property without involving the DUT frontend."""
    ast = invoke_slang(config.property_file, config.slang_path)
    imported = import_all_assertions(ast)
    node, clock, original_text, label = _select_assertion(imported, config.property_name)
    if clock.signal != config.clock:
        raise SvaCompileError(
            message=(
                f"property clock is {clock.signal!r}, but formal clock is "
                f"{config.clock!r}"
            ),
            source_loc=clock.source_loc,
        )
    normalized = normalize(node)
    property_class = classify_property(normalized)
    invariant = _direct_invariant(normalized)
    if invariant is not None:
        checker = compose(invariant, clock, label, original_text)
        return FormalCompilation(
            checker=optimize(checker),
            property_class=property_class,
            backend="direct-invariant-safety",
        )
    if _is_bare_sequence_property(normalized):
        raise UnsupportedConstruct(
            message=(
                "a bare sequence no-match is not the same as monitor fail; wrap "
                "the sequence in an implication/property obligation so the formal "
                "backend cannot report a vacuous proof"
            ),
            construct_name="bare sequence formal assertion",
            source_loc=normalized.source_loc,
        )
    backend = select_formal_backend(property_class)
    checker = compose(normalized, clock, label, original_text)
    return FormalCompilation(
        checker=optimize(checker),
        property_class=property_class,
        backend=backend,
    )


def _width_decl(width: int) -> str:
    return "" if width <= 1 else f" [{width - 1}:0]"


def _input_decl(name: str, width: int, signed: bool) -> str:
    signed_text = " signed" if signed else ""
    return f"    input logic{signed_text}{_width_decl(width)} {name}"


def render_formal_bind(
    checker: CheckerNode,
    *,
    top: str,
    clock: str,
    reset: str,
) -> str:
    """Render the bound assertion harness with explicit port connections."""
    for identifier in (top, clock, reset, checker.module_name):
        if _IDENTIFIER_RE.fullmatch(identifier) is None:
            raise ValueError(f"invalid SystemVerilog identifier: {identifier!r}")

    widths = observed_signal_widths(checker)
    signedness = observed_signal_signedness(checker)
    observed = [
        (port, signal)
        for port, signal in checker.observed_signals
        if port not in {clock, reset}
    ]
    port_lines = [f"    input logic {clock}", f"    input logic {reset}"]
    for port, _signal in observed:
        width = widths.get(port, 1)
        port_lines.append(_input_decl(port, width, signedness.get(port, False)))

    monitor_connections = [
        f"        .{clock}({clock})",
        f"        .rst_n({reset})",
        "        .start(1'b1)",
    ]
    monitor_connections.extend(f"        .{port}({port})" for port, _ in observed)
    monitor_connections.extend(
        (
            "        .disable_i(1'b0)",
            "        .active(monitor_active)",
            "        .pass(monitor_pass)",
            "        .fail(monitor_fail)",
            "        .attempt_fired(monitor_attempt_fired)",
            "        .disabled_o(monitor_disabled)",
        )
    )
    bind_connections = [f"    .{clock}({clock})", f"    .{reset}({reset})"]
    bind_connections.extend(f"    .{port}({signal})" for port, signal in observed)
    edge = checker.params.get("clock_edge", "posedge")
    if edge not in {"posedge", "negedge"}:
        raise ValueError(f"unsupported clock edge: {edge!r}")

    return (
        "// Generated open-formal harness. Original SVA is intentionally absent.\n"
        "module sva2rtl_formal_bind (\n"
        + ",\n".join(port_lines)
        + "\n);\n"
        "    wire monitor_active;\n"
        "    wire monitor_pass;\n"
        "    wire monitor_fail;\n"
        "    wire monitor_attempt_fired;\n"
        "    wire monitor_disabled;\n"
        "    reg formal_past_valid = 1'b0;\n\n"
        f"    {checker.module_name} u_monitor (\n"
        + ",\n".join(monitor_connections)
        + "\n    );\n\n"
        f"    always @({edge} {clock}) begin\n"
        "        formal_past_valid <= 1'b1;\n"
        "        if (!formal_past_valid) begin\n"
        f"            assume (!{reset});\n"
        "        end else begin\n"
        f"            assume ({reset});\n"
        "            assert (!monitor_fail);\n"
        "            cover (monitor_attempt_fired);\n"
        "        end\n"
        "    end\n"
        "endmodule\n\n"
        f"bind {top} sva2rtl_formal_bind u_sva2rtl_formal_bind (\n"
        + ",\n".join(bind_connections)
        + "\n);\n"
    )


def render_direct_invariant_bind(
    checker: CheckerNode,
    *,
    top: str,
    clock: str,
    reset: str,
) -> str:
    """Render an unbounded invariant directly, without a PASS-producing monitor."""
    for identifier in (top, clock, reset):
        if _IDENTIFIER_RE.fullmatch(identifier) is None:
            raise ValueError(f"invalid SystemVerilog identifier: {identifier!r}")
    expression = checker.params.get("bool_expr")
    if not expression:
        raise ValueError("direct invariant requires a structured boolean expression")
    widths = observed_signal_widths(checker)
    signedness = observed_signal_signedness(checker)
    observed = [
        (port, signal)
        for port, signal in checker.observed_signals
        if port not in {clock, reset}
    ]
    port_lines = [f"    input logic {clock}", f"    input logic {reset}"]
    port_lines.extend(
        _input_decl(port, widths.get(port, 1), signedness.get(port, False))
        for port, _signal in observed
    )
    bind_connections = [f"    .{clock}({clock})", f"    .{reset}({reset})"]
    bind_connections.extend(f"    .{port}({signal})" for port, signal in observed)
    edge = checker.params.get("clock_edge", "posedge")
    if edge not in {"posedge", "negedge"}:
        raise ValueError(f"unsupported clock edge: {edge!r}")
    return (
        "// Generated direct open-formal invariant. No finite PASS is synthesized.\n"
        "module sva2rtl_formal_bind (\n"
        + ",\n".join(port_lines)
        + "\n);\n"
        "    reg formal_past_valid = 1'b0;\n\n"
        f"    always @({edge} {clock}) begin\n"
        "        formal_past_valid <= 1'b1;\n"
        "        if (!formal_past_valid) begin\n"
        f"            assume (!{reset});\n"
        "        end else begin\n"
        f"            assume ({reset});\n"
        f"            assert ({expression});\n"
        "            cover (formal_past_valid);\n"
        "        end\n"
        "    end\n"
        "endmodule\n\n"
        f"bind {top} sva2rtl_formal_bind u_sva2rtl_formal_bind (\n"
        + ",\n".join(bind_connections)
        + "\n);\n"
    )
def _render_sby(config: FormalRunConfig, consumed_files: tuple[str, ...]) -> str:
    engine_line = f"{config.engine} {config.solver}".rstrip()
    source_args = " ".join(consumed_files)
    return (
        "[options]\n"
        f"mode {config.mode.value}\n"
        f"depth {config.depth}\n"
        "wait on\n\n"
        "[engines]\n"
        f"{engine_line}\n\n"
        "[script]\n"
        "plugin -i slang\n"
        f"read_slang --top {config.top} {source_args}\n"
        f"prep -top {config.top}\n\n"
        "[files]\n"
        + "\n".join(consumed_files)
        + "\n"
    )


def _prepare_output(config: FormalRunConfig) -> Path:
    output = config.output_dir.resolve()
    if output.exists():
        nonempty = not output.is_dir() or any(output.iterdir())
        if nonempty and not config.force:
            raise FileExistsError(
                f"formal evidence directory is not empty: {output}; use --force"
            )
        if config.force:
            if output.is_dir():
                shutil.rmtree(output)
            else:
                output.unlink()
    output.mkdir(parents=True, exist_ok=True)
    return output


def build_formal_bundle(config: FormalRunConfig) -> FormalEvidence:
    """Compile and write one replayable, source-isolated formal project."""
    bundle = _prepare_output(config)
    compilation = _compile_checker(config)
    checker = compilation.checker
    property_class = compilation.property_class
    backend = compilation.backend

    property_copy = bundle / "evidence" / "property.sv"
    property_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config.property_file, property_copy)

    consumed: list[str] = []
    dut_manifest: list[dict[str, str]] = []
    for index, source in enumerate(config.dut_sources):
        relative = f"dut_{index:03d}.sv"
        copied = bundle / relative
        shutil.copyfile(source, copied)
        consumed.append(relative)
        dut_manifest.append({"path": relative, "sha256": _sha256(copied)})

    modules = {} if backend == "direct-invariant-safety" else emit_all(checker)
    property_paths = {str(config.property_file), str(config.property_file.resolve())}
    generated_manifest: list[dict[str, str]] = []
    for index, (module_name, source_text) in enumerate(modules.items()):
        relative = f"generated_{index:03d}.sv"
        for property_path in property_paths:
            source_text = source_text.replace(property_path, "evidence/property.sv")
        generated = bundle / relative
        _write_text(generated, source_text)
        consumed.append(relative)
        generated_manifest.append(
            {"module": module_name, "path": relative, "sha256": _sha256(generated)}
        )

    bind_path = bundle / "formal_bind.sv"
    if backend == "direct-invariant-safety":
        bind_text = render_direct_invariant_bind(
            checker,
            top=config.top,
            clock=config.clock,
            reset=config.reset,
        )
    else:
        bind_text = render_formal_bind(
            checker,
            top=config.top,
            clock=config.clock,
            reset=config.reset,
        )
    _write_text(bind_path, bind_text)
    consumed.append("formal_bind.sv")
    _write_text(bundle / "formal.sby", _render_sby(config, tuple(consumed)))

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "backend": backend,
        "property_class": property_class.value,
        "config": {
            "top": config.top,
            "property": config.property_name,
            "clock": config.clock,
            "reset": config.reset,
            "mode": config.mode.value,
            "depth": config.depth,
            "timeout_seconds": config.timeout_seconds,
            "engine": config.engine,
            "solver": config.solver,
        },
        "property": {
            "path": "evidence/property.sv",
            "sha256": _sha256(property_copy),
        },
        "dut_sources": dut_manifest,
        "generated_sources": generated_manifest,
        "formal_bind": {"path": "formal_bind.sv", "sha256": _sha256(bind_path)},
        "sby": {"path": "formal.sby", "sha256": _sha256(bundle / "formal.sby")},
        "yosys_inputs": consumed,
        "assumptions": [
            "reset is asserted on the first sampled cycle",
            "reset is deasserted on every later sampled cycle",
        ]
        + (
            []
            if backend == "direct-invariant-safety"
            else [
                "monitor start is asserted on every non-reset cycle",
                "monitor disable_i is held low",
            ]
        ),
        "covers": [
            "direct invariant sampling becomes reachable after reset"
            if backend == "direct-invariant-safety"
            else "monitor attempt_fired becomes reachable after reset"
        ],
    }
    _write_json(bundle / "manifest.json", manifest)
    initial = FormalResult(
        status=FormalStatus.UNKNOWN,
        mode=config.mode,
        message="formal bundle compiled but not yet executed",
        returncode=None,
        duration_seconds=0.0,
        tool_versions={},
        log_path="sby.log",
    )
    _write_json(bundle / "result.json", initial.to_dict())
    return FormalEvidence(bundle, config, checker.module_name, property_class, manifest)


def classify_sby_result(
    *,
    mode: FormalMode,
    returncode: int,
    output: str,
    timed_out: bool = False,
) -> tuple[FormalStatus, str]:
    """Classify SBY output without treating every exit zero as a proof."""
    if timed_out:
        return FormalStatus.TIMEOUT, "formal run exceeded the configured timeout"
    if _FAIL_RE.search(output):
        return FormalStatus.FAILED, "formal engine found a counterexample"
    if returncode == 0 and _PASS_RE.search(output):
        if mode is FormalMode.PROVE:
            return FormalStatus.PROVEN, "unbounded safety proof completed"
        return (
            FormalStatus.UNKNOWN,
            "bounded model check found no counterexample within the configured depth",
        )
    return FormalStatus.ERROR, "formal engine ended without an unambiguous result"


def _probe_version(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "missing"
    combined = (completed.stdout + completed.stderr).strip().splitlines()
    return combined[0][:200] if combined else f"exit {completed.returncode}"


def _trace_paths(bundle: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for pattern in ("*.vcd", "*.yw", "*.vcd.gz"):
        for trace in bundle.rglob(pattern):
            if trace.is_file():
                paths.append(trace.relative_to(bundle).as_posix())
    return tuple(sorted(set(paths)))


def run_formal_bundle(evidence: FormalEvidence) -> FormalResult:
    """Run SBY for a compiled bundle and persist complete output and status."""
    config = evidence.config
    started = time.monotonic()
    output = ""
    returncode: int | None = None
    timed_out = False
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is validated and shell is disabled
            [config.sby_path, "-f", "formal.sby"],
            cwd=evidence.bundle_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError:
        status = FormalStatus.ERROR
        message = f"missing dependency: {config.sby_path}"
    else:
        try:
            output, _ = process.communicate(timeout=config.timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            output, _ = process.communicate()
        returncode = process.returncode
        status, message = classify_sby_result(
            mode=config.mode,
            returncode=returncode,
            output=output,
            timed_out=timed_out,
        )

    _write_text(evidence.bundle_dir / "sby.log", output)
    result = FormalResult(
        status=status,
        mode=config.mode,
        message=message,
        returncode=returncode,
        duration_seconds=time.monotonic() - started,
        tool_versions={
            "sby": _probe_version([config.sby_path, "--version"]),
            "slang": _probe_version([config.slang_path, "--version"]),
            "yosys": _probe_version(["yosys", "-V"]),
        },
        log_path="sby.log",
        trace_paths=_trace_paths(evidence.bundle_dir),
    )
    _write_json(evidence.bundle_dir / "result.json", result.to_dict())
    return result
