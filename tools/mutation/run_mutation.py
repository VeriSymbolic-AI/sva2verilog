"""Phase 13 mutation testing: AST-level mutation injection and test-driven kill detection.

Lightweight alternative to mutmut for targeted mutation testing on critical
semantic modules. Operates at the AST level, runs pytest on mutated source,
and reports kill/survive rates.

Usage:
    uv run python tools/mutation/run_mutation.py                    # all modules
    uv run python tools/mutation/run_mutation.py --module composer.py
    uv run python tools/mutation/run_mutation.py --module ast_importer.py --sample 30
"""

from __future__ import annotations

import argparse
import ast
import copy
import os
import random
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from coverage import Coverage

# ── Configuration ──────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent.parent
SRC_DIR = ROOT / "src" / "sva2rtl"

MUTATION_TARGETS: dict[str, list[str]] = {
    "bool_semantics.py": [
        "tests/test_bool_semantics.py",
    ],
    "behavioral_oracle.py": [
        "tests/test_behavioral_oracle.py",
        "tests/test_behavioral_oracle_mutation_boundaries.py",
        "tests/test_coverage_oracle_gaps.py",
        "tests/test_signal_functions.py",
        "tests/test_repetition.py",
        "tests/test_v13_operators.py",
        "tests/test_v13_independent_baseline.py",
        "tests/test_v15_risk02_gate.py",
        "tests/test_v151_nfa_intersect.py",
        "tests/test_v151_nfa_within_throughout.py",
        "tests/test_v151_p2_implication_nfa.py",
        "tests/test_v151_p3_nested.py",
    ],
    "composer.py": [
        "tests/test_composer.py",
        "tests/test_composer_mutation_boundaries.py",
        "tests/test_v151_p2_implication_nfa.py",
        "tests/test_sequential.py",
        "tests/test_v13_operators.py",
        "tests/test_repetition.py",
        "tests/test_liveness.py",
        "tests/test_multiclock.py",
        "tests/test_named_sequences.py",
        "tests/test_v15_g2a_reject.py",
        "tests/test_v151_nfa_intersect.py",
        "tests/test_v151_nfa_within_throughout.py",
        "tests/test_v151_p3_nested.py",
    ],
    "ast_importer.py": [
        "tests/test_ast_importer.py",
        "tests/test_ast_importer_mutation_boundaries.py",
        "tests/test_errors.py",
        "tests/test_nyquist_gaps.py",
        "tests/test_liveness.py",
        "tests/test_repetition.py",
        "tests/test_v13_operators.py",
        "tests/test_signal_functions.py",
        "tests/test_multiclock.py",
        "tests/test_named_sequences.py",
        "tests/test_sv_fixture_e2e.py",
        "tests/test_v15_g2a_reject.py",
        "tests/test_v151_p2_implication_nfa.py",
    ],
}

TARGET_KILL_RATE = 0.85
MODULE_KILL_RATE_FLOORS: dict[str, float] = {
    "bool_semantics.py": 1.00,
    "behavioral_oracle.py": 0.95,
    "composer.py": 0.90,
    "ast_importer.py": 0.86,
}

# ── Mutation operators ────────────────────────────────────────────────────


@dataclass
class Mutation:
    """A single mutation applied to source code."""

    module: str
    line_no: int
    col_offset: int
    end_line_no: int
    end_col_offset: int
    original: str
    mutated: str
    operator: str


@dataclass
class MutationResult:
    mutation: Mutation
    killed: bool
    valid: bool = True
    output: str = ""


@dataclass
class ModuleReport:
    module: str
    total: int = 0
    killed: int = 0
    survived: int = 0
    invalid: int = 0
    uncovered: int = 0
    survivors: list[Mutation] = field(default_factory=list)

    @property
    def kill_rate(self) -> float:
        scored = self.killed + self.survived
        return self.killed / scored if scored > 0 else 0.0


