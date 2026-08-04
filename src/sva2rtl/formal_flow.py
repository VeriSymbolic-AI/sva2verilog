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
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from sva2rtl import ir as sva_ir
from sva2rtl.ast_importer import import_all_assertions, parse_slang_integral_type
from sva2rtl.composer import compose
from sva2rtl.emitter import (
    emit_all,
    observed_signal_signedness,
    observed_signal_widths,
)
from sva2rtl.errors import PropertyNotFound, SvaCompileError, UnsupportedConstruct
from sva2rtl.formal_lowering import (
    lower_bounded_implication,
    lower_liveness_property,
    lower_local_capture,
)
from sva2rtl.frontend import SlangCompilationContext, invoke_slang
from sva2rtl.ir import CheckerNode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_TOOL_TOKEN_RE = re.compile(r"^[A-Za-z0-9_.+-]+$")
_PASS_RE = re.compile(r"(?:DONE\s*\(PASS|STATUS:\s*PASS(?:ED)?)", re.IGNORECASE)
_FAIL_RE = re.compile(
    r"(?:DONE\s*\(FAIL|STATUS:\s*FAIL(?:ED)?|counterexample)", re.IGNORECASE
)
_EVIDENCE_MARKER = ".sva2rtl-evidence"
_EVIDENCE_MARKER_TEXT = "sva2rtl formal evidence directory\n"


class FormalMode(StrEnum):
    """Supported SBY execution modes for the initial safety workflow."""

    PROVE = "prove"
    BMC = "bmc"


class AttemptMode(StrEnum):
    """How overlapping bounded property attempts are represented."""

    AUTO = "auto"
    MONITOR = "monitor"
    SYMBOLIC_WITNESS = "symbolic-witness"


