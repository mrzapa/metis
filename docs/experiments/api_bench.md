# Local API Benchmark Harness

- **Status**: Draft
- **Date**: 2026-03-15
- **Scope**: Reproducible local benchmark commands for the METIS FastAPI sidecar.
  Docs-only; no new endpoints or dependencies introduced.

## Overview

This guide gives you copy-pastable commands for `wrk` and `hey`, a results
capture template, and METIS-specific metric definitions. It is designed for
reproducibility on any developer machine, not universal thresholds — raw numbers
will vary with hardware.

**See also:** [Litestar API Experiment](litestar_api.md) — the companion note on
evaluating Litestar as a drop-in ASGI alternative; Stage 2 of that plan uses the
results captured here as its baseline.

---

## Prerequisites

### Install tools

**macOS (Homebrew)**

```bash
brew install wrk
brew install hey
```

**Linux (Debian/Ubuntu)**

```bash
# wrk — build from source or use the distro package
sudo apt-get install wrk          # available in Ubuntu 20.04+

# hey
go install github.com/rakyll/hey@latest
# or download the binary directly:
# https://github.com/rakyll/hey/releases
```

**Linux (Fedora/RHEL)**

```bash
# wrk
sudo dnf install wrk

# hey — use go install or the binary release above
```

### Start the API

```bash
# From the repo root
python -m metis_app.api
```

The server starts on a dynamic port and prints it to stdout, e.g.:

```
INFO:     Uvicorn running on http://127.0.0.1:8765 (Press CTRL+C to quit)
```

Export the port so you can paste the commands below unchanged:

```bash
export METIS_PORT=8765   # replace with the port printed above
```

---

## Benchmark Targets

### 1. Minimal-payload baseline — `GET /healthz`

**Why this endpoint:** Returns `{"ok": true}` with no dependency injection, no
database access, and no serialization beyond a single boolean. Measures raw
framework + uvicorn per-request overhead.

**wrk — 30 s, 4 threads, 50 connections**

```bash
wrk -t4 -c50 -d30s http://127.0.0.1:$METIS_PORT/healthz
```

**hey — 200 requests, 20 concurrent**

```bash
hey -n 200 -c 20 http://127.0.0.1:$METIS_PORT/healthz
```

**hey — sustained 10 s at 20 concurrent**

```bash
hey -z 10s -c 20 http://127.0.0.1:$METIS_PORT/healthz
```

---

### 2. Request-overhead baseline — `GET /v1/version`

**Why this endpoint:** One small dict lookup above the framework floor. The delta
between `/healthz` and `/v1/version` isolates the cost of one additional Python
function call and a slightly larger response body.

```bash
wrk -t4 -c50 -d30s http://127.0.0.1:$METIS_PORT/v1/version

hey -z 10s -c 20 http://127.0.0.1:$METIS_PORT/v1/version
```

---

### 3. Serialization overhead — `GET /v1/sessions`

**Why this endpoint:** Returns a Pydantic-validated list (empty on a fresh DB,
or populated from `rag_sessions.db`). The delta between `/v1/sessions` and
`/v1/version` isolates Pydantic v2 list serialization + SQLite read cost.

```bash
wrk -t4 -c50 -d30s http://127.0.0.1:$METIS_PORT/v1/sessions

hey -z 10s -c 20 http://127.0.0.1:$METIS_PORT/v1/sessions
```

> **Note:** Run this on both an empty `rag_sessions.db` and a seeded one (e.g.,
> after a few queries) to separate the fixed serialization cost from the
> per-row O(n) cost.

---

### 4. SSE stability — `POST /v1/query/rag/stream`

**Why this endpoint:** The highest-complexity surface. Measures time-to-first-token
(TTFT), frame rate under concurrent load, and connection drop rate. This is the
primary benchmark target referenced in the Litestar experiment's Stage 2 plan.

Neither `wrk` nor `hey` natively supports streaming SSE responses. Use one of the
following approaches:

#### Option A — curl timing loop (simplest, sequential)

```bash
# Measure wall-clock TTFT for a single request
# Replace the JSON body with a valid query for your local index.
time curl -s -N \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "index_name": "default", "session_id": null}' \
  http://127.0.0.1:$METIS_PORT/v1/query/rag/stream \
  | head -n 1
```

Run this in a loop to collect a sample:

```bash
for i in $(seq 1 20); do
  { time curl -s -N \
      -H "Content-Type: application/json" \
      -d '{"query": "test", "index_name": "default", "session_id": null}' \
      http://127.0.0.1:$METIS_PORT/v1/query/rag/stream \
      | head -n 1 ; } 2>&1 | grep real
done
```

#### Option B — wrk with a Lua script (concurrent load)

Save the following as `bench/rag_stream.lua`:

```lua
-- bench/rag_stream.lua
wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.body = '{"query":"test","index_name":"default","session_id":null}'
```

```bash
wrk -t2 -c10 -d30s -s bench/rag_stream.lua \
  http://127.0.0.1:$METIS_PORT/v1/query/rag/stream
```

> **Interpreting wrk SSE results:** `wrk` closes the connection as soon as the
> response body is fully read. For a streaming endpoint this means it measures
> total stream duration, not TTFT. Use Option A (curl loop) for TTFT, and Option B
> for aggregate throughput and connection stability under concurrency.