class MutationVisitor(ast.NodeTransformer):
    """Walk AST and collect candidate mutations."""

    def __init__(self, source: str, module_name: str) -> None:
        self.source = source
        self.module_name = module_name
        self.mutations: list[Mutation] = []

    def _record(self, node: ast.AST, mutated: str, operator: str) -> None:
        if not all(
            hasattr(node, attr) for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset")
        ):
            return
        original = ast.get_source_segment(self.source, node)
        if original is None:
            return
        self.mutations.append(
            Mutation(
                module=self.module_name,
                line_no=int(getattr(node, "lineno")),
                col_offset=int(getattr(node, "col_offset")),
                end_line_no=int(getattr(node, "end_lineno")),
                end_col_offset=int(getattr(node, "end_col_offset")),
                original=original,
                mutated=mutated,
                operator=operator,
            )
        )

    def visit_Compare(self, node: ast.Compare) -> ast.AST:  # noqa: N802
        """Invert comparison operators."""
        invert_map = {
            ast.Eq: ast.NotEq,
            ast.NotEq: ast.Eq,
            ast.Lt: ast.GtE,
            ast.Gt: ast.LtE,
            ast.LtE: ast.Gt,
            ast.GtE: ast.Lt,
        }
        if len(node.ops) == 1:
            op_type = type(node.ops[0])
            if op_type in invert_map:
                new_node = copy.deepcopy(node)
                new_node.ops = [invert_map[op_type]()]
                mutated = ast.unparse(new_node)
                self._record(node, mutated, f"invert_{op_type.__name__}")
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:  # noqa: N802
        """Swap And/Or operators."""
        swap_map = {ast.And: ast.Or, ast.Or: ast.And}
        op_type = type(node.op)
        if op_type in swap_map:
            new_node = copy.deepcopy(node)
            new_node.op = swap_map[op_type]()
            mutated = ast.unparse(new_node)
            self._record(node, mutated, f"swap_{op_type.__name__}")
        return node

    def visit_UnaryOp(self, node: ast.UnaryOp) -> ast.AST:  # noqa: N802
        """Remove Not operators."""
        if isinstance(node.op, ast.Not):
            mutated = ast.unparse(node.operand)
            self._record(node, mutated, "remove_Not")
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST:  # noqa: N802
        """Invert boolean return values."""
        if node.value is not None:
            for const_val, inverted in [(True, False), (False, True)]:
                if isinstance(node.value, ast.Constant) and node.value.value is const_val:
                    new_node = ast.Return(value=ast.Constant(value=inverted))
                    mutated = ast.unparse(new_node)
                    self._record(node, mutated, f"invert_return_{const_val}")
                    break
        return node


def collect_mutations(filepath: Path, module_name: str) -> list[Mutation]:
    """Parse file and collect all candidate mutations."""
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source)
    visitor = MutationVisitor(source, module_name)
    visitor.visit(tree)
    return visitor.mutations


def apply_mutation(source: str, mutation: Mutation) -> str:
    """Replace exactly the AST node span, preserving its surrounding statement."""
    source_bytes = source.encode("utf-8")
    line_starts = [0]
    for line in source.splitlines(keepends=True):
        line_starts.append(line_starts[-1] + len(line.encode("utf-8")))
    start = line_starts[mutation.line_no - 1] + mutation.col_offset
    end = line_starts[mutation.end_line_no - 1] + mutation.end_col_offset
    mutated_bytes = mutation.mutated.encode("utf-8")
    return (source_bytes[:start] + mutated_bytes + source_bytes[end:]).decode("utf-8")