class LogicSemantics(StrEnum):
    """Named value-domain abstraction used by the open formal backend."""

    TWO_STATE = "two-state"


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
    suprove_path: str = "suprove"
    logic_semantics: LogicSemantics = LogicSemantics.TWO_STATE
    fairness_signals: tuple[str, ...] = ()
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
        if self.logic_semantics is not LogicSemantics.TWO_STATE:
            raise ValueError("only the explicit two-state formal profile is supported")
        for label, value in (
            ("engine", self.engine),
            ("solver", self.solver),
            ("slang path", self.slang_path),
            ("sby path", self.sby_path),
            ("suprove path", self.suprove_path),
        ):
            if not value or any(char in value for char in ("\x00", "\n", "\r")):
                raise ValueError(f"invalid {label}: {value!r}")
        if _TOOL_TOKEN_RE.fullmatch(self.engine) is None:
            raise ValueError(f"invalid engine token: {self.engine!r}")
        if _TOOL_TOKEN_RE.fullmatch(self.solver) is None:
            raise ValueError(f"invalid solver token: {self.solver!r}")
        if len(set(self.fairness_signals)) != len(self.fairness_signals):
            raise ValueError("fairness signals must be unique")
        for fairness_signal in self.fairness_signals:
            if _IDENTIFIER_RE.fullmatch(fairness_signal) is None:
                raise ValueError(f"invalid fairness signal: {fairness_signal!r}")
        for source in (*self.dut_sources, self.property_file):
            if not source.is_file():
                raise ValueError(f"input source does not exist: {source}")
        for source in self.dut_sources:
            if source.resolve() == self.property_file.resolve() or os.path.samefile(
                source, self.property_file
            ):
                raise ValueError(
                    "DUT and property inputs must be separate files; the original "
                    "SVA source may never enter Yosys inputs"
                )
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
class LiveBackendInfo:
    """Discovered unbounded liveness engine and its evidence metadata."""

    available: bool
    path: str
    version: str
    guidance: str


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
    manifest_sha256: str = ""
    property_sha256: str = ""
    checker: str = ""
    replay_commands: tuple[tuple[str, ...], ...] = ()
    log_sha256: str = ""
    cover_log_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-compatible representation."""
        return {
            "schema_version": 2,
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
            "manifest_sha256": self.manifest_sha256,
            "property_sha256": self.property_sha256,
            "checker": self.checker,
            "replay_commands": [list(command) for command in self.replay_commands],
            "log_sha256": self.log_sha256,
            "cover_log_sha256": self.cover_log_sha256,
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
    dut_source_sha256s: tuple[str, ...]
    source_certificate_sha256: str
    relation_checker: str
    relation_proof_artifact_path: Path
    relation_proof_artifact_sha256: str
    members: tuple[_DecompositionMember, ...]


@dataclass(frozen=True)
class _DutSignal:
    """One elaborated signal visible in the selected DUT top scope."""

    name: str
    width: int
    signed: bool
    kind: str


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk_ast(value: object) -> Iterator[dict[str, Any]]:
    """Yield every dictionary node from a slang JSON value."""
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_ast(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_ast(child)


def _dut_top_body(ast: dict[str, object], top: str) -> dict[str, object]:
    design = ast.get("design")
    if not isinstance(design, dict):
        raise SvaCompileError(message="slang DUT AST is missing the design root")
    members = design.get("members")
    if not isinstance(members, list):
        raise SvaCompileError(message="slang DUT AST is missing top-level instances")
    matches = [
        member
        for member in members
        if isinstance(member, dict)
        and member.get("kind") == "Instance"
        and member.get("name") == top
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("body"), dict):
        raise SvaCompileError(
            message=f"formal DUT contract requires exactly one elaborated top {top!r}"
        )
    return cast(dict[str, object], matches[0]["body"])


def _elaborate_dut_signals(
    config: FormalRunConfig,
    required_signals: frozenset[str],
) -> dict[str, _DutSignal]:
    """Elaborate the DUT, reject assertions, and type only contract signals."""
    ast = invoke_slang(
        config.dut_sources[0],
        config.slang_path,
        context=SlangCompilationContext(
            source_files=config.dut_sources[1:],
            top_modules=(config.top,),
        ),
    )
    for node in _walk_ast(ast):
        node_kind = node.get("kind")
        if isinstance(node_kind, str) and "Assertion" in node_kind:
            assertion_kind = str(node.get("assertionKind", "concurrent assertion"))
            raise SvaCompileError(
                message=(
                    f"DUT sources must be assertion-free; found {assertion_kind} "
                    f"({node_kind}). "
                    "Keep the original SVA only in --property-file so it cannot "
                    "enter the Yosys model."
                )
            )

    body = _dut_top_body(ast, config.top)
    members = body.get("members")
    if not isinstance(members, list):
        raise SvaCompileError(message=f"DUT top {config.top!r} has no visible members")
    signals: dict[str, _DutSignal] = {}
    for member in members:
        if (
            not isinstance(member, dict)
            or member.get("kind") not in {"Port", "Variable", "Net"}
            or not isinstance(member.get("name"), str)
            or not member["name"]
        ):
            continue
        name = member["name"]
        if name not in required_signals:
            continue
        type_text = member.get("type")
        if not isinstance(type_text, str):
            continue
        width, signed = parse_slang_integral_type(type_text)
        candidate = _DutSignal(name, width, signed, str(member["kind"]))
        previous = signals.get(name)
        if previous is not None and (previous.width, previous.signed) != (
            width,
            signed,
        ):
            raise SvaCompileError(
                message=f"DUT signal {name!r} has inconsistent elaborated types"
            )
        signals[name] = candidate
    return signals


def _validate_dut_contract(
    config: FormalRunConfig,
    checker: CheckerNode,
) -> dict[str, Any]:
    """Fail before proof when property and DUT signal contracts differ."""
    widths = observed_signal_widths(checker)
    signedness = observed_signal_signedness(checker)
    required_signals = frozenset(
        {
            config.clock,
            config.reset,
            *config.fairness_signals,
            *(signal for _port, signal in checker.observed_signals),
        }
    )
    dut_signals = _elaborate_dut_signals(config, required_signals)
    checked: list[dict[str, Any]] = []

    def require(
        signal: str,
        *,
        role: str,
        expected_width: int,
        expected_signed: bool | None,
        property_port: str | None = None,
    ) -> None:
        actual = dut_signals.get(signal)
        if actual is None:
            raise SvaCompileError(
                message=f"formal {role} signal {signal!r} does not exist in DUT top {config.top!r}"
            )
        signed_mismatch = (
            expected_signed is not None and actual.signed != expected_signed
        )
        if actual.width != expected_width or signed_mismatch:
            expected_type = (
                f"width={expected_width}"
                + (f", signed={expected_signed}" if expected_signed is not None else "")
            )
            raise SvaCompileError(
                message=(
                    f"formal {role} signal {signal!r} type mismatch: property expects "
                    f"{expected_type}; DUT elaborates width={actual.width}, "
                    f"signed={actual.signed}. Refusing a silently truncated or "
                    "extended proof model."
                )
            )
        checked.append(
            {
                "role": role,
                "property_port": property_port,
                "dut_signal": signal,
                "width": actual.width,
                "signed": actual.signed,
                "kind": actual.kind,
            }
        )

    require(
        config.clock,
        role="clock",
        expected_width=1,
        expected_signed=None,
    )
    require(
        config.reset,
        role="reset",
        expected_width=1,
        expected_signed=None,
    )
    for port, observed_signal in checker.observed_signals:
        require(
            observed_signal,
            role="property-observation",
            property_port=port,
            expected_width=widths.get(port, 1),
            expected_signed=signedness.get(port, False),
        )
    for fairness_signal in config.fairness_signals:
        require(
            fairness_signal,
            role="fairness",
            expected_width=1,
            expected_signed=None,
        )
    return {
        "schema_version": 1,
        "top": config.top,
        "status": "MATCHED",
        "signals": checked,
    }


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


def _require_proven_artifact(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be a JSON result artifact") from exc
    if not isinstance(payload, dict) or payload.get("status") != FormalStatus.PROVEN.value:
        raise ValueError(f"{label} does not report PROVEN")
    if payload.get("schema_version") != 2:
        raise ValueError(f"{label} is not a current replay-bound result artifact")
    if payload.get("mode") != FormalMode.PROVE.value:
        raise ValueError(f"{label} is not an unbounded prove result")
    if payload.get("cover_status") != CoverStatus.REACHED.value:
        raise ValueError(f"{label} does not have complete cover evidence")
    if payload.get("returncode") != 0 or payload.get("cover_returncode") != 0:
        raise ValueError(f"{label} does not record successful proof and cover exits")
    manifest_path = path.parent / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is missing its replay manifest") from exc
    if not isinstance(manifest, dict):
        raise ValueError(f"{label} replay manifest must be a JSON object")
    if payload.get("manifest_sha256") != _sha256(manifest_path):
        raise ValueError(f"{label} is not bound to its replay manifest")
    _verify_manifest_artifacts(path.parent, manifest, label)
    if not isinstance(manifest.get("interface_contract"), dict):
        raise ValueError(f"{label} predates mandatory DUT/property interface checking")
    if manifest.get("checker") != payload.get("checker"):
        raise ValueError(f"{label} checker is not bound to its replay manifest")
    property_entry = manifest.get("property")
    if not isinstance(property_entry, dict) or payload.get("property_sha256") != property_entry.get(
        "sha256"
    ):
        raise ValueError(f"{label} is not bound to its property input")
    replay_commands = payload.get("replay_commands")
    if replay_commands != [
        ["sby", "-f", "formal.sby"],
        ["sby", "-f", "formal_cover.sby"],
    ]:
        raise ValueError(f"{label} does not declare deterministic replay commands")
    for key, hash_key in (
        ("log_path", "log_sha256"),
        ("cover_log_path", "cover_log_sha256"),
    ):
        relative = payload.get(key)
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"{label} is missing {key}")
        log_path = (path.parent / relative).resolve()
        try:
            log_path.relative_to(path.parent.resolve())
        except ValueError as exc:
            raise ValueError(f"{label} {key} escapes its replay bundle") from exc
        if not log_path.is_file() or _PASS_RE.search(
            log_path.read_text(encoding="utf-8", errors="replace")
        ) is None:
            raise ValueError(f"{label} {key} does not contain PASS evidence")
        if payload.get(hash_key) != _sha256(log_path):
            raise ValueError(f"{label} {key} hash does not match")
    payload["_verified_manifest"] = manifest
    return payload


def _validate_decomposition_certificate(
    certificate: Path,
    *,
    config: FormalRunConfig,
    expected_original_property_sha256: str | None = None,
    expected_dut_source_sha256s: tuple[str, ...] | None = None,
) -> _ValidatedDecomposition:
    """Validate every decomposition claim against files and proof artifacts."""
    original_property_sha256 = (
        expected_original_property_sha256
        if expected_original_property_sha256 is not None
        else _sha256(config.property_file)
    )
    dut_source_sha256s = (
        expected_dut_source_sha256s
        if expected_dut_source_sha256s is not None
        else tuple(_sha256(source) for source in config.dut_sources)
    )
    expected_context: dict[str, object] = {
        "top": config.top,
        "clock": config.clock,
        "reset": config.reset,
        "mode": FormalMode.PROVE.value,
        "attempt_mode": config.attempt_mode.value,
        "logic_semantics": config.logic_semantics.value,
        "fairness_signals": list(config.fairness_signals),
    }

    def require_context(result: dict[str, Any], label: str) -> None:
        manifest = result.get("_verified_manifest")
        manifest_config = manifest.get("config") if isinstance(manifest, dict) else None
        if not isinstance(manifest_config, dict) or any(
            manifest_config.get(key) != value for key, value in expected_context.items()
        ):
            raise ValueError(
                f"{label} formal context does not match current top, clock, reset, "
                "prove mode, attempt model, logic semantics, and fairness assumptions"
            )

    def require_dut_inputs(result: dict[str, Any], label: str) -> None:
        manifest = result.get("_verified_manifest")
        raw_sources = manifest.get("dut_sources") if isinstance(manifest, dict) else None
        if (
            not isinstance(raw_sources, list)
            or not all(isinstance(entry, dict) for entry in raw_sources)
            or [entry.get("sha256") for entry in raw_sources]
            != list(dut_source_sha256s)
        ):
            raise ValueError(f"{label} DUT inputs do not match current inputs")

    try:
        payload = json.loads(certificate.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid decomposition certificate: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 2:
        raise ValueError("decomposition certificate requires schema_version 2")
    relation = payload.get("relation")
    if relation not in {"equivalent", "stronger"}:
        raise ValueError("decomposition relation must be equivalent or stronger")
    claimed_original = _require_sha256(
        payload.get("original_property_sha256"), "original property hash"
    )
    if claimed_original != original_property_sha256:
        raise ValueError("decomposition original property hash does not match input")
    claimed_dut_hashes = payload.get("dut_source_sha256s")
    if claimed_dut_hashes != list(dut_source_sha256s):
        raise ValueError("decomposition DUT source hashes do not match current inputs")
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
    relation_result = _require_proven_artifact(
        relation_proof_path, "decomposition relation proof artifact"
    )
    require_context(relation_result, "decomposition relation proof artifact")
    require_dut_inputs(relation_result, "decomposition relation proof artifact")
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
        proof_result = _require_proven_artifact(
            proof_path, f"proof artifact for {identifier}"
        )
        require_context(proof_result, f"proof artifact for {identifier}")
        require_dut_inputs(proof_result, f"proof artifact for {identifier}")
        if proof_result.get("property_sha256") != property_sha256:
            raise ValueError(f"proof artifact is not bound to {identifier}")
        if proof_result.get("checker") != checker:
            raise ValueError(f"proof artifact checker does not match for {identifier}")
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
    expected_subproperty_hashes = [member.property_sha256 for member in members]
    if (
        relation_result.get("relation") != relation
        or relation_result.get("original_property_sha256") != claimed_original
        or relation_result.get("subproperty_sha256s") != expected_subproperty_hashes
        or relation_result.get("checker") != relation_checker
        or relation_result.get("dut_source_sha256s") != list(dut_source_sha256s)
    ):
        raise ValueError("relation proof artifact is not bound to this decomposition")
    return _ValidatedDecomposition(
        relation=relation,
        original_property_sha256=claimed_original,
        dut_source_sha256s=dut_source_sha256s,
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


def _result_binding(
    bundle: Path,
    manifest: dict[str, Any],
    checker: str,
    replay_commands: tuple[tuple[str, ...], ...] = (
        ("sby", "-f", "formal.sby"),
        ("sby", "-f", "formal_cover.sby"),
    ),
) -> dict[str, Any]:
    if manifest.get("checker") != checker:
        raise ValueError("formal manifest checker does not match result binding")
    property_entry = manifest.get("property")
    property_sha256 = (
        str(property_entry.get("sha256", ""))
        if isinstance(property_entry, dict)
        else ""
    )
    return {
        "manifest_sha256": _sha256(bundle / "manifest.json"),
        "property_sha256": property_sha256,
        "checker": checker,
        "replay_commands": replay_commands,
    }


def _manifest_artifacts(value: object) -> Iterator[tuple[str, str]]:
    """Yield every path/hash artifact pair in a manifest value."""
    if isinstance(value, dict):
        path = value.get("path")
        sha256 = value.get("sha256")
        if isinstance(path, str) and isinstance(sha256, str):
            yield path, sha256
        for child in value.values():
            yield from _manifest_artifacts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _manifest_artifacts(child)


def _verify_manifest_artifacts(
    bundle_dir: Path,
    manifest: dict[str, Any],
    label: str = "formal evidence",
) -> None:
    bundle = bundle_dir.resolve()
    for relative, expected_sha256 in _manifest_artifacts(manifest):
        artifact = (bundle / relative).resolve()
        try:
            artifact.relative_to(bundle)
        except ValueError as exc:
            raise ValueError(f"{label} artifact escapes its bundle: {relative}") from exc
        if not artifact.is_file():
            raise ValueError(f"{label} artifact is missing: {relative}")
        if _sha256(artifact) != expected_sha256:
            raise ValueError(f"{label} artifact hash changed: {relative}")


def _verify_evidence_integrity(evidence: FormalEvidence) -> None:
    """Rehash every declared proof input immediately before solver execution."""
    manifest_path = evidence.bundle_dir / "manifest.json"
    try:
        disk_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("formal manifest is missing or invalid before replay") from exc
    if disk_manifest != evidence.manifest:
        raise ValueError("formal manifest changed after bundle construction")
    _verify_manifest_artifacts(evidence.bundle_dir, disk_manifest, "formal replay")

    property_entry = disk_manifest.get("property")
    property_path = property_entry.get("path") if isinstance(property_entry, dict) else None
    yosys_inputs = disk_manifest.get("yosys_inputs")
    if not isinstance(yosys_inputs, list) or not all(
        isinstance(item, str) for item in yosys_inputs
    ):
        raise ValueError("formal manifest has invalid Yosys input inventory")
    if isinstance(property_path, str) and property_path in yosys_inputs:
        raise ValueError("original SVA property appears in Yosys inputs")


def _manifest_input_hashes(
    manifest: dict[str, Any],
) -> tuple[str, tuple[str, ...]]:
    """Return strictly validated property and ordered DUT hashes."""
    property_entry = manifest.get("property")
    if not isinstance(property_entry, dict):
        raise ValueError("formal manifest is missing its property input")
    property_sha256 = _require_sha256(
        property_entry.get("sha256"), "formal manifest property hash"
    )
    raw_dut_sources = manifest.get("dut_sources")
    if not isinstance(raw_dut_sources, list) or not all(
        isinstance(entry, dict) for entry in raw_dut_sources
    ):
        raise ValueError("formal manifest has invalid DUT source inventory")
    dut_source_sha256s = tuple(
        _require_sha256(entry.get("sha256"), "formal manifest DUT source hash")
        for entry in raw_dut_sources
    )
    if not dut_source_sha256s:
        raise ValueError("formal manifest requires at least one DUT source")
    return property_sha256, dut_source_sha256s


def _materialize_decomposition(
    bundle: Path,
    decomposition: _ValidatedDecomposition,
) -> dict[str, str]:
    """Copy verified inputs under stable names and emit a path-sanitized certificate."""
    def copy_replay_bundle(result_path: Path, relative_dir: str) -> str:
        source_dir = result_path.parent.resolve()
        target = bundle / relative_dir
        target.mkdir(parents=True, exist_ok=True)
        manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("decomposition replay manifest must be a JSON object")
        shutil.copyfile(source_dir / "manifest.json", target / "manifest.json")
        shutil.copyfile(result_path, target / "result.json")
        for artifact_path, _artifact_sha256 in _manifest_artifacts(manifest):
            source = (source_dir / artifact_path).resolve()
            source.relative_to(source_dir)
            destination = target / artifact_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        result_payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not isinstance(result_payload, dict):
            raise ValueError("decomposition replay result must be a JSON object")
        for key in ("log_path", "cover_log_path"):
            log_relative = result_payload.get(key)
            if isinstance(log_relative, str) and log_relative:
                source = (source_dir / log_relative).resolve()
                source.relative_to(source_dir)
                destination = target / log_relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        for trace_relative in result_payload.get("trace_paths", []):
            if isinstance(trace_relative, str):
                source = (source_dir / trace_relative).resolve()
                source.relative_to(source_dir)
                destination = target / trace_relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
        return (Path(relative_dir) / "result.json").relative_to("evidence").as_posix()

    members: list[dict[str, Any]] = []
    target_dir = bundle / "evidence" / "decomposition"
    target_dir.mkdir(parents=True, exist_ok=True)
    relation_relative = copy_replay_bundle(
        decomposition.relation_proof_artifact_path,
        "evidence/decomposition/relation_bundle",
    )
    for index, member in enumerate(decomposition.members):
        property_suffix = member.property_path.suffix or ".sv"
        property_bundle_relative = (
            f"evidence/decomposition/subproperty_{index:03d}{property_suffix}"
        )
        property_relative = Path(property_bundle_relative).relative_to("evidence").as_posix()
        proof_relative = copy_replay_bundle(
            member.proof_artifact_path,
            f"evidence/decomposition/proof_bundle_{index:03d}",
        )
        property_target = bundle / property_bundle_relative
        shutil.copyfile(member.property_path, property_target)
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
        "schema_version": 2,
        "relation": decomposition.relation,
        "relation_status": FormalStatus.PROVEN.value,
        "relation_checker": decomposition.relation_checker,
        "relation_proof_artifact_path": relation_relative,
        "relation_proof_artifact_sha256": (
            decomposition.relation_proof_artifact_sha256
        ),
        "original_property_sha256": decomposition.original_property_sha256,
        "dut_source_sha256s": list(decomposition.dut_source_sha256s),
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
    if isinstance(node, (sva_ir.PropEventually, sva_ir.PropStrongUntil)):
        return PropertyClass.LIVENESS
    if isinstance(node, sva_ir.PropLocalCapture):
        return PropertyClass.FINITE_VERDICT
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
    local_witness = lower_local_capture(
        node,
        label=label,
        original_text=original_text,
        clock_signal=clock.signal,
        clock_edge=clock.edge,
    )
    if local_witness is not None:
        if config.attempt_mode is AttemptMode.MONITOR:
            raise UnsupportedConstruct(
                message=(
                    "local-variable capture is formal-only and requires the "
                    "symbolic-witness attempt model"
                ),
                construct_name="local-variable monitor synthesis",
                source_loc=node.source_loc,
            )
        return FormalCompilation(
            checker=local_witness,
            property_class=PropertyClass.FINITE_VERDICT,
            backend="symbolic-witness-local",
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
    live = lower_liveness_property(
        node,
        label=label,
        original_text=original_text,
        clock_signal=clock.signal,
        clock_edge=clock.edge,
    )
    if live is not None:
        if config.mode is FormalMode.BMC:
            raise ValueError(
                "true liveness requires --mode prove with a live engine; "
                "a bounded BMC PASS cannot discharge eventuality"
            )
        return FormalCompilation(
            checker=live,
            property_class=PropertyClass.LIVENESS,
            backend="open-live-suprove",
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
    if property_class is PropertyClass.UNSUPPORTED:
        select_formal_backend(property_class)
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


def render_local_witness_bind(
    checker: CheckerNode,
    *,
    top: str,
    clock: str,
    reset: str,
) -> str:
    """Render the restricted per-attempt scalar local capture proof harness."""
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
    guard = checker.params["capture_guard_expr"]
    capture = checker.params["capture_value_expr"]
    condition = checker.params["condition_expr"]
    disable = checker.params["disable_expr"]
    delay = int(checker.params["delay_cycles"])
    counter_width = int(checker.params["counter_width"])
    return (
        "// Generated restricted per-attempt local-variable witness harness.\n"
        "module sva2rtl_formal_bind (\n"
        + ",\n".join(port_lines)
        + "\n);\n"
        f"    localparam integer DELAY_CYCLES = {delay};\n"
        "    (* anyseq *) logic witness_select;\n"
        "    logic formal_past_valid = 1'b0;\n"
        "    logic tracking_q = 1'b0;\n"
        "    logic captured_q = 1'b0;\n"
        f"    logic [{counter_width - 1}:0] age_q = '0;\n"
        f"    wire witness_start = !tracking_q && !({disable}) && "
        f"({antecedent}) && witness_select;\n\n"
        f"    always @({edge} {clock}) begin\n"
        "        formal_past_valid <= 1'b1;\n"
        "        if (!formal_past_valid) begin\n"
        f"            assume (!{reset});\n"
        "            tracking_q <= 1'b0;\n"
        "            captured_q <= 1'b0;\n"
        "            age_q <= '0;\n"
        "        end else begin\n"
        f"            assume ({reset});\n"
        f"            cover ({antecedent});\n"
        "            cover (witness_start);\n"
        f"            if ({disable}) begin\n"
        "                tracking_q <= 1'b0;\n"
        "                captured_q <= 1'b0;\n"
        "                age_q <= '0;\n"
        "            end else if (witness_start) begin\n"
        f"                assert ({guard});\n"
        f"                captured_q <= {capture};\n"
        "                tracking_q <= 1'b1;\n"
        "                age_q <= '0;\n"
        "            end else if (tracking_q) begin\n"
        "                age_q <= age_q + 1'b1;\n"
        "                if (age_q + 1'b1 >= DELAY_CYCLES) begin\n"
        f"                    assert ({condition});\n"
        f"                    cover ({condition});\n"
        "                    tracking_q <= 1'b0;\n"
        "                end\n"
        "            end\n"
        "        end\n"
        "    end\n"
        "endmodule\n\n"
        f"bind {top} sva2rtl_formal_bind u_sva2rtl_formal_bind (\n"
        + ",\n".join(bind_connections)
        + "\n);\n"
    )


def render_liveness_bind(
    checker: CheckerNode,
    *,
    top: str,
    clock: str,
    reset: str,
    fairness_signals: tuple[str, ...] = (),
) -> str:
    """Render formal-only Yosys live/fair primitives and safety obligations."""
    for identifier in (top, clock, reset, *fairness_signals):
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
    fairness_ports = [f"fair_{index}" for index in range(len(fairness_signals))]
    port_lines.extend(f"    input logic {port}" for port in fairness_ports)
    bind_connections = [f"    .{clock}({clock})", f"    .{reset}({reset})"]
    bind_connections.extend(f"    .{port}({signal})" for port, signal in observed)
    bind_connections.extend(
        f"    .{port}({signal})"
        for port, signal in zip(fairness_ports, fairness_signals, strict=True)
    )
    edge = checker.params["clock_edge"]
    antecedent = checker.params["antecedent_expr"]
    eventual = checker.params["eventual_expr"]
    disable = checker.params["disable_expr"]
    safety = checker.params["safety_expr"]
    uses_witness = checker.params["uses_witness"] == "1"
    start_offset = int(checker.params["start_offset"])

    declarations = ""
    sequential = ""
    if uses_witness:
        declarations = (
            "    (* anyseq *) logic witness_select;\n"
            "    logic pending_q = 1'b0;\n"
            "    logic armed_q = 1'b0;\n"
            f"    wire witness_start = !pending_q && !armed_q && !({disable}) "
            f"&& ({antecedent}) && witness_select;\n"
        )
        live_expression = f"(({disable}) || ({eventual}) || (!pending_q && !armed_q))"
        start_logic = (
            "                armed_q <= 1'b1;\n"
            if start_offset == 1
            else (
                f"                if (!({eventual}))\n"
                "                    pending_q <= 1'b1;\n"
            )
        )
        sequential = (
            f"            cover ({antecedent});\n"
            "            cover (witness_start);\n"
            f"            cover ({eventual});\n"
            f"            if ({disable}) begin\n"
            "                pending_q <= 1'b0;\n"
            "                armed_q <= 1'b0;\n"
            "            end else begin\n"
            f"                if (pending_q && ({eventual}))\n"
            "                    pending_q <= 1'b0;\n"
            "                if (armed_q) begin\n"
            "                    armed_q <= 1'b0;\n"
            f"                    if (!({eventual}))\n"
            "                        pending_q <= 1'b1;\n"
            "                end\n"
            "                if (witness_start) begin\n"
            + start_logic
            + "                end\n"
            "            end\n"
        )
    else:
        live_expression = f"(({disable}) || ({eventual}))"
        sequential = f"            cover ({eventual});\n"

    safety_logic = ""
    if safety:
        safety_logic = (
            "            // strong-until safety obligation\n"
            f"            if (!({disable})) assert ({safety});\n"
        )
    fairness_cells = "".join(
        r"    \$fair fair_obligation_"
        f"{index} (.A({port}), .EN(formal_past_valid && {reset}));\n"
        for index, port in enumerate(fairness_ports)
    )
    fairness_covers = "".join(
        f"            cover ({port});\n" for port in fairness_ports
    )

    return (
        "// Generated open-formal liveness harness. Original SVA is absent.\n"
        "(* blackbox *) module \\$live (input A, input EN); endmodule\n"
        + (
            "(* blackbox *) module \\$fair (input A, input EN); endmodule\n"
            if fairness_ports
            else ""
        )
        + "module sva2rtl_formal_bind (\n"
        + ",\n".join(port_lines)
        + "\n);\n"
        "    logic formal_past_valid = 1'b0;\n"
        + declarations
        + f"    wire live_condition = {live_expression};\n"
        r"    \$live eventual_discharge "
        f"(.A(live_condition), .EN(formal_past_valid && {reset}));\n"
        + fairness_cells
        + "\n"
        + f"    always @({edge} {clock}) begin\n"
        "        formal_past_valid <= 1'b1;\n"
        "        if (!formal_past_valid) begin\n"
        f"            assume (!{reset});\n"
        + ("            pending_q <= 1'b0;\n" if uses_witness else "")
        + ("            armed_q <= 1'b0;\n" if uses_witness else "")
        + "        end else begin\n"
        f"            assume ({reset});\n"
        + safety_logic
        + sequential
        + fairness_covers
        + "        end\n"
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
    engine_line: str | None = None,
    formal_primitives: bool = False,
    fairness_primitives: bool = False,
) -> str:
    selected_mode = mode or config.mode.value
    selected_engine = engine_line or f"{config.engine} {config.solver}".rstrip()
    source_args = " ".join(consumed_files)
    depth_line = "" if selected_mode == "live" else f"depth {config.depth}\n"
    multiclock = "multiclock on\n" if selected_mode == "live" else ""
    primitive_cleanup = "delete =\\$live\n" if formal_primitives else ""
    if fairness_primitives:
        primitive_cleanup += "delete =\\$fair\n"
    return (
        "[options]\n"
        f"mode {selected_mode}\n"
        f"{depth_line}"
        f"{multiclock}"
        "wait on\n\n"
        "[engines]\n"
        f"{selected_engine}\n\n"
        "[script]\n"
        "plugin -i slang\n"
        f"read_slang --top {config.top} {source_args}\n"
        f"{primitive_cleanup}"
        f"prep -top {config.top}\n\n"
        "[files]\n"
        + "\n".join(consumed_files)
        + "\n"
    )


def _decomposition_input_paths(
    config: FormalRunConfig,
    decomposition: _ValidatedDecomposition | None = None,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    if config.decomposition_certificate is not None:
        paths.append(config.decomposition_certificate)
    if decomposition is not None:
        paths.append(decomposition.relation_proof_artifact_path)
        for member in decomposition.members:
            paths.extend((member.property_path, member.proof_artifact_path))
    return tuple(paths)


def _prepare_output(
    config: FormalRunConfig,
    *,
    decomposition: _ValidatedDecomposition | None = None,
) -> Path:
    output = config.output_dir.resolve()
    source_paths = tuple(
        source.resolve()
        for source in (
            *config.dut_sources,
            config.property_file,
            *_decomposition_input_paths(config, decomposition),
        )
    )
    filesystem_root = Path(output.anchor).resolve()
    dangerous_exact = {filesystem_root, Path.cwd().resolve(), Path.home().resolve()}
    if output in dangerous_exact:
        raise ValueError(f"refusing dangerous formal evidence output directory: {output}")
    for source in source_paths:
        if output == source or output in source.parents:
            raise ValueError(
                f"formal evidence output {output} contains input source {source}; "
                "choose a dedicated leaf directory"
            )
    if output.exists():
        if not output.is_dir():
            raise FileExistsError(
                f"formal evidence output exists and is not a directory: {output}"
            )
        nonempty = any(output.iterdir())
        if nonempty and not config.force:
            raise FileExistsError(
                f"formal evidence directory is not empty: {output}; use --force"
            )
        if config.force:
            marker = output / _EVIDENCE_MARKER
            if nonempty and (
                not marker.is_file()
                or marker.read_text(encoding="utf-8") != _EVIDENCE_MARKER_TEXT
            ):
                raise FileExistsError(
                    f"refusing --force for unmarked directory: {output}; only a "
                    "previous sva2rtl formal evidence directory can be replaced"
                )
            if nonempty:
                shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    _write_text(output / _EVIDENCE_MARKER, _EVIDENCE_MARKER_TEXT)
    return output


def _build_verified_decomposition_bundle(
    config: FormalRunConfig,
    decomposition: _ValidatedDecomposition,
    original_error: UnsupportedConstruct,
) -> FormalEvidence:
    """Aggregate replay-bound proofs when the original shape is unsupported."""
    if config.mode is not FormalMode.PROVE:
        raise ValueError("verified decomposition aggregation requires --mode prove")
    bundle = _prepare_output(config, decomposition=decomposition)
    evidence_dir = bundle / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    property_copy = evidence_dir / "property.sv"
    shutil.copyfile(config.property_file, property_copy)
    dut_manifest: list[dict[str, str]] = []
    for index, source in enumerate(config.dut_sources):
        relative = f"evidence/dut_{index:03d}.sv"
        copied = bundle / relative
        shutil.copyfile(source, copied)
        dut_manifest.append({"path": relative, "sha256": _sha256(copied)})
    decomposition_entry = _materialize_decomposition(bundle, decomposition)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "backend": "verified-decomposition",
        "checker": decomposition.relation_checker,
        "property_class": PropertyClass.UNSUPPORTED.value,
        "config": {
            "top": config.top,
            "property": config.property_name,
            "clock": config.clock,
            "reset": config.reset,
            "mode": config.mode.value,
            "attempt_mode": config.attempt_mode.value,
            "logic_semantics": config.logic_semantics.value,
            "fairness_signals": list(config.fairness_signals),
        },
        "property": {
            "path": "evidence/property.sv",
            "sha256": _sha256(property_copy),
        },
        "dut_sources": dut_manifest,
        "decomposition": decomposition_entry,
        "original_boundary": {
            "construct": original_error.construct_name,
            "message": original_error.message,
        },
        "yosys_inputs": [],
        "assumptions": [
            "final result depends on replay-bound subproperty proofs and a "
            "human-reviewed relation property whose proof bundle is bound here"
        ],
        "covers": [
            "every imported subproperty proof and relation proof records REACHED cover"
        ],
    }
    _write_json(bundle / "manifest.json", manifest)
    binding = _result_binding(
        bundle,
        manifest,
        decomposition.relation_checker,
        replay_commands=(),
    )
    initial = FormalResult(
        status=FormalStatus.UNKNOWN,
        mode=config.mode,
        message="verified decomposition bundle compiled but not yet aggregated",
        returncode=None,
        duration_seconds=0.0,
        tool_versions={},
        log_path="",
        **binding,
    )
    _write_json(bundle / "result.json", initial.to_dict())
    return FormalEvidence(
        bundle,
        config,
        decomposition.relation_checker,
        PropertyClass.UNSUPPORTED,
        manifest,
    )


def build_formal_bundle(config: FormalRunConfig) -> FormalEvidence:
    """Compile and write one replayable, source-isolated formal project."""
    decomposition = None
    if config.decomposition_certificate is not None:
        decomposition = _validate_decomposition_certificate(
            config.decomposition_certificate,
            config=config,
        )
    try:
        compilation = _compile_checker(config)
    except UnsupportedConstruct as exc:
        if decomposition is None:
            raise
        return _build_verified_decomposition_bundle(config, decomposition, exc)
    checker = compilation.checker
    property_class = compilation.property_class
    backend = compilation.backend
    interface_contract = _validate_dut_contract(config, checker)
    bundle = _prepare_output(config, decomposition=decomposition)

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
        if backend
        in {
            "direct-invariant-safety",
            "symbolic-witness-safety",
            "symbolic-witness-local",
            "open-live-suprove",
        }
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
    elif backend == "symbolic-witness-local":
        bind_text = render_local_witness_bind(
            checker,
            top=config.top,
            clock=config.clock,
            reset=config.reset,
        )
    elif backend == "open-live-suprove":
        bind_text = render_liveness_bind(
            checker,
            top=config.top,
            clock=config.clock,
            reset=config.reset,
            fairness_signals=config.fairness_signals,
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
    if backend == "open-live-suprove":
        formal_sby_text = _render_sby(
            config,
            tuple(consumed),
            mode="live",
            engine_line="aiger suprove",
            formal_primitives=True,
            fairness_primitives=bool(config.fairness_signals),
        )
    else:
        formal_sby_text = _render_sby(config, tuple(consumed))
    _write_text(bundle / "formal.sby", formal_sby_text)
    _write_text(
        bundle / "formal_cover.sby",
        _render_sby(
            config,
            tuple(consumed),
            mode="cover",
            formal_primitives=backend == "open-live-suprove",
            fairness_primitives=bool(config.fairness_signals),
        ),
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
    fairness_path = bundle / "evidence" / "fairness.json"
    _write_json(
        fairness_path,
        {
            "schema_version": 1,
            "assumptions": [
                {
                    "kind": "user/model-assumption",
                    "semantics": f"GF({signal})",
                    "signal": signal,
                }
                for signal in config.fairness_signals
            ],
        },
    )
    semantic_profile_path = bundle / "evidence" / "semantic_profile.json"
    _write_json(
        semantic_profile_path,
        {
            "schema_version": 1,
            "logic_semantics": config.logic_semantics.value,
            "x_z_semantics": "unsupported",
            "clock_semantics": "single-clock",
            "local_variable_semantics": "restricted-symbolic-witness-only",
        },
    )
    interface_contract_path = bundle / "evidence" / "interface_contract.json"
    _write_json(interface_contract_path, interface_contract)
    live_info = discover_live_backend(config) if backend == "open-live-suprove" else None

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "backend": backend,
        "checker": checker.module_name,
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
            "logic_semantics": config.logic_semantics.value,
            "fairness_signals": list(config.fairness_signals),
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
        "fairness": {
            "path": "evidence/fairness.json",
            "sha256": _sha256(fairness_path),
        },
        "semantic_profile": {
            "path": "evidence/semantic_profile.json",
            "sha256": _sha256(semantic_profile_path),
        },
        "interface_contract": {
            "path": "evidence/interface_contract.json",
            "sha256": _sha256(interface_contract_path),
        },
        "yosys_inputs": consumed,
        "assumptions": [
            "reset is asserted on the first sampled cycle",
            "reset is deasserted on every later sampled cycle",
        ]
        + [
            f"user/model fairness assumption: GF({signal})"
            for signal in config.fairness_signals
        ]
        + (
            []
            if backend
            in {
                "direct-invariant-safety",
                "symbolic-witness-safety",
                "symbolic-witness-local",
                "open-live-suprove",
            }
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
                if backend in {"symbolic-witness-safety", "symbolic-witness-local"}
                else (
                    "liveness antecedent, selection, discharge, and fairness signals "
                    "are reachable"
                    if backend == "open-live-suprove"
                    else "monitor attempt_fired becomes reachable after reset"
                )
            )
        ],
    }
    if live_info is not None:
        manifest["live_engine"] = {
            "name": "suprove",
            "sby_mode": "live",
            "engine": "aiger suprove",
            "available": live_info.available,
            "executable": Path(live_info.path).name if live_info.path else "suprove",
            "version": live_info.version,
            "guidance": live_info.guidance,
        }
        manifest["obligations"] = (
            ["weak-until-safety", "eventual-discharge"]
            if checker.params["obligation_kind"] == "strong-until"
            else ["eventual-discharge"]
        )
    if decomposition is not None:
        manifest["decomposition"] = _materialize_decomposition(bundle, decomposition)
    _write_json(bundle / "manifest.json", manifest)
    binding = _result_binding(bundle, manifest, checker.module_name)
    initial = FormalResult(
        status=FormalStatus.UNKNOWN,
        mode=config.mode,
        message="formal bundle compiled but not yet executed",
        returncode=None,
        duration_seconds=0.0,
        tool_versions={},
        log_path="sby.log",
        **binding,
    )
    _write_json(bundle / "result.json", initial.to_dict())
    return FormalEvidence(bundle, config, checker.module_name, property_class, manifest)


def write_unsupported_evidence(
    config: FormalRunConfig,
    error: UnsupportedConstruct,
) -> Path:
    """Persist a sanitized, machine-readable unsupported semantic boundary."""
    bundle = _prepare_output(config)
    evidence_dir = bundle / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    property_copy = evidence_dir / "property.sv"
    shutil.copyfile(config.property_file, property_copy)
    dut_manifest: list[dict[str, str]] = []
    for index, source in enumerate(config.dut_sources):
        relative = f"dut_{index:03d}.sv"
        copied = bundle / relative
        shutil.copyfile(source, copied)
        dut_manifest.append({"path": relative, "sha256": _sha256(copied)})

    profile_path = evidence_dir / "semantic_profile.json"
    _write_json(
        profile_path,
        {
            "schema_version": 1,
            "logic_semantics": config.logic_semantics.value,
            "x_z_semantics": "unsupported",
            "clock_semantics": "single-clock",
            "local_variable_semantics": "restricted-symbolic-witness-only",
        },
    )
    location = ""
    if error.source_loc is not None:
        location = (
            f"evidence/property.sv:{error.source_loc.line}:"
            f"{error.source_loc.col}: "
        )
    message = (
        f"{location}error SVA-E002: unsupported construct "
        f"'{error.construct_name}': {error.message}"
    )
    boundary = {
        "construct": error.construct_name,
        "message": message,
        "remediation": (
            "Split multi-clock properties by named domain and verify a reviewed "
            "sampled handoff, remove X/Z dependence or use an explicit four-state "
            "frontend, expose a reviewed one-dimensional packed alias for "
            "unsupported array/aggregate signal types, or rewrite locals into the "
            "documented restricted capture shape."
        ),
    }
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "backend": "unsupported-boundary",
        "checker": "unsupported-boundary",
        "property_class": PropertyClass.UNSUPPORTED.value,
        "status": FormalStatus.UNSUPPORTED.value,
        "config": {
            "top": config.top,
            "property": config.property_name,
            "clock": config.clock,
            "reset": config.reset,
            "mode": config.mode.value,
            "logic_semantics": config.logic_semantics.value,
        },
        "property": {
            "path": "evidence/property.sv",
            "sha256": _sha256(property_copy),
        },
        "dut_sources": dut_manifest,
        "semantic_profile": {
            "path": "evidence/semantic_profile.json",
            "sha256": _sha256(profile_path),
        },
        "boundary": boundary,
        "yosys_inputs": [],
        "assumptions": [],
        "covers": [],
    }
    _write_json(bundle / "manifest.json", manifest)
    binding = _result_binding(bundle, manifest, "unsupported-boundary")
    result = FormalResult(
        status=FormalStatus.UNSUPPORTED,
        mode=config.mode,
        message=message,
        returncode=None,
        duration_seconds=0.0,
        tool_versions={"slang": _probe_version([config.slang_path, "--version"])},
        log_path="",
        replay_commands=(),
        manifest_sha256=binding["manifest_sha256"],
        property_sha256=binding["property_sha256"],
        checker=binding["checker"],
    )
    result_path = bundle / "result.json"
    _write_json(result_path, result.to_dict())
    return result_path


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


def classify_live_result(
    *,
    returncode: int,
    output: str,
    timed_out: bool = False,
) -> tuple[FormalStatus, str]:
    """Classify only a real unbounded live task as liveness proof evidence."""
    if timed_out:
        return FormalStatus.TIMEOUT, "unbounded liveness run exceeded the timeout"
    if _FAIL_RE.search(output):
        return FormalStatus.FAILED, "live engine found a liveness counterexample"
    if returncode == 0 and _PASS_RE.search(output):
        return FormalStatus.PROVEN, "unbounded liveness proof completed"
    return FormalStatus.ERROR, "live engine ended without an unambiguous result"


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


def discover_live_backend(config: FormalRunConfig) -> LiveBackendInfo:
    """Discover Super Prove without confusing SBY's ``--live`` output flag."""
    requested = config.suprove_path
    resolved = shutil.which(requested)
    if resolved is None:
        candidate = Path(requested)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            resolved = str(candidate.resolve())
    guidance = (
        "Install an OSS CAD Suite build containing Super Prove on Linux x64, "
        "or pass --suprove-path to a compatible executable. Bounded BMC can "
        "find bugs but cannot prove this unbounded liveness obligation."
    )
    if resolved is None:
        return LiveBackendInfo(
            available=False,
            path=requested,
            version="missing",
            guidance=guidance,
        )
    return LiveBackendInfo(
        available=True,
        path=resolved,
        version=_probe_version([resolved, "--version"]),
        guidance="qualified SBY mode live / aiger suprove path discovered",
    )


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
    command = [config.sby_path, "-f", project_file]
    if (
        evidence.manifest.get("backend") == "open-live-suprove"
        and project_file == "formal.sby"
    ):
        live_info = discover_live_backend(config)
        if live_info.available:
            command.extend(("--suprove", live_info.path))
    try:
        process = subprocess.Popen(  # noqa: S603 - argv is validated and shell is disabled
            command,
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
    _verify_evidence_integrity(evidence)
    config = evidence.config
    started = time.monotonic()
    if evidence.manifest.get("backend") == "verified-decomposition":
        decomposition_entry = evidence.manifest.get("decomposition")
        if not isinstance(decomposition_entry, dict) or not isinstance(
            decomposition_entry.get("path"), str
        ):
            raise ValueError("verified decomposition manifest is missing its certificate")
        property_sha256, dut_source_sha256s = _manifest_input_hashes(evidence.manifest)
        _validate_decomposition_certificate(
            evidence.bundle_dir / decomposition_entry["path"],
            config=config,
            expected_original_property_sha256=property_sha256,
            expected_dut_source_sha256s=dut_source_sha256s,
        )
        log_text = (
            "STATUS: PASSED\n"
            "Replay-bound subproperty proof bundles and the human-reviewed "
            "relation-model proof were integrity-validated.\n"
        )
        _write_text(evidence.bundle_dir / "aggregation.log", log_text)
        binding = _result_binding(
            evidence.bundle_dir,
            evidence.manifest,
            evidence.checker_module,
            replay_commands=(),
        )
        result = FormalResult(
            status=FormalStatus.PROVEN,
            mode=FormalMode.PROVE,
            message=(
                "unsupported original property discharged by replay-bound proven "
                "subproperties under a human-reviewed proven relation model"
            ),
            returncode=0,
            duration_seconds=time.monotonic() - started,
            tool_versions={"aggregator": "sva2rtl"},
            log_path="aggregation.log",
            trace_paths=_trace_paths(evidence.bundle_dir),
            cover_status=CoverStatus.REACHED,
            cover_returncode=0,
            cover_log_path="aggregation.log",
            log_sha256=_sha256(evidence.bundle_dir / "aggregation.log"),
            cover_log_sha256=_sha256(evidence.bundle_dir / "aggregation.log"),
            **binding,
        )
        _write_json(evidence.bundle_dir / "result.json", result.to_dict())
        return result
    is_live = evidence.manifest.get("backend") == "open-live-suprove"
    live_info = discover_live_backend(config) if is_live else None
    if live_info is not None and not live_info.available:
        returncode, output, timed_out = None, live_info.guidance, False
        status = FormalStatus.UNKNOWN
        message = f"live backend is unavailable: {live_info.guidance}"
    else:
        returncode, output, timed_out = _run_sby_process(evidence, "formal.sby")
    if live_info is None or live_info.available:
        if returncode is None:
            status = FormalStatus.ERROR
            message = f"missing dependency: {config.sby_path}"
        elif is_live:
            status, message = classify_live_result(
                returncode=returncode,
                output=output,
                timed_out=timed_out,
            )
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
    if status is FormalStatus.PROVEN or is_live:
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
        if status is FormalStatus.PROVEN and cover_status is not CoverStatus.REACHED:
            status = FormalStatus.UNKNOWN
            message = (
                "safety proof completed, but critical cover evidence is not "
                f"complete: {cover_message}"
            )
    binding = _result_binding(evidence.bundle_dir, evidence.manifest, evidence.checker_module)
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
        }
        | ({"suprove": live_info.version} if live_info is not None else {}),
        log_path="sby.log",
        trace_paths=_trace_paths(evidence.bundle_dir),
        cover_status=cover_status,
        cover_returncode=cover_returncode,
        cover_log_path=cover_log_path,
        log_sha256=_sha256(evidence.bundle_dir / "sby.log"),
        cover_log_sha256=(
            _sha256(evidence.bundle_dir / cover_log_path) if cover_log_path else ""
        ),
        **binding,
    )
    _write_json(evidence.bundle_dir / "result.json", result.to_dict())
    return result
