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
from sva2rtl.formal_lowering import lower_bounded_implication
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


class AttemptMode(StrEnum):
    """How overlapping bounded property attempts are represented."""

    AUTO = "auto"
    MONITOR = "monitor"
    SYMBOLIC_WITNESS = "symbolic-witness"


class FormalStatus(StrEnum):
    """Externally visible, fail-closed formal result states."""

    PROVEN = "PROVEN"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


class CoverStatus(StrEnum):
    """Reachability result for the separate critical-cover task."""

    NOT_RUN = "NOT_RUN"
    REACHED = "REACHED"
    UNREACHED = "UNREACHED"
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
    attempt_mode: AttemptMode = AttemptMode.AUTO
    depth: int = 20
    timeout_seconds: int = 120
    engine: str = "smtbmc"
    solver: str = "yices"
    slang_path: str = "slang"
    sby_path: str = "sby"
    decomposition_certificate: Path | None = None
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
        if (
            self.decomposition_certificate is not None
            and not self.decomposition_certificate.is_file()
        ):
            raise ValueError(
                "decomposition certificate does not exist: "
                f"{self.decomposition_certificate}"
            )


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
    cover_status: CoverStatus = CoverStatus.NOT_RUN
    cover_returncode: int | None = None
    cover_log_path: str | None = None

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
            "cover_status": self.cover_status.value,
            "cover_returncode": self.cover_returncode,
            "cover_log_path": self.cover_log_path,
        }


@dataclass(frozen=True)
class _DecompositionMember:
    identifier: str
    property_path: Path
    property_sha256: str
    checker: str
    proof_artifact_path: Path
    proof_artifact_sha256: str


@dataclass(frozen=True)
class _ValidatedDecomposition:
    relation: str
    original_property_sha256: str
    source_certificate_sha256: str
    relation_checker: str
    relation_proof_artifact_path: Path
    relation_proof_artifact_sha256: str
    members: tuple[_DecompositionMember, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"invalid {label}: expected lowercase SHA-256")
    return value