def run_tests(test_files: list[str]) -> bool:
    """Run pytest on specified test files. Returns True if all pass.

    Excludes simulation/formal/differential tests to keep mutation runs fast.
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-x",
        "-q",
        "--timeout=30",
        "-m",
        "not simulation and not differential and not differential_slow",
    ] + test_files
    try:
        # Source mutants can have the same byte length and second-resolution
        # mtime as the original.  A normal subprocess may then reuse a stale
        # timestamp-based .pyc and never execute the mutant.  An isolated empty
        # cache prefix forces every mutation subprocess to compile fresh source.
        with tempfile.TemporaryDirectory(prefix="sva2rtl-mutation-pycache-") as pycache_dir:
            env = os.environ.copy()
            env["PYTHONPYCACHEPREFIX"] = pycache_dir
            result = subprocess.run(
                cmd,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            return result.returncode == 0
    except subprocess.TimeoutExpired:
        return True  # treat timeout as "survived" (tests didn't catch the mutant fast enough)


def collect_covered_lines(filepath: Path, test_files: list[str]) -> set[int]:
    """Run the baseline under branch coverage and return executed target lines."""

    with tempfile.TemporaryDirectory(prefix="sva2rtl-mutation-coverage-") as temp_dir:
        data_file = Path(temp_dir) / ".coverage"
        pycache_dir = Path(temp_dir) / "pycache"
        cmd = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--data-file={data_file}",
            "-m",
            "pytest",
            "-x",
            "-q",
            "--timeout=30",
            "-m",
            "not simulation and not differential and not differential_slow",
            *test_files,
        ]
        env = os.environ.copy()
        env["PYTHONPYCACHEPREFIX"] = str(pycache_dir)
        result = subprocess.run(
            cmd,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"coverage baseline failed for {filepath.name}:\n{result.stdout}\n{result.stderr}"
            )
        coverage = Coverage(data_file=str(data_file))
        coverage.load()
        lines = coverage.get_data().lines(str(filepath.resolve()))
        return set(lines or ())


def test_mutation(filepath: Path, mutation: Mutation, test_files: list[str]) -> MutationResult:
    """Apply mutation, run tests, restore original. Returns result."""
    original_source = filepath.read_text(encoding="utf-8")
    mutated_source = apply_mutation(original_source, mutation)
    try:
        ast.parse(mutated_source)
    except SyntaxError as exc:
        return MutationResult(
            mutation=mutation,
            killed=False,
            valid=False,
            output=f"invalid mutant: {exc.msg}",
        )

    try:
        filepath.write_text(mutated_source, encoding="utf-8")
        passed = run_tests(test_files)
        return MutationResult(
            mutation=mutation,
            killed=not passed,
            output="" if not passed else "tests passed (mutant survived)",
        )
    finally:
        filepath.write_text(original_source, encoding="utf-8")


def run_module(filepath: Path, module_name: str, sample_n: int = 0) -> ModuleReport:
    """Run mutation testing on a single module.

    If ``sample_n`` > 0, randomly sample that many mutations instead of
    running all (useful for long modules like composer.py / ast_importer.py
    where a full run takes hours).
    """
    test_files = MUTATION_TARGETS.get(module_name, [])
    if not test_files:
        print(f"  No test targets configured for {module_name}, skipping.")
        return ModuleReport(module=module_name)

    if not run_tests(test_files):
        raise RuntimeError(f"baseline tests failed for {module_name}; refusing to score mutants")

    covered_lines = collect_covered_lines(filepath, test_files)
    all_mutations = collect_mutations(filepath, module_name)
    mutations = [mutation for mutation in all_mutations if mutation.line_no in covered_lines]
    uncovered = len(all_mutations) - len(mutations)
    if sample_n > 0 and len(mutations) > sample_n:
        random.seed(42)  # deterministic sampling for reproducibility
        mutations = sorted(random.sample(mutations, sample_n), key=lambda m: m.line_no)
        print(f"  {len(mutations)} covered mutations sampled from {len(all_mutations) - uncovered}")
    else:
        print(f"  {len(mutations)} covered candidate mutations ({uncovered} uncovered excluded)")

    report = ModuleReport(module=module_name, total=len(mutations), uncovered=uncovered)

    for i, mut in enumerate(mutations):
        print(f"    [{i + 1}/{len(mutations)}] line {mut.line_no}: {mut.operator}", end="")
        result = test_mutation(filepath, mut, test_files)
        if not result.valid:
            report.invalid += 1
            print(f" INVALID ({result.output})")
        elif result.killed:
            report.killed += 1
            print(" KILLED")
        else:
            report.survived += 1
            report.survivors.append(mut)
            print(f" SURVIVED ({mut.original[:50]})")

    return report


def mutation_exit_code(
    total: int,
    killed: int,
    target: float = TARGET_KILL_RATE,
) -> int:
    """Return a failing status when a non-empty sweep misses its quality target."""
    if total == 0:
        return 0
    return 0 if killed / total >= target else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="sva2rtl mutation testing")
    parser.add_argument(
        "--module",
        default=None,
        help="Run only this module (e.g. composer.py, ast_importer.py)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=0,
        help="Randomly sample N mutations (for large modules). 0 = run all.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("sva2rtl Phase 13 Mutation Testing Report")
    print("=" * 60)

    reports: list[ModuleReport] = []

    modules_to_run = {args.module: []} if args.module else MUTATION_TARGETS

    for module_name, _targets in modules_to_run.items():
        filepath = SRC_DIR / module_name
        if not filepath.exists():
            print(f"\n[{module_name}] FILE NOT FOUND, skipping")
            continue

        print(f"\n[{module_name}]")
        report = run_module(filepath, module_name, sample_n=args.sample)
        reports.append(report)
        valid_total = report.killed + report.survived
        print(
            f"  Kill rate: {report.killed}/{valid_total} = {report.kill_rate:.1%} "
            f"({report.invalid} invalid excluded)"
        )

    # ── Summary ────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    total_candidates = sum(r.total + r.uncovered for r in reports)
    total_killed = sum(r.killed for r in reports)
    total_survived = sum(r.survived for r in reports)
    total_invalid = sum(r.invalid for r in reports)
    total_mut = total_killed + total_survived

    for r in reports:
        bar = "█" * int(r.kill_rate * 20) + "░" * (20 - int(r.kill_rate * 20))
        valid_total = r.killed + r.survived
        target = MODULE_KILL_RATE_FLOORS.get(r.module, TARGET_KILL_RATE)
        print(
            f"  {r.module:30s} {bar} {r.kill_rate:.0%} "
            f"({r.killed}/{valid_total}; floor={target:.0%}; "
            f"invalid={r.invalid}; uncovered={r.uncovered})"
        )

    print(f"\n  OVERALL: {total_killed}/{total_mut} = {total_killed / max(total_mut, 1):.1%}")
    print(f"  Survivors: {total_survived}")
    print(f"  Invalid excluded: {total_invalid}/{total_candidates}")
    print(f"  Uncovered excluded: {sum(r.uncovered for r in reports)}/{total_candidates}")

    if total_survived > 0:
        print("\n  SURVIVING MUTANTS:")
        for r in reports:
            for s in r.survivors:
                print(f"    [{r.module}:{s.line_no}] {s.operator}")
                print(f"      {s.original[:80]}")

    print(f"\n  Default kill-rate floor: {TARGET_KILL_RATE:.0%}")
    all_modules_pass = True
    if total_mut > 0:
        all_modules_pass = all(
            mutation_exit_code(
                report.killed + report.survived,
                report.killed,
                MODULE_KILL_RATE_FLOORS.get(report.module, TARGET_KILL_RATE),
            )
            == 0
            for report in reports
        )
        status = "PASS" if all_modules_pass else "BELOW MODULE FLOOR"
        print(f"  Status: {status}")
    return 0 if all_modules_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
