from pathlib import Path

from econeval.config import load_config


def test_repo_scaffold_exists() -> None:
    assert Path("README.md").exists()
    assert Path("pyproject.toml").exists()
    assert Path(".pre-commit-config.yaml").exists()
    assert Path("action.yml").exists()
    assert Path("CHANGELOG.md").exists()
    assert Path("CONTRIBUTING.md").exists()
    assert Path("examples/fairness_model/README.md").exists()
    assert Path("examples/csv_model/README.md").exists()
    assert Path("examples/csv_model/econeval.yml").exists()
    assert Path("scripts/precommit_econeval.py").exists()


def test_load_config_reads_example_file() -> None:
    config = load_config("examples/basic_model/econeval.yml")

    assert config.project == "basic-model"
    assert config.version == 1
    assert len(config.invariants) == 1
    assert len(config.economic_checks) == 3
    assert len(config.stress_tests) == 2
    assert len(config.drift_tests) == 1
    assert len(config.economic_drift_tests) == 0
    assert config.invariants[0].name == "elasticity_must_be_negative"
    assert config.fairness.enabled is True
    assert config.fairness.dataset == "data/fairness.csv"


def test_load_config_reads_advanced_example_file() -> None:
    config = load_config("examples/advanced_model/econeval.yml")

    assert config.project == "advanced-model"
    assert len(config.invariants) == 2
    assert len(config.economic_checks) == 5
    assert len(config.stress_tests) == 6
    assert config.stress_tests[1].kind == "synthetic"
    assert config.stress_tests[2].kind == "parameter_shock"
    assert config.stress_tests[3].kind == "monte_carlo"
    assert config.stress_tests[4].kind == "grid"
    assert config.stress_tests[5].manipulations[0].variable == "input_data.unemployment_rate"
    assert len(config.economic_drift_tests) == 1


def test_load_config_reads_policy_example_file() -> None:
    config = load_config("examples/policy_model/econeval.yml")

    assert config.project == "policy-model"
    assert len(config.invariants) == 3
    assert len(config.stress_tests) == 1
    assert len(config.economic_checks) == 1
    assert config.fairness.enabled is True
    assert config.fairness.metrics == [
        "demographic_parity_difference",
        "gini",
        "equal_opportunity_difference",
    ]


def test_load_config_reads_drift_example_file() -> None:
    config = load_config("examples/drift_model/econeval.yml")

    assert config.project == "drift-model"
    assert len(config.drift_tests) == 4
    assert config.drift_tests[1].mode == "trend"
    assert config.drift_tests[1].time_column == "period"
    assert config.drift_tests[2].mode == "regression"
    assert config.drift_tests[3].statistic == "psi"


def test_load_config_reads_csv_example_file() -> None:
    config = load_config("examples/csv_model/econeval.yml")

    assert config.project == "csv-model"
    assert len(config.stress_tests) == 1
    relation = config.stress_tests[0]
    assert relation.kind == "relation"
    assert relation.input_dataset == "data/input.csv"
    assert relation.output_dataset == "data/output.csv"
    assert relation.join_key == "id"
    assert relation.expression == "output.revenue == input.price * input.quantity"


def test_load_config_reads_relation_example_file(tmp_path: Path) -> None:
    config_file = tmp_path / "econeval.yml"
    input_csv = tmp_path / "input.csv"
    output_csv = tmp_path / "output.csv"

    input_csv.write_text("id,price,quantity\n1,2,3\n2,4,5\n", encoding="utf-8")
    output_csv.write_text("id,revenue\n1,6\n2,20\n", encoding="utf-8")
    config_file.write_text(
        "\n".join(
            [
                "project: csv-model",
                "version: 1",
                "stress_tests:",
                "  - name: revenue_matches_input",
                "    kind: relation",
                "    input_dataset: input.csv",
                "    output_dataset: output.csv",
                "    join_key: id",
                "    expression: output.revenue == input.price * input.quantity",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(config_file)

    assert len(config.stress_tests) == 1
    relation = config.stress_tests[0]
    assert relation.kind == "relation"
    assert relation.input_dataset == "input.csv"
    assert relation.output_dataset == "output.csv"
    assert relation.join_key == "id"
    assert relation.expression == "output.revenue == input.price * input.quantity"
