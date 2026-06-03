"""Report generation helpers."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

from .config import EconEvalConfig
from .errors import ExecutionIssue
from .invariants import InvariantResult
from .scenarios import (
    DriftResult,
    EconomicCheckResult,
    EconomicDriftResult,
    FairnessResult,
    ScenarioResult,
)

_REPORT_SECTIONS = (
    ("invariants", "Invariant"),
    ("economic_checks", "Economic Check"),
    ("economic_drift_checks", "Economic Drift Check"),
    ("stress_tests", "Stress Test"),
    ("drift_checks", "Drift Check"),
    ("fairness_checks", "Fairness Check"),
    ("issues", "Issue"),
)


def build_json_report(
    config: EconEvalConfig,
    results: list[InvariantResult],
    scenario_results: list[ScenarioResult] | None = None,
    drift_results: list[DriftResult] | None = None,
    fairness_results: list[FairnessResult] | None = None,
    issues: list[ExecutionIssue] | None = None,
    economic_results: list[EconomicCheckResult] | None = None,
    economic_drift_results: list[EconomicDriftResult] | None = None,
) -> dict[str, Any]:
    """Build the JSON payload written by the CLI."""

    passed_count = sum(1 for result in results if result.passed)
    failed_count = len(results) - passed_count
    economic_results = economic_results or []
    economic_passed_count = sum(1 for result in economic_results if result.passed)
    economic_failed_count = len(economic_results) - economic_passed_count
    scenario_results = scenario_results or []
    scenario_passed_count = sum(1 for result in scenario_results if result.passed)
    scenario_failed_count = len(scenario_results) - scenario_passed_count
    drift_results = drift_results or []
    drift_passed_count = sum(1 for result in drift_results if result.passed)
    drift_failed_count = len(drift_results) - drift_passed_count
    economic_drift_results = economic_drift_results or []
    economic_drift_passed_count = sum(1 for result in economic_drift_results if result.passed)
    economic_drift_failed_count = len(economic_drift_results) - economic_drift_passed_count
    fairness_results = fairness_results or []
    fairness_passed_count = sum(
        1 for result in fairness_results if not _is_fairness_failure(result)
    )
    fairness_failed_count = sum(1 for result in fairness_results if _is_fairness_failure(result))
    issues = issues or []
    issue_count = len(issues)
    overall_failed = (
        failed_count
        + economic_failed_count
        + scenario_failed_count
        + drift_failed_count
        + economic_drift_failed_count
        + fairness_failed_count
        + issue_count
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project": config.project,
        "version": config.version,
        "summary": {
            "total": (
                len(results)
                + len(economic_results)
                + len(scenario_results)
                + len(drift_results)
                + len(economic_drift_results)
                + len(fairness_results)
                + issue_count
            ),
            "passed": passed_count
            + economic_passed_count
            + scenario_passed_count
            + drift_passed_count
            + economic_drift_passed_count
            + fairness_passed_count,
            "failed": overall_failed,
            "status": "pass" if overall_failed == 0 else "fail",
        },
        "invariants": [asdict(result) for result in results],
        "economic_checks": [asdict(result) for result in economic_results],
        "economic_drift_checks": [asdict(result) for result in economic_drift_results],
        "stress_tests": [asdict(result) for result in scenario_results],
        "drift_checks": [asdict(result) for result in drift_results],
        "fairness_checks": [asdict(result) for result in fairness_results],
        "issues": [asdict(issue) for issue in issues],
    }


def build_report_comparison(
    current_report: dict[str, Any],
    baseline_report: dict[str, Any],
) -> dict[str, Any]:
    """Summarize how the current report differs from a baseline report."""

    sections = [section for section, _ in _REPORT_SECTIONS if section != "issues"]
    baseline_summary = baseline_report.get("summary", {})
    summary_delta = {
        key: int(current_report["summary"].get(key, 0)) - int(baseline_summary.get(key, 0))
        for key in ("total", "passed", "failed")
    }

    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    new_checks: list[dict[str, Any]] = []
    removed_checks: list[dict[str, Any]] = []

    for section in sections:
        current_items = {item.get("name"): item for item in current_report.get(section, [])}
        baseline_items = {item.get("name"): item for item in baseline_report.get(section, [])}
        for name in sorted(set(current_items) | set(baseline_items), key=lambda value: str(value)):
            current_item = current_items.get(name)
            baseline_item = baseline_items.get(name)
            if current_item is None and baseline_item is None:
                continue
            if current_item is None:
                removed_checks.append(_comparison_entry(section, baseline_item, "removed"))
                continue
            if baseline_item is None:
                new_checks.append(_comparison_entry(section, current_item, "new"))
                continue

            current_passed = not _item_is_hard_failure(section, current_item)
            baseline_passed = not _item_is_hard_failure(section, baseline_item)
            if baseline_passed and not current_passed:
                regressions.append(
                    _comparison_entry(section, current_item, "regression", baseline_item)
                )
            elif not baseline_passed and current_passed:
                improvements.append(
                    _comparison_entry(section, current_item, "improvement", baseline_item)
                )

    return {
        "baseline_generated_at": baseline_report.get("generated_at"),
        "baseline_project": baseline_report.get("project"),
        "summary_delta": summary_delta,
        "regressions": regressions,
        "improvements": improvements,
        "new_checks": new_checks,
        "removed_checks": removed_checks,
    }


def write_json_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_markdown_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a Markdown report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_markdown_report(report), encoding="utf-8")


def write_github_step_summary(path: str | Path, report: dict[str, Any]) -> None:
    """Write a GitHub Actions step summary artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_github_step_summary(report), encoding="utf-8")


