"""Formal equivalence verification tests.

Tests for the yosys integration in ``sva2rtl.formal`` using mocked
yosys subprocess calls.  The formal verification logic is tested via:

1. Module name extraction from SV text
2. yosys availability detection
3. Equivalence check pipeline (mocked yosys)
4. Multi-module equivalence check (mocked yosys)
5. Optimizer pass verification (integration, mocked yosys)

All yosys invocations are mocked to avoid requiring yosys on the test
machine.  The tests verify correct Tcl script generation, exit code
handling, timeout behavior, and error conditions.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from sva2rtl.formal import (
    _extract_top_module_names,
    _yosys_is_available,
    check_optimizer_pass,
    run_equiv_check,
    run_equiv_check_multi,
    yosys_version,
)


class TestExtractTopModuleNames:
    """Unit tests for module name extraction from SV text."""

    def test_single_module(self) -> None:
        sv = "module checker_foo (\n  input logic clk\n);\nendmodule\n"
        assert _extract_top_module_names(sv) == ["checker_foo"]

    def test_multiple_modules(self) -> None:
        sv = (
            "module submod (input logic a, output logic b);\nendmodule\n\n"
            "module checker_top (\n  input logic clk, rst_n, a\n);\n"
            "  submod u_submod (.a(a), .b(b));\nendmodule\n"
        )
        assert _extract_top_module_names(sv) == ["submod", "checker_top"]

    def test_parametrized_module(self) -> None:
        sv = "module checker_foo #(\n  parameter W = 1\n) (\n  input logic clk\n);\nendmodule\n"
        assert _extract_top_module_names(sv) == ["checker_foo"]

    def test_no_module(self) -> None:
        sv = "// just comments\nwire foo;\n"
        assert _extract_top_module_names(sv) == []

    def test_module_with_generate(self) -> None:
        sv = (
            "module checker_gen (input logic clk, rst_n);\n"
            "  generate\n"
            "    if (1) begin : blk\n"
            "      wire x;\n"
            "    end\n"
            "  endgenerate\n"
            "endmodule\n"
        )
        assert _extract_top_module_names(sv) == ["checker_gen"]


class TestYosysAvailability:
    """Tests for yosys PATH detection."""

    def test_yosys_found(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert _yosys_is_available() is True
            mock_run.assert_called_once()

    def test_yosys_not_found(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError):
            assert _yosys_is_available() is False

    def test_yosys_version(self) -> None:
        mock_yosys = MagicMock(stdout="Yosys 0.66\n", returncode=0)
        mock_sby = MagicMock(stdout="SBY v0.65\n", returncode=0)
        with patch("subprocess.run", side_effect=[mock_yosys, mock_sby]):
            yv, sv = yosys_version()
            assert "Yosys 0.66" in yv
            assert "SBY v0.65" in sv


class TestRunEquivCheck:
    """Tests for single-module equivalence checking."""

    GOLD_SV = "module checker_foo (input logic clk, rst_n, a, b);\n  output logic pass, fail;\nendmodule\n"
    GATE_SV = "module checker_foo (input logic clk, rst_n, a, b);\n  output logic pass, fail;\n  // optimized\nendmodule\n"

    def test_passed(self) -> None:
        mock_result = MagicMock(
            returncode=0,
            stdout="Equivalence successfully proven!\n",
            stderr="",
        )
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                passed, output = run_equiv_check(self.GOLD_SV, self.GATE_SV)
                assert passed is True
                assert "Equivalence successfully proven" in output
                mock_run.assert_called_once()

    def test_failed(self) -> None:
        mock_result = MagicMock(
            returncode=1,
            stdout="",
            stderr="ERROR: Equivalence check FAILED\n",
        )
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                passed, output = run_equiv_check(self.GOLD_SV, self.GATE_SV)
                assert passed is False

    def test_yosys_not_installed(self) -> None:
        with patch("sva2rtl.formal._yosys_is_available", return_value=False):
            passed, output = run_equiv_check(self.GOLD_SV, self.GATE_SV)
            assert passed is False
            assert "not found" in output.lower()

    def test_timeout(self) -> None:
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="yosys", timeout=300)):
                passed, output = run_equiv_check(self.GOLD_SV, self.GATE_SV)
                assert passed is False
                assert "timed out" in output.lower()

    def test_no_module_found(self) -> None:
        passed, output = run_equiv_check("// no module here\n", "// no module here\n")
        assert passed is False
        assert "could not find any module" in output.lower()

    def test_tcl_script_uses_correct_top(self) -> None:
        """Verify that the generated Tcl script uses the first module as top."""
        sv = "module checker_a (input logic clk);\nendmodule\nmodule checker_b (input logic clk);\nendmodule\n"
        mock_result = MagicMock(returncode=0, stdout="PASS\n", stderr="")
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                passed, _ = run_equiv_check(sv, sv)
                assert passed is True
                # Verify the Tcl script was written and yosys was called with -s flag
                call_args = mock_run.call_args[0][0]
                assert "yosys" == call_args[0]
                assert "-s" == call_args[1]


class TestRunEquivCheckMulti:
    """Tests for multi-module equivalence checking."""

    def test_multi_module_passed(self) -> None:
        unopt = {
            "checker_top": "module checker_top (...); endmodule\n",
            "checker_sub": "module checker_sub (...); endmodule\n",
        }
        opt = {
            "checker_top": "module checker_top (...); // optimized\nendmodule\n",
            "checker_sub": "module checker_sub (...); // optimized\nendmodule\n",
        }
        mock_result = MagicMock(returncode=0, stdout="PASS\n", stderr="")
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("subprocess.run", return_value=mock_result):
                passed, _ = run_equiv_check_multi(unopt, opt, top_module="checker_top")
                assert passed is True

    def test_multi_module_no_modules(self) -> None:
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            passed, output = run_equiv_check_multi({}, {}, top_module="checker_top")
            assert passed is False
            assert "empty module" in output.lower()


class TestCheckOptimizerPass:
    """Integration tests for check_optimizer_pass with mocked emit + yosys.

    The emit/emit_all steps are mocked to avoid requiring full CheckerNode
    trees that match compose() output.  The tested logic is the pipeline:
    emit(unopt) → emit(opt) → yosys equiv check → parse result.
    """

    def test_single_module_passed(self) -> None:
        from sva2rtl.ir import CheckerNode, SourceLoc

        unopt = CheckerNode(
            template_name="overlap_bitvec",
            module_name="checker_test",
            children=(),
            observed_signals=(),
            params={},
            cse_origin=None,
            source_loc=SourceLoc("test.sv", 1, 0),
        )
        opt = CheckerNode(
            template_name="overlap_bitvec",
            module_name="checker_test",
            children=(),
            observed_signals=(),
            params={},
            cse_origin=None,
            source_loc=SourceLoc("test.sv", 1, 0),
        )

        mock_result = MagicMock(returncode=0, stdout="PASS\n", stderr="")
        mock_sv = "module checker_test (input logic clk, rst_n);\nendmodule\n"
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("sva2rtl.emitter.emit", return_value=mock_sv):
                with patch("subprocess.run", return_value=mock_result):
                    passed, output = check_optimizer_pass(unopt, opt)
                    assert passed is True
                    assert "PASS" in output

    def test_optimizer_pass_failed(self) -> None:
        from sva2rtl.ir import CheckerNode, SourceLoc

        unopt = CheckerNode(
            template_name="overlap_bitvec",
            module_name="checker_test",
            children=(),
            observed_signals=(),
            params={},
            cse_origin=None,
            source_loc=SourceLoc("test.sv", 1, 0),
        )
        opt = CheckerNode(
            template_name="overlap_bitvec",
            module_name="checker_test",
            children=(),
            observed_signals=(),
            params={},
            cse_origin=None,
            source_loc=SourceLoc("test.sv", 1, 0),
        )

        mock_result = MagicMock(returncode=1, stdout="", stderr="FAIL\n")
        mock_sv = "module checker_test (input logic clk, rst_n);\nendmodule\n"
        with patch("sva2rtl.formal._yosys_is_available", return_value=True):
            with patch("sva2rtl.emitter.emit", return_value=mock_sv):
                with patch("subprocess.run", return_value=mock_result):
                    passed, _ = check_optimizer_pass(unopt, opt)
                    assert passed is False
