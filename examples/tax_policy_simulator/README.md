# Tax Policy Simulator

This example uses a small sample derived from the Adult Census Income dataset to
show a simple tax policy workflow.

## Policy Scenario

The model estimates a taxable income from a few income-related fields:

- `age`
- `education_num`
- `hours_per_week`
- `capital_gain`
- `capital_loss`
- `income_bracket`

It then applies a small progressive tax schedule to compute tax liability.

## What Can Go Wrong

- tax liability can go negative if deductions or credits are misapplied
- effective tax rates can drift above 1 if the policy is coded incorrectly
- a broken schedule can make higher incomes pay less than lower incomes

## What EconEval Validates

The bundled config checks that:

- tax liability stays non-negative
- effective tax rate stays between 0 and 1
- tax liability is monotonic in income
- the sample CSV still matches the model output closely

## How To Run

From the repository root:

```bash
econeval --config examples/tax_policy_simulator/econeval.yml --model examples/tax_policy_simulator/model.py --class TaxPolicyModel --report tax-policy-report.json
```

The sample file in `data/sample_income.csv` is intentionally small so it can run in CI.