def _certificate_file(base: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"invalid {label}")
    relative = Path(value)
    if relative.is_absolute():
        raise ValueError(f"{label} must be relative to the certificate")
    resolved = (base / relative).resolve()
    try:
        resolved.relative_to(base.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes the certificate directory") from exc
    if not resolved.is_file():
        raise ValueError(f"{label} does not exist: {value}")
    return resolved


def _require_checker(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 200
        or any(char in value for char in ("\x00", "\n", "\r"))
    ):
        raise ValueError(f"invalid {label}")
    return value


def _require_proven_artifact(path: Path, label: str) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be a JSON result artifact") from exc
    if not isinstance(payload, dict) or payload.get("status") != FormalStatus.PROVEN.value:
        raise ValueError(f"{label} does not report PROVEN")


def _validate_decomposition_certificate(
    certificate: Path,
    *,
    original_property_sha256: str,
) -> _ValidatedDecomposition:
    """Validate every decomposition claim against files and proof artifacts."""
    try:
        payload = json.loads(certificate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid decomposition certificate: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("decomposition certificate requires schema_version 1")
    relation = payload.get("relation")
    if relation not in {"equivalent", "stronger"}:
        raise ValueError("decomposition relation must be equivalent or stronger")
    claimed_original = _require_sha256(
        payload.get("original_property_sha256"), "original property hash"
    )
    if claimed_original != original_property_sha256:
        raise ValueError("decomposition original property hash does not match input")
    if payload.get("relation_status") != FormalStatus.PROVEN.value:
        raise ValueError("decomposition relation is not PROVEN")
    relation_checker = _require_checker(
        payload.get("relation_checker"), "decomposition relation checker"
    )
    relation_proof_path = _certificate_file(
        certificate.parent,
        payload.get("relation_proof_artifact_path"),
        "decomposition relation proof artifact path",
    )
    relation_proof_sha256 = _require_sha256(
        payload.get("relation_proof_artifact_sha256"),
        "decomposition relation proof artifact hash",
    )
    if _sha256(relation_proof_path) != relation_proof_sha256:
        raise ValueError("decomposition relation proof artifact hash does not match")
    _require_proven_artifact(relation_proof_path, "decomposition relation proof artifact")
    raw_members = payload.get("subproperties")
    if not isinstance(raw_members, list) or not raw_members:
        raise ValueError("decomposition certificate requires non-empty subproperties")

    members: list[_DecompositionMember] = []
    for index, raw in enumerate(raw_members):
        if not isinstance(raw, dict):
            raise ValueError(f"decomposition subproperty {index} must be an object")
        identifier = raw.get("id")
        if not isinstance(identifier, str) or _IDENTIFIER_RE.fullmatch(identifier) is None:
            raise ValueError(f"invalid decomposition subproperty id at index {index}")
        if raw.get("obligation_status") != FormalStatus.PROVEN.value:
            raise ValueError(f"decomposition subproperty {identifier} is not PROVEN")
        checker = _require_checker(
            raw.get("checker"), f"decomposition checker for {identifier}"
        )
        property_path = _certificate_file(
            certificate.parent, raw.get("property_path"), "subproperty path"
        )
        property_sha256 = _require_sha256(
            raw.get("property_sha256"), "subproperty hash"
        )
        if _sha256(property_path) != property_sha256:
            raise ValueError(f"subproperty hash does not match for {identifier}")
        proof_path = _certificate_file(
            certificate.parent,
            raw.get("proof_artifact_path"),
            "proof artifact path",
        )
        proof_sha256 = _require_sha256(
            raw.get("proof_artifact_sha256"), "proof artifact hash"
        )
        if _sha256(proof_path) != proof_sha256:
            raise ValueError(f"proof artifact hash does not match for {identifier}")
        _require_proven_artifact(proof_path, f"proof artifact for {identifier}")
        members.append(
            _DecompositionMember(
                identifier=identifier,
                property_path=property_path,
                property_sha256=property_sha256,
                checker=checker,
                proof_artifact_path=proof_path,
                proof_artifact_sha256=proof_sha256,
            )
        )
    return _ValidatedDecomposition(
        relation=relation,
        original_property_sha256=claimed_original,
        source_certificate_sha256=_sha256(certificate),
        relation_checker=relation_checker,
        relation_proof_artifact_path=relation_proof_path,
        relation_proof_artifact_sha256=relation_proof_sha256,
        members=tuple(members),
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def _materialize_decomposition(
    bundle: Path,
    decomposition: _ValidatedDecomposition,
) -> dict[str, str]:
    """Copy verified inputs under stable names and emit a path-sanitized certificate."""
    members: list[dict[str, Any]] = []
    target_dir = bundle / "evidence" / "decomposition"
    target_dir.mkdir(parents=True, exist_ok=True)
    relation_suffix = decomposition.relation_proof_artifact_path.suffix or ".json"
    relation_relative = f"evidence/decomposition/relation_proof{relation_suffix}"
    shutil.copyfile(
        decomposition.relation_proof_artifact_path, bundle / relation_relative
    )
    for index, member in enumerate(decomposition.members):
        property_suffix = member.property_path.suffix or ".sv"
        proof_suffix = member.proof_artifact_path.suffix or ".json"
        property_relative = f"evidence/decomposition/subproperty_{index:03d}{property_suffix}"
        proof_relative = f"evidence/decomposition/proof_{index:03d}{proof_suffix}"
        property_target = bundle / property_relative
        proof_target = bundle / proof_relative
        shutil.copyfile(member.property_path, property_target)
        shutil.copyfile(member.proof_artifact_path, proof_target)
        members.append(
            {
                "id": member.identifier,
                "property_path": property_relative,
                "property_sha256": member.property_sha256,
                "obligation_status": FormalStatus.PROVEN.value,
                "checker": member.checker,
                "proof_artifact_path": proof_relative,
                "proof_artifact_sha256": member.proof_artifact_sha256,
            }
        )
    normalized = {
        "schema_version": 1,
        "relation": decomposition.relation,
        "relation_status": FormalStatus.PROVEN.value,
        "relation_checker": decomposition.relation_checker,
        "relation_proof_artifact_path": relation_relative,
        "relation_proof_artifact_sha256": (
            decomposition.relation_proof_artifact_sha256
        ),
        "original_property_sha256": decomposition.original_property_sha256,
        "source_certificate_sha256": decomposition.source_certificate_sha256,
        "subproperties": members,
    }
    relative = "evidence/decomposition.json"
    target = bundle / relative
    _write_json(target, normalized)
    return {"path": relative, "sha256": _sha256(target)}


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
    if config.attempt_mode is not AttemptMode.MONITOR:
        witness = lower_bounded_implication(
            node,
            label=label,
            original_text=original_text,
            clock_signal=clock.signal,
            clock_edge=clock.edge,
        )
        if witness is not None:
            return FormalCompilation(
                checker=witness,
                property_class=classify_property(normalize(node)),
                backend="symbolic-witness-safety",
            )
        if config.attempt_mode is AttemptMode.SYMBOLIC_WITNESS:
            raise UnsupportedConstruct(
                message=(
                    "symbolic-witness mode supports only a Boolean antecedent "
                    "with Boolean, fixed/ranged-delay, nexttime, or bounded "
                    "consecutive consequent"
                ),
                construct_name="symbolic-witness property shape",
                source_loc=node.source_loc,
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


def render_symbolic_witness_bind(
    checker: CheckerNode,
    *,
    top: str,
    clock: str,
    reset: str,
) -> str:
    """Render one arbitrary bounded attempt without a fixed thread budget."""
    for identifier in (top, clock, reset):
        if _IDENTIFIER_RE.fullmatch(identifier) is None:
            raise ValueError(f"invalid SystemVerilog identifier: {identifier!r}")
    widths = observed_signal_widths(checker)
    signedness = observed_signal_signedness(checker)
    observed = list(checker.observed_signals)
    port_lines = [f"    input logic {clock}", f"    input logic {reset}"]
    port_lines.extend(
        _input_decl(port, widths.get(port, 1), signedness.get(port, False))
        for port, _signal in observed
    )
    bind_connections = [f"    .{clock}({clock})", f"    .{reset}({reset})"]
    bind_connections.extend(f"    .{port}({signal})" for port, signal in observed)
    edge = checker.params["clock_edge"]
    antecedent = checker.params["antecedent_expr"]
    condition = checker.params["condition_expr"]
    disable = checker.params["disable_expr"]
    kind = checker.params["obligation_kind"]
    lo = int(checker.params["min_cycles"])
    hi = int(checker.params["max_cycles"])
    start_offset = int(checker.params["start_offset"])
    counter_width = int(checker.params["counter_width"])

    if kind == "eventually":
        if hi == 0:
            obligation_logic = (
                "            if (witness_start) begin\n"
                f"                assert ({condition});\n"
                f"                cover ({condition});\n"
                "            end\n"
            )
        else:
            eligible_at_start = lo == 0
            initial_seen = f"({condition})" if eligible_at_start else "1'b0"
            obligation_logic = (
                "            if (witness_start) begin\n"
                "                tracking_q <= 1'b1;\n"
                "                age_q <= '0;\n"
                f"                seen_q <= {initial_seen};\n"
                "            end else if (tracking_q) begin\n"
                "                age_q <= age_q + 1'b1;\n"
                f"                if ((age_q + 1'b1 >= MIN_CYCLES) && ({condition}))\n"
                "                    seen_q <= 1'b1;\n"
                "                if (age_q + 1'b1 >= MAX_CYCLES) begin\n"
                f"                    assert (seen_q || ({condition}));\n"
                f"                    cover (seen_q || ({condition}));\n"
                "                    tracking_q <= 1'b0;\n"
                "                end\n"
                "            end\n"
            )
    else:
        start_check = start_offset == 0
        if start_check:
            start_body = (
                f"                assert ({condition});\n"
                + (
                    f"                cover ({condition});\n"
                    "                tracking_q <= 1'b0;\n"
                    if lo <= 1
                    else "                tracking_q <= 1'b1;\n"
                    "                count_q <= 1;\n"
                )
            )
        else:
            start_body = (
                "                tracking_q <= 1'b1;\n"
                "                count_q <= '0;\n"
            )
        obligation_logic = (
            "            if (witness_start) begin\n"
            "                age_q <= '0;\n"
            + start_body
            + "            end else if (tracking_q) begin\n"
            f"                if (age_q + 1'b1 < START_OFFSET) begin\n"
            "                    age_q <= age_q + 1'b1;\n"
            "                end else begin\n"
            f"                    assert ({condition});\n"
            f"                    if ({condition}) begin\n"
            "                        count_q <= count_q + 1'b1;\n"
            "                        if (count_q + 1'b1 >= MIN_CYCLES) begin\n"
            f"                            cover ({condition});\n"
            "                            tracking_q <= 1'b0;\n"
            "                        end\n"
            "                    end else begin\n"
            "                        tracking_q <= 1'b0;\n"
            "                    end\n"
            "                end\n"
            "            end\n"
        )

    return (
        "// Generated symbolic-witness safety harness.\n"
        "module sva2rtl_formal_bind (\n"
        + ",\n".join(port_lines)
        + "\n);\n"
        f"    localparam integer MIN_CYCLES = {lo};\n"
        f"    localparam integer MAX_CYCLES = {hi};\n"
        f"    localparam integer START_OFFSET = {start_offset};\n"
        f"    (* anyseq *) logic witness_select;\n"
        "    logic formal_past_valid = 1'b0;\n"
        "    logic tracking_q = 1'b0;\n"
        "    logic seen_q = 1'b0;\n"
        f"    logic [{counter_width - 1}:0] age_q = '0;\n"
        f"    logic [{counter_width - 1}:0] count_q = '0;\n"
        f"    wire witness_start = !tracking_q && !({disable}) && "
        f"({antecedent}) && witness_select;\n\n"
        f"    always @({edge} {clock}) begin\n"
        "        formal_past_valid <= 1'b1;\n"
        "        if (!formal_past_valid) begin\n"
        f"            assume (!{reset});\n"
        "            tracking_q <= 1'b0;\n"
        "            seen_q <= 1'b0;\n"
        "            age_q <= '0;\n"
        "            count_q <= '0;\n"
        "        end else begin\n"
        f"            assume ({reset});\n"
        f"            cover ({antecedent});\n"
        "            cover (witness_start);\n"
        f"            if ({disable}) begin\n"
        "                tracking_q <= 1'b0;\n"
        "                seen_q <= 1'b0;\n"
        "                age_q <= '0;\n"
        "                count_q <= '0;\n"
        "            end else begin\n"
        + obligation_logic
        + "            end\n"
        "        end\n"
        "    end\n"
        "endmodule\n\n"
        f"bind {top} sva2rtl_formal_bind u_sva2rtl_formal_bind (\n"
        + ",\n".join(bind_connections)
        + "\n);\n"
    )


def _render_sby(
    config: FormalRunConfig,
    consumed_files: tuple[str, ...],
    *,
    mode: str | None = None,
) -> str:
    engine_line = f"{config.engine} {config.solver}".rstrip()
    source_args = " ".join(consumed_files)
    return (
        "[options]\n"
        f"mode {mode or config.mode.value}\n"
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
    decomposition = None
    if config.decomposition_certificate is not None:
        decomposition = _validate_decomposition_certificate(
            config.decomposition_certificate,
            original_property_sha256=_sha256(config.property_file),
        )
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

    modules = (
        {}
        if backend in {"direct-invariant-safety", "symbolic-witness-safety"}
        else emit_all(checker)
    )
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
    elif backend == "symbolic-witness-safety":
        bind_text = render_symbolic_witness_bind(
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
    _write_text(
        bundle / "formal_cover.sby",
        _render_sby(config, tuple(consumed), mode="cover"),
    )

    widths = observed_signal_widths(checker)
    signedness = observed_signal_signedness(checker)
    observed_slice = [
        {
            "port": port,
            "dut_signal": signal,
            "width": widths.get(port, 1),
            "signed": signedness.get(port, False),
        }
        for port, signal in checker.observed_signals
        if port not in {config.clock, config.reset}
        and signal not in {config.clock, config.reset}
    ]
    slice_path = bundle / "evidence" / "slice.json"
    _write_json(
        slice_path,
        {
            "schema_version": 1,
            "kind": "logical-property-cone",
            "top": config.top,
            "clock": config.clock,
            "reset": config.reset,
            "backend": backend,
            "source_scope": "complete-dut-sources",
            "pruning_boundary": "yosys-prep-and-formal-cone",
            "observed_signals": observed_slice,
        },
    )

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
            "attempt_mode": config.attempt_mode.value,
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
        "formal_cover.sby": {
            "path": "formal_cover.sby",
            "sha256": _sha256(bundle / "formal_cover.sby"),
        },
        "property_slice": {
            "path": "evidence/slice.json",
            "sha256": _sha256(slice_path),
        },
        "yosys_inputs": consumed,
        "assumptions": [
            "reset is asserted on the first sampled cycle",
            "reset is deasserted on every later sampled cycle",
        ]
        + (
            []
            if backend in {"direct-invariant-safety", "symbolic-witness-safety"}
            else [
                "monitor start is asserted on every non-reset cycle",
                "monitor disable_i is held low",
            ]
        ),
        "covers": [
            "direct invariant sampling becomes reachable after reset"
            if backend == "direct-invariant-safety"
            else (
                "antecedent, witness selection, and obligation completion are reachable"
                if backend == "symbolic-witness-safety"
                else "monitor attempt_fired becomes reachable after reset"
            )
        ],
    }
    if decomposition is not None:
        manifest["decomposition"] = _materialize_decomposition(bundle, decomposition)
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


def classify_cover_result(
    *,
    returncode: int,
    output: str,
    timed_out: bool = False,
) -> tuple[CoverStatus, str]:
    """Classify a separate SBY cover task without upgrading ambiguity."""
    if timed_out:
        return CoverStatus.TIMEOUT, "critical cover task exceeded the configured timeout"
    if returncode == 0 and _PASS_RE.search(output):
        return CoverStatus.REACHED, "all critical cover statements were reached"
    if _FAIL_RE.search(output):
        return CoverStatus.UNREACHED, "one or more critical cover statements were not reached"
    return CoverStatus.ERROR, "cover engine ended without an unambiguous result"


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


def _run_sby_process(
    evidence: FormalEvidence,
    project_file: str,
) -> tuple[int | None, str, bool]:
    """Run one SBY project with process-group timeout cleanup."""
    config = evidence.config
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is validated and shell is disabled
            [config.sby_path, "-f", project_file],
            cwd=evidence.bundle_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
    except FileNotFoundError:
        return None, "", False
    try:
        output, _ = process.communicate(timeout=config.timeout_seconds)
        return process.returncode, output, False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        output, _ = process.communicate()
        return process.returncode, output, True


def run_formal_bundle(evidence: FormalEvidence) -> FormalResult:
    """Run SBY for a compiled bundle and persist complete output and status."""
    config = evidence.config
    started = time.monotonic()
    returncode, output, timed_out = _run_sby_process(evidence, "formal.sby")
    if returncode is None:
        status = FormalStatus.ERROR
        message = f"missing dependency: {config.sby_path}"
    else:
        status, message = classify_sby_result(
            mode=config.mode,
            returncode=returncode,
            output=output,
            timed_out=timed_out,
        )

    _write_text(evidence.bundle_dir / "sby.log", output)
    cover_status = CoverStatus.NOT_RUN
    cover_returncode: int | None = None
    cover_log_path: str | None = None
    if status is FormalStatus.PROVEN:
        cover_returncode, cover_output, cover_timed_out = _run_sby_process(
            evidence, "formal_cover.sby"
        )
        cover_log_path = "cover.log"
        _write_text(evidence.bundle_dir / cover_log_path, cover_output)
        if cover_returncode is None:
            cover_status = CoverStatus.ERROR
            cover_message = f"missing dependency: {config.sby_path}"
        else:
            cover_status, cover_message = classify_cover_result(
                returncode=cover_returncode,
                output=cover_output,
                timed_out=cover_timed_out,
            )
        if cover_status is not CoverStatus.REACHED:
            status = FormalStatus.UNKNOWN
            message = (
                "safety proof completed, but critical cover evidence is not "
                f"complete: {cover_message}"
            )
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
        cover_status=cover_status,
        cover_returncode=cover_returncode,
        cover_log_path=cover_log_path,
    )
    _write_json(evidence.bundle_dir / "result.json", result.to_dict())
    return result
