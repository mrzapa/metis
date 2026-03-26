# Contributing

Thanks for contributing to METIS AI.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,api]"
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
python -m pytest --cov=metis_app --cov-report=xml --cov-report=term
```

## Developer check script

Use the helper scripts to run linting, the test suite, and a quick settings JSON validation from the repo root:

```bash
./scripts/dev_check.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev_check.ps1
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
