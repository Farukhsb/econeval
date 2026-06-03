# EconEval

EconEval is a small open-source framework for checking economic and policy models in CI.

It is built for the kind of code that can look fine at the syntax level and still be wrong in practice. A model can run, pass unit tests, and still break an economic rule, drift off course after a data change, or produce results that no longer make sense under stress. EconEval is meant to catch those problems early, before they reach a report, dashboard, or paper.

## What It Does

EconEval currently does three things:

- loads a model check config
- runs invariant tests against a Python object
- writes a JSON report that CI can keep or fail on

That gives you a practical starting point for:

- checking that important economic rules still hold
- making model assumptions explicit in code
- failing pull requests when a change breaks a rule you care about

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

fairness:
  enabled: true
  metrics:
    - demographic_parity_difference
    - disparate_impact_ratio
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
  examples/
    basic_model/
      model.py
      econeval.yml
  src/
    econeval/
      __init__.py
      config.py
      invariants.py
      scenarios.py
      reporting.py
  tests/
    test_config.py
    test_invariants.py
```

## Install

```bash
git clone https://github.com/Farukhsb/econeval.git
cd econeval
pip install -e .[dev]
```

`pytest` and `ruff` are included in the `dev` extra. If you only want the CLI, install the package without the extra.

## How To Use It

Create a config file that lists the checks you want to enforce, then point EconEval at a Python model class.

Command line example:

```bash
econeval --config examples/basic_model/econeval.yml --model examples/basic_model/model.py --class DemoModel --report econeval-report.json
```

If you prefer module execution, `python -m econeval` works the same way.

What the current runner expects:

- a model file that defines a class you can import by name
- a `predict(features)` method for stress tests, drift checks, and fairness checks
- CSV datasets with an `actual` column for stress tests
- CSV datasets with the feature or group columns required by the check

Example invariant rule:

```yaml
- name: elasticity_must_be_negative
  expression: model.elasticity < 0
```

If the expression returns `False`, the invariant fails.

The JSON report includes the project name, a summary count, and the result of each invariant, stress test, drift check, and fairness check.

## Next Step

The next useful additions are:

- a richer report viewer
- more scenario types
- a GitHub Action that runs the suite on every pull request

## License

MIT
