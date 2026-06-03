"""Run a lightweight EconEval check from pre-commit.

This hook keeps a fast, repo-local example in front of contributors so changes
that break the core CLI path get caught before they land.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    report_dir = tempfile.TemporaryDirectory()
    report_path = Path(report_dir.name) / "econeval-pre-commit-report.json"
    command = [
        sys.executable,
        "-m",
        "econeval",
        "--config",
        str(root / "examples" / "basic_model" / "econeval.yml"),
        "--model",
        str(root / "examples" / "basic_model" / "model.py"),
        "--class",
        "DemoModel",
        "--report",
        str(report_path),
    ]
    completed = subprocess.run(command, cwd=root, check=False)
    report_dir.cleanup()
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
