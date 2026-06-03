"""Interoperability helpers for external model runtimes.

The public EconEval checks are intentionally small, but many real models do not
expose the exact same surface. This module normalizes a few common shapes:

- classic Python objects with ``predict(features)`` and ``solve()`` methods
- callable wrappers, which are convenient for Julia or GAMS bridges
- PyMC-style objects that expose posterior predictive sampling instead of a
  direct point prediction API

The goal is not to hide the underlying runtime. It is to make thin adapters
easy, so the rest of the check pipeline can stay unchanged.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from statistics import mean
from typing import Any

_PREDICT_METHOD_NAMES = (
    "predict",
    "predict_proba",
    "forecast",
    "evaluate",
)
_PREDICTIVE_SAMPLE_METHOD_NAMES = (
    "sample_posterior_predictive",
    "posterior_predictive",
    "sample_prior_predictive",
)
_SOLVE_METHOD_NAMES = (
    "solve",
    "run",
    "execute",
    "optimize",
)
_PREFERRED_OUTPUT_KEYS = (
    "prediction",
    "predictions",
    "value",
    "values",
    "y",
    "yhat",
    "mean",
    "median",
)
_CONVERGED_STATUSES = {
    "converged",
    "optimal",
    "solved",
    "success",
    "feasible",
    "ok",
}


@dataclass(slots=True)
class ModelRuntime:
    """Normalized access to a model object."""

    model: Any
    predict_method: str | None = None
    predictive_sample_method: str | None = None
    solve_method: str | None = None
    prediction_key: str | None = None

    def predict(self, features: dict[str, float]) -> Any:
        if self.predict_method:
            return _summarize_prediction_output(
                _invoke_bound_method(getattr(self.model, self.predict_method), features)
            )
        if self.predictive_sample_method:
            output = _invoke_bound_method(
                getattr(self.model, self.predictive_sample_method), features
            )
            if self.prediction_key is not None:
                selected = _extract_value(output, self.prediction_key)
                if selected is not None:
                    return _summarize_prediction_output(selected)
            return _summarize_prediction_output(output)
        if callable(self.model):
            return _summarize_prediction_output(_invoke_callable(self.model, features))
        raise AttributeError(
            f"model does not expose a prediction interface; {describe_model_interface(self.model)}"
        )

    def solve(self) -> Any:
        if self.solve_method:
            return _invoke_bound_method(getattr(self.model, self.solve_method))
        if hasattr(self.model, "converged"):
            return bool(self.model.converged)
        raise AttributeError(
            f"model does not expose a solve interface; {describe_model_interface(self.model)}"
        )

    @property
    def capabilities(self) -> list[str]:
        capabilities: list[str] = []
        if self.predict_method:
            capabilities.append(self.predict_method)
        if self.predictive_sample_method:
            capabilities.append(self.predictive_sample_method)
        if callable(self.model):
            capabilities.append("__call__")
        if self.solve_method:
            capabilities.append(self.solve_method)
        if hasattr(self.model, "converged"):
            capabilities.append("converged")
        return capabilities


def resolve_model_runtime(
    model: Any,
    *,
    prediction_key: str | None = None,
) -> ModelRuntime:
    """Return a normalized runtime wrapper for a model object."""

    return ModelRuntime(
        model=model,
        predict_method=_first_callable(model, _PREDICT_METHOD_NAMES),
        predictive_sample_method=_first_callable(model, _PREDICTIVE_SAMPLE_METHOD_NAMES),
        solve_method=_first_callable(model, _SOLVE_METHOD_NAMES),
        prediction_key=prediction_key,
    )


def describe_model_interface(model: Any) -> str:
    """Summarize the call surface exposed by a model object."""

    capabilities = []
    for name in _PREDICT_METHOD_NAMES + _PREDICTIVE_SAMPLE_METHOD_NAMES + _SOLVE_METHOD_NAMES:
        if _is_callable_attribute(model, name):
            capabilities.append(name)
    if callable(model):
        capabilities.append("__call__")
    if not capabilities:
        return "available callables: none"
    return "available callables: " + ", ".join(sorted(dict.fromkeys(capabilities)))


def _first_callable(model: Any, names: tuple[str, ...]) -> str | None:
    for name in names:
        if _is_callable_attribute(model, name):
            return name
    return None


def _is_callable_attribute(model: Any, name: str) -> bool:
    candidate = getattr(model, name, None)
    return callable(candidate)


def _invoke_bound_method(method: Any, features: dict[str, float] | None = None) -> Any:
    if features is None:
        return method()
    if _accepts_positional_argument(method):
        return method(features)
    return method()


def _invoke_callable(function: Any, features: dict[str, float]) -> Any:
    if _accepts_positional_argument(function):
        return function(features)
    return function()


def _accepts_positional_argument(function: Any) -> bool:
    try:
        signature = inspect.signature(function)
    except (TypeError, ValueError):
        return True

    for parameter in signature.parameters.values():
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            return True
    return False


def _extract_value(value: Any, key: str) -> Any | None:
    if isinstance(value, dict) and key in value:
        return value[key]
    if hasattr(value, key):
        return getattr(value, key)
    return None


def _summarize_prediction_output(value: Any) -> Any:
    scalar = _to_scalar(value)
    if scalar is not None:
        return scalar

    if isinstance(value, dict):
        for key in _PREFERRED_OUTPUT_KEYS:
            if key in value:
                selected = _to_scalar(value[key])
                if selected is not None:
                    return selected
        leaves = _collect_numeric_values(value.values())
        if leaves:
            return mean(leaves)
        return value

    if isinstance(value, (list, tuple, set)):
        leaves = _collect_numeric_values(value)
        if leaves:
            return mean(leaves)
        return value

    if hasattr(value, "tolist"):
        try:
            return _summarize_prediction_output(value.tolist())
        except Exception:
            pass

    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes, dict)):
        leaves = _collect_numeric_values(list(value))
        if leaves:
            return mean(leaves)

    return value


def _collect_numeric_values(value: Any) -> list[float]:
    if isinstance(value, bool):
        return [float(value)]
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, dict):
        values: list[float] = []
        for item in value.values():
            values.extend(_collect_numeric_values(item))
        return values
    if isinstance(value, (list, tuple, set)):
        values: list[float] = []
        for item in value:
            values.extend(_collect_numeric_values(item))
        return values
    if hasattr(value, "tolist"):
        try:
            return _collect_numeric_values(value.tolist())
        except Exception:
            return []
    if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
        values: list[float] = []
        for item in value:
            values.extend(_collect_numeric_values(item))
        return values
    return []


def _to_scalar(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if hasattr(value, "item"):
        try:
            item = value.item()
        except Exception:
            return None
        return _to_scalar(item)
    return None
