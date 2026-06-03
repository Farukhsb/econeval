import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from econeval.cli import run_cli


def test_cli_entrypoint_runs_via_subprocess(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "cli-report.json"
    config_path = root / "examples" / "basic_model" / "econeval.yml"
    model_path = root / "examples" / "basic_model" / "model.py"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "econeval",
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "DemoModel",
            "--report",
            str(report_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert report_path.exists()
    assert "EconEval" in completed.stdout


def test_run_cli_writes_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "econeval-report.json"
    config_path = root / "examples" / "basic_model" / "econeval.yml"
    model_path = root / "examples" / "basic_model" / "model.py"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "DemoModel",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["project"] == "basic-model"
    assert payload["summary"]["status"] == "pass"


def test_run_cli_returns_nonzero_for_broken_example(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "broken-report.json"
    config_path = root / "examples" / "broken_model" / "econeval.yml"
    model_path = root / "examples" / "broken_model" / "model.py"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "BrokenModel",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["project"] == "broken-model"
    assert payload["summary"]["status"] == "fail"


@pytest.mark.parametrize(
    ("section", "check_name"),
    [
        ("invariants", "elasticity_must_be_negative"),
        ("stress_tests", "stagflation_shock"),
    ],
)
def test_broken_model_example_fails_expected_checks(
    tmp_path: Path, section: str, check_name: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "broken-report.json"
    config_path = root / "examples" / "broken_model" / "econeval.yml"
    model_path = root / "examples" / "broken_model" / "model.py"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "BrokenModel",
            "--report",
            str(report_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    failed_names = {item["name"] for item in payload[section] if not item.get("passed", True)}

    assert exit_code == 1
    assert payload["summary"]["status"] == "fail"
    assert check_name in failed_names


def test_run_cli_writes_structured_config_error(tmp_path: Path) -> None:
    report_path = tmp_path / "config-error-report.json"

    exit_code = run_cli(
        [
            "--config",
            str(tmp_path / "missing.yml"),
            "--model",
            str(tmp_path / "missing_model.py"),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "fail"
    assert payload["issues"][0]["stage"] == "config"


def test_run_cli_writes_junit_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "econeval-report.xml"
    config_path = root / "examples" / "basic_model" / "econeval.yml"
    model_path = root / "examples" / "basic_model" / "model.py"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "DemoModel",
            "--report",
            str(report_path),
            "--format",
            "junit",
        ]
    )

    assert exit_code == 0
    root_element = ET.fromstring(report_path.read_text(encoding="utf-8"))
    assert root_element.tag == "testsuites"


def test_run_cli_writes_github_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "econeval-report.json"
    summary_path = tmp_path / "step-summary.md"
    config_path = root / "examples" / "broken_model" / "econeval.yml"
    model_path = root / "examples" / "broken_model" / "model.py"

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "BrokenModel",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    assert summary_path.exists()
    text = summary_path.read_text(encoding="utf-8")
    assert text.startswith("# EconEval Summary")
    assert "<details>" in text
    assert "All Checks" in text
    assert (
        "| Type | Check | Severity | Margin / Error | Scan Grid / Values | "
        "Outcome Distribution | Worst Sample | Impacted Variables | Details |"
    ) in text
    assert "elasticity_must_be_negative" in text
    assert "## Failed Checks" in text


def test_run_cli_writes_github_step_summary_with_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "econeval-report.json"
    summary_path = tmp_path / "step-summary.md"
    config_path = root / "examples" / "advanced_model" / "econeval.yml"
    model_path = root / "examples" / "advanced_model" / "model.py"

    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "AdvancedModel",
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    text = summary_path.read_text(encoding="utf-8")
    assert "price_elasticity_scan" in text
    assert "grid=1 -> 1.01 -> 1.05 -> 1.1" in text
    assert "values=" in text
    assert "->" in text


@pytest.mark.parametrize(
    ("report_format", "suffix", "expected"),
    [
        ("markdown", ".md", "# EconEval Report"),
        ("html", ".html", "<!doctype html>"),
    ],
)
def test_run_cli_writes_text_reports(
    tmp_path: Path, report_format: str, suffix: str, expected: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / f"econeval-report{suffix}"
    config_path = root / "examples" / "advanced_model" / "econeval.yml"
    model_path = root / "examples" / "advanced_model" / "model.py"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "AdvancedModel",
            "--report",
            str(report_path),
            "--format",
            report_format,
        ]
    )

    assert exit_code == 0
    assert expected.lower() in report_path.read_text(encoding="utf-8").lower()


def test_run_cli_writes_dashboard_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "econeval-dashboard.html"
    config_path = root / "examples" / "broken_model" / "econeval.yml"
    model_path = root / "examples" / "broken_model" / "model.py"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(model_path),
            "--class",
            "BrokenModel",
            "--report",
            str(report_path),
            "--format",
            "dashboard",
        ]
    )

    assert exit_code == 1
    text = report_path.read_text(encoding="utf-8")
    assert "EconEval Dashboard" in text
    assert "Section Overview" in text
    assert "Failure Spotlight" in text
    assert "Top Failures" in text
    assert "Open card" in text


def test_run_cli_verbose_logs_stage_summaries(capsys: pytest.CaptureFixture[str]) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = root / "tmp-econeval-report.json"
    config_path = root / "examples" / "advanced_model" / "econeval.yml"
    model_path = root / "examples" / "advanced_model" / "model.py"

    try:
        exit_code = run_cli(
            [
                "--config",
                str(config_path),
                "--model",
                str(model_path),
                "--class",
                "AdvancedModel",
                "--report",
                str(report_path),
                "--verbose",
            ]
        )
        output = capsys.readouterr().out
    finally:
        if report_path.exists():
            report_path.unlink()

    assert exit_code == 0
    assert "[econeval] loading config" in output
    assert "[econeval] invariants:" in output
    assert "[econeval] economic checks:" in output
    assert "[econeval] wrote report to" in output


def test_run_cli_watch_mode_routes_to_watch_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = {}

    def fake_watch_mode(args, log):
        called["watch"] = True
        assert args.watch is True
        assert callable(log)
        return 0

    monkeypatch.setattr("econeval.cli._run_watch_mode", fake_watch_mode)

    exit_code = run_cli(
        [
            "--config",
            "examples/basic_model/econeval.yml",
            "--model",
            "examples/basic_model/model.py",
            "--watch",
        ]
    )

    assert exit_code == 0
    assert called["watch"] is True
