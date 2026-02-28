# Contributing

Thanks for contributing to Axiom.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
```

## Code style

- Run linting before opening a PR: `ruff check .`
- Keep changes focused and avoid unrelated refactors in the same PR.
- Prefer small, composable functions and clear names over clever shortcuts.

## Commit message guideline

Use concise, imperative commit messages (e.g., `Add CLI smoke test in CI`).

## Running tests locally

```bash
python -m pytest
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term
```

## Pull requests

- Keep PRs focused and small when possible.
- Include tests for behavior changes.
- Update docs (`README.md`, inline docstrings) when user-visible behavior changes.
- Ensure CI passes before requesting review.

## Code of Conduct

Please follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Issues

Please include:

- Reproduction steps
- Expected behavior
- Actual behavior
- Environment details (OS, Python version)
