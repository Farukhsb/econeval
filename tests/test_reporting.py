import sys
import types
from pathlib import Path

import pytest

from econeval.config import EconEvalConfig, FairnessConfig, InvariantRule
from econeval.errors import ExecutionIssue
from econeval.invariants import InvariantResult
from econeval.reporting import (
    build_json_report,
    build_report_comparison,
    write_dashboard_report,
    write_github_step_summary,
    write_html_report,
    write_json_report,
    write_junit_report,
    write_markdown_report,
    write_pdf_report,
)
from econeval.scenarios import (
    DriftResult,
    EconomicCheckResult,
    EconomicDriftResult,
    FairnessResult,
    ScenarioResult,
)


def test_build_json_report_summarizes_results() -> None:
    config = EconEvalConfig(
        project="demo-model",
        invariants=[InvariantRule(name="elasticity", expression="model.elasticity < 0")],
        fairness=FairnessConfig(enabled=False, metrics=[]),
    )
    results = [
        InvariantResult(name="elasticity", expression="model.elasticity < 0", passed=True),
        InvariantResult(name="supply", expression="model.supply >= 0", passed=False),
    ]

    report = build_json_report(config, results)

    assert report["project"] == "demo-model"
    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 1
    assert report["summary"]["failed"] == 1
    assert report["summary"]["status"] == "fail"
    assert report["stress_tests"] == []
    assert report["economic_checks"] == []


def test_build_json_report_counts_scenario_results() -> None:
    config = EconEvalConfig(project="demo-model")
    results = [InvariantResult(name="elasticity", expression="model.elasticity < 0", passed=True)]
    scenarios = [
        ScenarioResult(
            name="stagflation_shock",
            dataset="data/stagflation.csv",
            kind="synthetic",
            metric="mape",
            threshold=0.1,
            value=0.0,
            passed=True,
        )
    ]

    report = build_json_report(config, results, scenarios)

    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 2
    assert report["summary"]["failed"] == 0
    assert report["summary"]["status"] == "pass"
    assert len(report["stress_tests"]) == 1


def test_build_json_report_counts_economic_results() -> None:
    config = EconEvalConfig(project="demo-model")
    results = [InvariantResult(name="elasticity", expression="model.elasticity < 0", passed=True)]
    economic_results = [
        EconomicCheckResult(
            name="gdp_accounting_identity",
            kind="accounting_identity",
            passed=True,
            value=0.0,
            tolerance=1e-9,
            states=1,
        )
    ]

    report = build_json_report(config, results, economic_results=economic_results)

    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 2
    assert report["summary"]["failed"] == 0
    assert report["summary"]["status"] == "pass"
    assert len(report["economic_checks"]) == 1


def test_build_json_report_includes_worst_state_fields() -> None:
    config = EconEvalConfig(project="demo-model")
    economic_results = [
        EconomicCheckResult(
            name="solver_converges",
            kind="convergence",
            passed=False,
            value=1.0,
            tolerance=1e-9,
            detail="method=solve",
            states=3,
            worst_state={"supply": 10.0},
        )
    ]

    report = build_json_report(config, [], economic_results=economic_results)

    item = report["economic_checks"][0]
    assert item["states"] == 3
    assert item["worst_state"] == {"supply": 10.0}


def test_build_json_report_includes_scan_inputs() -> None:
    config = EconEvalConfig(project="demo-model")
    economic_results = [
        EconomicCheckResult(
            name="price_elasticity_scan",
            kind="scan",
            passed=True,
            value=0.0,
            tolerance=1e-9,
            detail="method=demand",
            observations=[10.0, 9.98, 9.9, 9.8],
            scan_inputs=[1.0, 1.01, 1.05, 1.1],
        )
    ]

    report = build_json_report(config, [], economic_results=economic_results)

    item = report["economic_checks"][0]
    assert item["scan_inputs"] == [1.0, 1.01, 1.05, 1.1]


