## Task Statement

Implement the first Ladder-inspired improvement-pipeline slice inside METIS.

## Desired Outcome

Add a backend improvement artifact system that stores structured workflow entries and automatically captures:
- `source` artifacts from autonomous research runs
- `idea` artifacts from companion reflections

Expose the artifacts through API/orchestrator methods and cover the new behavior with tests.

## Known Facts / Evidence

- Ladder's main value is its typed artifact loop, not its code engine.
- METIS already has durable SQLite + markdown materialization patterns in Atlas.
- METIS already emits useful signals through companion reflection, autonomous research, trace storage, and behavior discovery.
- METIS already supports both FastAPI and Litestar routes and has strong API/service test coverage.

## Constraints

- No new dependencies.
- Reuse existing repository/orchestrator/API patterns where possible.
- Keep the first slice backend-focused and reviewable.
- Must preserve existing assistant/autonomous behavior while adding artifact capture.

## Unknowns / Open Questions

- Whether the first slice should also materialize improvement artifacts into the Brain graph now or later.
- Whether artifact creation should happen inside services directly or be coordinated from the orchestrator.

## Likely Codebase Touchpoints

- `metis_app/models/`
- `metis_app/services/assistant_companion.py`
- `metis_app/services/autonomous_research_service.py`
- `metis_app/services/workspace_orchestrator.py`
- `metis_app/api/`
- `metis_app/api_litestar/routes/`
- `tests/`