#### SSE drop-rate check

Count streams that return at least one `token` event vs. streams that close early
or return a non-200 status. A drop rate above 0 % in a local, unloaded environment
indicates a buffering or error-handling regression.

```bash
DROPS=0; TOTAL=20
for i in $(seq 1 $TOTAL); do
  GOT=$(curl -s -N \
        -H "Content-Type: application/json" \
        -d '{"query":"test","index_name":"default","session_id":null}' \
        http://127.0.0.1:$METIS_PORT/v1/query/rag/stream \
        | grep -c "event: token" || true)
  [ "$GOT" -eq 0 ] && DROPS=$((DROPS+1))
done
echo "Drop rate: $DROPS / $TOTAL"
```

---

## Results Template

Copy this table into your notes or a `docs/experiments/results/` file after each
benchmark run. Fill in one row per endpoint per tool.

```markdown
## Benchmark Run — YYYY-MM-DD

**Machine:** <!-- e.g. MacBook Pro M3, 16 GB RAM -->
**OS:** <!-- e.g. macOS 15.3 / Ubuntu 24.04 -->
**Python:** <!-- python --version -->
**METIS commit:** <!-- git rev-parse --short HEAD -->
**Uvicorn workers:** <!-- default: 1 -->

| Endpoint | Tool | Requests | Concurrency | RPS | p50 ms | p90 ms | p99 ms | Errors |
|---|---|---|---|---|---|---|---|---|
| GET /healthz | wrk | — | 50 | | | | | |
| GET /healthz | hey | 200 | 20 | | | | | |
| GET /v1/version | wrk | — | 50 | | | | | |
| GET /v1/sessions (empty DB) | wrk | — | 50 | | | | | |
| GET /v1/sessions (seeded DB) | wrk | — | 50 | | | | | |
| POST /v1/query/rag/stream | curl loop | 20 | 1 | — | TTFT p50 | TTFT p90 | TTFT p99 | drop rate |
| POST /v1/query/rag/stream | wrk+lua | — | 10 | | | | | |
```

---

## METIS-Specific Metric Definitions

### SSE Stability

The fraction of streaming requests that deliver at least one `token` event before
closing. Measured as `1 - (drop_count / total_requests)`. A value below 100 % in
a local, single-client environment is a regression signal.

**What breaks it:** buffering the full stream before flushing (breaks TTFT
and stability simultaneously), uncaught exceptions inside the generator,
or connection timeouts from the client side when the generator stalls.

### Request Overhead

The per-request latency floor attributable to the framework, uvicorn, and Python
function-call stack, independent of business logic.

**Measured as:** p50 RTT for `GET /healthz` (zero business logic, zero
serialization beyond `{"ok": true}`).

**Delta signal:** `p50(/v1/version) − p50(/healthz)` isolates one additional
function call. `p50(/v1/sessions, empty) − p50(/healthz)` isolates the
dependency-injection + SQLite cost. Keep these deltas under 5 ms each in a local,
unloaded environment.

### Serialization Overhead

The cost of Pydantic v2 model validation and JSON serialization for a realistic
response body.

**Measured as:** `p50(/v1/sessions, N rows) − p50(/v1/sessions, empty)`. Divide
by N to get per-row serialization cost. The sessions list endpoint was chosen
because its response schema is representative of the broader API surface (nested
Pydantic models, datetime fields, optional fields).

---

## Interpreting Results

### Hardware variance

Raw RPS and latency numbers are not universally comparable. When sharing results,
always include the machine spec row from the template above. The useful signal is
the **delta between endpoints on the same machine**, not the absolute values.

### Regression threshold (local baseline)

There is no universal RPS target. Instead, track regressions against your own
baseline:

- Establish a baseline on a quiet machine (no background load).
- Flag any run where `p99(/healthz)` increases by more than **2×** relative to
  the baseline as a potential framework or uvicorn configuration regression.
- Flag any SSE drop rate above **0 %** on a local, single-client run as a
  streaming correctness regression.

### Using results with the Litestar experiment

The [Litestar API Experiment](litestar_api.md) Stage 2 plan defines explicit
regression thresholds relative to the FastAPI baseline:

| Metric | Threshold |
|---|---|
| TTFT p95 on `/v1/query/rag/stream` | ≤ FastAPI baseline + 50 ms |
| Non-streaming RTT p95 on `/v1/query/rag` | ≤ FastAPI baseline + 20 ms |
| Session list RTT p95 on `GET /v1/sessions` | ≤ FastAPI baseline + 5 ms |

Capture a FastAPI baseline run using the commands in this guide before running
Stage 2 of the Litestar evaluation.

---

## Quick-start Checklist

```
[ ] python -m metis_app.api is running; note the port
[ ] export METIS_PORT=<port>
[ ] wrk and hey are installed
[ ] Run GET /healthz with wrk and hey; record results
[ ] Run GET /v1/version with wrk; record the delta vs /healthz
[ ] Run GET /v1/sessions (empty DB) with wrk; record the DI+SQLite delta
[ ] Run POST /v1/query/rag/stream curl loop; record TTFT sample
[ ] Run POST /v1/query/rag/stream SSE drop-rate check; expect 0 drops
[ ] Fill in the results template above and save to docs/experiments/results/
```
