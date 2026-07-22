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

from sva2rtl.behavioral_oracle import SVABehavioralSim

BoolKind = Literal["signal", "const", "not", "and", "or"]
ReferenceKind = Literal[
    "bool",
    "rose",
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
            str(self.minimum)
            if self.minimum == self.maximum
            else f"{self.minimum}:{self.maximum}"
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
            right=(
                SourceBoolExpr.from_dict(right_raw) if isinstance(right_raw, dict) else None
            ),
            minimum=int(payload.get("minimum", 0)),
            maximum=int(payload.get("maximum", 0)),
            depth=int(payload.get("depth", 1)),
            disable=(
                SourceBoolExpr.from_dict(disable_raw)
                if isinstance(disable_raw, dict)
                else None
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


class SourceReferenceRunner:
    """Stateful evaluator built solely from :class:`SourceReferenceSpec`."""

    def __init__(self, spec: SourceReferenceSpec) -> None:
        self._spec = spec
        self._left = _RegisteredBool(spec.left)
        self._right = _RegisteredBool(spec.right) if spec.right is not None else None
        self._primitive = self._build_primitive(spec)

    @staticmethod
    def _build_primitive(spec: SourceReferenceSpec) -> SVABehavioralSim | None:
        if spec.kind == "delay":
            return SVABehavioralSim(
                "delay_range" if spec.minimum != spec.maximum else "delay_fixed",
                {"delay_min": spec.minimum, "delay_max": spec.maximum},
            )
        if spec.kind == "repetition":
            return SVABehavioralSim(
                "rep_consecutive",
                {"rep_min": spec.minimum, "rep_max": spec.maximum},
            )
        if spec.kind in {"rose", "past"}:
            kind = "rose" if spec.kind == "rose" else "past"
            return SVABehavioralSim(kind, {"depth": spec.depth})
        return None

    def reset(self) -> None:
        self._left.reset()
        if self._right is not None:
            self._right.reset()
        if self._primitive is not None:
            self._primitive.reset()

    def tick(self, signals: dict[str, bool]) -> dict[str, bool]:
        if self._spec.disable is not None and self._spec.disable.evaluate(signals):
            self.reset()
            return {"active": False, "pass": False, "fail": False, "overflow": False}

        start = bool(signals.get("start", False))
        if self._spec.kind == "bool":
            return self._left.tick(signals, start)

        if self._spec.kind in {"rose", "past"}:
            assert self._primitive is not None
            signal_value = self._spec.left.evaluate(signals)
            return self._primitive.tick({"start": start, "sig": signal_value})

        if self._spec.kind == "repetition":
            assert self._primitive is not None
            return self._primitive.tick(
                {"start": start, "sig": self._spec.left.evaluate(signals)}
            )

        left = self._left.tick(signals, start)
        assert self._right is not None

        if self._spec.kind == "delay":
            assert self._primitive is not None
            delay = self._primitive.tick({"start": left["pass"]})
            right = self._right.tick(signals, delay["pass"])
            return {
                "active": left["active"] or delay["active"] or right["active"],
                "pass": right["pass"],
                "fail": left["fail"] or right["fail"],
                "overflow": False,
            }

        if self._spec.kind == "implication_overlap":
            right = self._right.tick(signals, start)
            return {
                "active": left["active"] or right["active"],
                "pass": left["pass"] and right["pass"],
                "fail": left["pass"] and right["fail"],
                "overflow": False,
            }

        right = self._right.tick(signals, left["pass"])
        return {
            "active": left["active"] or right["active"],
            "pass": right["pass"],
            "fail": right["fail"],
            "overflow": False,
        }


def simulate_source_reference(
    spec: SourceReferenceSpec,
    stimulus: list[dict[str, bool]],
) -> list[dict[str, bool]]:
    """Evaluate a source specification over a bounded stimulus trace."""

    runner = SourceReferenceRunner(spec)
    return [runner.tick(cycle) for cycle in stimulus]
