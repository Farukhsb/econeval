from pathlib import Path

from econeval.config import EconEvalConfig, FairnessConfig, InvariantRule
from econeval.errors import ExecutionIssue
from econeval.invariants import InvariantResult
from econeval.reporting import (
    build_json_report,
    write_dashboard_report,
    write_github_step_summary,
    write_html_report,
    write_json_report,
    write_junit_report,
    write_markdown_report,
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
        )
    ]

    report = build_json_report(config, [], [], drift_results, fairness_results)

    assert report["summary"]["total"] == 2
    assert report["summary"]["passed"] == 2
    assert report["summary"]["failed"] == 0
    assert report["summary"]["status"] == "pass"
    assert len(report["drift_checks"]) == 1
    assert len(report["fairness_checks"]) == 1


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


def test_write_html_report_writes_text(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.html"
    report = build_json_report(EconEvalConfig(project="demo-model"), [])

    write_html_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "<!doctype html>" in text.lower()
    assert "econeval report" in text.lower()


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


def test_write_github_step_summary_writes_table(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "step-summary.md"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [],
        [
            ScenarioResult(
                name="elasticity_monte_carlo",
                dataset="",
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
        "| Type | Check | Margin / Error | Scan Grid / Values | Outcome "
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
