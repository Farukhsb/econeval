"""Report generation helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import EconEvalConfig
from .invariants import InvariantResult


def build_json_report(config: EconEvalConfig, results: list[InvariantResult]) -> dict[str, Any]:
    """Build the JSON payload written by the CLI."""

    passed_count = sum(1 for result in results if result.passed)
    failed_count = len(results) - passed_count

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": config.project,
        "version": config.version,
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "failed": failed_count,
            "status": "pass" if failed_count == 0 else "fail",
        },
        "invariants": [asdict(result) for result in results],
    }


def write_json_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

