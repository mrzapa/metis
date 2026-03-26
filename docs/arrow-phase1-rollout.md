# Arrow Phase 1 and Phase 2 Rollout and Decision Gates

Last updated: 2026-03-23
Owner: Chat + Runtime team
Scope: Phase 1 boundary safety + Phase 2 runtime subset rendering

## Implementation status (current)

This document has two concerns:
- Sections 1-10 define rollout policy, thresholds, and operator process.
- This section and the implementation references capture current integration details.

Current direct integration status in apps/metis-web:
- Direct integration is implemented with Standard Agents Arrow scoped packages: `@arrow-js/core` and `@arrow-js/sandbox`.
- Runtime integration for allowlisted artifact rendering lives in `apps/metis-web/components/chat/artifacts/artifact-message-content.tsx` (Arrow template rendering and sandbox execution path).
- Chat boundary wiring for runtime attempts and fallback behavior lives in `apps/metis-web/components/chat/artifacts/arrow-artifact-boundary.tsx` and `apps/metis-web/components/chat/chat-panel.tsx`.
- Next.js must transpile Arrow packages because sandbox exports include source TypeScript; this is configured via `transpilePackages` in `apps/metis-web/next.config.ts`.

## 1) Phase 1 feature scope (historical baseline)

Phase 1 delivered safe rendering of Arrow artifacts inside chat responses without runtime Arrow rendering. The runtime subset described in Section 1b is now directly integrated and controlled by feature flags.

Included:
- Artifact extraction and normalization on backend and frontend, capped to 5 artifacts per message.
- Boundary-based UI rendering that falls back to markdown for all unsafe or unsupported cases.
- Error boundary containment so renderer failures do not break message rendering.
- Best-effort telemetry emission from UI and strict telemetry schema validation in API.
- Metadata-only persistence of artifacts in traces and stream replay storage.

Not included:
- True Arrow runtime renderer execution pipeline.
- Runtime dependency loading, execution sandboxing, or Arrow compute kernels in frontend.
- New artifact authoring flow.

## 1b) Phase 2 runtime feature scope

Phase 2 adds a narrow runtime renderer for allowlisted artifact types while retaining per-artifact and boundary-level fallback safety.

Included:
- Runtime rendering for allowlisted types only (`timeline`, `metric_cards`) under strict payload assumptions.
- Per-artifact runtime lifecycle telemetry (`artifact_runtime_attempt`, `artifact_runtime_success`, `artifact_runtime_failure`, `artifact_runtime_skipped`).
- Dual-flag control:
  - `enable_arrow_artifacts` gates all artifact rendering.
  - `enable_arrow_artifact_runtime` gates runtime attempts while preserving fallback cards.
- Per-artifact fallback when runtime fails for one artifact while other artifacts continue rendering.

Not included:
- Arbitrary artifact execution.
- Dynamic code evaluation or plugin execution paths.
- Runtime support for non-allowlisted artifact types.

## 2) Feature flags and safe defaults

Primary flag:
- Setting key: enable_arrow_artifacts
- Safe default: false

Runtime kill switch:
- Setting key: enable_arrow_artifact_runtime
- Safe default: true

Current behavior:
- If enable_arrow_artifacts is false, backend does not emit artifacts in final stream event.
- UI boundary treats artifactsEnabled false as a hard markdown fallback.
- If enable_arrow_artifacts is true and enable_arrow_artifact_runtime is false, UI renders artifact cards/fallback only and skips runtime attempts.
- UI boundary also falls back for no artifacts, invalid payload, and renderer exceptions.
- Telemetry is best-effort and must never block rendering.

Kill switch guidance:
- Immediate global disable: set enable_arrow_artifacts=false in settings and publish through existing settings update path.
- Emergency hard stop target: return to markdown-only path by forcing artifactsEnabled=false in chat UI state if needed.

## 3) Required telemetry events and dashboard metrics

