# Fairness Model Example

This example shows the full dataset shape expected by EconEval fairness checks.

## Dataset Schema

`examples/fairness_model/data/fairness.csv` uses these columns:

- `group`: the protected or comparison group label
- `signal`: the feature passed into `model.predict(...)`
- `actual`: the observed label used by label-based fairness metrics

Example rows:

```text
actual,signal,group
1.0,0.4,A
1.2,0.6,A
1.4,0.4,B
1.6,0.6,B
```

## How EconEval Interprets The Columns

- `group` defines the cohort split.
- Every column except `group` and `actual` is passed to `predict(features)`.
- `actual` is used when a metric needs labels, such as `equal_opportunity_difference` or `equalized_odds_difference`.
- `positive_threshold` controls which prediction scores count as positive.
- `actual_threshold` controls which observed labels count as positive.

## Thresholds In This Example

The bundled config in `econeval.yml` uses:

- `positive_threshold: 1.5`
- `actual_threshold: 1.0`
- `demographic_parity_difference`
- `disparate_impact_ratio`
- `equal_opportunity_difference`
- `equalized_odds_difference`

## How The Metrics Are Read

- `demographic_parity_difference` compares positive prediction rates between groups: `max(rate) - min(rate)`.
- `disparate_impact_ratio` compares the lowest positive rate to the highest positive rate: `min(rate) / max(rate)`.
- `equal_opportunity_difference` compares true positive rates between groups.
- `equalized_odds_difference` compares both true positive rates and false positive rates between groups.

In this example, a prediction is counted as positive when it is at or above `positive_threshold`, and an observed label is counted as positive when it is at or above `actual_threshold`.

The example is intentionally balanced so the fairness checks pass while still showing the full schema used by the fairness engine.
