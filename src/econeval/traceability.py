"""Traceability helpers for failed checks."""

from __future__ import annotations

import ast
import inspect
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import InvariantRule


@dataclass(slots=True)
class BlameEntry:
    path: str
    line: int
    commit: str
    author: str | None = None
    summary: str | None = None
    pull_request: int | None = None


def collect_invariant_blame(model: Any, rule: InvariantRule) -> list[dict[str, Any]]:
    """Return git blame metadata for likely source lines tied to a failed rule."""

    source_path, candidate_lines = _candidate_model_lines(model, rule.expression)
    if source_path is None or not candidate_lines:
        return []

    root = _git_root(source_path)
    if root is None:
        return []

    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for line in candidate_lines:
        blame = _git_blame_line(root, source_path, line)
        if blame is None:
            continue
        key = (blame.commit, blame.line)
        if key in seen:
            continue
        seen.add(key)
        payload: dict[str, Any] = {
            "path": str(Path(source_path).resolve()),
            "line": blame.line,
            "commit": blame.commit,
        }
        if blame.author:
            payload["author"] = blame.author
        if blame.summary:
            payload["summary"] = blame.summary
        if blame.pull_request is not None:
            payload["pull_request"] = blame.pull_request
        entries.append(payload)
    return entries


def format_blame_entries(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return ""
    parts: list[str] = []
    for entry in entries:
        summary = str(entry.get("summary") or "").strip()
        pull_request = entry.get("pull_request")
        suffix = f" (PR #{pull_request})" if pull_request else ""
        author = f" by {entry['author']}" if entry.get("author") else ""
        parts.append(
            f"{Path(str(entry.get('path', ''))).name}:{entry.get('line')} "
            f"-> {entry.get('commit')}{author}: {summary}{suffix}".strip()
        )
    return "; ".join(parts)


def _candidate_model_lines(model: Any, expression: str) -> tuple[str | None, list[int]]:
    model_type = type(model)
    source_path = inspect.getsourcefile(model_type) or inspect.getfile(model_type)
    if source_path is None:
        return None, []

    try:
        source_lines, start_line = inspect.getsourcelines(model_type)
    except (OSError, TypeError):
        return source_path, []

    attribute_names = _expression_attribute_names(expression)
    candidate_lines: list[int] = []
    for offset, line in enumerate(source_lines, start=start_line):
        if _line_mentions_any_name(line, attribute_names):
            candidate_lines.append(offset)

    if candidate_lines:
        return source_path, candidate_lines[:5]

    return source_path, [start_line]


def _expression_attribute_names(expression: str) -> list[str]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return []

    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            tail = _attribute_tail(node)
            if tail and tail not in names:
                names.append(tail)
    return names


def _attribute_tail(node: ast.Attribute) -> str | None:
    parts: list[str] = [node.attr]
    current = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name) and current.id == "model":
        return parts[-1]
    return None


def _line_mentions_any_name(line: str, names: list[str]) -> bool:
    if not names:
        return False
    return any(re.search(rf"\b{re.escape(name)}\b", line) for name in names)


def _git_root(path: str) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(Path(path).resolve().parent), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    root = completed.stdout.strip()
    return Path(root) if root else None


def _git_blame_line(root: Path, source_path: str, line: int) -> BlameEntry | None:
    source = Path(source_path).resolve()
    try:
        relative_path = source.relative_to(root)
    except ValueError:
        return None
    try:
        completed = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "blame",
                "--porcelain",
                "-L",
                f"{line},{line}",
                "--",
                str(relative_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    lines = completed.stdout.splitlines()
    if not lines:
        return None

    header = lines[0].split()
    if not header:
        return None

    commit = header[0]
    author = None
    summary = None
    pull_request = None
    for line_text in lines[1:]:
        if line_text.startswith("author "):
            author = line_text.partition(" ")[2].strip() or None
        elif line_text.startswith("summary "):
            summary = line_text.partition(" ")[2].strip() or None
            if summary:
                pull_request = _extract_pull_request(summary)

    return BlameEntry(
        path=str(relative_path),
        line=line,
        commit=commit[:12],
        author=author,
        summary=summary,
        pull_request=pull_request,
    )


def _extract_pull_request(summary: str) -> int | None:
    match = re.search(r"Merge pull request #(\d+)", summary)
    if match:
        return int(match.group(1))
    match = re.search(r"\(#(\d+)\)", summary)
    if match:
        return int(match.group(1))
    return None
