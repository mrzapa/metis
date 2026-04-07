# Test Spec: Improvement Pipeline

## Repository

- Can create and persist an improvement entry in memory-backed SQLite.
- Can list entries with type/status filters and newest-first ordering.
- Writes markdown output for saved entries.

## Orchestrator

- Captures an improvement `source` after a successful autonomous research run.
- Captures an improvement `idea` after a successful assistant reflection.
- Returns list/get payloads through orchestrator methods.

## API

- FastAPI list endpoint returns improvement artifacts.
- FastAPI get endpoint returns one artifact and 404 for missing ids.
- Litestar list endpoint returns the same shape.
- Litestar get endpoint returns 404 for missing ids.

## Regression

- Existing assistant reflection and autonomous research tests continue to pass.
- No regressions in Atlas routes.