Required events (all must be present in ingestion data):
- artifact_boundary_flag_state
- artifact_payload_detected
- artifact_render_attempt
- artifact_render_success
- artifact_render_failure
- artifact_render_fallback_markdown
- artifact_interaction
- artifact_runtime_attempt
- artifact_runtime_success
- artifact_runtime_failure
- artifact_runtime_skipped

Required metric definitions:
- Exposure count: count of artifact_payload_detected where has_valid_artifacts=true.
- Render attempt count: count of artifact_render_attempt.
- Render success rate: artifact_render_success / artifact_render_attempt.
- Render failure rate: artifact_render_failure / artifact_render_attempt.
- Fallback rate by reason:
  - feature_disabled
  - no_artifacts
  - invalid_payload
  - render_error
- Interaction rate (engagement): artifact_interaction / artifact_render_success.
- Runtime attempt rate among eligible artifacts:
  - artifact_runtime_attempt / artifact_payload_detected where has_valid_artifacts=true.
- Runtime success rate:
  - artifact_runtime_success / artifact_runtime_attempt.
- Runtime failure rate:
  - artifact_runtime_failure / artifact_runtime_attempt.
- Runtime skip mix:
  - count by reason in artifact_runtime_skipped (`runtime_disabled`, `unsupported_type`, `payload_truncated`, `invalid_payload`).
- End-to-end fallback rate among valid payloads:
  - count of fallback_markdown where reason in invalid_payload, render_error
  - divided by artifact_payload_detected with has_valid_artifacts=true.
- Telemetry acceptance rate: accepted events / submitted events at UI telemetry endpoint.

Dashboard windows:
- Daily rollup (24h) for alerting.
- 7-day rolling for go/no-go decisions.

Minimum sample sizes before decisions:
- Internal stage: at least 300 valid artifact exposures.
- Beta stage: at least 1,000 valid artifact exposures.
- Percentage rollout stages: at least 2,000 valid artifact exposures per stage before advancing.

## 4) Baseline vs experiment comparison method

Population split:
- Baseline cohort: markdown-only path (flag disabled).
- Experiment cohort: artifact boundary rendering enabled.

Comparison window:
- Fixed 7-day window after each stage reaches minimum sample size.

Primary comparison metrics:
- Reliability delta:
  - Experiment render success rate versus baseline equivalent stability proxy (no assistant-message render interruption incidents).
- Performance delta:
  - Client p95 message render time for assistant messages with artifacts versus markdown-only messages of similar token length bucket.
- Engagement delta:
  - Interaction rate in experiment versus baseline proxy (copy action or source-click rate) for comparable sessions.

Method rules:
- Bucket by streaming state (is_streaming true/false).
- Exclude runs with missing run_id from denominator-based metrics.
- Use absolute deltas and relative deltas; require both to pass go criteria.

## 5) Explicit success thresholds for expansion (go)

All thresholds below must pass for 7 consecutive days at current stage:

Reliability:
- Render success rate >= 99.5%.
- Render failure rate <= 0.3%.
- Fallback due to render_error <= 0.2% of valid artifact payloads.
- Invalid payload fallback <= 1.0% of artifact payload detections.

Performance:
- p95 assistant message render latency regression <= +50 ms versus baseline bucket.
- p99 assistant message render latency regression <= +100 ms versus baseline bucket.
- No sustained increase in client error logs attributable to artifact boundary over 0.2 percentage points.

Engagement:
- Artifact interaction rate >= 8% of successful renders.
- No statistically meaningful drop (>2.0 percentage points absolute) in downstream session completion rate versus baseline.

Data quality:
- Telemetry acceptance rate >= 99.0%.
- At least 95% of artifact events include run_id and source=chat_artifact_boundary.

Phase 2 runtime-specific go thresholds (7-day window):
- Runtime success rate >= 99.0%.
- Runtime failure rate <= 0.5% of runtime attempts.
- Runtime skip reason `invalid_payload` <= 2.0% of detected artifact payloads.
- Runtime skip reason `payload_truncated` <= 5.0% of detected artifact payloads.
- Runtime-disabled skips are expected and excluded from reliability denominators.

