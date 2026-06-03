"""Configuration loading helpers for EconEval."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvariantRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    expression: str = Field(min_length=1)
    backend: Literal["auto", "numexpr"] = "auto"


class StressManipulation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variable: str = Field(min_length=1)
    action: Literal["add", "multiply", "set"]
    value: float
    sigma: float | None = Field(default=None, gt=0)
    correlation_group: str | None = Field(default=None, min_length=1)
    correlation: float | None = Field(default=None, ge=-1.0, le=1.0)


class StressSweepAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variable: str = Field(min_length=1)
    values: list[float] = Field(min_length=1)


class StressTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    metric: str = Field(default="mape", min_length=1)
    threshold: float | None = None
    dataset: str | None = None
    kind: Literal["dataset", "synthetic", "parameter_shock", "monte_carlo", "grid"] = "dataset"
    variable: str | None = None
    shock_type: Literal["multiplier", "additive", "absolute"] = "multiplier"
    value: float | None = None
    baseline_value: float = 1.0
    manipulations: list[StressManipulation] = Field(default_factory=list)
    sweep_axes: list[StressSweepAxis] = Field(default_factory=list)
    invariants: list[InvariantRule] = Field(default_factory=list)
    samples: int = Field(default=100, ge=1)
    seed: int | None = None
    percentile_cutoffs: list[float] = Field(default_factory=lambda: [10.0, 50.0, 90.0])

    @model_validator(mode="after")
    def validate_shape(self) -> StressTest:
        if self.kind == "dataset":
            if not self.dataset:
                raise ValueError("dataset stress tests require dataset")
            if self.threshold is None:
                raise ValueError("dataset stress tests require threshold")
            if self.metric.lower() not in {"rmse", "mae", "mape"}:
                raise ValueError(
                    "dataset stress test metric must be one of rmse, mae, or mape, "
                    f"got {self.metric!r}"
                )
        else:
            if self.kind == "monte_carlo":
                if not self.manipulations:
                    raise ValueError("monte carlo stress tests require manipulations")
                if not self.invariants:
                    raise ValueError("monte carlo stress tests require invariants")
                if not self.percentile_cutoffs:
                    raise ValueError("monte carlo stress tests require percentile_cutoffs")
            elif self.kind == "grid":
                if not self.sweep_axes:
                    raise ValueError("grid stress tests require sweep_axes")
                if not self.invariants:
                    raise ValueError("grid stress tests require invariants")
            elif self.manipulations:
                if not self.invariants:
                    raise ValueError("manipulation stress tests require invariants")
            else:
                if not self.variable:
                    raise ValueError("synthetic stress tests require variable")
                if self.value is None:
                    raise ValueError("synthetic stress tests require value")
                if self.metric.lower() not in {"delta", "absolute_change", "relative_change"}:
                    raise ValueError(
                        "synthetic stress test metric must be delta, absolute_change, "
                        f"or relative_change, got {self.metric!r}"
                    )
        return self


class EconomicDriftTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    baseline_dataset: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    metric: Literal["absolute_change", "relative_change"] = "relative_change"
    output: Literal["mean_prediction", "median_prediction", "positive_rate"] = "mean_prediction"
    threshold: float = Field(gt=0)
    positive_threshold: float = Field(default=0.5, gt=0)


class EconomicCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    left_expression: str | None = None
    right_expression: str | None = None
    expression: str | None = None
    method: str | None = None
    variable: str | None = None
    lower: float | None = None
    upper: float | None = None
    initial_states: list[dict[str, Any]] = Field(default_factory=list)
    steps: int = Field(default=5, ge=2)
    tolerance: float = Field(default=1e-9, ge=0)
    direction: Literal[
        "nonincreasing",
        "nondecreasing",
        "strictly_nonincreasing",
        "strictly_nondecreasing",
    ] = "nonincreasing"
    input_variable: str | None = None
    output_variable: str | None = None
    scan_kind: Literal["monotonicity", "elasticity"] = "monotonicity"
    perturbations: list[float] = Field(default_factory=lambda: [0.01, 0.05, 0.1])
    expected_direction: (
        Literal[
            "nonincreasing",
            "nondecreasing",
            "strictly_nonincreasing",
            "strictly_nondecreasing",
        ]
        | None
    ) = None

    @model_validator(mode="after")
    def validate_shape(self) -> EconomicCheck:
        if self.kind == "accounting_identity":
            if not self.left_expression or not self.right_expression:
                raise ValueError(
                    "accounting identity checks require left_expression and right_expression"
                )
        elif self.kind == "monotonicity":
            if not self.method or not self.variable:
                raise ValueError("monotonicity checks require method and variable")
            if self.lower is None or self.upper is None:
                raise ValueError("monotonicity checks require lower and upper")
        elif self.kind == "boundary_condition":
            if not self.expression:
                raise ValueError("boundary condition checks require expression")
            if self.lower is None or self.upper is None:
                raise ValueError("boundary condition checks require lower and upper")
        elif self.kind == "convergence":
            if not self.method:
                raise ValueError("convergence checks require method")
        elif self.kind == "scan":
            if not self.method:
                raise ValueError("scan checks require method")
            if not self.input_variable or not self.output_variable:
                raise ValueError("scan checks require input_variable and output_variable")
            if self.expected_direction is None:
                raise ValueError("scan checks require expected_direction")
            if self.perturbations is None or not self.perturbations:
                raise ValueError("scan checks require at least one perturbation")
        return self


class DriftTest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    baseline_dataset: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    feature: str = Field(min_length=1)
    threshold: float = Field(gt=0)
    statistic: Literal["mean", "median", "psi"] = "mean"
    mode: Literal["snapshot", "trend", "regression"] = "snapshot"
    time_column: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> DriftTest:
        if self.mode in {"trend", "regression"} and not self.time_column:
            raise ValueError(f"{self.mode} drift checks require time_column")
        if self.statistic == "psi" and self.mode != "snapshot":
            raise ValueError("psi drift checks require mode=snapshot")
        return self


class FairnessConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    metrics: list[
        Literal[
            "demographic_parity_difference",
            "disparate_impact_ratio",
            "gini",
            "atkinson",
            "equal_opportunity_difference",
            "equalized_odds_difference",
        ]
    ] = Field(default_factory=list)
    dataset: str | None = None
    group_column: str = "group"
    positive_threshold: float = Field(default=0.5, gt=0)
    actual_threshold: float = Field(default=0.5, gt=0)

    @model_validator(mode="after")
    def validate_shape(self) -> FairnessConfig:
        if self.enabled:
            if not self.dataset:
                raise ValueError("fairness checks require dataset when enabled")
            if not self.metrics:
                raise ValueError("fairness checks require at least one metric when enabled")
        return self


class EconEvalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    invariants: list[InvariantRule] = Field(default_factory=list)
    economic_checks: list[EconomicCheck] = Field(default_factory=list)
    stress_tests: list[StressTest] = Field(default_factory=list)
    drift_tests: list[DriftTest] = Field(default_factory=list)
    economic_drift_tests: list[EconomicDriftTest] = Field(default_factory=list)
    fairness: FairnessConfig = Field(default_factory=FairnessConfig)


def load_config(path: str | Path) -> EconEvalConfig:
    """Load an EconEval YAML config from disk.

    The parser is intentionally small and only supports the configuration
    shape used by EconEval. Pydantic validates the resulting object graph so
    schema mistakes fail before evaluation starts.
    """

    data = _parse_yaml_like(Path(path).read_text(encoding="utf-8"))
    return EconEvalConfig.model_validate(data)


def _config_from_mapping(data: dict[str, Any]) -> EconEvalConfig:
    return EconEvalConfig.model_validate(data)


def _parse_yaml_like(text: str) -> dict[str, Any]:
    lines = [line.rstrip() for line in text.splitlines()]
    data: dict[str, Any] = {}
    index = 0

    while index < len(lines):
        line = lines[index].strip()
        if not line or line.startswith("#"):
            index += 1
            continue

        if line.endswith(":"):
            key = line[:-1].strip()
            if key in {
                "invariants",
                "economic_checks",
                "stress_tests",
                "drift_tests",
                "economic_drift_tests",
            }:
                items, index = _parse_mapping_list(lines, index + 1)
                data[key] = items
                continue
            if key == "fairness":
                value, index = _parse_fairness_block(lines, index + 1)
                data[key] = value
                continue
            raise ValueError(f"unsupported section: {key}")

        key, value = _parse_key_value(line)
        data[key] = _parse_scalar(value)
        index += 1

    return data


def _parse_mapping_list(lines: list[str], start_index: int) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    index = start_index
    current: dict[str, Any] | None = None

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent < 2:
            break

        if stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            remainder = stripped[2:].strip()
            if remainder:
                key, value = _parse_key_value(remainder)
                current[key] = _parse_scalar(value)
            index += 1
            continue

        if current is None:
            raise ValueError("list item content found before any item header")

        if stripped.startswith("initial_states:"):
            nested_items, index = _parse_nested_mapping_list(lines, index + 1, min_indent=6)
            current["initial_states"] = nested_items
            continue

        if stripped.startswith("manipulations:"):
            nested_items, index = _parse_nested_mapping_list(lines, index + 1, min_indent=6)
            current["manipulations"] = nested_items
            continue

        if stripped.startswith("sweep_axes:"):
            nested_items, index = _parse_nested_mapping_list(lines, index + 1, min_indent=6)
            current["sweep_axes"] = nested_items
            continue

        if stripped.startswith("invariants:"):
            nested_items, index = _parse_nested_mapping_list(lines, index + 1, min_indent=6)
            current["invariants"] = nested_items
            continue

        if stripped.startswith("perturbations:"):
            perturbations, index = _parse_nested_scalar_list(lines, index + 1, min_indent=6)
            current["perturbations"] = perturbations
            continue

        if stripped.startswith("percentile_cutoffs:"):
            percentile_cutoffs, index = _parse_nested_scalar_list(lines, index + 1, min_indent=6)
            current["percentile_cutoffs"] = percentile_cutoffs
            continue

        key, value = _parse_key_value(stripped)
        current[key] = _parse_scalar(value)
        index += 1

    if current is not None:
        items.append(current)

    return items, index


def _parse_nested_mapping_list(
    lines: list[str],
    start_index: int,
    min_indent: int,
) -> tuple[list[dict[str, Any]], int]:
    items: list[dict[str, Any]] = []
    index = start_index
    current: dict[str, Any] | None = None

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent < min_indent:
            break

        if stripped.startswith("- "):
            if current is not None:
                items.append(current)
            current = {}
            remainder = stripped[2:].strip()
            if remainder:
                key, value = _parse_key_value(remainder)
                current[key] = _parse_scalar(value)
            index += 1
            continue

        if current is None:
            raise ValueError("nested list item content found before any item header")

        if stripped.startswith("values:"):
            value_items, index = _parse_nested_mapping_list(lines, index + 1, min_indent=8)
            current["values"] = [
                float(item["value"]) if "value" in item else item for item in value_items
            ]
            continue

        key, value = _parse_key_value(stripped)
        current[key] = _parse_scalar(value)
        index += 1

    if current is not None:
        items.append(current)

    return items, index


def _parse_nested_scalar_list(
    lines: list[str],
    start_index: int,
    min_indent: int,
) -> tuple[list[Any], int]:
    items: list[Any] = []
    index = start_index

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent < min_indent:
            break

        if not stripped.startswith("- "):
            raise ValueError("nested scalar list must contain list items")

        items.append(_parse_scalar(stripped[2:].strip()))
        index += 1

    return items, index


def _parse_fairness_block(lines: list[str], start_index: int) -> tuple[dict[str, Any], int]:
    fairness: dict[str, Any] = {}
    index = start_index

    while index < len(lines):
        raw = lines[index]
        stripped = raw.strip()

        if not stripped or stripped.startswith("#"):
            index += 1
            continue

        indent = len(raw) - len(raw.lstrip(" "))
        if indent < 2:
            break

        if stripped.startswith("enabled:"):
            _, value = _parse_key_value(stripped)
            fairness["enabled"] = _parse_scalar(value)
            index += 1
            continue

        if stripped.startswith("metrics:"):
            metrics: list[str] = []
            index += 1
            while index < len(lines):
                metric_raw = lines[index]
                metric_stripped = metric_raw.strip()
                metric_indent = len(metric_raw) - len(metric_raw.lstrip(" "))

                if not metric_stripped or metric_stripped.startswith("#"):
                    index += 1
                    continue

                if metric_indent < 4:
                    break

                if not metric_stripped.startswith("- "):
                    raise ValueError("fairness.metrics must contain list items")

                metrics.append(str(_parse_scalar(metric_stripped[2:].strip())))
                index += 1

            fairness["metrics"] = metrics
            continue

        if stripped.startswith("dataset:"):
            _, value = _parse_key_value(stripped)
            fairness["dataset"] = _optional_str(_parse_scalar(value))
            index += 1
            continue

        if stripped.startswith("group_column:"):
            _, value = _parse_key_value(stripped)
            fairness["group_column"] = _require_str({"value": _parse_scalar(value)}, "value")
            index += 1
            continue

        if stripped.startswith("positive_threshold:"):
            _, value = _parse_key_value(stripped)
            fairness["positive_threshold"] = float(_parse_scalar(value))
            index += 1
            continue

        if stripped.startswith("actual_threshold:"):
            _, value = _parse_key_value(stripped)
            fairness["actual_threshold"] = float(_parse_scalar(value))
            index += 1
            continue

        raise ValueError(f"unsupported fairness field: {stripped}")

    return fairness, index


def _parse_key_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise ValueError(f"invalid mapping entry: {text}")

    key, value = text.split(":", 1)
    return key.strip(), value.strip()


def _parse_scalar(value: str) -> Any:
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null":
        return None

    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _require_list_of_mappings(value: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    for item in value:
        if not isinstance(item, dict):
            raise ValueError(f"{key} must contain mappings")
    return value


def _require_list_of_strings(value: Any, key: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{key} must contain strings")
        result.append(item)
    return result


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("value must be a non-empty string when provided")
    return value


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
