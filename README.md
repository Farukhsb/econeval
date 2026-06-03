# EconEval

<p align="left">
  <img src="assets/logo.svg" alt="EconEval logo" width="120" />
</p>

[![PyPI version](https://img.shields.io/pypi/v/econeval.svg)](https://pypi.org/project/econeval/)
[![CI](https://github.com/Farukhsb/econeval/actions/workflows/ci.yml/badge.svg)](https://github.com/Farukhsb/econeval/actions/workflows/ci.yml)
[![Python 3.10-3.11](https://img.shields.io/badge/python-3.10%20%7C%203.11-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-v0.3.1-blue.svg)](https://github.com/Farukhsb/econeval/releases/tag/v0.3.1)

EconEval is a small open-source framework for checking economic and policy models in CI.

It is built for the kind of code that can look fine at the syntax level and still be wrong in practice. A model can run, pass unit tests, and still break an economic rule, drift off course after a data change, or produce results that no longer make sense under stress. EconEval is meant to catch those problems early, before they reach a report, dashboard, or paper.

Latest release: [`v0.3.1`](https://github.com/Farukhsb/econeval/releases/tag/v0.3.1)

## What It Does

EconEval currently does three things:

- loads a model check config
- runs invariant tests against a Python object
- writes JSON, JUnit, Markdown, or HTML reports that CI can keep or fail on

The config layer is validated with Pydantic, and invariant evaluation can route to `numexpr` for vectorized math or a restricted logical evaluator for model-state checks.

That gives you a practical starting point for:

- checking that important economic rules still hold
- making model assumptions explicit in code
- failing pull requests when a change breaks a rule you care about

## Who Should Use This

EconEval is a fit for people who need model checks that are closer to policy and economics than generic unit tests.

It is especially useful when the people reviewing a model are not just software engineers, but also domain stakeholders who care about whether the model still makes sense economically.

- academic economists validating research code and replication projects
- policy analysts checking that a model still respects program rules and constraints
- quantitative consultants delivering models to clients with auditability requirements
- teams working on forecasting, scenario analysis, or simulation pipelines
- researchers who want a lightweight validation layer before a model is published or deployed
- applied data scientists building models that need economics-aware guardrails
- analysts who want CI checks they can explain in a report or appendix

## Why It Exists

Traditional software tests are useful, but they do not tell you whether a model still behaves like a valid model.

For example, a change might:

- flip the sign of an elasticity
- violate a market-clearing condition
- break a policy constraint
- quietly change the meaning of a downstream output

EconEval gives you a place to encode those rules and run them automatically.

## Current MVP

The first usable version of EconEval does three things well:

1. read a simple YAML config
2. evaluate invariant expressions against a model object
3. return a clear pass or fail result that GitHub Actions can use

That is enough to support a real workflow without pretending to solve every validation problem at once.

## Example Config

```yaml
project: demo-model
version: 1

invariants:
  - name: elasticity_must_be_negative
    expression: model.elasticity < 0
  - name: supply_must_be_non_negative
    expression: model.supply >= 0

stress_tests:
  - name: stagflation_shock
    dataset: data/stagflation.csv
    metric: mape
    threshold: 0.15

  - name: macro_stagflation
    kind: synthetic
    metric: invariants
    manipulations:
      - variable: input_data.unemployment_rate
        action: add
        value: 0.04
      - variable: input_data.energy_costs
        action: multiply
        value: 1.5
    invariants:
      - name: slowdown_flag
        expression: model.predicted_gdp_growth < 0.01

fairness:
  enabled: true
  metrics:
    - demographic_parity_difference
    - disparate_impact_ratio
    - gini
    - atkinson
    - equal_opportunity_difference
    - equalized_odds_difference
```

## How It Fits Together

```text
model repo
  -> econeval.yml
  -> load config
  -> run invariant checks
  -> collect results
  -> fail or pass CI
```

## Project Layout

```text
econeval/
  .github/
    workflows/
      ci.yml
  action.yml
  examples/
    basic_model/
      model.py
      econeval.yml
    drift_model/
      model.py
      econeval.yml
    fairness_model/
      README.md
      model.py
      econeval.yml
    broken_model/
      model.py
      econeval.yml
    policy_model/
      model.py
      econeval.yml
    advanced_model/
      model.py
      econeval.yml
  src/
    econeval/
      __init__.py
      cli.py
      config.py
      invariants.py
      scenarios.py
      reporting.py
  tests/
    test_config.py
    test_invariants.py
```

## Install

For development from a checkout:

```bash
git clone https://github.com/Farukhsb/econeval.git
cd econeval
pip install -e .[dev]
```

`pytest` and `ruff` are included in the `dev` extra. If you only want the CLI, install the package without the extra.

EconEval parses its YAML-like config format with its own loader, so you do not need `PyYAML` for the current release.

Once the package is published to PyPI, the normal install path will be:

```bash
pip install econeval
```

If you want the published package state, start from the `v0.3.1` release tag or the GitHub release page.

## How To Use It

Create a config file that lists the checks you want to enforce, then point EconEval at a Python model class.

Command line example:

```bash
econeval --config examples/basic_model/econeval.yml --model examples/basic_model/model.py --class DemoModel --report econeval-report.json
```

If you prefer module execution, `python -m econeval` works the same way.

To write a text report instead:

```bash
econeval --config examples/advanced_model/econeval.yml --model examples/advanced_model/model.py --class AdvancedModel --report econeval-report.md --format markdown
econeval --config examples/advanced_model/econeval.yml --model examples/advanced_model/model.py --class AdvancedModel --report econeval-report.html --format html
```

## GitHub Action

The repository also exposes a composite GitHub Action so workflows can run EconEval in one step.

```yaml
- uses: Farukhsb/econeval@v1
  with:
    config: examples/basic_model/econeval.yml
    model: examples/basic_model/model.py
    class: DemoModel
    report: econeval-report.json
    python-version: "3.11"
```

The action installs the package from the action source, sets up Python, and runs the CLI with the inputs you provide.

## Fairness Checks

Fairness checks expect a tabular dataset with:

- a group column, defaulting to `group`
- one or more feature columns that are passed to `predict(features)`
- an `actual` column when you use label-based metrics such as `equal_opportunity_difference` or `equalized_odds_difference`

The example in [examples/fairness_model/README.md](examples/fairness_model/README.md) shows the full data format.

The built-in thresholds are:

- `demographic_parity_difference`: pass at `<= 0.2`
- `disparate_impact_ratio`: pass at `>= 0.8`
- `equal_opportunity_difference`: pass at `<= 0.2`
- `equalized_odds_difference`: pass at `<= 0.2`
- `gini`: pass at `<= 0.3`
- `atkinson`: pass at `<= 0.2`

Fairness results also include a `severity` field:

- `pass` for checks within the threshold
- `warn` for borderline misses that should not fail CI
- `fail` for clear misses or execution errors

To run the full advanced example with synthetic shocks, drift checks, fairness metrics, and scan checks:

```bash
econeval --config examples/advanced_model/econeval.yml --model examples/advanced_model/model.py --class AdvancedModel --report artifacts/advanced-report.md --format markdown
```

What the current runner expects:

- a model file that defines a class you can import by name
- a `predict(features)` method for stress tests, drift checks, and fairness checks
- CSV datasets with an `actual` column for stress tests
- CSV datasets with the feature or group columns required by the check

If your runtime looks different, use a thin adapter. EconEval now normalizes
common shapes like callable models, `solve()`-style solver wrappers, and
PyMC-style posterior predictive samplers so you can bridge external engines
without rewriting the check pipeline.

Example invariant rule:

```yaml
- name: elasticity_must_be_negative
  expression: model.elasticity < 0
```

If the expression returns `False`, the invariant fails.

The JSON report includes the project name, a summary count, and the result of each invariant, economic check, stress test, drift check, economic drift check, and fairness check.

## Expression Engine

EconEval uses a restricted AST-based expression engine for invariants.

That keeps the syntax simple for users while avoiding raw `eval()`. It is still a security-sensitive surface, so the allowed syntax is intentionally narrow:

- comparisons, boolean logic, simple arithmetic, and attribute access on the model object

It explicitly rejects function calls, subscripts, comprehensions, lambdas, dictionaries, sets, and private attributes such as `__class__`.

If you need a broader or more standardized expression engine later, the most likely replacement options are `asteval` or `numexpr`, depending on whether you need general Python-like rules or numeric-only expressions.

## Examples

- `examples/basic_model` shows the happy path with invariants, stress tests, drift checks, and fairness checks.
- `examples/broken_model` shows a model and dataset that fail the checks.
- `examples/drift_model` focuses on drift validation, including trend drift over time.
- `examples/fairness_model` focuses on fairness checks and a simple stress test.
- `examples/policy_model` is a minimal policy-focused fairness example.
- `examples/advanced_model` shows accounting identities, monotonicity, convergence, grid sweeps, and synthetic shocks.
- `examples/advanced_model` also shows synthetic manipulations, economic drift checks, and GitHub-friendly report output.
- `examples/advanced_model` now includes a native scan check for monotonicity and elasticity-style responses.
- `examples/demo_notebook.ipynb` is a short walkthrough you can open in Jupyter or VS Code.
- The repository examples are intended to double as a lightweight demo workflow.

## Roadmap

Planned or likely next steps for the project:

- expand stress testing with parameter shocks and Monte Carlo runs
- deepen drift detection over time with rolling windows and alerting
- add fairness and equity checks for policy-relevant models
- add deeper interop with tools like `pandas`, `statsmodels`, `PyMC`, `GAMS`, and Julia
- fairness and drift checks already accept pandas-like row data through `to_dict(orient="records")`
- install `econeval[stats]` if you want the optional `statsmodels`-based drift helper
- use `--format dashboard` for a richer HTML overview with filtering and collapsible drill-downs

## Release Flow

Publishing a GitHub Release triggers the release workflow in [`.github/workflows/release.yml`](.github/workflows/release.yml).

That workflow:

- installs the package
- runs the test suite
- runs EconEval against the example model
- uploads a release report artifact

## Next Step

The next useful additions are:

- a richer report viewer
- more scenario types

## Release Checklist

When you are ready to publish a new version:

1. run the test suite locally
2. update the package version if needed
3. tag the release, for example `v0.3.1`
4. publish the GitHub Release so the release workflow runs
5. confirm the release artifact uploaded from Actions
6. confirm the wheel and sdist were published to PyPI

To publish to PyPI through GitHub Actions, enable PyPI trusted publishing for this
repository and then publish the GitHub Release. The release workflow will build the
distribution and upload it automatically.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version-by-version changes.

## License

MIT
