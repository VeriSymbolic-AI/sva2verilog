"""Generated checker interface capability queries.

Keep optional-port knowledge in one place. Hard-coded template lists in Jinja
wrappers and testbench builders previously allowed ``overflow_flag`` to vanish
when a new bounded-concurrency backend was introduced.
"""

from __future__ import annotations

from sva2rtl.ir import CheckerNode

TEMPLATES_WITH_OVERFLOW: frozenset[str] = frozenset(
    {
        "overlap_bitvec",
        "nonoverlap",
        "nfa_generic",
        "implication_nfa",
        "implication_delay_window",
    }
)


def checker_has_overflow_flag(checker: CheckerNode) -> bool:
    """Return whether *checker* exposes the optional ``overflow_flag`` port."""
    if checker.template_name in TEMPLATES_WITH_OVERFLOW:
        return True
    if checker.template_name == "disable_iff_top" and checker.children:
        return checker_has_overflow_flag(checker.children[0])
    return False
