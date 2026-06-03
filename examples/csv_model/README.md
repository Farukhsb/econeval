# CSV Model Example

This example shows the model-less CSV mode.

EconEval reads an input CSV and an output CSV, then checks whether each paired row satisfies the configured expression.

In this example:

- `input.csv` provides `price` and `quantity`
- `output.csv` provides `revenue`
- the check verifies `output.revenue == input.price * input.quantity`

The rows are matched by `id`.

