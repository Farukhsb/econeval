import json
import xml.etree.ElementTree as ET
from pathlib import Path

from econeval.cli import run_cli


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
