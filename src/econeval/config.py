"""Configuration loading helpers for EconEval."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class InvariantRule:
    name: str
    expression: str


@dataclass(slots=True)
class StressTest:
    name: str
    dataset: str
    metric: str
    threshold: float


@dataclass(slots=True)
class FairnessConfig:
    enabled: bool = False
    metrics: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EconEvalConfig:
    project: str
    version: int = 1
    invariants: list[InvariantRule] = field(default_factory=list)
    stress_tests: list[StressTest] = field(default_factory=list)
    fairness: FairnessConfig = field(default_factory=FairnessConfig)


def load_config(path: str | Path) -> EconEvalConfig:
    """Load an EconEval YAML config from disk.

    The parser is intentionally small and only supports the configuration
    shape used by EconEval. That keeps the dependency footprint low while still
    giving the project a real config file format.
    """

    data = _parse_yaml_like(Path(path).read_text(encoding="utf-8"))
    return _config_from_mapping(data)


def _config_from_mapping(data: dict[str, Any]) -> EconEvalConfig:
    project = _require_str(data, "project")
    version = int(data.get("version", 1))

    invariants = [
        InvariantRule(
            name=_require_str(item, "name"),
            expression=_require_str(item, "expression"),
        )
        for item in _require_list_of_mappings(data.get("invariants", []), "invariants")
    ]

    stress_tests = [
        StressTest(
            name=_require_str(item, "name"),
            dataset=_require_str(item, "dataset"),
            metric=_require_str(item, "metric"),
            threshold=float(item.get("threshold")),
        )
        for item in _require_list_of_mappings(data.get("stress_tests", []), "stress_tests")
    ]

    fairness_data = data.get("fairness", {})
    if not isinstance(fairness_data, dict):
        raise ValueError("fairness must be a mapping")

    fairness = FairnessConfig(
        enabled=bool(fairness_data.get("enabled", False)),
        metrics=_require_list_of_strings(fairness_data.get("metrics", []), "fairness.metrics"),
    )

    return EconEvalConfig(
        project=project,
        version=version,
        invariants=invariants,
        stress_tests=stress_tests,
        fairness=fairness,
    )


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
            if key in {"invariants", "stress_tests"}:
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

        key, value = _parse_key_value(stripped)
        current[key] = _parse_scalar(value)
        index += 1

    if current is not None:
        items.append(current)

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

