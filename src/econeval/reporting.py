"""Report generation helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import EconEvalConfig
from .invariants import InvariantResult
from .scenarios import DriftResult, FairnessResult, ScenarioResult


def build_json_report(
    config: EconEvalConfig,
    results: list[InvariantResult],
    scenario_results: list[ScenarioResult] | None = None,
    drift_results: list[DriftResult] | None = None,
    fairness_results: list[FairnessResult] | None = None,
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
    overall_failed = failed_count + scenario_failed_count + drift_failed_count + fairness_failed_count

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": config.project,
        "version": config.version,
        "summary": {
            "total": len(results) + len(scenario_results) + len(drift_results) + len(fairness_results),
            "passed": passed_count + scenario_passed_count + drift_passed_count + fairness_passed_count,
            "failed": overall_failed,
            "status": "pass" if overall_failed == 0 else "fail",
        },
        "invariants": [asdict(result) for result in results],
        "stress_tests": [asdict(result) for result in scenario_results],
        "drift_checks": [asdict(result) for result in drift_results],
        "fairness_checks": [asdict(result) for result in fairness_results],
    }


def write_json_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