def write_html_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write an HTML report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_html_report(report), encoding="utf-8")


def write_dashboard_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a dashboard-style HTML report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_render_dashboard_report(report), encoding="utf-8")


def write_junit_report(path: str | Path, report: dict[str, Any]) -> None:
    """Write a JUnit XML report artifact to disk."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tests = int(report["summary"]["total"])
    failures = int(report["summary"]["failed"])
    skipped = 0

    root = ET.Element(
        "testsuites",
        attrib={
            "tests": str(tests),
            "failures": str(failures),
            "skipped": str(skipped),
        },
    )
    suite = ET.SubElement(
        root,
        "testsuite",
        attrib={
            "name": str(report["project"]),
            "tests": str(tests),
            "failures": str(failures),
            "skipped": str(skipped),
            "timestamp": str(report["generated_at"]),
        },
    )

    for item in report.get("invariants", []):
        _append_case(suite, "invariant", item["name"], item)
    for item in report.get("economic_checks", []):
        _append_case(suite, "economic_check", item["name"], item)
    for item in report.get("economic_drift_checks", []):
        _append_case(suite, "economic_drift_check", item["name"], item)
    for item in report.get("stress_tests", []):
        _append_case(suite, "stress_test", item["name"], item)
    for item in report.get("drift_checks", []):
        _append_case(suite, "drift_check", item["name"], item)
    for item in report.get("fairness_checks", []):
        _append_case(suite, "fairness_check", item["name"], item)
    for item in report.get("issues", []):
        _append_issue_case(suite, item)

    output_path.write_text(ET.tostring(root, encoding="unicode") + "\n", encoding="utf-8")


def _append_case(parent: ET.Element, kind: str, name: str, payload: dict[str, Any]) -> None:
    case = ET.SubElement(
        parent,
        "testcase",
        attrib={
            "classname": kind,
            "name": str(name),
        },
    )
    if payload.get("passed", True):
        return

    failure = ET.SubElement(
        case,
        "failure",
        attrib={"message": payload.get("error") or "check failed"},
    )
    body = {
        "kind": kind,
        "name": name,
        "payload": payload,
    }
    failure.text = json.dumps(body, indent=2, sort_keys=True)


def _append_issue_case(parent: ET.Element, issue: dict[str, Any]) -> None:
    case = ET.SubElement(
        parent,
        "testcase",
        attrib={
            "classname": "issue",
            "name": str(issue["stage"]),
        },
    )
    failure = ET.SubElement(
        case,
        "error",
        attrib={
            "message": issue.get("message") or "execution issue",
        },
    )
    failure.text = json.dumps(issue, indent=2, sort_keys=True)


def _render_markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# EconEval Report",
        "",
        f"- Project: `{report['project']}`",
        f"- Status: `{report['summary']['status']}`",
        f"- Passed: `{report['summary']['passed']}`",
        f"- Failed: `{report['summary']['failed']}`",
        f"- Total: `{report['summary']['total']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
        "## Checks",
    ]

    for key, title in _REPORT_SECTIONS:
        items = report.get(key, [])
        if not items:
            continue
        lines.extend(["", f"### {title}s"])
        for item in items:
            lines.extend(_render_markdown_item(key, item))

    comparison = report.get("comparison")
    if comparison:
        lines.extend(["", "## Baseline Comparison", ""])
        lines.extend(_render_markdown_comparison(comparison))

    return "\n".join(lines).rstrip() + "\n"


def _render_github_step_summary(report: dict[str, Any]) -> str:
    lines = [
        "# EconEval Summary",
        "",
        f"- Project: `{report['project']}`",
        f"- Status: `{report['summary']['status']}`",
        f"- Passed: `{report['summary']['passed']}`",
        f"- Failed: `{report['summary']['failed']}`",
        f"- Total: `{report['summary']['total']}`",
        f"- Generated at: `{report['generated_at']}`",
        "",
        (
            "_Outcome Distribution uses percentile shorthand: `p10` = 10th percentile, "
            "`p50` = median, `p90` = 90th percentile._"
        ),
    ]

    all_checks = _collect_all_items(report)
    if all_checks:
        lines.extend(
            [
                "",
                "<details>",
                "<summary>All Checks</summary>",
                "",
                (
                    "| Type | Check | Status | Margin / Error | Scan Grid / Values | "
                    "Outcome Distribution | Worst Sample | Impacted Variables | Details |"
                ),
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in all_checks:
            lines.append(
                (
                    "| {type} | {name} | {status} | {margin} | {scan} | {distribution} |"
                    " {worst_sample} | {impacted} | {details} |"
                ).format(
                    type=_markdown_cell(item["type"]),
                    name=_markdown_cell(item["name"]),
                    status=_markdown_cell(item["status"]),
                    margin=_markdown_cell(item["margin"]),
                    scan=_markdown_cell(item["scan"]),
                    distribution=_markdown_cell(item["distribution"]),
                    worst_sample=_markdown_cell(item["worst_sample"]),
                    impacted=_markdown_cell(item["impacted"]),
                    details=_markdown_cell(item["details"]),
                )
            )
        lines.extend(["", "</details>"])

    failures = _collect_failed_items(report)
    if not failures:
        lines.extend(["", "## Failed Checks", "", "No failures."])
        return "\n".join(lines).rstrip() + "\n"

    lines.extend(
        [
            "",
            "## Failed Checks",
            "",
            (
                "| Type | Check | Severity | Margin / Error | Scan Grid / Values | Outcome "
                "Distribution | Worst Sample | Impacted Variables | Details |"
            ),
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for failure in failures:
        lines.append(
            (
                "| {type} | {name} | {severity} | {margin} | {scan} | {distribution} | "
                "{worst_sample} | {impacted} | {details} |"
            ).format(
                type=_markdown_cell(failure["type"]),
                name=_markdown_cell(failure["name"]),
                severity=_markdown_cell(failure.get("severity", "")),
                margin=_markdown_cell(failure["margin"]),
                scan=_markdown_cell(failure["scan"]),
                distribution=_markdown_cell(failure.get("distribution", "")),
                worst_sample=_markdown_cell(failure.get("worst_sample", "")),
                impacted=_markdown_cell(failure["impacted"]),
                details=_markdown_cell(failure["details"]),
            )
        )

    return "\n".join(lines).rstrip() + "\n"


def _render_markdown_item(section: str, item: dict[str, Any]) -> list[str]:
    lines = [f"- `{_item_name(section, item)}`: `{_item_status(section, item)}`"]
    for key, value in _item_details(section, item):
        lines.append(f"  - {key}: `{value}`")
    if item.get("visual"):
        lines.append(f"  - visual: `{item['visual']}`")
    return lines


def _render_markdown_comparison(comparison: dict[str, Any]) -> list[str]:
    lines = [
        f"- Baseline generated at: `{comparison.get('baseline_generated_at') or '-'}`",
        f"- Baseline project: `{comparison.get('baseline_project') or '-'}`",
        (
            "- Summary delta: "
            f"`total={comparison.get('summary_delta', {}).get('total', 0)}`, "
            f"`passed={comparison.get('summary_delta', {}).get('passed', 0)}`, "
            f"`failed={comparison.get('summary_delta', {}).get('failed', 0)}`"
        ),
    ]
    for key in ("regressions", "improvements", "new_checks", "removed_checks"):
        items = comparison.get(key, [])
        lines.append("")
        lines.append(f"### {key.replace('_', ' ').title()}")
        if not items:
            lines.append("No entries.")
            continue
        for item in items:
            detail = item.get("current_detail") or item.get("baseline_detail") or "-"
            baseline_status = item.get("baseline_status")
            current_status = item.get("current_status")
            status = current_status if current_status is not None else baseline_status
            lines.append(
                f"- `{item.get('section')}` / `{item.get('name')}`: `{status}` "
                f"({item.get('change_type')})"
            )
            lines.append(f"  - detail: `{detail}`")
    return lines


def _render_html_report(report: dict[str, Any]) -> str:
    sections = []
    for key, title in _REPORT_SECTIONS:
        items = report.get(key, [])
        if not items:
            continue
        rows = "".join(_render_html_item(key, item) for item in items)
        sections.append(
            f"<section><h2>{escape(title)}s</h2><div class='cards'>{rows}</div></section>"
        )
    comparison = report.get("comparison")
    comparison_html = _render_html_comparison(comparison) if comparison else ""

    styles = (
        "body{font-family:Arial,sans-serif;max-width:960px;margin:32px auto;"
        "padding:0 20px;background:#f7f7fb;color:#1f2937;}"
        "h1,h2{margin:0 0 12px;}"
        ".meta,.summary,.cards{display:grid;gap:12px;}"
        ".summary{grid-template-columns:repeat(auto-fit,minmax(160px,1fr));"
        "margin-bottom:24px;}"
        ".card,.stat{background:#fff;border:1px solid #e5e7eb;border-radius:12px;"
        "padding:16px;box-shadow:0 1px 2px rgba(0,0,0,.04);}"
        ".cards{grid-template-columns:repeat(auto-fit,minmax(240px,1fr));}"
        ".status-pass{color:#166534}.status-warn{color:#b45309}.status-fail{color:#b91c1c}"
        ".status-error{color:#92400e}"
        ".state-summary{margin-top:8px;padding:10px;border-radius:10px;"
        "background:#f9fafb;border:1px solid #e5e7eb;}"
        ".state-summary h4{margin:0 0 6px;font-size:0.9rem;}"
        ".state-summary .kv{margin-top:6px}"
        ".visual{margin:8px 0 0;font-family:monospace;white-space:pre-wrap;}"
        ".kv{margin:8px 0 0;padding-left:18px}.kv li{margin:4px 0}"
        "code{background:#f3f4f6;padding:2px 5px;border-radius:6px;}"
    )
    summary_status = escape(str(report["summary"]["status"]))
    body = "".join(
        [
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            "<title>EconEval Report</title>",
            "<style>",
            styles,
            "</style></head><body>",
            (
                "<h1>EconEval Report</h1><p><strong>Project:</strong> "
                f"{escape(str(report['project']))} <strong>Status:</strong> "
                f"<span class='status-{summary_status}'>{summary_status}</span></p>"
            ),
            "<div class='summary'>",
            *_render_html_stat("Passed", report["summary"]["passed"]),
            *_render_html_stat("Failed", report["summary"]["failed"]),
            *_render_html_stat("Total", report["summary"]["total"]),
            (
                "<div class='stat'><strong>Generated at</strong><div>"
                f"{escape(str(report['generated_at']))}</div></div>"
            ),
            "</div>",
            "<h2>Checks</h2>",
            "".join(sections),
            comparison_html,
            "</body></html>",
        ]
    )
    return body


def _render_dashboard_report(report: dict[str, Any]) -> str:
    overview = _dashboard_overview(report)
    spotlight = _failure_spotlight(report)
    top_failures = _top_failures_table(report)
    controls = _dashboard_controls()
    fairness_warnings = _fairness_warning_count(report)
    comparison = report.get("comparison")
    comparison_html = _render_dashboard_comparison(comparison) if comparison else ""
    sections = []
    for key, title in _REPORT_SECTIONS:
        items = report.get(key, [])
        if not items:
            continue
        rows = "".join(
            _render_html_item(key, item, _card_id(key, item, index))
            for index, item in enumerate(items)
        )
        sections.append(
            f"<details class='section' id='{escape(key)}' open>"
            f"<summary>{escape(title)}s <span class='section-count'>{len(items)}</span></summary>"
            f"<div class='cards'>{rows}</div></details>"
        )

    styles = (
        "body{font-family:Inter,Arial,sans-serif;max-width:1200px;margin:0 auto;"
        "padding:28px 20px 48px;background:linear-gradient(180deg,#f8fafc, #eef2ff);"
        "color:#111827;}"
        "h1,h2,h3{margin:0}"
        "h1{font-size:2.4rem;letter-spacing:-0.04em}"
        "h2{font-size:1.2rem;margin:0 0 12px}"
        ".hero{display:flex;justify-content:space-between;gap:24px;align-items:end;"
        "margin-bottom:24px;flex-wrap:wrap}"
        ".hero p{margin:8px 0 0;max-width:68ch;color:#4b5563}"
        ".pill{display:inline-flex;align-items:center;gap:8px;padding:8px 12px;"
        "border-radius:999px;font-size:0.9rem;font-weight:600;background:#fff;"
        "border:1px solid #dbeafe;box-shadow:0 8px 24px rgba(37,99,235,.08)}"
        ".pill.pass{color:#166534}.pill.fail{color:#b91c1c}.pill.error{color:#92400e}"
        ".grid{display:grid;gap:16px}"
        ".overview{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));margin-bottom:20px}"
        ".card,.stat,.spotlight{background:#fff;border:1px solid #e5e7eb;border-radius:16px;"
        "padding:16px;box-shadow:0 8px 24px rgba(15,23,42,.06)}"
        ".section-index{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 24px}"
        ".section-index a{padding:6px 10px;border-radius:999px;background:#e0e7ff;color:#1e1b4b;"
        "text-decoration:none;font-size:0.9rem}"
        ".controls{display:flex;flex-wrap:wrap;gap:12px;align-items:center;margin:4px 0 20px}"
        ".controls input{min-width:260px;flex:1;padding:10px 12px;border-radius:12px;"
        "border:1px solid #cbd5e1;background:#fff;font-size:0.95rem}"
        ".controls label{display:inline-flex;align-items:center;gap:8px;font-size:0.95rem;"
        "color:#334155}"
        ".cards{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}"
        ".section{margin:0 0 18px;border:1px solid #e5e7eb;border-radius:16px;"
        "background:rgba(255,255,255,.72);box-shadow:0 8px 24px rgba(15,23,42,.06);"
        "overflow:hidden}"
        ".section summary{list-style:none;cursor:pointer;padding:14px 16px;font-weight:700;"
        "display:flex;align-items:center;justify-content:space-between;gap:12px;"
        "background:linear-gradient(180deg,#fff,#f8fafc)}"
        ".section summary::-webkit-details-marker{display:none}"
        ".section .cards{padding:16px;border-top:1px solid #e5e7eb}"
        ".section-count{font-size:0.85rem;font-weight:600;color:#4b5563;background:#e2e8f0;"
        "padding:4px 8px;border-radius:999px}"
        ".table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;"
        "border-radius:16px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,.06);}"
        ".table th,.table td{padding:10px 12px;text-align:left;border-bottom:1px solid #e5e7eb;}"
        ".table th{background:#f8fafc;font-size:0.9rem;color:#374151;}"
        ".table a{color:#4338ca;text-decoration:none;font-weight:600}"
        ".status-pass{color:#166534}.status-fail{color:#b91c1c}.status-error{color:#92400e}"
        ".spotlight ol{margin:0;padding-left:20px}.spotlight li{margin:8px 0}"
        ".bar{height:10px;border-radius:999px;background:#e5e7eb;overflow:hidden}"
        ".bar > span{display:block;height:100%;background:linear-gradient(90deg,#2563eb,#7c3aed)}"
        ".meta{color:#6b7280;font-size:0.92rem;margin-top:4px}"
        ".state-summary{margin-top:8px;padding:10px;border-radius:10px;"
        "background:#f9fafb;border:1px solid #e5e7eb;}"
        ".state-summary h4{margin:0 0 6px;font-size:0.9rem;}"
        ".state-summary .kv{margin-top:6px}"
        ".visual{margin:8px 0 0;font-family:monospace;white-space:pre-wrap;}"
        ".kv{margin:8px 0 0;padding-left:18px}.kv li{margin:4px 0}"
        ".hidden{display:none !important}"
        "code{background:#f3f4f6;padding:2px 5px;border-radius:6px;}"
    )
    status = str(report["summary"]["status"])
    body = "".join(
        [
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            "<title>EconEval Dashboard</title>",
            "<style>",
            styles,
            "</style></head><body>",
            "<div class='hero'>",
            "<div>",
            "<h1>EconEval Dashboard</h1>",
            (
                f"<p>Project <code>{escape(str(report['project']))}</code> "
                f"generated at {escape(str(report['generated_at']))}.</p>"
            ),
            "</div>",
            f"<div class='pill {escape(status)}'>Status: {escape(status)}</div>",
            "</div>",
            "<div class='grid overview'>",
            *_render_dashboard_stat("Passed", report["summary"]["passed"]),
            *_render_dashboard_stat("Failed", report["summary"]["failed"]),
            *_render_dashboard_stat("Total", report["summary"]["total"]),
            *_render_dashboard_stat("Pass rate", _dashboard_pass_rate(report)),
            *_render_dashboard_stat("Fairness warnings", fairness_warnings),
            "</div>",
            overview,
            controls,
            "<div class='spotlight'>",
            "<h2>Failure Spotlight</h2>",
            spotlight,
            "</div>",
            "<div class='spotlight'>",
            "<h2>Top Failures</h2>",
            top_failures,
            "</div>",
            comparison_html,
            "<h2>Sections</h2>",
            "<div class='section-index'>",
            "".join(
                f"<a href='#{escape(key)}'>{escape(title)}s</a>"
                for key, title in _REPORT_SECTIONS
                if report.get(key, [])
            ),
            "</div>",
            "".join(sections),
            _dashboard_script(),
            "</body></html>",
        ]
    )
    return body


def _render_html_comparison(comparison: dict[str, Any]) -> str:
    rows = []
    for key in ("regressions", "improvements", "new_checks", "removed_checks"):
        items = comparison.get(key, [])
        if not items:
            continue
        body = "".join(
            "".join(
                [
                    "<li>",
                    f"<strong>{escape(item.get('section', ''))}:</strong> ",
                    f"{escape(item.get('name', ''))}",
                    f"<div class='meta'>{escape(item.get('change_type', ''))} | ",
                    f"current={escape(str(item.get('current_status', '')))}",
                    (
                        f" | baseline={escape(str(item.get('baseline_status', '')))}"
                        if item.get("baseline_status") is not None
                        else ""
                    ),
                    "</div>",
                    "</li>",
                ]
            )
            for item in items
        )
        rows.append(
            "<details class='section'><summary>"
            f"{escape(key.replace('_', ' ').title())} "
            f"<span class='section-count'>{len(items)}</span></summary>"
            f"<div class='spotlight'><ol>{body}</ol></div></details>"
        )
    if not rows:
        return ""
    return "<section><h2>Baseline Comparison</h2>" + "".join(rows) + "</section>"


def _render_dashboard_comparison(comparison: dict[str, Any]) -> str:
    regressions = len(comparison.get("regressions", []))
    improvements = len(comparison.get("improvements", []))
    new_checks = len(comparison.get("new_checks", []))
    removed_checks = len(comparison.get("removed_checks", []))
    return "".join(
        [
            "<div class='spotlight'>",
            "<h2>Baseline Comparison</h2>",
            "<div class='grid overview'>",
            *_render_dashboard_stat("Regressions", regressions),
            *_render_dashboard_stat("Improvements", improvements),
            *_render_dashboard_stat("New checks", new_checks),
            *_render_dashboard_stat("Removed checks", removed_checks),
            "</div>",
            _render_dashboard_comparison_list("Regressions", comparison.get("regressions", [])),
            _render_dashboard_comparison_list("Improvements", comparison.get("improvements", [])),
            _render_dashboard_comparison_list("New Checks", comparison.get("new_checks", [])),
            _render_dashboard_comparison_list(
                "Removed Checks", comparison.get("removed_checks", [])
            ),
            "</div>",
        ]
    )


def _render_dashboard_comparison_list(title: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    lis = "".join(
        "".join(
            [
                "<li>",
                (
                    f"<strong>{escape(item.get('section', ''))}:</strong> "
                    f"{escape(item.get('name', ''))}"
                ),
                f"<div class='meta'>{escape(item.get('change_type', ''))} | ",
                f"current={escape(str(item.get('current_status', '')))}",
                (
                    f" | baseline={escape(str(item.get('baseline_status', '')))}"
                    if item.get("baseline_status") is not None
                    else ""
                ),
                "</div>",
                "</li>",
            ]
        )
        for item in items[:8]
    )
    return (
        "<details class='section'><summary>"
        f"{escape(title)} <span class='section-count'>{len(items)}</span></summary>"
        f"<div class='spotlight'><ol>{lis}</ol></div></details>"
    )


def _render_html_stat(label: str, value: Any) -> list[str]:
    return [
        (f"<div class='stat'><strong>{escape(label)}</strong><div>{escape(str(value))}</div></div>")
    ]


def _render_dashboard_stat(label: str, value: Any) -> list[str]:
    return [
        f"<div class='stat'><strong>{escape(label)}</strong><div>{escape(str(value))}</div></div>"
    ]


def _render_html_item(section: str, item: dict[str, Any], anchor: str | None = None) -> str:
    card_id = f" id='{escape(anchor)}'" if anchor else ""
    search_terms = _dashboard_search_terms(section, item)
    body = [
        f"<article class='card'{card_id} data-search='{escape(search_terms)}'>",
        f"<h3>{escape(_item_name(section, item))}</h3>",
        f"<p class='status-{escape(_item_status(section, item))}'>",
        f"{escape(_item_status(section, item))}</p>",
    ]
    if section == "fairness_checks" and item.get("severity"):
        body.append(
            f"<p class='severity'><strong>severity:</strong> {escape(str(item['severity']))}</p>"
        )
    state_summary = _render_html_state_summary(section, item)
    if state_summary:
        body.append(state_summary)
    if item.get("visual"):
        body.append(f"<p class='visual'><strong>visual:</strong> {escape(str(item['visual']))}</p>")
    body.append("</article>")
    return "".join(body)


def _item_name(section: str, item: dict[str, Any]) -> str:
    if section == "issues":
        return item["stage"]
    return item["name"]


def _item_status(section: str, item: dict[str, Any]) -> str:
    if section == "issues":
        return "error"
    if section == "fairness_checks":
        return str(item.get("severity") or ("pass" if item.get("passed", True) else "fail"))
    return "pass" if item.get("passed", True) else "fail"


def _item_details(section: str, item: dict[str, Any]) -> list[tuple[str, Any]]:
    labels = {
        "states": "initial states",
        "worst_state": "worst initial state",
        "worst_value": "worst observed value",
        "percentiles": "outcome percentiles",
        "worst_sample": "worst sample",
        "mode": "drift mode",
        "backend": "drift backend",
    }
    keys = (
        "stage",
        "message",
        "value",
        "threshold",
        "tolerance",
        "metric",
        "severity",
        "kind",
        "dataset",
        "baseline_dataset",
        "feature",
        "statistic",
        "variable",
        "input_variable",
        "output_variable",
        "method",
        "scan_kind",
        "expected_direction",
        "perturbations",
        "manipulations",
        "invariants",
        "samples",
        "grid_points",
        "failure_count",
        "percentiles",
        "worst_sample",
        "states",
        "worst_state",
        "worst_value",
        "scan_inputs",
        "observations",
        "shock_type",
        "direction",
        "detail",
        "error_type",
        "error",
    )
    details = [
        (labels.get(key, key), item[key])
        for key in keys
        if key in item and item.get(key) not in (None, "", [])
    ]
    if item.get("observations"):
        details.append(("observations", item["observations"]))
    return details


def _dashboard_controls() -> str:
    return (
        "<div class='controls'>"
        "<input id='dashboard-filter' type='search' "
        "placeholder='Filter checks by name, status, or detail'>"
        "<label><input id='dashboard-failures-only' type='checkbox'> Failures only</label>"
        "</div>"
    )


def _dashboard_script() -> str:
    return (
        "<script>"
        "(function(){"
        "const queryInput=document.getElementById('dashboard-filter');"
        "const failuresOnly=document.getElementById('dashboard-failures-only');"
        "const sections=[...document.querySelectorAll('details.section')];"
        "const cards=[...document.querySelectorAll('article.card')];"
        "function applyFilter(){"
        "const query=(queryInput.value||'').trim().toLowerCase();"
        "const onlyFailures=failuresOnly.checked;"
        "sections.forEach(section=>{"
        "let visibleCount=0;"
        "section.querySelectorAll('article.card').forEach(card=>{"
        "const text=(card.dataset.search||'').toLowerCase();"
        "const status=(card.querySelector('p')?.textContent||'').toLowerCase();"
        "const matchesQuery=!query||text.includes(query);"
        "const matchesFailure=!onlyFailures||status!=='pass';"
        "const visible=matchesQuery&&matchesFailure;"
        "card.classList.toggle('hidden',!visible);"
        "if(visible){visibleCount+=1;}"
        "});"
        "section.classList.toggle('hidden',visibleCount===0);"
        "section.open=visibleCount>0;"
        "});"
        "cards.forEach(card=>{"
        "if(!card.dataset.search){card.dataset.search='';}"
        "});"
        "}"
        "queryInput.addEventListener('input',applyFilter);"
        "failuresOnly.addEventListener('change',applyFilter);"
        "applyFilter();"
        "})();"
        "</script>"
    )


def _dashboard_search_terms(section: str, item: dict[str, Any]) -> str:
    parts = [_item_name(section, item), _item_status(section, item)]
    for key, value in _item_details(section, item):
        parts.append(f"{key} {value}")
    if item.get("visual"):
        parts.append(str(item["visual"]))
    return " ".join(str(part) for part in parts if part not in (None, "", []))


def _collect_failed_items(report: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for section, label in (
        ("invariants", "Invariant"),
        ("economic_checks", "Economic Check"),
        ("economic_drift_checks", "Economic Drift Check"),
        ("stress_tests", "Stress Test"),
        ("drift_checks", "Drift Check"),
        ("fairness_checks", "Fairness Check"),
    ):
        for index, item in enumerate(report.get(section, [])):
            if not _item_is_hard_failure(section, item):
                continue
            failures.append(
                {
                    "type": label,
                    "name": str(item.get("name", "")),
                    "anchor": _card_id(section, item, index),
                    "margin": _failure_margin(item),
                    "scan": _scan_values(item),
                    "distribution": _outcome_distribution(item),
                    "worst_sample": _worst_sample(item),
                    "impacted": _impacted_variables(item),
                    "details": _failure_details(item),
                }
            )

    for issue in report.get("issues", []):
        failures.append(
            {
                "type": "Issue",
                "name": str(issue.get("stage", "")),
                "anchor": "issues",
                "margin": str(issue.get("message", "")),
                "scan": "",
                "distribution": "",
                "worst_sample": "",
                "impacted": str(issue.get("detail", "")),
                "details": "",
            }
        )
    return failures


def _collect_all_items(report: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section, label in (
        ("invariants", "Invariant"),
        ("economic_checks", "Economic Check"),
        ("economic_drift_checks", "Economic Drift Check"),
        ("stress_tests", "Stress Test"),
        ("drift_checks", "Drift Check"),
        ("fairness_checks", "Fairness Check"),
    ):
        for index, item in enumerate(report.get(section, [])):
            rows.append(
                {
                    "type": label,
                    "name": str(item.get("name", "")),
                    "anchor": _card_id(section, item, index),
                    "status": _item_status(section, item),
                    "severity": str(item.get("severity", "")),
                    "margin": _failure_margin(item),
                    "scan": _scan_values(item),
                    "distribution": _outcome_distribution(item),
                    "worst_sample": _worst_sample(item),
                    "impacted": _impacted_variables(item),
                    "details": _failure_details(item),
                }
            )

    for issue in report.get("issues", []):
        rows.append(
            {
                "type": "Issue",
                "name": str(issue.get("stage", "")),
                "anchor": "issues",
                "status": "error",
                "severity": "error",
                "margin": str(issue.get("message", "")),
                "scan": "",
                "distribution": "",
                "worst_sample": "",
                "impacted": str(issue.get("detail", "")),
                "details": "",
            }
        )
    return rows


def _failure_margin(item: dict[str, Any]) -> str:
    value = item.get("value")
    threshold = item.get("threshold")
    tolerance = item.get("tolerance")
    if value is None:
        return ""
    if threshold is not None:
        return f"value={value}, threshold={threshold}"
    if tolerance is not None:
        return f"value={value}, tolerance={tolerance}"
    return f"value={value}"


def _impacted_variables(item: dict[str, Any]) -> str:
    impacted: list[str] = []
    for key in (
        "worst_state",
        "feature",
        "variable",
        "input_variable",
        "output_variable",
        "dataset",
        "baseline_dataset",
    ):
        value = item.get(key)
        if not value:
            continue
        if isinstance(value, dict):
            impacted.extend(f"{name}={val}" for name, val in value.items())
        else:
            impacted.append(f"{key}={value}")
    for manipulation in item.get("manipulations", []) or []:
        variable = manipulation.get("variable")
        action = manipulation.get("action")
        value = manipulation.get("value")
        if variable:
            impacted.append(f"manipulation={variable}:{action}({value})")
    return ", ".join(impacted)


def _failure_details(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "severity",
        "detail",
        "error",
        "error_type",
        "visual",
        "states",
        "worst_value",
        "scan_inputs",
        "observations",
        "manipulations",
        "invariants",
        "samples",
        "failure_count",
        "percentiles",
        "worst_sample",
        "statistic",
        "mode",
        "backend",
    ):
        value = item.get(key)
        if value in (None, "", []):
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts)


def _item_is_hard_failure(section: str, item: dict[str, Any]) -> bool:
    if section == "fairness_checks":
        if item.get("error"):
            return True
        return str(item.get("severity", "fail")) == "fail"
    return not item.get("passed", True)


def _is_fairness_failure(result: FairnessResult) -> bool:
    return result.error is not None or result.severity == "fail"


def _item_is_warning(section: str, item: dict[str, Any]) -> bool:
    return section == "fairness_checks" and str(item.get("severity")) == "warn"


def _fairness_warning_count(report: dict[str, Any]) -> int:
    return sum(
        1 for item in report.get("fairness_checks", []) if str(item.get("severity")) == "warn"
    )


def _comparison_entry(
    section: str,
    item: dict[str, Any],
    change_type: str,
    baseline_item: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry = {
        "section": section,
        "name": str(item.get("name", "")),
        "change_type": change_type,
        "current_status": _item_status(section, item),
        "current_detail": _failure_details(item),
    }
    if baseline_item is not None:
        entry.update(
            {
                "baseline_status": _item_status(section, baseline_item),
                "baseline_detail": _failure_details(baseline_item),
            }
        )
    return entry


def _scan_values(item: dict[str, Any]) -> str:
    scan_inputs = item.get("scan_inputs")
    observations = item.get("observations")
    if not scan_inputs and not observations:
        return ""
    parts: list[str] = []
    if scan_inputs:
        parts.append(f"grid={_arrow_sequence(scan_inputs)}")
    if observations:
        parts.append(f"values={_arrow_sequence(observations)}")
    return ", ".join(parts)


def _outcome_distribution(item: dict[str, Any]) -> str:
    percentiles = item.get("percentiles")
    if not percentiles:
        return ""
    if not isinstance(percentiles, dict):
        return str(percentiles)

    parts: list[str] = []
    for key in sorted(percentiles):
        parts.append(f"{key}={_format_sequence_value(percentiles[key])}")
    return ", ".join(parts)


def _worst_sample(item: dict[str, Any]) -> str:
    worst_sample = item.get("worst_sample")
    if not worst_sample:
        return ""
    if not isinstance(worst_sample, dict):
        return str(worst_sample)

    if worst_sample.get("score") is not None:
        return f"score={_format_sequence_value(worst_sample['score'])}"
    return ""


def _arrow_sequence(values: list[Any]) -> str:
    return " -> ".join(_format_sequence_value(value) for value in values)


def _format_sequence_value(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


def _markdown_cell(value: Any) -> str:
    text = str(value).replace("|", "\\|").replace("\n", " ")
    return text or "-"


def _render_html_state_summary(section: str, item: dict[str, Any]) -> str:
    details = _item_details(section, item)
    if not details:
        return ""

    state_labels = {
        "initial states",
        "worst initial state",
        "worst observed value",
    }

    if section != "economic_checks" or not any(key in state_labels for key, _ in details):
        return f"<ul class='kv'>{_render_html_kv_list(details)}</ul>"

    summary_items = [(key, value) for key, value in details if key in state_labels]
    other_items = [(key, value) for key, value in details if key not in state_labels]

    parts = ["<div class='state-summary'><h4>State Summary</h4>"]
    parts.append(f"<ul class='kv'>{_render_html_kv_list(summary_items)}</ul>")
    if other_items:
        parts.append(f"<ul class='kv'>{_render_html_kv_list(other_items)}</ul>")
    parts.append("</div>")
    return "".join(parts)


def _render_html_kv_list(items: list[tuple[str, Any]]) -> str:
    return "".join(
        f"<li><strong>{escape(key)}:</strong> {escape(str(value))}</li>" for key, value in items
    )


def _dashboard_pass_rate(report: dict[str, Any]) -> str:
    total = report["summary"]["total"]
    passed = report["summary"]["passed"]
    if total == 0:
        return "0%"
    return f"{(passed / total) * 100:.0f}%"


def _dashboard_overview(report: dict[str, Any]) -> str:
    counts = []
    for key, title in _REPORT_SECTIONS:
        items = report.get(key, [])
        if not items:
            continue
        passed = sum(1 for item in items if not _item_is_hard_failure(key, item))
        warnings = sum(1 for item in items if _item_is_warning(key, item))
        total = len(items)
        counts.append(
            (
                title,
                passed,
                warnings,
                total - passed,
                total,
            )
        )

    if not counts:
        return ""

    cards = []
    for title, passed, warnings, failed, total in counts:
        width = 100 if total == 0 else round((passed / total) * 100)
        warning_text = f", {warnings} warnings" if warnings else ""
        cards.append(
            "".join(
                [
                    "<div class='card'>",
                    f"<h3>{escape(title)}s</h3>",
                    f"<div class='bar'><span style='width:{width}%'></span></div>",
                    (
                        "<div class='meta'>"
                        f"{passed}/{total} passed, {failed} failed{warning_text}"
                        "</div>"
                    ),
                    "</div>",
                ]
            )
        )

    return "".join(["<h2>Section Overview</h2><div class='cards'>", "".join(cards), "</div>"])


def _failure_spotlight(report: dict[str, Any]) -> str:
    failures = _collect_failed_items(report)
    if not failures:
        return "<p class='meta'>No failures.</p>"

    items = []
    for failure in failures[:5]:
        items.append(
            "".join(
                [
                    "<li>",
                    f"<strong>{escape(failure['type'])}:</strong> {escape(failure['name'])}",
                    f"<div class='meta'>{escape(failure['details'] or failure['margin'])}</div>",
                    "</li>",
                ]
            )
        )
    return f"<ol>{''.join(items)}</ol>"


def _top_failures_table(report: dict[str, Any]) -> str:
    failures = _collect_failed_items(report)
    if not failures:
        return "<p class='meta'>No failures.</p>"

    rows = []
    for failure in failures[:5]:
        link = f"<a href='#{escape(failure['anchor'])}'>Open card</a>"
        rows.append(
            "".join(
                [
                    "<tr>",
                    f"<td>{escape(failure['type'])}</td>",
                    f"<td>{escape(failure['name'])}</td>",
                    f"<td>{escape(failure['margin'] or failure['details'])}</td>",
                    f"<td>{link}</td>",
                    "</tr>",
                ]
            )
        )

    return "".join(
        [
            "<table class='table'>",
            "<thead><tr><th>Type</th><th>Check</th><th>Margin</th><th>Link</th></tr></thead>",
            f"<tbody>{''.join(rows)}</tbody>",
            "</table>",
        ]
    )


def _card_id(section: str, item: dict[str, Any], index: int) -> str:
    name = str(item.get("name", item.get("stage", "item")))
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
    return f"{section}-{index}-{slug or 'item'}"