## 6) Explicit rollback thresholds (no-go)

Trigger immediate rollback (disable enable_arrow_artifacts) if any condition holds in a 24h window:
- Render success rate < 98.5%.
- Render failure rate > 1.0%.
- Render_error fallback > 0.5% of valid artifact payloads.
- Invalid payload fallback > 3.0% of detections.
- p95 render latency regression > +120 ms versus baseline.
- Telemetry acceptance rate < 95.0%.
- Any auth-related failure blocks telemetry for authenticated deployments for more than 30 minutes.
- Any user-visible incident where assistant message content is not rendered and fallback does not recover.

Trigger immediate runtime rollback (set enable_arrow_artifact_runtime=false, keep artifacts enabled) if either condition holds in a 24h window:
- Runtime failure rate > 1.0% of runtime attempts.
- Runtime success rate < 98.0%.

Hold (no advance, no rollback) if metrics are between go and rollback bands.

## 7) Rollout stages

Stage 0: Internal only
- Audience: team members, dogfood sessions.
- Duration: minimum 3 days and 300 valid exposures.
- Exit criteria: meet go thresholds.

Stage 1: Beta opt-in
- Audience: users with explicit opt-in setting.
- Suggested exposure: ~10% of active chat users.
- Duration: minimum 7 days and 1,000 valid exposures.
- Exit criteria: meet go thresholds.

Stage 2: Percentage rollout
- Step A: 25% for minimum 7 days and 2,000 valid exposures.
- Step B: 50% for minimum 7 days and 2,000 valid exposures.
- Step C: 100% when prior steps pass and no Sev-1 or Sev-2 incidents in prior 14 days.

Gate rule:
- Do not advance more than one stage per 7 days.

## 8) Incident handling runbook

Detection:
- Monitor daily dashboard and alert on rollback thresholds.
- Watch for spikes in artifact_render_failure and artifact_render_fallback_markdown reason=render_error.

Immediate actions (first 15 minutes):
1. Flip kill switch: set enable_arrow_artifacts=false.
2. Confirm markdown fallback behavior in chat responses.
3. Validate API health and telemetry endpoint auth path.

Triage (first 60 minutes):
1. Pull recent trace events for affected run_id values.
2. Segment failures by renderer kind (default/custom), streaming mode, and artifact type.
3. Confirm whether failure is payload quality, renderer defect, or telemetry delivery/auth issue.

Recovery:
- Keep feature disabled until two consecutive 24h windows pass all reliability thresholds in internal stage.
- Ship fix, then restart from Stage 0.

Communication:
- Log incident summary including trigger metric, affected window, mitigation time, and root cause category.

## 9) Next-step criteria after Phase 2 runtime launch

Do not expand runtime type support until all are true:
- Phase 1 runs at 100% for at least 14 days.
- Reliability thresholds met each day in that 14-day window.
- Render_error fallback <= 0.1% of valid payloads for last 7 days.
- Interaction rate does not regress for 14 days.
- No open Sev-1 or Sev-2 artifact incidents.

Readiness checklist for expanding beyond the Phase 2 subset:
- Define additional payload schemas per new artifact type before enabling runtime.
- Keep per-artifact execution guardrails (count limits, truncation behavior, and fallback cards).
- Add benchmark coverage for each newly supported type before rollout.
- Validate telemetry acceptance and auth paths before percentage increases.

## 10) Rollout decision API and operator workflow

Summary endpoint:
- Route: `GET /v1/telemetry/ui/summary`
- Query params:
  - `window_hours` (optional, default `24`, positive integer)
  - `limit` (optional, default `50000`, positive integer scan cap)
- Auth: same as all protected API routes; requires `Authorization: Bearer <METIS_API_TOKEN>` when token auth is configured.

