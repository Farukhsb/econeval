"""Command line interface for EconEval."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from .config import load_config
from .invariants import run_invariant_suite, suite_passed
from .reporting import build_json_report, write_json_report
from .scenarios import run_stress_suite, suite_passed as stress_suite_passed


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

    config = load_config(args.config)
    model_class = load_model_class(args.model, args.class_name)
    model = model_class()

    results = run_invariant_suite(model, config.invariants)
    scenario_results = run_stress_suite(model, config.stress_tests, base_path=Path(args.config).parent)
    report = build_json_report(config, results, scenario_results)
    write_json_report(args.report, report)

    status = report["summary"]["status"]
    print(f"EconEval: {status} ({report['summary']['passed']}/{report['summary']['total']} checks passed)")

    return 0 if suite_passed(results) and stress_suite_passed(scenario_results) else 1


def main(argv: list[str] | None = None) -> int:
    return run_cli(argv)
