"""EconEval: CI/CD checks for economic and policy models."""

from .cli import main, run_cli
from .config import (
    DriftTest,
    EconEvalConfig,
    EconomicCheck,
    EconomicDriftTest,
    FairnessConfig,
    InvariantRule,
    StressTest,
    load_config,
)
from .errors import ExecutionIssue
from .interop import ModelRuntime, describe_model_interface, resolve_model_runtime
from .invariants import (
    InvariantResult,
    evaluate_expression,
    run_invariant,
    run_invariant_suite,
    suite_passed,
)
from .reporting import (
    build_json_report,
    write_dashboard_report,
    write_html_report,
    write_json_report,
    write_markdown_report,
)
from .scenarios import (
    DriftResult,
    EconomicCheckResult,
    EconomicDriftResult,
    FairnessResult,
    ScenarioResult,
    economic_drift_suite_passed,
    economic_suite_passed,
    run_drift_suite,
    run_economic_drift_suite,
    run_economic_suite,
    run_fairness_checks,
    run_stress_suite,
)

__all__ = [
    "__version__",
    "build_json_report",
    "write_dashboard_report",
    "EconEvalConfig",
    "EconomicCheck",
    "InvariantResult",
    "InvariantRule",
    "ExecutionIssue",
    "ModelRuntime",
    "DriftResult",
    "DriftTest",
    "EconomicCheckResult",
    "EconomicDriftResult",
    "EconomicDriftTest",
    "FairnessConfig",
    "FairnessResult",
    "ScenarioResult",
    "StressTest",
    "main",
    "load_config",
    "evaluate_expression",
    "describe_model_interface",
    "run_invariant",
    "run_invariant_suite",
    "run_cli",
    "resolve_model_runtime",
    "run_drift_suite",
    "run_economic_drift_suite",
    "run_economic_suite",
    "run_fairness_checks",
    "run_stress_suite",
    "economic_suite_passed",
    "economic_drift_suite_passed",
    "suite_passed",
    "write_json_report",
    "write_markdown_report",
    "write_html_report",
]

__version__ = "0.4.0"
