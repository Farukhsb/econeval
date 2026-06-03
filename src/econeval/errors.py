"""Shared error models for EconEval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionIssue:
    stage: str
    message: str
    detail: str | None = None
