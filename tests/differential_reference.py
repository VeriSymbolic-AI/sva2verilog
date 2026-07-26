"""Independent source-semantic reference model for differential tests.

The compiler-under-test consumes rendered SVA source and produces ``CheckerNode``
and RTL.  This module consumes the typed specification that rendered that source;
it deliberately imports neither compiler IR nor composition/emission code.  That
separation prevents importer/composer mistakes from automatically becoming the
expected differential result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

BoolKind = Literal["signal", "const", "not", "and", "or"]
ReferenceKind = Literal[
    "bool",
    "rose",
    "fell",
    "stable",
    "changed",
    "past",
    "delay",
    "implication_overlap",
    "implication_nonoverlap",
    "repetition",
]


@dataclass(frozen=True)
class SourceBoolExpr:
    """Small two-state boolean grammar shared only by source generation/reference."""

    kind: BoolKind
    name: str | None = None
    value: bool | None = None
    left: SourceBoolExpr | None = None
    right: SourceBoolExpr | None = None

    @classmethod
    def signal(cls, name: str) -> SourceBoolExpr:
        return cls("signal", name=name)

    @classmethod
    def constant(cls, value: bool) -> SourceBoolExpr:
        return cls("const", value=value)

    @classmethod
    def negate(cls, operand: SourceBoolExpr) -> SourceBoolExpr:
        return cls("not", left=operand)

    @classmethod
    def conjunction(cls, left: SourceBoolExpr, right: SourceBoolExpr) -> SourceBoolExpr:
        return cls("and", left=left, right=right)

    @classmethod
    def disjunction(cls, left: SourceBoolExpr, right: SourceBoolExpr) -> SourceBoolExpr:
        return cls("or", left=left, right=right)

    def __post_init__(self) -> None:
        if self.kind == "signal" and not self.name:
            raise ValueError("signal expression requires a name")
        if self.kind == "const" and self.value is None:
            raise ValueError("constant expression requires a value")
        if self.kind == "not" and self.left is None:
            raise ValueError("not expression requires an operand")
        if self.kind in {"and", "or"} and (self.left is None or self.right is None):
            raise ValueError(f"{self.kind} expression requires two operands")

    def render(self) -> str:
        if self.kind == "signal":
            assert self.name is not None
            return self.name
        if self.kind == "const":
            return "1'b1" if self.value else "1'b0"
        if self.kind == "not":
            assert self.left is not None
            return f"!({self.left.render()})"
        assert self.left is not None and self.right is not None
        op = "&&" if self.kind == "and" else "||"
        return f"({self.left.render()} {op} {self.right.render()})"

    def evaluate(self, signals: dict[str, bool]) -> bool:
        if self.kind == "signal":
            assert self.name is not None
            return bool(signals.get(self.name, False))
        if self.kind == "const":
            return bool(self.value)
        if self.kind == "not":
            assert self.left is not None
            return not self.left.evaluate(signals)
        assert self.left is not None and self.right is not None
        if self.kind == "and":
            return self.left.evaluate(signals) and self.right.evaluate(signals)
        return self.left.evaluate(signals) or self.right.evaluate(signals)

    def signal_names(self) -> tuple[str, ...]:
        if self.kind == "signal":
            assert self.name is not None
            return (self.name,)
        names: list[str] = []
        if self.left is not None:
            names.extend(self.left.signal_names())
        if self.right is not None:
            names.extend(self.right.signal_names())
        return tuple(dict.fromkeys(names))

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation for replay artifacts."""
        return {
            "kind": self.kind,
            "name": self.name,
            "value": self.value,
            "left": self.left.as_dict() if self.left is not None else None,
            "right": self.right.as_dict() if self.right is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SourceBoolExpr:
        """Restore a boolean expression from a sanitized replay artifact."""
        left_raw = payload.get("left")
        right_raw = payload.get("right")
        return cls(
            kind=payload["kind"],
            name=payload.get("name"),
            value=payload.get("value"),
            left=cls.from_dict(left_raw) if isinstance(left_raw, dict) else None,
            right=cls.from_dict(right_raw) if isinstance(right_raw, dict) else None,
        )


@dataclass(frozen=True)
class SourceReferenceSpec:
    """Typed source property used to render SVA and evaluate expected behavior."""

    kind: ReferenceKind
    left: SourceBoolExpr
    right: SourceBoolExpr | None = None
    minimum: int = 0
    maximum: int = 0
    depth: int = 1
    disable: SourceBoolExpr | None = None

    def __post_init__(self) -> None:
        if self.kind in {"delay", "implication_overlap", "implication_nonoverlap"}:
            if self.right is None:
                raise ValueError(f"{self.kind} requires a right operand")
        if self.minimum < 0 or self.maximum < self.minimum:
            raise ValueError("invalid bounded reference range")
        if self.kind == "repetition" and self.minimum < 1:
            raise ValueError("repetition count must be positive")
        if self.kind == "past" and self.depth < 1:
            raise ValueError("past depth must be positive")

    def render(self) -> str:
        left = self.left.render()
        if self.kind == "bool":
            return left
        if self.kind == "rose":
            return f"$rose({left})"
        if self.kind == "fell":
            return f"$fell({left})"
        if self.kind == "stable":
            return f"$stable({left})"
        if self.kind == "changed":
            return f"$changed({left})"
        if self.kind == "past":
            return f"$past({left}, {self.depth})"
        if self.kind == "delay":
            assert self.right is not None
            delay = (
                str(self.minimum)
                if self.minimum == self.maximum
                else f"[{self.minimum}:{self.maximum}]"
            )
            return f"{left} ##{delay} {self.right.render()}"
        if self.kind.startswith("implication_"):
            assert self.right is not None
            op = "|->" if self.kind == "implication_overlap" else "|=>"
            return f"{left} {op} {self.right.render()}"
        repeat = (
            str(self.minimum) if self.minimum == self.maximum else f"{self.minimum}:{self.maximum}"
        )
        # Keep a lexical separator before the repetition suffix.  Without it,
        # slang accepts the assertion but can reduce ``a[*N]`` to plain ``a``.
        return f"{left} [*{repeat}]"

    def signal_names(self) -> tuple[str, ...]:
        names = list(self.left.signal_names())
        if self.right is not None:
            names.extend(self.right.signal_names())
        if self.disable is not None:
            names.extend(self.disable.signal_names())
        return tuple(dict.fromkeys(names))

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation for replay artifacts."""
        return {
            "kind": self.kind,
            "left": self.left.as_dict(),
            "right": self.right.as_dict() if self.right is not None else None,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "depth": self.depth,
            "disable": self.disable.as_dict() if self.disable is not None else None,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SourceReferenceSpec:
        """Restore a source reference from a sanitized replay artifact."""
        right_raw = payload.get("right")
        disable_raw = payload.get("disable")
        return cls(
            kind=payload["kind"],
            left=SourceBoolExpr.from_dict(payload["left"]),
            right=(SourceBoolExpr.from_dict(right_raw) if isinstance(right_raw, dict) else None),
            minimum=int(payload.get("minimum", 0)),
            maximum=int(payload.get("maximum", 0)),
            depth=int(payload.get("depth", 1)),
            disable=(
                SourceBoolExpr.from_dict(disable_raw) if isinstance(disable_raw, dict) else None
            ),
        )


class _RegisteredBool:
    """Reference for the public registered bool-leaf observation contract."""

    def __init__(self, expr: SourceBoolExpr) -> None:
        self._expr = expr
        self.reset()

    def reset(self) -> None:
        self._active = False
        self._pass = False
        self._fail = False

    def tick(self, signals: dict[str, bool], start: bool) -> dict[str, bool]:
        output = {
            "active": self._active,
            "pass": self._pass,
            "fail": self._fail,
            "overflow": False,
        }
        self._active = start
        truth = self._expr.evaluate(signals)
        self._pass = start and truth
        self._fail = start and not truth
        return output


class _SampledReference:
    """Independent bounded model for sampled-value system functions."""

    def __init__(self, kind: ReferenceKind, depth: int) -> None:
        self._kind = kind
        self._depth = max(depth, 1)
        self.reset()

    def reset(self) -> None:
        self._previous = False
        self._history = [False] * self._depth

    def tick(self, signal: bool, start: bool) -> dict[str, bool]:
        if self._kind == "past":
            truth = self._history[-1]
            self._history = [signal, *self._history[:-1]]
        else:
            if self._kind == "rose":
                truth = signal and not self._previous
            elif self._kind == "fell":
                truth = not signal and self._previous
            elif self._kind == "stable":
                truth = signal == self._previous
            else:
                assert self._kind == "changed"
                truth = signal != self._previous
            self._previous = signal
        return {
            "active": start,
            "pass": start and truth,
            "fail": start and not truth,
            "overflow": False,
        }


class _DelayReference:
    """Independent counter model for bounded ``##`` delay windows."""

    def __init__(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = maximum
        self.reset()

    def reset(self) -> None:
        self._running = False
        self._count = 0

    def tick(self, start: bool) -> dict[str, bool]:
        if self._minimum == 0 and self._maximum == 0:
            return {
                "active": start,
                "pass": start,
                "fail": False,
                "overflow": False,
            }

        old_running = self._running
        old_count = self._count
        if start:
            self._running = True
            self._count = 0
        elif old_running:
            if old_count >= self._maximum:
                self._running = False
                self._count = 0
            else:
                self._count = old_count + 1

        counter_min = max(self._minimum - 2, 0)
        counter_max = max(self._maximum - 2, 0)
        passes_now = start and self._minimum <= 1 <= self._maximum
        passes_later = (
            self._maximum >= 2 and old_running and counter_min <= old_count <= counter_max
        )
        return {
            "active": old_running,
            "pass": passes_now or passes_later,
            "fail": False,
            "overflow": False,
        }


class _RepetitionReference:
    """Independent model for bounded consecutive repetition."""

    def __init__(self, minimum: int, maximum: int) -> None:
        self._minimum = minimum
        self._maximum = maximum
        self.reset()

    def reset(self) -> None:
        self._running = False
        self._count = 0

    def tick(self, signal: bool, start: bool) -> dict[str, bool]:
        old_running = self._running
        old_count = self._count
        if start and signal:
            self._running = True
            self._count = 1
        elif old_running and signal:
            if old_count < self._maximum:
                self._count = old_count + 1
        elif old_running:
            self._running = False
            self._count = 0

        return {
            "active": old_running,
            "pass": (old_running and signal and self._minimum <= old_count <= self._maximum),
            "fail": old_running and not signal and old_count < self._minimum,
            "overflow": False,
        }


class SourceReferenceRunner:
    """Stateful evaluator built solely from :class:`SourceReferenceSpec`."""

    def __init__(self, spec: SourceReferenceSpec) -> None:
        self._spec = spec
        self._left = _RegisteredBool(spec.left)
        self._right = _RegisteredBool(spec.right) if spec.right is not None else None
        self._primitive = self._build_primitive(spec)
        self._attempt_fired = False

    @staticmethod
    def _build_primitive(
        spec: SourceReferenceSpec,
    ) -> _DelayReference | _RepetitionReference | _SampledReference | None:
        if spec.kind == "delay":
            return _DelayReference(spec.minimum, spec.maximum)
        if spec.kind == "repetition":
            return _RepetitionReference(spec.minimum, spec.maximum)
        if spec.kind in {"rose", "fell", "stable", "changed", "past"}:
            return _SampledReference(spec.kind, spec.depth)
        return None

    def reset(self) -> None:
        """Reset both semantic evaluation state and the sticky contract state."""

        self._reset_evaluation()
        self._attempt_fired = False

    def _reset_evaluation(self) -> None:
        """Abort in-flight evaluation without clearing ``attempt_fired``."""

        self._left.reset()
        if self._right is not None:
            self._right.reset()
        if self._primitive is not None:
            self._primitive.reset()

    def tick(self, signals: dict[str, bool]) -> dict[str, bool]:
        start = bool(signals.get("start", False))
        attempt_fired = self._attempt_fired
        if start:
            # The RTL contract is registered: a start sampled on this edge is
            # visible in the observation captured at the following edge.
            self._attempt_fired = True

        disabled_o = bool(signals.get("disable_i", False))
        local_disable = (
            self._spec.disable is not None and self._spec.disable.evaluate(signals)
        )
        if disabled_o or local_disable:
            self._reset_evaluation()
            result = {"active": False, "pass": False, "fail": False, "overflow": False}
            return self._with_contract(result, attempt_fired, disabled_o)

        if self._spec.kind == "bool":
            result = self._left.tick(signals, start)
            return self._with_contract(result, attempt_fired, disabled_o)

        if self._spec.kind in {"rose", "fell", "stable", "changed", "past"}:
            assert isinstance(self._primitive, _SampledReference)
            signal_value = self._spec.left.evaluate(signals)
            result = self._primitive.tick(signal_value, start)
            return self._with_contract(result, attempt_fired, disabled_o)

        if self._spec.kind == "repetition":
            assert isinstance(self._primitive, _RepetitionReference)
            result = self._primitive.tick(self._spec.left.evaluate(signals), start)
            return self._with_contract(result, attempt_fired, disabled_o)

        left = self._left.tick(signals, start)
        assert self._right is not None

        if self._spec.kind == "delay":
            assert isinstance(self._primitive, _DelayReference)
            delay = self._primitive.tick(left["pass"])
            right = self._right.tick(signals, delay["pass"])
            result = {
                "active": left["active"] or delay["active"] or right["active"],
                "pass": right["pass"],
                "fail": left["fail"] or right["fail"],
                "overflow": False,
            }
            return self._with_contract(result, attempt_fired, disabled_o)

        if self._spec.kind == "implication_overlap":
            right = self._right.tick(signals, start)
            result = {
                "active": left["active"] or right["active"],
                "pass": left["pass"] and right["pass"],
                "fail": left["pass"] and right["fail"],
                "overflow": False,
            }
            return self._with_contract(result, attempt_fired, disabled_o)

        right = self._right.tick(signals, left["pass"])
        result = {
            "active": left["active"] or right["active"],
            "pass": right["pass"],
            "fail": right["fail"],
            "overflow": False,
        }
        return self._with_contract(result, attempt_fired, disabled_o)

    @staticmethod
    def _with_contract(
        result: dict[str, bool],
        attempt_fired: bool,
        disabled_o: bool,
    ) -> dict[str, bool]:
        """Attach the two release-critical checker contract outputs."""

        return {
            **result,
            "attempt_fired": attempt_fired,
            "disabled_o": disabled_o,
        }


def simulate_source_reference(
    spec: SourceReferenceSpec,
    stimulus: list[dict[str, bool]],
) -> list[dict[str, bool]]:
    """Evaluate a source specification over a bounded stimulus trace."""

    runner = SourceReferenceRunner(spec)
    return [runner.tick(cycle) for cycle in stimulus]
