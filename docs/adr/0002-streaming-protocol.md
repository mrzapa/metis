# 0002: Streaming Protocol

- `Status`: Draft
- `Date`: 2026-03-13

## Context

There is no external local API in Axiom today. Streaming behavior is internal to the current Python and PySide6 Qt MVC-backed runtime. If Axiom adds a local API plus a meta-framework web UI inside a desktop container, it will also need a framework-neutral streaming contract between the API and that UI.

This ADR is intentionally pre-decision. It defines the goal and evaluation criteria for streaming, not a final transport.

## Proposed Direction

Define a framework-neutral local API streaming contract that can carry incremental response updates, completion, and errors for a meta-framework UI while remaining suitable for local-first desktop use.

The contract should be evaluated on:

- Simplicity for a local API running inside a desktop container
- Compatibility with offline-capable operation
- Provider-agnostic event handling rather than provider-specific payloads
- Minimal vendor lock-in at the transport and framework layer

## Constraints

- Local-first
- Offline-capable
- Provider-agnostic
- Minimal vendor lock-in

## Alternatives Considered

- Keep Qt-only: avoids defining a new protocol, but does not support the target local API plus web UI direction.
- Pure web without desktop container: could simplify browser-oriented streaming choices, but weakens the intended desktop packaging model.
- Python-only UI via Reflex: may reduce protocol surface in the short term, but ties the UI direction to a Python-specific framework choice.
- Performance-first API variant using Litestar: may influence transport choices, but it is an API implementation preference rather than a settled streaming contract.

## Consequences

- Streaming will need a stable event model before multiple shells can share the same local API.
- The final transport should be selected only after the desktop container and UI integration constraints are clearer.
- Internal runtime streaming and external API streaming may need to coexist during migration.

## Open Questions

- What event shape is sufficient for tokens, status, citations, completion, and errors?
- Are reconnect or resume semantics required for a local desktop session, or is best-effort streaming enough for v1?
- Which streaming approach fits best with offline desktop packaging without adding avoidable complexity?
