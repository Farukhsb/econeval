# Changelog

All notable changes to this project will be documented in this file.

Releases follow semantic versioning:

- `MAJOR` for breaking changes
- `MINOR` for new backwards-compatible features
- `PATCH` for bug fixes, docs updates, and small cleanup

## Unreleased

- No unreleased changes yet. The current work is already in `v0.5.2`.

## v0.5.2

- Added the Adult-derived tax policy simulator example and CI-friendly sample data.
- Documented a lightweight tax policy workflow with liability, rate, and monotonicity checks.
- Updated the examples list so the new scenario is easy to find.

## v0.5.1

- Added expression-safety coverage, clearer rejection errors, and a max-length guard.
- Expanded traceability, HTML reporting, drift, fairness, CSV relation-mode, and baseline-comparison tests.
- Refreshed the roadmap, limitations, and stabilization docs for the current release.

## v0.5.0

- Added traceability mode for failed invariants, including optional git blame metadata in reports.
- Surfaced invariant evaluation values and traces in JSON, Markdown, HTML, and dashboard outputs.
- Added a CLI `--blame` flag and focused tests for the traceability path.

## v0.4.0

- Added a safer numeric expression path with static validation and clearer failures.
- Improved HTML reporting with collapsible sections and richer output.
- Added a baseline report comparison flow for release validation.
- Added PDF output, benchmark tooling, and extension hooks for custom checks.
- Expanded examples, docs, type hints, and repo hygiene metadata.

## v0.3.2

- Added PSI-based drift detection and a worked drift example.
- Added `--watch` mode for iterative reruns.
- Added a repo-local pre-commit hook for the basic example.
- Improved direct interop for tabular sklearn/statsmodels-style models.
- Added baseline report comparison with `--baseline-report`.

## v0.3.1

- Restored trusted publishing in the release workflow.
- Bumped the package version to `0.3.1` for the next release.
- Updated the README release instructions and version references.

## v0.3.0

- Initial public release of EconEval.
- Added config loading, invariant checks, scenario checks, drift checks, fairness checks, and report generation.
