"""Static regression checks for release-critical GitHub Actions setup."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "tools" / "ci" / "install_verilator.sh"
SLANG_INSTALLER = ROOT / "tools" / "ci" / "install_slang.sh"
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "differential-nightly.yml",
)
FORMAL_WORKFLOW = ROOT / ".github" / "workflows" / "formal-full.yml"
SUPPORT_MATRIX = ROOT / "SUPPORT_MATRIX.md"
PROJECT_STATUS = ROOT / "PROJECT_STATUS.md"
README = ROOT / "README.md"
NIGHTLY_WORKFLOW = ROOT / ".github" / "workflows" / "differential-nightly.yml"
CHECKOUT_NODE24_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_UV_NODE24_SHA = "c771a70e6277c0a99b617c7a806ffedaca235ff9"


def test_verilator_installer_has_all_source_build_dependencies() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    for dependency in (
        "autoconf",
        "bison",
        "build-essential",
        "flex",
        "help2man",
        "libfl-dev",
    ):
        assert dependency in script
    assert 'test -r /usr/include/FlexLexer.h' in script
    assert "brew --prefix flex" in script
    assert "brew --prefix bison" in script
    assert "HOMEBREW_NO_AUTO_UPDATE=1" in script
    assert 'verilator_prefix="$(brew --prefix)"' in script
    assert "verilator_install=(make install)" in script
    assert './configure --prefix="${verilator_prefix}"' in script
    assert '"${verilator_install[@]}"' in script
    assert "\nsudo make install\n" not in script
    assert "VERILATOR_VERSION:-v5.028" in script
    assert "02d4b6f34754b46a97cfd70f5fcbc9b730bd1f0a24c3fc37223397778fcb142c" in script
    assert "shasum -a 256 -c -" in script


def test_slang_installer_verifies_both_pinned_archives() -> None:
    script = SLANG_INSTALLER.read_text(encoding="utf-8")
    assert "SLANG_VERSION:-v11.0" in script
    assert "951a170e10e25e54c91565030acfdfc11c3226714ebf225a18ad4166a898d8a4" in script
    assert "6d2f86ffedfefe663c6f55fd77348806faafccd69e71f7359986b0c9604f9187" in script
    assert "shasum -a 256 -c -" in script


def test_all_verilator_jobs_use_the_shared_installer() -> None:
    workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in WORKFLOWS)
    assert workflow_text.count("bash tools/ci/install_verilator.sh") == 4
    assert 'wget -q "https://github.com/verilator/verilator' not in workflow_text


def test_verilator_installer_has_valid_shell_syntax() -> None:
    for installer in (INSTALLER, SLANG_INSTALLER):
        result = subprocess.run(
            ["bash", "-n", str(installer)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr


def test_templates_do_not_accidentally_start_verilator_metacomments() -> None:
    directive_like_comment = re.compile(r"^\s*//\s*verilator\b", re.IGNORECASE)
    for template in (ROOT / "templates").glob("*.j2"):
        for line_number, line in enumerate(template.read_text(encoding="utf-8").splitlines(), 1):
            assert not directive_like_comment.match(line), f"{template}:{line_number}: {line}"


def test_full_formal_uses_a_pinned_coherent_toolchain() -> None:
    workflow = FORMAL_WORKFLOW.read_text(encoding="utf-8")
    ci_workflow = WORKFLOWS[0].read_text(encoding="utf-8")
    for formal_configuration in (workflow, ci_workflow):
        assert (
            "YosysHQ/setup-oss-cad-suite@c7845bc0d335c8076aa22047e85972caa8a916df"
            in formal_configuration
        )
        assert 'version: "2026-07-21"' in formal_configuration
        assert "git clone --depth 1 https://github.com/YosysHQ/sby.git" not in (
            formal_configuration
        )


def test_full_formal_isolates_expensive_implication_miters() -> None:
    workflow = FORMAL_WORKFLOW.read_text(encoding="utf-8")
    assert "tests/test_v151_nfa_bmc.py tests/test_v151_p2_bmc.py" not in workflow
    assert "tests/test_v151_p2_bmc.py::TestOverlapImplNfaMiter" in workflow
    assert "tests/test_v151_p2_bmc.py::TestNonoverlapImplNfaMiter" in workflow


def test_nightly_runs_both_differential_backends_and_all_mutation_surfaces() -> None:
    workflow = NIGHTLY_WORKFLOW.read_text(encoding="utf-8")
    for simulator in ("iverilog", "verilator"):
        assert f"--simulator={simulator}" in workflow
    assert workflow.count("differential_slow") >= 2
    assert workflow.count("--hypothesis-seed=20260722") == 2
    assert workflow.count("HYPOTHESIS_ROTATING_SEED") >= 4
    assert workflow.count("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02") == 2
    assert workflow.count("differential-artifacts/*.json") == 2
    for module in (
        "bool_semantics.py",
        "behavioral_oracle.py",
        "composer.py",
        "ast_importer.py",
    ):
        assert f"--module {module}" in workflow
    assert "tools/mutation/run_template_mutation.py" in workflow


def test_nightly_prepares_nested_basetemp_and_uploads_sanitized_hidden_artifacts() -> None:
    """A clean checkout must support nested pytest basetemp and replay paths."""
    workflow = NIGHTLY_WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count("mkdir -p .artifacts") == 2
    assert workflow.count("include-hidden-files: true") == 2
    job_markers = {
        "iverilog": "differential-slow-iverilog:",
        "verilator": "differential-verilator:",
    }
    for backend, job_marker in job_markers.items():
        prepare = workflow.index("mkdir -p .artifacts", workflow.index(job_marker))
        fast_run = workflow.index(f"--basetemp=.artifacts/{backend}-fast")
        assert prepare < fast_run


def test_ci_enforces_real_coverage_and_critical_module_floors() -> None:
    workflow = WORKFLOWS[0].read_text(encoding="utf-8")
    assert "--cov=src/sva2rtl" in workflow
    assert "--cov-branch" in workflow
    assert "--cov-fail-under=82" in workflow
    assert "tools/ci/check_coverage.py coverage.json" in workflow


def test_ci_and_nightly_enforce_test_execution_budgets() -> None:
    ci = WORKFLOWS[0].read_text(encoding="utf-8")
    nightly = NIGHTLY_WORKFLOW.read_text(encoding="utf-8")
    formal = FORMAL_WORKFLOW.read_text(encoding="utf-8")

    assert ci.count("tools/ci/check_junit.py") == 6
    assert "--min-passed 1200 --max-skipped 200" in ci
    assert "--min-passed 160 --max-skipped 1" in ci
    assert "--min-passed 130 --max-skipped 0" in ci
    assert "--min-passed 3 --max-skipped 0" in ci
    assert "--min-passed 900 --max-skipped 200" in ci
    assert nightly.count("tools/ci/check_junit.py") == 4
    assert formal.count("tools/ci/check_junit.py") == 1
    assert "max-skipped: 1" in formal
    assert "--max-skipped ${{ matrix.max-skipped }}" in formal


def test_ci_builds_and_smokes_distribution_on_python_314() -> None:
    workflow = WORKFLOWS[0].read_text(encoding="utf-8")

    assert "Python 3.14 + installed distribution" in workflow
    assert "uv sync --dev --frozen --python 3.14" in workflow
    assert "uv build --out-dir dist" in workflow
    assert "tools/ci/smoke_distribution.py" in workflow


def test_external_actions_and_dependency_sync_are_immutable() -> None:
    workflows = (*WORKFLOWS, FORMAL_WORKFLOW)
    action_ref = re.compile(r"^\s*- uses: [^@\s]+@([^\s#]+)", re.MULTILINE)
    sha = re.compile(r"^[0-9a-f]{40}$")
    for path in workflows:
        workflow = path.read_text(encoding="utf-8")
        refs = action_ref.findall(workflow)
        assert refs
        assert all(sha.fullmatch(ref) for ref in refs), f"mutable action ref in {path.name}"
        assert "uv sync --dev\n" not in workflow
        assert "uv sync --dev --frozen" in workflow
        assert "wget -q" not in workflow


def test_core_actions_use_pinned_native_node24_releases() -> None:
    """Do not rely on GitHub's temporary Node 20-to-24 compatibility shim."""

    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in (*WORKFLOWS, FORMAL_WORKFLOW)
    )

    assert workflow_text.count(f"actions/checkout@{CHECKOUT_NODE24_SHA}") == 10
    assert workflow_text.count(f"astral-sh/setup-uv@{SETUP_UV_NODE24_SHA}") == 10
    assert workflow_text.count("prune-cache: true") == 10
    assert "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683" not in workflow_text
    assert "astral-sh/setup-uv@e4db8464a088ece1b920f60402e813ea4de65b8f" not in workflow_text


def test_support_claims_do_not_reuse_historical_remote_evidence() -> None:
    matrix = SUPPORT_MATRIX.read_text(encoding="utf-8")
    status = PROJECT_STATUS.read_text(encoding="utf-8")
    # The one occurrence is the legend definition, not a promoted matrix row.
    assert matrix.count("| Fully supported |") == 1
    assert "0 construct rows are promoted" in matrix
    assert "current-commit rerun pending" in matrix
    assert "当前支持矩阵保持\n0 个 Fully supported" in status


def test_readme_describes_the_implemented_optimizer() -> None:
    readme = README.read_text(encoding="utf-8")
    assert "DFA minimization" not in readme
    assert "Hopcroft" not in readme
    assert "Constant folding" in readme
