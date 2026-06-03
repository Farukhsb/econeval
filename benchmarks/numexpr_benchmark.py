"""Compare EconEval's numexpr path against the Python AST evaluator on large arrays."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from time import perf_counter

import numpy as np

from econeval.invariants import _evaluate_python_ast, _validate_expression, evaluate_expression

EXPRESSION = (
    "((a * b) + (c / d) - (e**2) + (a / (b + 1)) + (c * d) - (a - e) "
    "+ (b * c) - (d / (e + 1)) + (a * e) + (c / (b + 1)))"
)


@dataclass(slots=True)
class BenchmarkResult:
    backend: str
    iterations: int
    size: int
    average_ms: float
    checksum: float


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark EconEval expression evaluation.")
    parser.add_argument("--size", type=int, default=100_000, help="Array length to benchmark.")
    parser.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="How many timing iterations to run per backend.",
    )
    return parser


def build_context(size: int) -> dict[str, np.ndarray | float]:
    return {
        "a": np.linspace(0.0, 10.0, size),
        "b": np.linspace(1.0, 2.0, size),
        "c": np.linspace(0.0, 5.0, size),
        "d": np.linspace(1.0, 3.0, size),
        "e": np.linspace(0.0, 1.0, size),
        "threshold": 12.0,
    }


def benchmark_numexpr(context: dict[str, np.ndarray | float], iterations: int) -> BenchmarkResult:
    checksum = 0.0
    started_at = perf_counter()
    for _ in range(iterations):
        result = evaluate_expression(EXPRESSION, context, backend="numexpr")
        checksum = float(np.asarray(result).sum())
    elapsed_ms = (perf_counter() - started_at) * 1000.0 / iterations
    size = len(next(value for value in context.values() if isinstance(value, np.ndarray)))
    return BenchmarkResult("numexpr", iterations, size, elapsed_ms, checksum)


def benchmark_python(context: dict[str, np.ndarray | float], iterations: int) -> BenchmarkResult:
    tree = _validate_expression(EXPRESSION)
    checksum = 0.0
    started_at = perf_counter()
    for _ in range(iterations):
        result = _evaluate_python_ast(EXPRESSION, context, tree)
        checksum = float(np.asarray(result).sum())
    elapsed_ms = (perf_counter() - started_at) * 1000.0 / iterations
    size = len(next(value for value in context.values() if isinstance(value, np.ndarray)))
    return BenchmarkResult("python_ast", iterations, size, elapsed_ms, checksum)


def main() -> int:
    args = build_parser().parse_args()
    context = build_context(args.size)
    numexpr_result = benchmark_numexpr(context, args.iterations)
    python_result = benchmark_python(context, args.iterations)
    speedup = (
        python_result.average_ms / numexpr_result.average_ms
        if numexpr_result.average_ms
        else float("inf")
    )

    print(f"Expression: {EXPRESSION}")
    print(f"Size: {args.size:,}")
    print(f"Iterations: {args.iterations}")
    print(
        f"{numexpr_result.backend}: {numexpr_result.average_ms:.3f} ms/iter "
        f"(checksum={numexpr_result.checksum:.6f})"
    )
    print(
        f"{python_result.backend}: {python_result.average_ms:.3f} ms/iter "
        f"(checksum={python_result.checksum:.6f})"
    )
    print(f"Speedup: {speedup:.2f}x")

    if abs(numexpr_result.checksum - python_result.checksum) > 1e-9:
        raise SystemExit("benchmark results differ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
