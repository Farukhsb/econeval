from pathlib import Path

from econeval.config import DriftTest, EconEvalConfig, FairnessConfig, InvariantRule
from econeval.errors import ExecutionIssue
from econeval.invariants import InvariantResult
from econeval.reporting import build_json_report, write_json_report, write_junit_report
from econeval.scenarios import DriftResult, FairnessResult, ScenarioResult


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


def test_build_json_report_includes_drift_and_fairness_results() -> None:
    config = EconEvalConfig(project="demo-model")
    drift_results = [
        DriftResult(
            name="shock_feature_stability",
            baseline_dataset="data/baseline.csv",
            dataset="data/current.csv",
            feature="shock",
            threshold=0.05,
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


def test_write_junit_report_writes_xml(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.xml"
    report = build_json_report(
        EconEvalConfig(project="demo-model"),
        [InvariantResult(name="elasticity", expression="model.elasticity < 0", passed=False, error="bad")],
        issues=[ExecutionIssue(stage="config", message="missing config")],
    )

    write_junit_report(report_path, report)

    text = report_path.read_text(encoding="utf-8")
    assert "<testsuites" in text
    assert "<failure" in text
    assert "<error" in text
