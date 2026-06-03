"""Command line interface for EconEval."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from time import perf_counter
from typing import Any

from .config import EconEvalConfig, load_config
from .errors import ExecutionIssue
from .invariants import run_invariant_suite, suite_passed
from .reporting import (
    build_json_report,
    build_report_comparison,
    write_dashboard_report,
    write_github_step_summary,
    write_html_report,
    write_json_report,
    write_junit_report,
    write_markdown_report,
    write_pdf_report,
)
from .scenarios import (
    drift_suite_passed,
    economic_drift_suite_passed,
    economic_suite_passed,
    fairness_suite_passed,
    run_drift_suite,
    run_economic_drift_suite,
    run_economic_suite,
    run_fairness_checks,
    run_stress_suite,
)
from .scenarios import (
    suite_passed as stress_suite_passed,
)

Logger = Callable[[str], None]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="econeval",
        description="Run EconEval checks against a model.",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the EconEval YAML config.",
    )
    parser.add_argument(
        "--model",
        help=(
            "Path to the Python file that defines the model. Omit it for "
            "model-less CSV relation checks."
        ),
    )
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
        "--baseline-report",
        help="Optional JSON report to compare against the current run.",
    )
    parser.add_argument(
        "--format",
        choices=("json", "junit", "markdown", "html", "dashboard", "pdf"),
        default="json",
        help="Report format to write.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print detailed progress messages.")
    parser.add_argument("--quiet", action="store_true", help="Suppress non-error output.")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep rerunning checks when the config or model file changes.",
    )
    parser.add_argument(
        "--watch-interval",
        type=float,
        default=1.0,
        help="Seconds to wait between watch polls.",
    )
    return parser


def load_model_class(model_path: str | Path, class_name: str) -> type[Any]:
    """Load a model class from a Python file path."""

    module_path = Path(model_path).resolve()
    if not module_path.exists():
        raise FileNotFoundError(f"model file not found: {module_path}")
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
        available_classes = sorted(
            name for name, value in vars(module).items() if isinstance(value, type)
        )
        suffix = f" available classes: {', '.join(available_classes)}" if available_classes else ""
        raise ValueError(f"class {class_name!r} not found in {module_path}.{suffix}") from exc


def run_cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    log = _build_logger(args.verbose, args.quiet)

    if args.watch:
        return _run_watch_mode(args, log)

    report, exit_code = _run_checks_once(args, log)
    _write_report(args.format, args.report, report)
    _write_step_summary(report)
    log(f"wrote report to {args.report}")
    _print_summary(
        report["summary"]["status"],
        report["summary"]["passed"],
        report["summary"]["total"],
        args.quiet,
        args.format,
    )
    return exit_code


def _placeholder_config() -> EconEvalConfig:
    return EconEvalConfig(project="unavailable")


def _config_requires_model(config: EconEvalConfig) -> bool:
    return bool(
        config.invariants
        or config.economic_checks
        or config.economic_drift_tests
        or config.fairness.enabled
        or any(test.kind != "relation" for test in config.stress_tests)
    )


def _run_checks_once(args: argparse.Namespace, log: Logger) -> tuple[dict[str, Any], int]:
    issues: list[ExecutionIssue] = []
    config = None

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
        _print_failure("config load", exc, args.quiet)
        return report, 1

    model = None
    requires_model = _config_requires_model(config)
    if requires_model:
        if not args.model:
            exc = ValueError("this config requires --model because it includes model-based checks")
            issues.append(ExecutionIssue(stage="model", message=str(exc), detail="--model"))
            report = build_json_report(
                config=config,
                results=[],
                scenario_results=[],
                drift_results=[],
                fairness_results=[],
                issues=issues,
            )
            _print_failure("model load", exc, args.quiet)
            return report, 1

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
            _print_failure("model load", exc, args.quiet)
            return report, 1
    elif args.model:
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
            _print_failure("model load", exc, args.quiet)
            return report, 1

    log("running invariants")
    started_at = perf_counter()
    results = run_invariant_suite(model, config.invariants) if model is not None else []
    _log_stage_summary(log, "invariants", results, perf_counter() - started_at)
    log("running economic checks")
    started_at = perf_counter()
    economic_results = (
        run_economic_suite(model, config.economic_checks) if model is not None else []
    )
    _log_stage_summary(log, "economic checks", economic_results, perf_counter() - started_at)
    log("running stress tests")
    started_at = perf_counter()
    scenario_results = run_stress_suite(
        model,
        config.stress_tests,
        base_path=Path(args.config).parent,
    )
    _log_stage_summary(log, "stress tests", scenario_results, perf_counter() - started_at)
    log("running drift checks")
    started_at = perf_counter()
    drift_results = run_drift_suite(config.drift_tests, base_path=Path(args.config).parent)
    _log_stage_summary(log, "drift checks", drift_results, perf_counter() - started_at)
    log("running economic drift checks")
    started_at = perf_counter()
    economic_drift_results = run_economic_drift_suite(
        model,
        config.economic_drift_tests,
        base_path=Path(args.config).parent,
    )
    _log_stage_summary(
        log,
        "economic drift checks",
        economic_drift_results,
        perf_counter() - started_at,
    )
    fairness_results = []
    if config.fairness.enabled and config.fairness.dataset:
        log("running fairness checks")
        started_at = perf_counter()
        fairness_results = run_fairness_checks(
            model,
            config.fairness.dataset,
            config.fairness.metrics,
            group_column=config.fairness.group_column,
            positive_threshold=config.fairness.positive_threshold,
            actual_threshold=config.fairness.actual_threshold,
            base_path=Path(args.config).parent,
        )
        _log_stage_summary(log, "fairness checks", fairness_results, perf_counter() - started_at)

    report = build_json_report(
        config,
        results,
        scenario_results,
        drift_results,
        fairness_results,
        economic_results=economic_results,
        economic_drift_results=economic_drift_results,
    )
    if args.baseline_report:
        try:
            baseline_report = _load_baseline_report(args.baseline_report)
            report["comparison"] = build_report_comparison(report, baseline_report)
        except Exception as exc:
            issues.append(
                ExecutionIssue(
                    stage="baseline_report",
                    message=str(exc),
                    detail=str(args.baseline_report),
                )
            )
            report = build_json_report(
                config,
                results,
                scenario_results,
                drift_results,
                fairness_results,
                issues=issues,
                economic_results=economic_results,
                economic_drift_results=economic_drift_results,
            )
            report["comparison_error"] = str(exc)
    status = (
        0
        if (
            suite_passed(results)
            and economic_suite_passed(economic_results)
            and stress_suite_passed(scenario_results)
            and drift_suite_passed(drift_results)
            and economic_drift_suite_passed(economic_drift_results)
            and fairness_suite_passed(fairness_results)
        )
        else 1
    )
    return report, status


def _run_watch_mode(args: argparse.Namespace, log: Logger) -> int:
    watched_paths = _watch_paths(args)
    watched_state = _snapshot_watch_state(watched_paths)

    while True:
        report, exit_code = _run_checks_once(args, log)
        _write_report(args.format, args.report, report)
        _write_step_summary(report)
        log(f"wrote report to {args.report}")
        _print_summary(
            report["summary"]["status"],
            report["summary"]["passed"],
            report["summary"]["total"],
            args.quiet,
            args.format,
        )
        log(
            "watching for changes in "
            + ", ".join(str(path) for path in watched_paths)
            + f" (interval={args.watch_interval:.2f}s)"
        )
        _wait_for_watch_change(watched_paths, watched_state, args.watch_interval)


def _watch_paths(args: argparse.Namespace) -> list[Path]:
    paths = [Path(args.config).resolve()]
    if args.model:
        paths.append(Path(args.model).resolve())
    return paths


def _snapshot_watch_state(paths: list[Path]) -> dict[Path, tuple[int, int] | None]:
    state: dict[Path, tuple[int, int] | None] = {}
    for path in paths:
        state[path] = _path_state(path)
    return state


def _path_state(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _wait_for_watch_change(
    paths: list[Path],
    watched_state: dict[Path, tuple[int, int] | None],
    interval: float,
) -> None:
    while True:
        for path in paths:
            current_state = _path_state(path)
            if current_state != watched_state[path]:
                watched_state[path] = current_state
                return
        time.sleep(max(interval, 0.1))


def _write_report(report_format: str, path: str | Path, report: dict[str, Any]) -> None:
    writers = {
        "json": write_json_report,
        "junit": write_junit_report,
        "markdown": write_markdown_report,
        "html": write_html_report,
        "dashboard": write_dashboard_report,
        "pdf": write_pdf_report,
    }
    writers[report_format](path, report)


def _write_step_summary(report: dict[str, Any]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    write_github_step_summary(summary_path, report)


def _load_baseline_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path).resolve()
    if not report_path.exists():
        raise FileNotFoundError(f"baseline report not found: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def _build_logger(verbose: bool, quiet: bool) -> Logger:
    if quiet:
        return lambda message: None
    if not verbose:
        return lambda message: None
    return lambda message: print(f"[econeval] {message}")


def _log_stage_summary(log: Logger, stage: str, results: list[Any], elapsed: float) -> None:
    if not results:
        log(f"{stage}: no checks configured ({elapsed:.2f}s)")
        return
    passed = sum(1 for result in results if getattr(result, "passed", False))
    total = len(results)
    log(f"{stage}: {passed}/{total} passed ({elapsed:.2f}s)")


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
