"""Report generation helpers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import EconEvalConfig
from .errors import ExecutionIssue
from .invariants import InvariantResult
from .scenarios import DriftResult, FairnessResult, ScenarioResult


def build_json_report(
    config: EconEvalConfig,
    results: list[InvariantResult],
    scenario_results: list[ScenarioResult] | None = None,
    drift_results: list[DriftResult] | None = None,
    fairness_results: list[FairnessResult] | None = None,
    issues: list[ExecutionIssue] | None = None,
) -> dict[str, Any]:
    """Build the JSON payload written by the CLI."""

    passed_count = sum(1 for result in results if result.passed)
    failed_count = len(results) - passed_count
    scenario_results = scenario_results or []
    scenario_passed_count = sum(1 for result in scenario_results if result.passed)
    scenario_failed_count = len(scenario_results) - scenario_passed_count
    drift_results = drift_results or []
    drift_passed_count = sum(1 for result in drift_results if result.passed)
    drift_failed_count = len(drift_results) - drift_passed_count
    fairness_results = fairness_results or []
    fairness_passed_count = sum(1 for result in fairness_results if result.passed)
    fairness_failed_count = len(fairness_results) - fairness_passed_count
    issues = issues or []
    issue_count = len(issues)
    overall_failed = failed_count + scenario_failed_count + drift_failed_count + fairness_failed_count + issue_count

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": config.project,
        "version": config.version,
        "summary": {
            "total": len(results) + len(scenario_results) + len(drift_results) + len(fairness_results) + issue_count,
            "passed": passed_count + scenario_passed_count + drift_passed_count + fairness_passed_count,
            "failed": overall_failed,
            "status": "pass" if overall_failed == 0 else "fail",
        },
        "invariants": [asdict(result) for result in results],
        "stress_tests": [asdict(result) for result in scenario_results],
        "drift_checks": [asdict(result) for result in drift_results],
        "fairness_checks": [asdict(result) for result in fairness_results],
        "issues": [asdict(issue) for issue in issues],
    }


def write_json_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_junit_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a JUnit XML report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tests = int(report["summary"]["total"])
    failures = int(report["summary"]["failed"])
    skipped = 0

    root = ET.Element(
        "testsuites",
        attrib={
            "tests": str(tests),
            "failures": str(failures),
            "skipped": str(skipped),
        },
    )
    suite = ET.SubElement(
        root,
        "testsuite",
        attrib={
            "name": str(report["project"]),
            "tests": str(tests),
            "failures": str(failures),
            "skipped": str(skipped),
            "timestamp": str(report["generated_at"]),
        },
    )

    for item in report.get("invariants", []):
        _append_case(suite, "invariant", item["name"], item)
    for item in report.get("stress_tests", []):
        _append_case(suite, "stress_test", item["name"], item)
    for item in report.get("drift_checks", []):
        _append_case(suite, "drift_check", item["name"], item)
    for item in report.get("fairness_checks", []):
        _append_case(suite, "fairness_check", item["name"], item)
    for item in report.get("issues", []):
        _append_issue_case(suite, item)

    output_path.write_text(ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")


def _append_case(parent: ET.Element, kind: str, name: str, payload: dict[str, Any]) -> None:
    case = ET.SubElement(
        parent,
        "testcase",
        attrib={
            "classname": kind,
            "name": str(name),
        },
    )
    if payload.get("passed", True):
        return

    failure = ET.SubElement(case, "failure", attrib={"message": payload.get("error") or "check failed"})
    body = {
        "kind": kind,
        "name": name,
        "payload": payload,
    }
    failure.text = json.dumps(body, indent=2, sort_keys=True)


def _append_issue_case(parent: ET.Element, issue: dict[str, Any]) -> None:
    case = ET.SubElement(
        parent,
        "testcase",
        attrib={
            "classname": "issue",
            "name": str(issue["stage"]),
        },
    )
    failure = ET.SubElement(
        case,
        "error",
        attrib={
            "message": issue.get("message") or "execution issue",
        },
    )
    failure.text = json.dumps(issue, indent=2, sort_keys=True)
