from pathlib import Path

from econeval.config import load_config


def test_repo_scaffold_exists() -> None:
    assert Path("README.md").exists()
    assert Path("pyproject.toml").exists()


def test_load_config_reads_example_file() -> None:
    config = load_config("examples/basic_model/econeval.yml")

    assert config.project == "basic-model"
    assert config.version == 1
    assert len(config.invariants) == 1
    assert config.invariants[0].name == "elasticity_must_be_negative"
    assert config.fairness.enabled is False

