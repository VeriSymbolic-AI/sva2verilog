"""Source-level differential test case helpers.

This module is intentionally test-local.  It generates small, bounded SVA
source modules and routes them through the normal sva2rtl compiler pipeline so
differential tests validate the user-facing path instead of a direct IR shortcut.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hypothesis import strategies as st

from sva2rtl.ast_importer import import_all_assertions
from sva2rtl.behavioral_oracle import simulate_checker_hierarchy
from sva2rtl.composer import compose
from sva2rtl.emitter import emit_all
from sva2rtl.frontend import invoke_slang
from sva2rtl.ir import CheckerNode, ClockSpec, SVANode
from sva2rtl.normalizer import normalize
from sva2rtl.optimizer import optimize
from tests.simulation.tb_generator import (
    TEMPLATES_WITH_OVERFLOW,
    extra_inputs_from_checker,
    generate_testbench,
    run_simulation,
)

DEFAULT_SIGNALS: tuple[str, ...] = ("a", "b", "c")
SUPPORTED_FAMILIES: frozenset[str] = frozenset(
    {
        "bool",
        "structured_bool",
        "sampled",
        "past",
        "delay_fixed",
        "delay_range",
        "implication_overlap",
        "implication_nonoverlap",
        "rep_consecutive_fixed",
        "rep_consecutive_range",
        "disable_iff",
    }
)
DEFERRED_FAMILIES: frozenset[str] = frozenset(
    {
        "multi_clock",
        "unbounded_liveness",
        "local_variables",
        "arithmetic",
        "wide_part_select",
        "unsupported_zero_delay_rewrite",
    }
)
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_UNSAFE_METADATA_RE = re.compile(
    r"(/Users/|/home/|\\\\|[A-Za-z]:\\\\|token|password|secret|company)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DifferentialBudget:
    """Generation limits for a bounded differential profile."""

    name: str = "fast"
    min_trace_length: int = 6
    max_trace_length: int = 12
    max_expr_depth: int = 3
    max_temporal_depth: int = 2
    max_delay: int = 3
    max_range_width: int = 2
    max_repeat: int = 3
    include_disable: bool = True

    def __post_init__(self) -> None:
        if self.min_trace_length < 1:
            raise ValueError("min_trace_length must be positive")
        if self.max_trace_length < self.min_trace_length:
            raise ValueError("max_trace_length must be >= min_trace_length")
        if self.max_expr_depth < 0:
            raise ValueError("max_expr_depth must be non-negative")
        if self.max_temporal_depth < 0:
            raise ValueError("max_temporal_depth must be non-negative")
        if self.max_delay < 0:
            raise ValueError("max_delay must be non-negative")
        if self.max_range_width < 0:
            raise ValueError("max_range_width must be non-negative")
        if self.max_repeat < 1:
            raise ValueError("max_repeat must be positive")


DEFAULT_BUDGET = DifferentialBudget()
FAILURE_ARTIFACT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GeneratedSvaCase:
    """One generated source-level differential test case."""

    case_id: str
    module_name: str
    property_label: str
    assertion_expr: str
    source_text: str
    signal_names: tuple[str, ...]
    family_tags: tuple[str, ...]
    trace_length: int
    expects_overflow: bool = False
    budget_name: str = "fast"

    def __post_init__(self) -> None:
        for field_name in ("case_id", "module_name", "property_label"):
            value = str(getattr(self, field_name))
            if not _IDENT_RE.fullmatch(value):
                raise ValueError(f"{field_name} is not a safe SystemVerilog identifier")
            if _UNSAFE_METADATA_RE.search(value):
                raise ValueError(f"{field_name} contains unsafe metadata")

        if not self.signal_names:
            raise ValueError("signal_names must not be empty")
        if any(not _IDENT_RE.fullmatch(sig) for sig in self.signal_names):
            raise ValueError("all signal names must be safe identifiers")
        if any(family not in SUPPORTED_FAMILIES for family in self.family_tags):
            unsupported = sorted(set(self.family_tags) - SUPPORTED_FAMILIES)
            raise ValueError(f"unsupported generated families: {unsupported}")
        if set(self.family_tags) & DEFERRED_FAMILIES:
            raise ValueError("deferred families must not be generated")
        if self.trace_length < 1:
            raise ValueError("trace_length must be positive")

    def metadata(self) -> dict[str, object]:
        """Return stable, sanitized metadata used in diagnostics."""

        return {
            "case_id": self.case_id,
            "module_name": self.module_name,
            "property_label": self.property_label,
            "families": list(self.family_tags),
            "signals": list(self.signal_names),
            "trace_length": self.trace_length,
            "expects_overflow": self.expects_overflow,
            "budget": self.budget_name,
        }


@dataclass(frozen=True)
class CompiledGeneratedCase:
    """Compiler output for one generated SVA case."""

    case: GeneratedSvaCase
    node: SVANode
    clock: ClockSpec
    original_text: str
    checker: CheckerNode


@dataclass(frozen=True)
class CycleObservation:
    """One normalized observable checker output cycle."""

    cycle: int
    active: bool
    pass_value: bool
    fail: bool
    overflow: bool | None = None
    backend: str = "oracle"

    def as_dict(self) -> dict[str, bool | int | str | None]:
        """Return a JSON-serializable observation dictionary."""

        return {
            "cycle": self.cycle,
            "active": self.active,
            "pass": self.pass_value,
            "fail": self.fail,
            "overflow": self.overflow,
            "backend": self.backend,
        }


@dataclass(frozen=True)
class DifferentialMismatch:
    """First trace mismatch between the oracle and a backend."""

    case_id: str
    backend: str
    cycle: int
    signal: str
    expected: bool | None
    actual: bool | None
    source_text: str
    stimulus_slice: tuple[dict[str, bool], ...]
    oracle_observation: dict[str, bool | int | str | None] | None
    actual_observation: dict[str, bool | int | str | None] | None
    family_tags: tuple[str, ...]
    reason: str

    def as_dict(self) -> dict[str, object]:
        """Return a sanitized, JSON-serializable mismatch payload."""

        return {
            "case_id": self.case_id,
            "backend": self.backend,
            "cycle": self.cycle,
            "signal": self.signal,
            "expected": self.expected,
            "actual": self.actual,
            "source_text": self.source_text,
            "stimulus_slice": list(self.stimulus_slice),
            "oracle_observation": self.oracle_observation,
            "actual_observation": self.actual_observation,
            "family_tags": list(self.family_tags),
            "reason": self.reason,
        }

    def format_message(self) -> str:
        """Format a compact pytest failure message."""

        return (
            f"Differential mismatch for {self.case_id} on {self.backend}: "
            f"cycle={self.cycle} signal={self.signal} expected={self.expected} "
            f"actual={self.actual} reason={self.reason}\n"
            f"families={','.join(self.family_tags)}\n"
            f"stimulus_slice={list(self.stimulus_slice)!r}\n"
            f"oracle={self.oracle_observation!r}\n"
            f"actual={self.actual_observation!r}\n"
            f"source:\n{self.source_text}"
        )


@dataclass(frozen=True)
class DifferentialFailureArtifact:
    """Sanitized reproduction artifact for a differential mismatch."""

    schema_version: int
    case: dict[str, object]
    stimulus: list[dict[str, bool]]
    oracle_trace: list[dict[str, bool | int | str | None]]
    backend_trace: list[dict[str, bool | int | str | None]]
    mismatch: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        """Return the artifact as a deterministic JSON-ready dictionary."""

        return {
            "schema_version": self.schema_version,
            "case": self.case,
            "stimulus": self.stimulus,
            "oracle_trace": self.oracle_trace,
            "backend_trace": self.backend_trace,
            "mismatch": self.mismatch,
        }

    def to_json(self) -> str:
        """Serialize the artifact with stable formatting."""

        return json.dumps(self.as_dict(), indent=2, sort_keys=True) + "\n"


def stable_case_id(assertion_expr: str, families: tuple[str, ...], signals: tuple[str, ...]) -> str:
    """Create a deterministic path-free id from semantic case content."""

    payload = json.dumps(
        {
            "expr": assertion_expr,
            "families": sorted(families),
            "signals": signals,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]
    family = families[0] if families else "case"
    family_slug = re.sub(r"[^A-Za-z0-9_]", "_", family)
    return f"diff_{family_slug}_{digest}"


def render_source(
    *,
    module_name: str,
    property_label: str,
    assertion_expr: str,
    signal_names: tuple[str, ...],
    disable_condition: str | None = None,
) -> str:
    """Render a complete SystemVerilog module containing one assertion."""

    port_names = ("clk", "rst_n", *signal_names)
    if disable_condition is not None and disable_condition not in port_names:
        port_names = (*port_names, disable_condition)

    ports = ",\n    ".join(f"input logic {name}" for name in port_names)
    disable_prefix = f"disable iff ({disable_condition}) " if disable_condition else ""
    return (
        f"module {module_name}(\n"
        f"    {ports}\n"
        ");\n"
        f"  {property_label}: assert property (@(posedge clk) "
        f"{disable_prefix}{assertion_expr});\n"
        "endmodule\n"
    )


def make_generated_case(
    assertion_expr: str,
    family_tags: tuple[str, ...],
    signal_names: tuple[str, ...],
    *,
    trace_length: int = DEFAULT_BUDGET.min_trace_length,
    expects_overflow: bool = False,
    budget_name: str = DEFAULT_BUDGET.name,
    disable_condition: str | None = None,
) -> GeneratedSvaCase:
    """Construct a generated case with deterministic names and source text."""

    ordered_signals = tuple(dict.fromkeys(signal_names))
    if disable_condition is not None and disable_condition not in ordered_signals:
        ordered_signals = (*ordered_signals, disable_condition)
    case_id = stable_case_id(assertion_expr, family_tags, ordered_signals)
    module_name = f"{case_id}_mod"
    property_label = f"p_{case_id[5:]}"
    source_text = render_source(
        module_name=module_name,
        property_label=property_label,
        assertion_expr=assertion_expr,
        signal_names=ordered_signals,
        disable_condition=disable_condition,
    )
    return GeneratedSvaCase(
        case_id=case_id,
        module_name=module_name,
        property_label=property_label,
        assertion_expr=assertion_expr,
        source_text=source_text,
        signal_names=ordered_signals,
        family_tags=tuple(dict.fromkeys(family_tags)),
        trace_length=trace_length,
        expects_overflow=expects_overflow,
        budget_name=budget_name,
    )


def example_generated_cases() -> tuple[GeneratedSvaCase, ...]:
    """Small deterministic smoke catalog for source-level differential tests."""

    return (
        make_generated_case("(a && b)", ("bool", "structured_bool"), ("a", "b")),
        make_generated_case("$rose(a)", ("sampled",), ("a",)),
        make_generated_case("$past(a, 1)", ("past",), ("a",)),
        make_generated_case("a ##1 b", ("delay_fixed",), ("a", "b")),
        make_generated_case("a ##[1:2] b", ("delay_range",), ("a", "b")),
        make_generated_case("a |-> b", ("implication_overlap",), ("a", "b")),
        make_generated_case("a |=> b", ("implication_nonoverlap",), ("a", "b")),
        make_generated_case("a[*2]", ("rep_consecutive_fixed",), ("a",)),
        make_generated_case("a[*1:2]", ("rep_consecutive_range",), ("a",)),
        make_generated_case(
            "a",
            ("disable_iff", "bool"),
            ("a",),
            disable_condition="dis",
        ),
    )


def _leaf_exprs(signals: tuple[str, ...]) -> st.SearchStrategy[str]:
    leaves = [*signals, "1'b1", "1'b0"]
    return st.sampled_from(leaves)


def _bool_exprs(signals: tuple[str, ...], max_depth: int) -> st.SearchStrategy[str]:
    if max_depth <= 0:
        return _leaf_exprs(signals)

    return st.recursive(
        _leaf_exprs(signals),
        lambda children: st.one_of(
            children.map(lambda expr: f"!({expr})"),
            st.tuples(children, children).map(lambda pair: f"({pair[0]} && {pair[1]})"),
            st.tuples(children, children).map(lambda pair: f"({pair[0]} || {pair[1]})"),
        ),
        max_leaves=max(2, max_depth + 1),
    )


@st.composite
def generated_sva_cases(
    draw: st.DrawFn,
    budget: DifferentialBudget = DEFAULT_BUDGET,
) -> GeneratedSvaCase:
    """Hypothesis strategy for bounded supported SVA source cases."""

    signal_count = draw(st.integers(min_value=1, max_value=len(DEFAULT_SIGNALS)))
    signals = DEFAULT_SIGNALS[:signal_count]
    trace_length = draw(
        st.integers(min_value=budget.min_trace_length, max_value=budget.max_trace_length)
    )
    bool_expr = draw(_bool_exprs(signals, budget.max_expr_depth))
    second = signals[1] if len(signals) > 1 else signals[0]
    delay_hi = max(1, min(budget.max_delay, 3))
    range_hi = max(1, min(delay_hi, budget.max_range_width + 1))
    repeat_hi = max(1, min(budget.max_repeat, 3))

    families = [
        ("bool", bool_expr, ("bool", "structured_bool"), None),
        ("sampled", f"$rose({signals[0]})", ("sampled",), None),
        ("past", f"$past({signals[0]}, 1)", ("past",), None),
        (
            "delay_fixed",
            f"{signals[0]} ##{draw(st.integers(min_value=1, max_value=delay_hi))} {second}",
            ("delay_fixed",),
            None,
        ),
        (
            "delay_range",
            f"{signals[0]} ##[1:{range_hi}] {second}",
            ("delay_range",),
            None,
        ),
        ("overlap", f"{signals[0]} |-> {second}", ("implication_overlap",), None),
        ("nonoverlap", f"{signals[0]} |=> {second}", ("implication_nonoverlap",), None),
        (
            "rep_fixed",
            f"{signals[0]}[*{draw(st.integers(min_value=1, max_value=repeat_hi))}]",
            ("rep_consecutive_fixed",),
            None,
        ),
        (
            "rep_range",
            f"{signals[0]}[*1:{repeat_hi}]",
            ("rep_consecutive_range",),
            None,
        ),
    ]
    if budget.include_disable:
        families.append(("disable", bool_expr, ("disable_iff", "bool"), "dis"))

    _name, expr, tags, disable_condition = draw(st.sampled_from(families))
    case_signals = signals
    if disable_condition is not None:
        case_signals = (*signals, disable_condition)
    return make_generated_case(
        expr,
        tags,
        case_signals,
        trace_length=trace_length,
        budget_name=budget.name,
        disable_condition=disable_condition,
    )


def stimulus_input_names(
    case: GeneratedSvaCase,
    checker: CheckerNode | None = None,
) -> tuple[str, ...]:
    """Return deterministic per-cycle stimulus keys for a case or checker."""

    if checker is not None:
        return tuple(dict.fromkeys(extra_inputs_from_checker(checker)))
    return ("start", *case.signal_names)


def deterministic_stimulus(
    case: GeneratedSvaCase,
    checker: CheckerNode | None = None,
) -> list[dict[str, bool]]:
    """Create a bounded deterministic stimulus trace for smoke tests."""

    names = stimulus_input_names(case, checker)
    trace: list[dict[str, bool]] = []
    for cycle in range(case.trace_length):
        values: dict[str, bool] = {}
        for index, name in enumerate(names):
            if name == "start":
                values[name] = cycle % 3 == 0
            elif name == "dis":
                values[name] = False
            else:
                values[name] = ((cycle + index) % 2) == 0
        trace.append(values)
    return trace


@st.composite
def stimulus_traces(
    draw: st.DrawFn,
    case: GeneratedSvaCase,
    input_names: tuple[str, ...] | None = None,
) -> list[dict[str, bool]]:
    """Hypothesis strategy for bounded per-cycle boolean stimuli."""

    names = input_names if input_names is not None else stimulus_input_names(case)
    trace: list[dict[str, bool]] = []
    for _cycle in range(case.trace_length):
        cycle_values: dict[str, bool] = {}
        for name in names:
            if name == "dis":
                cycle_values[name] = False
            else:
                cycle_values[name] = draw(st.booleans())
        trace.append(cycle_values)
    return trace


def normalize_observation(
    raw: dict[str, Any],
    *,
    cycle: int,
    backend: str,
) -> CycleObservation:
    """Normalize raw oracle/simulator output keys to a cycle observation."""

    required = ("active", "pass", "fail")
    missing = [key for key in required if key not in raw]
    if missing:
        raise ValueError(f"{backend} observation at cycle {cycle} missing keys: {missing}")
    return CycleObservation(
        cycle=cycle,
        active=bool(raw["active"]),
        pass_value=bool(raw["pass"]),
        fail=bool(raw["fail"]),
        overflow=bool(raw["overflow"]) if "overflow" in raw else None,
        backend=backend,
    )


def run_oracle_trace(
    checker: CheckerNode,
    stimulus: list[dict[str, bool]],
) -> list[CycleObservation]:
    """Run the independent Python oracle and return normalized observations."""

    raw_trace = simulate_checker_hierarchy(checker, stimulus)
    return [
        normalize_observation(raw, cycle=cycle, backend="oracle")
        for cycle, raw in enumerate(raw_trace)
    ]


def checker_has_top_overflow(checker: CheckerNode) -> bool:
    """Return whether the top checker exposes `overflow_flag`."""

    return checker.template_name in TEMPLATES_WITH_OVERFLOW


def run_simulator_trace(
    checker: CheckerNode,
    stimulus: list[dict[str, bool]],
    *,
    backend: str,
    tmp_path: Path,
) -> list[CycleObservation]:
    """Run emitted RTL through an existing simulator backend."""

    modules = emit_all(checker)
    sv_sources = list(modules.values())
    extra_inputs = list(stimulus_input_names_from_checker(checker))
    has_overflow_flag = checker_has_top_overflow(checker)
    clock_signal = checker.params.get("clock_signal", "clk")
    tb_code = generate_testbench(
        checker.module_name,
        clock_signal,
        extra_inputs,
        stimulus,
        has_overflow_flag=has_overflow_flag,
    )
    raw_trace = run_simulation(
        checker.module_name,
        sv_sources,
        tb_code,
        work_dir=tmp_path,
        has_overflow_flag=has_overflow_flag,
        simulator=backend,
        stimulus=stimulus,
        extra_inputs=extra_inputs,
        clock_signal=clock_signal,
    )
    return [
        normalize_observation(raw, cycle=cycle, backend=backend)
        for cycle, raw in enumerate(raw_trace)
    ]


def stimulus_input_names_from_checker(checker: CheckerNode) -> tuple[str, ...]:
    """Return simulator input names from checker metadata."""

    return tuple(dict.fromkeys(extra_inputs_from_checker(checker)))


def find_trace_mismatch(
    case: GeneratedSvaCase,
    stimulus: list[dict[str, bool]],
    oracle: list[CycleObservation],
    actual: list[CycleObservation],
    *,
    backend: str,
) -> DifferentialMismatch | None:
    """Return the first trace mismatch, or None if traces match."""

    max_len = max(len(oracle), len(actual))
    for cycle in range(max_len):
        if cycle >= len(oracle):
            actual_obs = actual[cycle]
            return _mismatch(
                case,
                stimulus,
                backend,
                cycle,
                "trace_length",
                None,
                True,
                None,
                actual_obs,
                "backend produced extra cycle",
            )
        if cycle >= len(actual):
            oracle_obs = oracle[cycle]
            return _mismatch(
                case,
                stimulus,
                backend,
                cycle,
                "trace_length",
                True,
                None,
                oracle_obs,
                None,
                "backend missing cycle",
            )

        oracle_obs = oracle[cycle]
        actual_obs = actual[cycle]
        for signal in ("active", "pass_value", "fail", "overflow"):
            expected = getattr(oracle_obs, signal)
            observed = getattr(actual_obs, signal)
            if signal == "overflow" and (expected is None or observed is None):
                continue
            if expected != observed:
                signal_name = "pass" if signal == "pass_value" else signal
                return _mismatch(
                    case,
                    stimulus,
                    backend,
                    cycle,
                    signal_name,
                    expected,
                    observed,
                    oracle_obs,
                    actual_obs,
                    "value mismatch",
                )
    return None


def assert_traces_match(
    case: GeneratedSvaCase,
    stimulus: list[dict[str, bool]],
    oracle: list[CycleObservation],
    actual: list[CycleObservation],
    *,
    backend: str,
    artifact_dir: Path | None = None,
) -> None:
    """Assert that a backend trace matches the oracle trace."""

    mismatch = find_trace_mismatch(case, stimulus, oracle, actual, backend=backend)
    if mismatch is not None:
        artifact_note = ""
        if artifact_dir is not None:
            artifact_path = write_failure_artifact(
                case,
                mismatch,
                artifact_dir,
                stimulus=stimulus,
                oracle=oracle,
                actual=actual,
            )
            artifact_note = f"\nartifact={artifact_path.name}"
        raise AssertionError(mismatch.format_message() + artifact_note)


def build_failure_artifact(
    case: GeneratedSvaCase,
    mismatch: DifferentialMismatch,
    *,
    stimulus: list[dict[str, bool]],
    oracle: list[CycleObservation],
    actual: list[CycleObservation],
) -> DifferentialFailureArtifact:
    """Build a sanitized artifact from a mismatch."""

    artifact = DifferentialFailureArtifact(
        schema_version=FAILURE_ARTIFACT_SCHEMA_VERSION,
        case=case.metadata(),
        stimulus=stimulus,
        oracle_trace=[obs.as_dict() for obs in oracle],
        backend_trace=[obs.as_dict() for obs in actual],
        mismatch=mismatch.as_dict(),
    )
    encoded = artifact.to_json()
    if _UNSAFE_METADATA_RE.search(encoded):
        raise ValueError("failure artifact contains unsafe local or private metadata")
    return artifact


def write_failure_artifact(
    case: GeneratedSvaCase,
    mismatch: DifferentialMismatch,
    artifact_dir: Path,
    *,
    stimulus: list[dict[str, bool]],
    oracle: list[CycleObservation],
    actual: list[CycleObservation],
) -> Path:
    """Write a deterministic mismatch artifact and return its path."""

    artifact = build_failure_artifact(
        case,
        mismatch,
        stimulus=stimulus,
        oracle=oracle,
        actual=actual,
    )
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{case.case_id}_{mismatch.backend}_failure.json"
    path.write_text(artifact.to_json(), encoding="utf-8")
    return path


def _mismatch(
    case: GeneratedSvaCase,
    stimulus: list[dict[str, bool]],
    backend: str,
    cycle: int,
    signal: str,
    expected: bool | None,
    actual: bool | None,
    oracle_observation: CycleObservation | None,
    actual_observation: CycleObservation | None,
    reason: str,
) -> DifferentialMismatch:
    start = max(0, cycle - 2)
    end = min(len(stimulus), cycle + 3)
    return DifferentialMismatch(
        case_id=case.case_id,
        backend=backend,
        cycle=cycle,
        signal=signal,
        expected=expected,
        actual=actual,
        source_text=case.source_text,
        stimulus_slice=tuple(stimulus[start:end]),
        oracle_observation=oracle_observation.as_dict() if oracle_observation else None,
        actual_observation=actual_observation.as_dict() if actual_observation else None,
        family_tags=case.family_tags,
        reason=reason,
    )


def compile_generated_case(
    case: GeneratedSvaCase,
    tmp_path: Path,
    *,
    optimize_flag: bool = True,
    slang_path: str = "slang",
) -> CompiledGeneratedCase:
    """Compile generated source through the normal frontend/import/compose path."""

    source_path = tmp_path / f"{case.case_id}.sv"
    source_path.write_text(case.source_text, encoding="utf-8")

    try:
        ast = invoke_slang(source_path, slang_path)
        assertions = import_all_assertions(ast)
        selected: tuple[SVANode, ClockSpec, str, str | None] | None = None
        for node, clock, original_text, label in assertions:
            if label == case.property_label:
                selected = (node, clock, original_text, label)
                break
        if selected is None:
            labels = [label for _node, _clock, _text, label in assertions]
            raise AssertionError(
                f"{case.case_id}: generated label {case.property_label!r} "
                f"not found; available labels={labels!r}"
            )

        node, clock, original_text, label = selected
        normalized = normalize(node)
        checker = compose(normalized, clock, label, original_text)
        if optimize_flag:
            checker = optimize(checker)
        return CompiledGeneratedCase(
            case=case,
            node=normalized,
            clock=clock,
            original_text=original_text,
            checker=checker,
        )
    except Exception as exc:
        raise AssertionError(
            f"{case.case_id}: failed to compile generated SVA source\n"
            f"label={case.property_label}\n"
            f"source:\n{case.source_text}\n"
            f"error={exc}"
        ) from exc


def metadata_is_sanitized(metadata: dict[str, object]) -> bool:
    """Return whether generated metadata avoids local/private information."""

    encoded = json.dumps(metadata, sort_keys=True)
    return _UNSAFE_METADATA_RE.search(encoded) is None
