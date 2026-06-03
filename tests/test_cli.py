import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from econeval.cli import (
    _build_logger,
    _load_baseline_report,
    _path_state,
    _print_failure,
    _print_summary,
    _snapshot_watch_state,
    _wait_for_watch_change,
    _watch_paths,
    load_model_class,
    run_cli,
)


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


def test_run_cli_blame_flag_includes_traceability_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "econeval.yml"
    model_path = tmp_path / "model.py"
    report_path = tmp_path / "econeval-report.json"

    config_path.write_text(
        "\n".join(
            [
                "project: demo-model",
                "invariants:",
                "  - name: elasticity_must_be_negative",
                "    expression: model.elasticity < 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    model_path.write_text(
        "\n".join(
            [
                "class DemoModel:",
                "    def __init__(self) -> None:",
                "        self.elasticity = 0.25",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "econeval.invariants.collect_invariant_blame",
        lambda model, rule: [
            {
                "path": "model.py",
                "line": 3,
                "commit": "abc123def456",
                "summary": "Adjust elasticity default",
                "pull_request": 7,
            }
        ],
    )

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
            "--blame",
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    item = payload["invariants"][0]
    assert item["passed"] is False
    assert item["trace"] is not None
    assert item["blame"][0]["commit"] == "abc123def456"
    assert item["blame"][0]["pull_request"] == 7


def test_run_cli_requires_model_for_model_based_checks(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "missing-model-report.json"
    config_path = root / "examples" / "basic_model" / "econeval.yml"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "fail"
    assert payload["issues"][0]["stage"] == "model"
    assert "requires --model" in payload["issues"][0]["message"]


def test_run_cli_reports_missing_model_file(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "missing-file-report.json"
    config_path = root / "examples" / "basic_model" / "econeval.yml"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(tmp_path / "missing_model.py"),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "fail"
    assert payload["issues"][0]["stage"] == "model"
    assert "model file not found" in payload["issues"][0]["message"]


def test_run_cli_reports_missing_baseline_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "baseline-error-report.json"
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
            "--baseline-report",
            str(tmp_path / "missing-baseline.json"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "fail"
    assert payload["comparison_error"] is not None
    assert payload["issues"][0]["stage"] == "baseline_report"


def test_load_model_class_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="model file not found"):
        load_model_class(tmp_path / "missing_model.py", "DemoModel")


def test_load_model_class_raises_for_invalid_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_path = tmp_path / "example_model.py"
    model_path.write_text(
        "class ExampleModel:\n    pass\n",
        encoding="utf-8",
    )

    class FakeSpec:
        loader = None

    monkeypatch.setattr(
        "econeval.cli.importlib.util.spec_from_file_location", lambda *args: FakeSpec()
    )

    with pytest.raises(ValueError, match="could not load model file"):
        load_model_class(model_path, "ExampleModel")


def test_load_model_class_raises_for_missing_class(tmp_path: Path) -> None:
    model_path = tmp_path / "example_model.py"
    model_path.write_text(
        "class ExampleModel:\n    pass\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="class 'MissingModel' not found"):
        load_model_class(model_path, "MissingModel")


def test_watch_helpers_cover_paths_and_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yml"
    config_path.write_text("project: demo\n", encoding="utf-8")
    model_path = tmp_path / "model.py"
    model_path.write_text("class DemoModel:\n    pass\n", encoding="utf-8")

    args = type(
        "Args",
        (),
        {"config": str(config_path), "model": str(model_path), "watch_interval": 0.1},
    )()

    assert callable(_build_logger(verbose=True, quiet=False))
    watched_paths = _watch_paths(args)
    assert watched_paths == [config_path.resolve(), model_path.resolve()]
    state = _snapshot_watch_state(watched_paths)
    assert config_path.resolve() in state
    assert _path_state(tmp_path / "missing.txt") is None

    states = {
        watched_paths[0]: [
            state[watched_paths[0]],
            (state[watched_paths[0]][0] + 1, state[watched_paths[0]][1]),
        ],
        watched_paths[1]: [state[watched_paths[1]], state[watched_paths[1]]],
    }

    def fake_path_state(path: Path):
        values = states[path]
        return values.pop(0) if values else state[path]

    calls: list[float] = []

    def fake_sleep(value: float) -> None:
        calls.append(value)

    monkeypatch.setattr("econeval.cli._path_state", fake_path_state)
    monkeypatch.setattr("econeval.cli.time.sleep", fake_sleep)
    _wait_for_watch_change(watched_paths, {path: state[path] for path in watched_paths}, 0.0)
    assert calls == [0.1]


def test_run_cli_accepts_optional_model_for_relation_config(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "csv-with-model-report.json"
    config_path = root / "examples" / "csv_model" / "econeval.yml"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--model",
            str(tmp_path / "missing_model.py"),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 1
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["status"] == "fail"
    assert payload["issues"][0]["stage"] == "model"


def test_load_baseline_report_raises_for_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="baseline report not found"):
        _load_baseline_report(tmp_path / "missing-baseline.json")


def test_logger_helpers_and_summary_helpers(capsys: pytest.CaptureFixture[str]) -> None:
    quiet_logger = _build_logger(verbose=False, quiet=True)
    verbose_logger = _build_logger(verbose=True, quiet=False)

    quiet_logger("suppressed")
    verbose_logger("visible")
    _print_summary("pass", 2, 2, quiet=False, report_format="json")
    _print_summary("pass", 2, 2, quiet=True, report_format="json")
    _print_failure("model load", RuntimeError("boom"), quiet=False)
    _print_failure("model load", RuntimeError("boom"), quiet=True)

    output = capsys.readouterr().out
    assert "[econeval] visible" in output
    assert "EconEval: pass (2/2 checks passed, format=json)" in output
    assert "EconEval: fail (model load: boom)" in output
    assert "suppressed" not in output


def test_run_cli_supports_model_less_csv_relations(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "csv-report.json"
    config_path = root / "examples" / "csv_model" / "econeval.yml"

    exit_code = run_cli(
        [
            "--config",
            str(config_path),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["project"] == "csv-model"
    assert payload["summary"]["status"] == "pass"
    assert payload["stress_tests"][0]["kind"] == "relation"
    assert payload["stress_tests"][0]["input_dataset"] == "data/input.csv"


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


def test_run_cli_comparison_against_baseline_report(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    report_path = tmp_path / "current-report.json"
    baseline_path = tmp_path / "baseline-report.json"
    config_path = root / "examples" / "basic_model" / "econeval.yml"
    model_path = root / "examples" / "basic_model" / "model.py"

    baseline_path.write_text(
        json.dumps(
            {
                "project": "basic-model",
                "generated_at": "2026-05-03T00:00:00Z",
                "summary": {"total": 2, "passed": 2, "failed": 0, "status": "pass"},
                "invariants": [
                    {
                        "name": "elasticity_must_be_negative",
                        "passed": True,
                        "detail": None,
                        "error": None,
                    }
                ],
                "economic_checks": [],
                "economic_drift_checks": [],
                "stress_tests": [],
                "drift_checks": [],
                "fairness_checks": [],
                "issues": [],
            }
        ),
        encoding="utf-8",
    )

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
            "--baseline-report",
            str(baseline_path),
        ]
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["summary"]["status"] == "pass"
    assert payload["comparison"]["baseline_project"] == "basic-model"
    assert payload["comparison"]["summary_delta"]["total"] >= 0


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