Response shape (high level):
- `window_hours`, `generated_at`, `sampled_event_count`
- `metrics`:
  - `exposure_count`, `render_attempt_count`
  - `render_success_rate`, `render_failure_rate`
  - `fallback_rate_by_reason`
  - `interaction_rate`
  - `runtime_attempt_rate`, `runtime_success_rate`, `runtime_failure_rate`
  - `runtime_skip_mix`
  - `data_quality` (`events_with_run_id_pct`, `events_with_source_boundary_pct`, `events_with_client_timestamp_pct`)
- `thresholds`:
  - `per_metric` statuses (`pass|warn|fail`)
  - `overall_recommendation` (`go|hold|rollback_runtime|rollback_artifacts`)
  - `failed_conditions`
  - `sample` counts used for decision context

Example checks:

```bash
# 24h alerting window
curl -s "http://localhost:8000/v1/telemetry/ui/summary?window_hours=24" \
  -H "Authorization: Bearer $METIS_API_TOKEN"

# 7-day decision window
curl -s "http://localhost:8000/v1/telemetry/ui/summary?window_hours=168" \
  -H "Authorization: Bearer $METIS_API_TOKEN"
```

Operator workflow:
1. Check 24h summary first.
2. Open the Diagnostics page and review the Arrow rollout console, which shows both the 24h and 168h windows plus the current `enable_arrow_artifacts` and `enable_arrow_artifact_runtime` values.
3. If the 24h recommendation is `rollback_artifacts`, use the in-product rollback action to set `enable_arrow_artifacts=false`.
4. If the 24h recommendation is `rollback_runtime`, use the in-product rollback action to set `enable_arrow_artifact_runtime=false` while keeping artifacts enabled.
5. If recommendation is `hold`, keep the current stage and re-check daily.
6. Only consider stage advance when the 7-day (`window_hours=168`) recommendation is `go` and the console shows minimum exposure counts are satisfied.
7. Record `failed_conditions` and `sample` counts in rollout notes for every decision.

Diagnostics console notes:
- The 24h and 168h summary cards fail independently so one summary outage does not block the rest of diagnostics.
- Rollback actions require confirmation before applying settings changes.
- After a rollback action succeeds, the console refreshes settings and both summary windows automatically.

## Relevant implementation references

- Frontend package declarations for direct Arrow integration: apps/metis-web/package.json (`@arrow-js/core`, `@arrow-js/sandbox`)
- Next.js transpile configuration for Arrow packages: apps/metis-web/next.config.ts (`transpilePackages`)
- Frontend boundary and fallback logic: apps/metis-web/components/chat/artifacts/arrow-artifact-boundary.tsx
- Frontend runtime renderer + sandbox execution path: apps/metis-web/components/chat/artifacts/artifact-message-content.tsx
- Frontend artifact extraction cap and validation: apps/metis-web/lib/artifacts/extract-arrow-artifacts.ts
- Frontend telemetry event construction and best-effort delivery: apps/metis-web/lib/telemetry/ui-telemetry.ts
- Chat wiring of artifactsEnabled into boundary: apps/metis-web/components/chat/chat-panel.tsx
- Chat setting resolution for enable_arrow_artifacts: apps/metis-web/app/chat/page.tsx
- API UI telemetry endpoint and request-size/auth handling: metis_app/api/app.py
- Telemetry schema validation and allowed event contracts: metis_app/api/models.py
- Safe default setting for feature flag: metis_app/default_settings.json
- Backend artifact extraction and flag behavior: metis_app/engine/querying.py
- Metadata-only artifact persistence in replay and trace paths: metis_app/services/stream_replay.py, metis_app/services/workspace_orchestrator.py
- Coverage tests for boundary and extraction: apps/metis-web/components/chat/artifacts/__tests__/arrow-artifact-boundary.test.tsx, apps/metis-web/lib/artifacts/__tests__/extract-arrow-artifacts.test.ts
- Coverage tests for telemetry endpoint auth and validation: tests/test_api_app.py
- Coverage tests for stream artifact persistence behavior: tests/test_stream_replay.py, tests/test_engine_streaming.py
