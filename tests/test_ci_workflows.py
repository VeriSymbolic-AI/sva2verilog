"""Static regression checks for release-critical GitHub Actions setup."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
INSTALLER = ROOT / "tools" / "ci" / "install_verilator.sh"
WORKFLOWS = (
    ROOT / ".github" / "workflows" / "ci.yml",
    ROOT / ".github" / "workflows" / "differential-nightly.yml",
)
FORMAL_WORKFLOW = ROOT / ".github" / "workflows" / "formal-full.yml"
SUPPORT_MATRIX = ROOT / "SUPPORT_MATRIX.md"
PROJECT_STATUS = ROOT / "PROJECT_STATUS.md"
README = ROOT / "README.md"
NIGHTLY_WORKFLOW = ROOT / ".github" / "workflows" / "differential-nightly.yml"


def test_verilator_installer_has_all_source_build_dependencies() -> None:
    script = INSTALLER.read_text(encoding="utf-8")
    for dependency in ("autoconf", "bison", "build-essential", "flex", "help2man"):
        assert dependency in script
    assert "brew --prefix flex" in script
    assert "brew --prefix bison" in script
    assert "HOMEBREW_NO_AUTO_UPDATE=1" in script
    assert 'verilator_prefix="$(brew --prefix)"' in script
    assert 'verilator_install=(make install)' in script
    assert './configure --prefix="${verilator_prefix}"' in script
    assert '"${verilator_install[@]}"' in script
    assert "\nsudo make install\n" not in script
    assert 'VERILATOR_VERSION:-v5.028' in script


def test_all_verilator_jobs_use_the_shared_installer() -> None:
    workflow_text = "\n".join(path.read_text(encoding="utf-8") for path in WORKFLOWS)
    assert workflow_text.count("bash tools/ci/install_verilator.sh") == 4
    assert "wget -q \"https://github.com/verilator/verilator" not in workflow_text


def test_verilator_installer_has_valid_shell_syntax() -> None:
    result = subprocess.run(
        ["bash", "-n", str(INSTALLER)],
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
    assert workflow.count("--hypothesis-seed=20260722") == 4
    for module in (
        "bool_semantics.py",
        "behavioral_oracle.py",
        "composer.py",
        "ast_importer.py",
    ):
        assert f"--module {module}" in workflow
    assert "tools/mutation/run_template_mutation.py" in workflow


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
