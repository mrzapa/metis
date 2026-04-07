# PRD: Improvement Pipeline

## Goal

Give METIS a durable, queryable improvement-pipeline backbone inspired by Ladder's workflow model, starting with the smallest useful vertical slice.

## Scope

This slice includes:
- a typed persistence model for improvement artifacts
- repository support with SQLite persistence and markdown materialization
- orchestrator methods for listing and retrieving artifacts
- automatic `source` capture from autonomous research results
- automatic `idea` capture from companion reflections
- FastAPI + Litestar API endpoints for listing and fetching artifacts

This slice does not include:
- Brain graph rendering of improvement artifacts
- full UI surfaces
- automatic hypothesis / experiment / result generation
- migration of Atlas entries into the new pipeline

## User Stories

### US-001 Persist Improvement Artifacts
As a METIS operator, I want structured improvement artifacts stored durably so the system's self-improvement loop is inspectable instead of implicit.

Acceptance criteria:
- Improvement entries can be saved and read back from SQLite.
- Entries materialize to markdown under a stable cache directory.
- Supported artifact types include `source`, `idea`, `hypothesis`, `experiment`, `algorithm`, and `result`.

### US-002 Capture Sources From Autonomous Research
As a user of autonomous research, I want each generated research star to leave behind a durable `source` artifact so its origin and evidence remain traceable.

Acceptance criteria:
- Successful autonomous research runs create a `source` artifact automatically.
- The stored artifact references the faculty, index id, and source URLs when available.

### US-003 Capture Ideas From Companion Reflection
As a user of the companion, I want meaningful reflections to become durable `idea` artifacts so promising next steps are not lost in memory alone.

Acceptance criteria:
- Successful reflections create an `idea` artifact automatically.
- The artifact keeps the trigger, session/run linkage, and concise summary.

### US-004 Query Artifacts Over API
As a developer or future UI surface, I want improvement artifacts exposed through the API so the new pipeline can be inspected programmatically.

Acceptance criteria:
- FastAPI and Litestar expose list and get endpoints.
- 404 behavior is consistent for missing entries.

## Design

- Reuse the Atlas repository style: dataclass model + SQLite table + markdown file export.
- Keep artifact creation coordinated from the orchestrator so assistant/autonomous services do not own cross-system persistence concerns.
- Use flexible metadata JSON rather than overfitting the first schema.

## Risks

- Overcoupling the first slice to current reflection/autonomous payloads.
- Creating a repository that is too Ladder-specific for METIS's architecture.

## Verification

- Repository unit tests
- Workspace orchestrator tests
- FastAPI + Litestar API tests