def test_build_json_report_includes_drift_and_fairness_results() -> None:
    config = EconEvalConfig(project="demo-model")
    drift_results = [
        DriftResult(
            name="shock_feature_stability",
            baseline_dataset="data/baseline.csv",
            dataset="data/current.csv",
            feature="shock",
            statistic="median",
            mode="snapshot",
            backend="manual",
            threshold=0.05,
            baseline_value=0.1,
            current_value=0.11,
            value=0.01,
            passed=True,
        )
    ]
    fairness_results = [
        FairnessResult(
            name="demographic_parity_difference",
            dataset="data/fairness.csv",
            metric="demographic_parity_difference",
            threshold=0.2,
            value=0.0,
            passed=True,
            severity="pass",
        )
    ]

    report = build_json_report(config, [], [], drift_results, fairness_results)

    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 2
    assert report["summary"]["failed"] == 0
    assert report["summary"]["status"] == "pass"
    assert len(report["drift_checks"]) == 1
    assert len(report["fairness_checks"]) == 1
    assert report["fairness_checks"][0]["severity"] == "pass"


def test_build_json_report_treats_fairness_warn_as_non_failing() -> None:
    config = EconEvalConfig(project="demo-model")
    report = build_json_report(
        config,
        [],
        fairness_results=[
            FairnessResult(
                name="disparate_impact_ratio",
                dataset="data/fairness.csv",
                metric="disparate_impact_ratio",
                threshold=0.8,
                value=0.79,
                passed=False,
                severity="warn",
            )
        ],
    )

    assert report["summary"]["status"] == "pass"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["passed"] == 1


def test_build_json_report_includes_economic_drift_results() -> None:
    config = EconEvalConfig(project="demo-model")
    economic_drift_results = [
        EconomicDriftResult(
            name="predicted_mean_shift",
            baseline_dataset="data/baseline.csv",
            dataset="data/current.csv",
            metric="relative_change",
            output="mean_prediction",
            threshold=0.02,
            baseline_value=1.0,
            current_value=1.01,
            value=0.01,
            passed=True,
        )
    ]

    report = build_json_report(config, [], economic_drift_results=economic_drift_results)

    assert report["summary"]["total"] == 1
    assert report["summary"]["passed"] == 1
    assert report["summary"]["failed"] == 0
    assert report["summary"]["status"] == "pass"
    assert len(report["economic_drift_checks"]) == 1


def test_build_json_report_includes_issues() -> None:
    config = EconEvalConfig(project="demo-model")
    report = build_json_report(
        config,
        [],
        issues=[ExecutionIssue(stage="config", message="missing config")],
    )

    assert report["summary"]["failed"] == 1
    assert report["summary"]["status"] == "fail"
    assert report["issues"][0]["stage"] == "config"


def test_build_report_comparison_detects_regressions_and_improvements() -> None:
    current = {
        "project": "demo-model",
        "generated_at": "2026-06-03T00:00:00Z",
        "summary": {"total": 2, "passed": 1, "failed": 1},
        "invariants": [
            {"name": "elasticity", "passed": False, "detail": "current fail"},
        ],
        "drift_checks": [
            {"name": "psi_feature", "passed": True, "detail": "current pass"},
        ],
        "economic_checks": [],
        "economic_drift_checks": [],
        "stress_tests": [],
        "fairness_checks": [],
        "issues": [],
    }
    baseline = {
        "project": "demo-model",
        "generated_at": "2026-05-03T00:00:00Z",
        "summary": {"total": 2, "passed": 2, "failed": 0},
        "invariants": [
            {"name": "elasticity", "passed": True, "detail": "baseline pass"},
        ],
        "drift_checks": [
            {"name": "psi_feature", "passed": False, "detail": "baseline fail"},
        ],
        "economic_checks": [],
        "economic_drift_checks": [],
        "stress_tests": [],
        "fairness_checks": [],
        "issues": [],
    }

    comparison = build_report_comparison(current, baseline)

    assert comparison["baseline_project"] == "demo-model"
    assert comparison["summary_delta"] == {"total": 0, "passed": -1, "failed": 1}
    assert comparison["regressions"][0]["name"] == "elasticity"
    assert comparison["improvements"][0]["name"] == "psi_feature"


