from pathlib import Path

from econeval.config import EconEvalConfig, FairnessConfig, InvariantRule
from econeval.invariants import InvariantResult
from econeval.reporting import build_json_report, write_json_report


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


def test_write_json_report_creates_parent_directories(tmp_path: Path) -> None:
    report_path = tmp_path / "artifacts" / "econeval-report.json"

    write_json_report(report_path, {"hello": "world"})

    assert report_path.exists()
    assert report_path.read_text(encoding="utf-8").strip() == '{\n  "hello": "world"\n}'

