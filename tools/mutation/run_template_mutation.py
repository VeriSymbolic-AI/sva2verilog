"""Targeted RTL-template mutation gate for semantic wiring and boundaries.

The Python AST mutator cannot reach Jinja2 RTL. This complementary runner
injects reviewed, deterministic faults into counter bounds, state retention,
register width, and child-port wiring, then requires focused tests to kill every
fault. Each template is restored in a ``finally`` block.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


@dataclass(frozen=True)
class TemplateMutation:
    """One exact mutation and the focused command that must kill it."""

    name: str
    template: str
    original: str
    replacement: str
    pytest_args: tuple[str, ...]


MUTATIONS: tuple[TemplateMutation, ...] = (
    TemplateMutation(
        name="delay-upper-bound-off-by-one",
        template="templates/concat_delay.sv.j2",
        original="{% set _cmax = [_emax - 2, 0] | max %}",
        replacement="{% set _cmax = [_emax - 1, 0] | max %}",
        pytest_args=("tests/test_sequential.py", "-k", "delay"),
    ),
    TemplateMutation(
        name="repetition-counter-overrun",
        template="templates/rep_consecutive.sv.j2",
        original="if (count_q < {{ cnt_width }}'d{{ rep_max }})",
        replacement="if (count_q <= {{ cnt_width }}'d{{ rep_max }})",
        pytest_args=(
            "tests/simulation/test_sim_repetition.py",
            "--simulator=iverilog",
        ),
    ),
    TemplateMutation(
        name="repetition-counter-width",
        template="templates/rep_consecutive.sv.j2",
        original="logic [CNT_WIDTH-1:0] count_q;",
        replacement="logic [CNT_WIDTH:0] count_q;",
        pytest_args=("tests/test_repetition.py", "-k", "counter_width_declaration"),
    ),
    TemplateMutation(
        name="nonoverlap-consequent-start-wiring",
        template="templates/nonoverlap.sv.j2",
        original=".{{ clock_signal }}({{ clock_signal }}), .rst_n(rst_n), .start(con_start_w),",
        replacement=".{{ clock_signal }}({{ clock_signal }}), .rst_n(rst_n), .start(start),",
        pytest_args=("tests/test_sequential.py", "-k", "nonoverlap"),
    ),
    TemplateMutation(
        name="sequence-or-failure-truth-table",
        template="templates/prop_or.sv.j2",
        original=(
            "wire _body_fail   = (left_fail  & (right_fail | right_failed_q))\n"
            "                      | (right_fail & (left_fail  | left_failed_q));"
        ),
        replacement="wire _body_fail   = left_fail | right_fail;",
        pytest_args=(
            "tests/simulation/test_sim_v13_operators.py",
            "-k",
            "SeqOr",
            "--simulator=iverilog",
        ),
    ),
    TemplateMutation(
        name="sequence-or-left-failure-retention",
        template="templates/prop_or.sv.j2",
        original="left_failed_q  <= left_failed_q  | left_fail;",
        replacement="left_failed_q  <= left_fail;",
        pytest_args=(
            "tests/simulation/test_sim_v13_operators.py",
            "-k",
            "delayed_failure_completes",
            "--simulator=iverilog",
        ),
    ),
    TemplateMutation(
        name="sequence-or-right-failure-retention",
        template="templates/prop_or.sv.j2",
        original="right_failed_q <= right_failed_q | right_fail;",
        replacement="right_failed_q <= right_fail;",
        pytest_args=(
            "tests/simulation/test_sim_v13_operators.py",
            "-k",
            "delayed_failure_completes",
            "--simulator=iverilog",
        ),
    ),
    TemplateMutation(
        name="overlap-attempt-evidence-must-track-start",
        template="templates/overlap_bitvec.sv.j2",
        original=(
            '{{ attempt_fired_logic(verilog_mode, clock_edge, clock_signal, "start") }}\n'
            "\n"
            "    // ── Output assignments (|-> single-cycle consequent)"
        ),
        replacement=(
            '{{ attempt_fired_logic(verilog_mode, clock_edge, clock_signal, "ant_pass_w") }}\n'
            "\n"
            "    // ── Output assignments (|-> single-cycle consequent)"
        ),
        pytest_args=(
            "tests/simulation/test_sim_implication.py",
            "-k",
            "attempt_fired and overlap",
            "--simulator=iverilog",
        ),
    ),
    TemplateMutation(
        name="nonoverlap-attempt-evidence-must-track-start",
        template="templates/nonoverlap.sv.j2",
        original=(
            '{{ attempt_fired_logic(verilog_mode, clock_edge, clock_signal, "start") }}\n'
            "\n"
            "    // ── Output assignments (|=> single-cycle consequent)"
        ),
        replacement=(
            '{{ attempt_fired_logic(verilog_mode, clock_edge, clock_signal, "ant_pass_w") }}\n'
            "\n"
            "    // ── Output assignments (|=> single-cycle consequent)"
        ),
        pytest_args=(
            "tests/simulation/test_sim_implication.py",
            "-k",
            "attempt_fired and nonoverlap",
            "--simulator=iverilog",
        ),
    ),
    TemplateMutation(
        name="multiclock-top-must-honor-start",
        template="templates/mc_seq_top.sv.j2",
        original="assign t0_pass = start;",
        replacement="assign t0_pass = 1'b1;",
        pytest_args=(
            "tests/test_multiclock.py",
            "-k",
            "standard_contract",
        ),
    ),
    TemplateMutation(
        name="multiclock-disable-must-clear-cdc-state",
        template="templates/sync_2dff.sv.j2",
        original="if (!rst_n || disable_i) begin",
        replacement="if (!rst_n) begin",
        pytest_args=(
            "tests/test_multiclock.py",
            "-k",
            "standard_contract",
        ),
    ),
    TemplateMutation(
        name="multiclock-meta-injection-must-be-one-shot",
        template="templates/lfsr_8bit.sv.j2",
        original="assign lfsr_out = (state == 8'h01);",
        replacement="assign lfsr_out = state[0];",
        pytest_args=(
            "tests/test_multiclock.py",
            "-k",
            "meta_injection_is_one_pulse",
        ),
    ),
)


def _run_tests(pytest_args: tuple[str, ...]) -> bool:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "--timeout=120", *pytest_args],
        cwd=ROOT,
        check=False,
    )
    return result.returncode == 0


def validate_mutation(mutation: TemplateMutation) -> Path:
    """Return the target path only when the mutation site is exact and unique."""
    path = ROOT / mutation.template
    source = path.read_text(encoding="utf-8")
    count = source.count(mutation.original)
    if count != 1:
        raise RuntimeError(
            f"{mutation.name}: expected one mutation site in {mutation.template}, found {count}"
        )
    if mutation.original == mutation.replacement:
        raise RuntimeError(f"{mutation.name}: replacement does not change the template")
    return path


def run_mutation(mutation: TemplateMutation) -> bool:
    """Return True when the focused tests kill the mutation."""
    path = validate_mutation(mutation)
    original_source = path.read_text(encoding="utf-8")
    mutated_source = original_source.replace(mutation.original, mutation.replacement, 1)
    try:
        path.write_text(mutated_source, encoding="utf-8")
        return not _run_tests(mutation.pytest_args)
    finally:
        path.write_text(original_source, encoding="utf-8")


def mutation_exit_code(total: int, killed: int) -> int:
    """Every reviewed RTL mutation is required to be killed."""
    return 0 if total > 0 and killed == total else 1


def main() -> int:
    print("sva2rtl targeted RTL template mutation report")
    killed = 0
    for index, mutation in enumerate(MUTATIONS, 1):
        if not _run_tests(mutation.pytest_args):
            raise RuntimeError(f"{mutation.name}: baseline tests fail; refusing to score")
        was_killed = run_mutation(mutation)
        killed += int(was_killed)
        status = "KILLED" if was_killed else "SURVIVED"
        print(f"[{index}/{len(MUTATIONS)}] {mutation.name}: {status}")
    print(f"TOTAL: {killed}/{len(MUTATIONS)} killed")
    return mutation_exit_code(len(MUTATIONS), killed)


if __name__ == "__main__":
    raise SystemExit(main())
