# Architecture Decision Records

This folder holds Architecture Decision Records (ADRs) for METIS. In this repo, an ADR is a short, iterative record of an architectural decision or a pending migration decision.

Keep ADRs short, decision-ready, and iterative. Start with a draft when the direction is still being shaped, then update the same record as the decision becomes clearer.

## Format

Each ADR should use this house format:

- `Title`
- `Status`
- `Date`
- `Context`
- `Proposed Direction` or `Decision`
- `Constraints`
- `Alternatives Considered`
- `Consequences`
- `Open Questions`

## Naming

- Use a four-digit numeric prefix, such as `0001`.
- Use kebab-case after the prefix.
- Keep one decision per file.

## Statuses

Use one of these statuses:

- `Draft`
- `Proposed`
- `Accepted`
- `Superseded`

## Index

- [0001-local-api-and-web-ui.md](0001-local-api-and-web-ui.md) - Superseded by 0004
- [0002-streaming-protocol.md](0002-streaming-protocol.md) - Superseded by 0004
- [0003-2026-tech-stack-review.md](0003-2026-tech-stack-review.md) - Superseded by 0004
- [0004-one-interface-tauri-next-fastapi.md](0004-one-interface-tauri-next-fastapi.md)