def test_build_json_report_has_stable_schema() -> None:
    report = build_json_report(EconEvalConfig(project="demo-model"), [])

    assert set(report) == {
        "generated_at",
        "project",
        "version",
        "summary",
        "invariants",
        "economic_checks",
        "economic_drift_checks",
        "stress_tests",
        "drift_checks",
        "fairness_checks",
        "issues",
    }
    assert set(report["summary"]) == {"total", "passed", "failed", "status"}
    assert report["summary"]["total"] == 0
    assert report["summary"]["passed"] == 0
    assert report["summary"]["failed"] == 0
    assert report["summary"]["status"] == "pass"
    assert report["invariants"] == []
    assert report["economic_checks"] == []
    assert report["economic_drift_checks"] == []
    assert report["stress_tests"] == []
    assert report["drift_checks"] == []
    assert report["fairness_checks"] == []
    assert report["issues"] == []


def test_write_json_report_creates_parent_directories(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.json"

    write_json_report(report_path, {"hello": "world"})

    assert report_path.exists()
    assert report_path.read_text(encoding="utf-8").strip() == '{\n  "hello": "world"\n}'


def test_write_markdown_report_writes_text(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.md"
    report = build_json_report(EconEvalConfig(project="demo-model"), [])

    write_markdown_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert text.startswith("# EconEval Report")
    assert "## Checks" in text


def test_write_markdown_report_includes_visual(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.md"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [
            ScenarioResult(
                name="broken_shock",
                dataset="data/stagflation.csv",
                kind="synthetic",
                metric="mape",
                threshold=0.01,
                value=0.2,
                passed=False,
                visual="[########----] value=0.2 threshold=0.01",
            )
        ],
    )

    write_markdown_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "visual" in text.lower()
    assert "[########----]" in text


def test_write_markdown_report_includes_worst_state(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.md"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        economic_results=[
            EconomicCheckResult(
                name="solver_converges",
                kind="convergence",
                passed=False,
                value=1.0,
                tolerance=1e-9,
                detail="method=solve",
                states=3,
                worst_state={"supply": 10.0},
                worst_value=0.0,
            )
        ],
    )

    write_markdown_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "worst initial state" in text
    assert "worst observed value" in text
    assert "10.0" in text


def test_write_markdown_report_includes_fairness_severity(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.md"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        fairness_results=[
            FairnessResult(
                name="disparate_impact_ratio",
                dataset="data/fairness.csv",
                metric="disparate_impact_ratio",
                threshold=0.8,
                value=0.78,
                passed=False,
                severity="warn",
            )
        ],
    )

    write_markdown_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "- `disparate_impact_ratio`: `warn`" in text
    assert "warn" in text


def test_write_html_report_writes_text(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.html"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [InvariantResult(name="elasticity", expression="model.elasticity < 0", passed=True)],
    )

    write_html_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in text.lower()
    assert "econeval report" in text.lower()
    assert "details class='section'" in text
    assert "section-count" in text


def test_write_html_report_includes_state_summary(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.html"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        economic_results=[
            EconomicCheckResult(
                name="solver_converges",
                kind="convergence",
                passed=False,
                value=1.0,
                tolerance=1e-9,
                detail="method=solve",
                states=3,
                worst_state={"supply": 10.0},
                worst_value=0.0,
            )
        ],
    )

    write_html_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "State Summary" in text
    assert "worst initial state" in text
    assert "state-summary" in text
    assert "details class='section'" in text


def test_write_html_report_handles_large_batch(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.html"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [
            InvariantResult(
                name=f"elasticity_{idx}",
                expression="model.elasticity < 0",
                passed=True,
            )
            for idx in range(100)
        ],
    )

    write_html_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert text.count("details class='section'") == 1
    assert "elasticity_99" in text


def test_write_pdf_report_uses_optional_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, str] = {}

    class FakeHTML:
        def __init__(self, string: str) -> None:
            captured["html"] = string

        def write_pdf(self, target: str) -> None:
            Path(target).write_bytes(b"%PDF-1.4\n% fake pdf\n")
            captured["target"] = target

    fake_module = types.SimpleNamespace(HTML=FakeHTML)
    monkeypatch.setitem(sys.modules, "weasyprint", fake_module)

    report = build_json_report(EconEvalConfig(project="demo-model"), [])
    report_path = tmp_path / "artifacts" / "econeval-report.pdf"

    write_pdf_report(report_path, report)

    assert report_path.exists()
    assert report_path.read_bytes().startswith(b"%PDF-1.4")
    assert "EconEval Report" in captured["html"]
    assert captured["target"] == str(report_path)


