"""Command line interface for EconEval."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from .config import load_config
from .errors import ExecutionIssue
from .invariants import run_invariant_suite, suite_passed
from .reporting import build_json_report, write_junit_report, write_json_report
from .scenarios import (
    fairness_suite_passed,
    drift_suite_passed,
    run_drift_suite,
    run_fairness_checks,
    run_stress_suite,
    suite_passed as stress_suite_passed,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="econeval", description="Run EconEval checks against a model.")
    parser.add_argument("--config", required=True, help="Path to the EconEval YAML config.")
    parser.add_argument("--model", required=True, help="Path to the Python file that defines the model.")
    parser.add_argument(
        "--class",
        dest="class_name",
        default="DemoModel",
        help="Model class name to instantiate from the model file.",
    )
    parser.add_argument(
        "--report",
        default="econeval-report.json",
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "junit"),
        default="json",
        help="Report format to write.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress messages.")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    return parser


def load_model_class(model_path: str | Path, class_name: str):
    """Load a model class from a Python file path."""

    module_path = Path(model_path).resolve()
    module_name = f"econeval_model_{module_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"could not load model file: {module_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    try:
        return getattr(module, class_name)
    except AttributeError as exc:
        raise ValueError(f"class {class_name!r} not found in {module_path}") from exc


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    issues: list[ExecutionIssue] = []
    log = _build_logger(args.verbose, args.quiet)

    try:
        log("loading config")
        config = load_config(args.config)
    except Exception as exc:
        issues.append(ExecutionIssue(stage="config", message=str(exc), detail=str(args.config)))
        report = build_json_report(
            config=_placeholder_config(),
            results=[],
            scenario_results=[],
            drift_results=[],
            fairness_results=[],
            issues=issues,
        )
        _write_report(args.format, args.report, report)
        _print_failure("config load", exc, args.quiet)
        return 1

    try:
        log("loading model")
        model_class = load_model_class(args.model, args.class_name)
        model = model_class()
    except Exception as exc:
        issues.append(ExecutionIssue(stage="model", message=str(exc), detail=str(args.model)))
        report = build_json_report(
            config=config,
            results=[],
            scenario_results=[],
            drift_results=[],
            fairness_results=[],
            issues=issues,
        )
        _write_report(args.format, args.report, report)
        _print_failure("model load", exc, args.quiet)
        return 1

    log("running invariants")
    results = run_invariant_suite(model, config.invariants)
    log("running stress tests")
    scenario_results = run_stress_suite(model, config.stress_tests, base_path=Path(args.config).parent)
    log("running drift checks")
    drift_results = run_drift_suite(config.drift_tests, base_path=Path(args.config).parent)
    fairness_results = []
    if config.fairness.enabled and config.fairness.dataset:
        log("running fairness checks")
        fairness_results = run_fairness_checks(
            model,
            config.fairness.dataset,
            config.fairness.metrics,
            group_column=config.fairness.group_column,
            positive_threshold=config.fairness.positive_threshold,
            base_path=Path(args.config).parent,
        )

    report = build_json_report(config, results, scenario_results, drift_results, fairness_results)
    _write_report(args.format, args.report, report)

    status = report["summary"]["status"]
    _print_summary(status, report["summary"]["passed"], report["summary"]["total"], args.quiet, args.format)

    return 0 if (
        suite_passed(results)
        and stress_suite_passed(scenario_results)
        and drift_suite_passed(drift_results)
        and fairness_suite_passed(fairness_results)
    ) else 1


def _placeholder_config():
    from .config import EconEvalConfig

    return EconEvalConfig(project="unavailable")


def _write_report(report_format: str, path: str | Path, report: dict[str, object]) -> None:
    if report_format == "junit":
        write_junit_report(path, report)
        return
    write_json_report(path, report)


def _build_logger(verbose: bool, quiet: bool):
    if quiet:
        return lambda message: None
    if not verbose:
        return lambda message: None
    return lambda message: print(f"[econeval] {message}")


def _print_summary(status: str, passed: int, total: int, quiet: bool, report_format: str) -> None:
    if quiet:
        return
    print(f"EconEval: {status} ({passed}/{total} checks passed, format={report_format})")


def _print_failure(stage: str, exc: Exception, quiet: bool) -> None:
    if quiet:
        return
    print(f"EconEval: fail ({stage}: {exc})")


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)
