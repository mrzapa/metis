---
id: agent-native-bridge
name: Agent-Native Bridge
description: Enables the METIS agentic loop to persist and read ephemeral state via the application_state KV store and emit structured action payloads.
enabled_by_default: false
priority: 80
triggers:
  keywords:
    - app state
    - agent state
    - poll
    - structured action
    - writeAppState
    - sendToAgentChat
  modes:
    - Research
  file_types: []
  output_styles: []
runtime_overrides:
  agentic_mode: true
---
Use this skill when the agentic loop (Research mode) needs to persist intermediate state across iterations, emit structured action payloads to the chat bridge, or signal the frontend via the polling endpoint.

## Overview

METIS follows a six-rule agent-native philosophy:

1. **State is explicit** — intermediate values must be written to the KV store; they cannot live only in memory.
2. **Reads confirm writes** — always read back a key after writing to verify round-trip success.
3. **Actions are structured** — any action sent to the chat surface must follow the `ActionPayload` wire format.
4. **Iterations are versioned** — the `version` counter on the KV store is the single source of truth for change detection.
5. **Session scope is absolute** — a key written for `session_id=X` is invisible to `session_id=Y`; never cross-reference.
6. **Values are escaped before render** — string values written by the agent must be treated as untrusted on the frontend.

## writeAppState

Use `POST /v1/app-state/{session_id}/{key}` to persist a value for the current session.

**curl example:**
```bash
curl -s -X POST http://localhost:8000/v1/app-state/sess-abc123/current_iteration \
  -H "Content-Type: application/json" \
  -d '{"value": "2"}'
```

**Python example (inside agentic loop):**
```python
import httpx

BASE = "http://localhost:8000"

def write_app_state(session_id: str, key: str, value: str) -> int:
    resp = httpx.post(
        f"{BASE}/v1/app-state/{session_id}/{key}",
        json={"value": value},
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()["version"]
```

Call this at the **start of each agentic iteration** to checkpoint progress:
```python
version = write_app_state(session_id, "iteration_summary", brief_summary)
write_app_state(session_id, "sub_query_count", str(len(sub_queries)))
```

## readAppState

Use `GET /v1/app-state/{session_id}` to list all keys for the session, or `GET /v1/app-state/{session_id}/{key}` to fetch a single key.

**List all state:**
```bash
curl -s http://localhost:8000/v1/app-state/sess-abc123
```

Returns a JSON array:
```json
[
  {"key": "current_iteration", "value": "2", "version": 3, "updated_at": "2026-04-02T10:00:00Z"},
  {"key": "iteration_summary", "value": "Found 4 relevant sources", "version": 4, "updated_at": "2026-04-02T10:00:01Z"}
]
```

**Python example (read between iterations):**
```python
def read_app_state(session_id: str, key: str) -> str | None:
    resp = httpx.get(f"{BASE}/v1/app-state/{session_id}/{key}", timeout=5)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()["value"]

prev_summary = read_app_state(session_id, "iteration_summary")
```

## Structured Actions

To emit an action to the chat surface, format the message body as an `ActionPayload`-compatible block. The agent must include this block as the **first content** in its response so the bridge can parse it before rendering.

Wire format:
```
[AGENT ACTION: {action_type}]
{payload JSON}

{original prompt or synthesised answer}
```

**Supported action types:**

| action_type | Purpose |
|---|---|
| `SEARCH` | Trigger a document search from the frontend |
| `SUMMARISE` | Request an inline summarisation pass |
| `CITE` | Attach a source citation block |
| `REDIRECT` | Navigate the user to a different view |

**Example — emitting a CITE action:**
```
[AGENT ACTION: CITE]
{"source": "arxiv:2401.00001", "excerpt": "LLMs can self-improve via iterative refinement.", "score": 0.91}

Based on the evidence above, the key finding is...
```

The chat bridge reads the `[AGENT ACTION: ...]` header, parses the JSON on the next line, strips both from the visible transcript, and dispatches the action to the appropriate frontend handler.

## Polling

The frontend detects agent state changes by polling `GET /v1/poll?since=<version>`.

**Response when new state exists:**
```json
{"version": 7, "changed": true}
```

**Response when nothing has changed:**
```json
{"version": 7, "changed": false}
```

The `version` value is the global monotonic counter from the KV store. Pass the last known version as `since` to receive only changes newer than that point.

**Python polling helper (for integration tests or agent self-checks):**
```python
import time

def wait_for_update(session_id: str, since: int, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = httpx.get(f"{BASE}/v1/poll", params={"since": since}, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data["changed"]:
            return data
        time.sleep(0.5)
    raise TimeoutError(f"No state update after {timeout}s (since version {since})")
```

The frontend poll hook runs on a 2 s interval in Research mode and automatically invalidates the relevant React Query cache keys when `changed` is `true`.

## Security

- **Session-scoped access only.** Every read and write enforces `session_id` boundary checks on the server. In single-user local mode, session_id scoping is enforced structurally via the URL path parameter. Multi-user deployments should add ownership validation at the route layer.
- **Never cross-session reads.** The agentic loop must never construct a key path with an external or user-supplied `session_id`. Always derive `session_id` from the current request context.
- **Escape values before render.** Values stored in the KV are arbitrary strings. The frontend must HTML-escape all values retrieved from `GET /v1/app-state/...` before injecting them into the DOM. Do not use `dangerouslySetInnerHTML` with raw KV values.
- **Validate action payload JSON.** Parse the `ActionPayload` block with a strict schema validator before dispatching. Reject malformed or oversized payloads (max 4 KB per payload block).
- **No secrets in state.** Do not write API tokens, passwords, or PII to the KV store. The store is ephemeral but may appear in logs.