def test_write_dashboard_report_includes_overview_and_spotlight(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-dashboard.html"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        economic_results=[
            EconomicCheckResult(
                name="solver_converges",
                kind="convergence",
                passed=False,
                value=1.0,
                tolerance=1e-9,
                detail="method=solve",
                states=3,
                worst_state={"supply": 10.0},
                worst_value=0.0,
            )
        ],
    )

    write_dashboard_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "EconEval Dashboard" in text
    assert "dashboard-filter" in text
    assert "details class='section'" in text
    assert "Section Overview" in text
    assert "Failure Spotlight" in text
    assert "Top Failures" in text
    assert "solver_converges" in text
    assert "Open card" in text


def test_write_dashboard_report_includes_fairness_severity(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-dashboard.html"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        fairness_results=[
            FairnessResult(
                name="disparate_impact_ratio",
                dataset="data/fairness.csv",
                metric="disparate_impact_ratio",
                threshold=0.8,
                value=0.78,
                passed=False,
                severity="warn",
            )
        ],
    )

    write_dashboard_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "severity" in text.lower()
    assert "warn" in text.lower()
    assert "Fairness warnings" in text
    assert "1 warnings" in text


def test_write_github_step_summary_writes_table(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "step-summary.md"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        [
            ScenarioResult(
                name="elasticity_monte_carlo",
                dataset="",
                kind="monte_carlo",
                metric="invariants",
                threshold=0.0,
                value=0.0,
                passed=True,
                detail="samples=12, failures=0, failure_rate=0",
                manipulations=[
                    {"variable": "elasticity", "action": "add", "value": 0.0, "sigma": 0.02}
                ],
                invariants=[
                    {
                        "name": "elasticity_remains_reasonable",
                        "expression": "model.elasticity < 0.5",
                        "backend": "auto",
                    }
                ],
                samples=12,
                failure_count=0,
                percentiles={"p10": 0.0, "p50": 0.0, "p90": 0.0},
                worst_sample={
                    "score": 0.0,
                    "failed_invariants": 0,
                    "manipulations": [{"variable": "elasticity", "action": "add", "value": 0.0}],
                },
            )
        ],
        economic_results=[
            EconomicCheckResult(
                name="price_elasticity_scan",
                kind="scan",
                passed=False,
                value=0.2,
                tolerance=1e-9,
                detail="method=demand",
                scan_inputs=[1.0, 1.01, 1.05, 1.1],
                observations=[10.0, 10.2, 10.5, 10.8],
            ),
            EconomicCheckResult(
                name="solver_converges",
                kind="convergence",
                passed=False,
                value=1.0,
                tolerance=1e-9,
                detail="method=solve",
                states=3,
                worst_state={"supply": 10.0},
                worst_value=0.0,
            ),
        ],
    )

    write_github_step_summary(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert text.startswith("# EconEval Summary")
    assert "<details>" in text
    assert "All Checks" in text
    assert (
        "| Type | Check | Severity | Margin / Error | Scan Grid / Values | Outcome "
        "Distribution | Worst Sample | Impacted Variables | Details |"
    ) in text
    assert "samples=12" in text
    assert "failure_count=0" in text
    assert "p50=0" in text
    assert "score=0" in text
    assert "grid=1 -> 1.01 -> 1.05 -> 1.1" in text
    assert "values=10 -> 10.2 -> 10.5 -> 10.8" in text
    assert "supply=10.0" in text
    assert "## Failed Checks" in text


def test_write_junit_report_writes_xml(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.xml"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [
            InvariantResult(
                name="elasticity",
                expression="model.elasticity < 0",
                passed=False,
                error="bad",
            )
        ],
        issues=[ExecutionIssue(stage="config", message="missing config")],
    )

    write_junit_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "<testsuites" in text
    assert "<failure" in text
    assert "<error" in text
