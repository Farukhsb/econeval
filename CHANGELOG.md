# Changelog

All notable changes to this project will be documented in this file.

Releases follow semantic versioning:

- `MAJOR` for breaking changes
- `MINOR` for new backwards-compatible features
- `PATCH` for bug fixes, docs updates, and small cleanup

## Unreleased

- No unreleased changes yet.

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
