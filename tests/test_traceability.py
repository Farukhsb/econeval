from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from econeval.config import InvariantRule
from econeval.traceability import (
    BlameEntry,
    _extract_pull_request,
    collect_invariant_blame,
    format_blame_entries,
)


def _load_temp_model_module(path: Path):
    spec = importlib.util.spec_from_file_location("temp_traceability_model", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_format_blame_entries_renders_metadata() -> None:
    text = format_blame_entries(
        [
            {
                "path": "models/demo.py",
                "line": 12,
                "commit": "abc123def456",
                "author": "Ada Lovelace",
                "summary": "Tune elasticity rule",
                "pull_request": 42,
            }
        ]
    )

    assert "demo.py:12" in text
    assert "abc123def456" in text
    assert "Ada Lovelace" in text
    assert "PR #42" in text


def test_extract_pull_request_parses_common_merge_messages() -> None:
    assert _extract_pull_request("Merge pull request #17 from owner/branch") == 17
    assert _extract_pull_request("Fix typo (#23)") == 23
    assert _extract_pull_request("plain commit message") is None


def test_collect_invariant_blame_uses_matching_model_lines(tmp_path: Path, monkeypatch) -> None:
    module_path = tmp_path / "model_for_traceability.py"
    module_path.write_text(
        "\n".join(
            [
                "class DemoModel:",
                "    def __init__(self) -> None:",
                "        self.elasticity = 0.25",
                "        self.supply = 10.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    module = _load_temp_model_module(module_path)
    model = module.DemoModel()
    rule = InvariantRule(name="elasticity", expression="model.elasticity < 0")

    monkeypatch.setattr("econeval.traceability._git_root", lambda path: tmp_path)
    monkeypatch.setattr(
        "econeval.traceability._git_blame_line",
        lambda root, source_path, line: (
            BlameEntry(
                path=str(Path(source_path).relative_to(root)),
                line=line,
                commit="abc123def456",
                author="Ada Lovelace",
                summary="Tune elasticity rule",
                pull_request=42,
            )
            if line == 3
            else None
        ),
    )

    entries = collect_invariant_blame(model, rule)

    assert entries
    assert entries[0]["line"] == 3
    assert entries[0]["commit"] == "abc123def456"
    assert entries[0]["pull_request"] == 42


def test_collect_invariant_blame_returns_empty_when_root_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    module_path = tmp_path / "model_for_traceability.py"
    module_path.write_text(
        "class DemoModel:\n    def __init__(self) -> None:\n        self.elasticity = 0.25\n",
        encoding="utf-8",
    )
    module = _load_temp_model_module(module_path)
    model = module.DemoModel()
    rule = InvariantRule(name="elasticity", expression="model.elasticity < 0")

    monkeypatch.setattr("econeval.traceability._git_root", lambda path: None)

    assert collect_invariant_blame(model, rule) == []
