"""EconEval: CI/CD checks for economic and policy models."""

from .cli import main, run_cli
from .config import EconEvalConfig, InvariantRule, load_config
from .invariants import InvariantResult, run_invariant, run_invariant_suite, suite_passed
from .reporting import build_json_report, write_json_report
from .scenarios import ScenarioResult, run_scenario, run_stress_suite

__all__ = [
    "__version__",
    "build_json_report",
    "EconEvalConfig",
    "InvariantResult",
    "InvariantRule",
    "ScenarioResult",
    "main",
    "load_config",
    "run_invariant",
    "run_invariant_suite",
    "run_cli",
    "run_scenario",
    "run_stress_suite",
    "suite_passed",
    "write_json_report",
]

__version__ = "0.1.0"
