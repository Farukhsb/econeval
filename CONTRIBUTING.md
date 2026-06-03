# Contributing to EconEval

Thanks for taking a look at the project.

## Setup

```bash
git clone https://github.com/Farukhsb/econeval.git
cd econeval
pip install -e .[dev]
```

## Development Workflow

1. Make your change.
2. Run the test suite:

```bash
pytest
```

3. Run linting if your change touches Python code:

```bash
ruff check .
```

## Project Conventions

- Keep runtime dependencies minimal.
- Prefer small, focused changes.
- Add or update tests for behavior changes.
- Update `README.md` when the public CLI, config format, or example usage changes.

## Release Notes

- The package version lives in `pyproject.toml`.
- GitHub Releases trigger the release workflow in `.github/workflows/release.yml`.
- If a release changes the public behavior, add an entry to `CHANGELOG.md`.
