/**
 * Type definitions for the M17 Network Audit panel (Phase 5b).
 *
 * These mirror the wire shapes emitted by
 * ``metis_app/api_litestar/routes/network_audit.py``. Keep field names,
 * nullability, and literal sets in sync with the Pydantic response
 * models in that module.
 *
 * See:
 * - ``metis_app/network_audit/events.py`` (NetworkAuditEvent dataclass)
 * - ``metis_app/network_audit/providers.py`` (provider registry,
 *   category union)
 * - ``plans/network-audit/plan.md`` (Phase 5b scope)
 */

/**
 * Interception source for a recorded audit event.
 *
 * - ``stdlib_urlopen`` — captured by the ``urllib`` wrapper (Phase 3).
 * - ``sdk_invocation`` — captured by the SDK factory wrappers (Phase 4).
 */
export type NetworkAuditSource = "stdlib_urlopen" | "sdk_invocation";

/**
 * One row from ``GET /v1/network-audit/events``.
 *
 * ``query_params_stored`` is a schema invariant: the audit store never
 * retains query-string contents (they routinely leak API keys / IDs).
 * The field exists purely so the panel can assert the invariant in its
 * UI copy.
 */
export interface NetworkAuditEvent {
  id: string;
  /** ISO-8601 timestamp (serialised from a ``datetime``). */
  timestamp: string;
  method: string;
  url_host: string;
  url_path_prefix: string;
  /** Hardcoded invariant — see module docstring. */
  query_params_stored: false;
  provider_key: string;
  trigger_feature: string;
  size_bytes_in: number | null;
  size_bytes_out: number | null;
  latency_ms: number | null;
  status_code: number | null;
  user_initiated: boolean;
  blocked: boolean;
  source: NetworkAuditSource;
}

/**
 * Broad grouping used by the provider matrix. Must stay in sync with
 * :data:`metis_app.network_audit.providers.ProviderCategory`.
 */
export type ProviderCategory =
  | "llm"
  | "embeddings"
  | "ingestion"
  | "search"
  | "model_hub"
  | "vector_db"
  | "fonts_cdn"
  | "other";

/** Human-readable label for a :type:`ProviderCategory`. */
export const PROVIDER_CATEGORY_LABELS: Record<ProviderCategory, string> = {
  llm: "LLM",
  embeddings: "Embeddings",
  ingestion: "Ingestion",
  search: "Search",
  model_hub: "Model hub",
  vector_db: "Vector DB",
  fonts_cdn: "Fonts CDN",
  other: "Other",
};

/** One row from ``GET /v1/network-audit/providers``. */
export interface NetworkAuditProvider {
  key: string;
  display_name: string;
  category: ProviderCategory;
  kill_switch_setting_key: string | null;
  blocked: boolean;
  events_7d: number;
  /** ISO-8601 timestamp of the newest call, or ``null`` if never called. */
  last_call_at: string | null;
}

/** Shape of ``GET /v1/network-audit/recent-count``. */
export interface RecentCountResponse {
  count: number;
  window_seconds: number;
}

/**
 * One frame from the ``/v1/network-audit/stream`` SSE endpoint.
 *
 * - ``audit_event`` — a new recorded event.
 * - ``no_store`` — the audit store is unavailable; the stream emits
 *   this once and closes. The panel should show a banner rather than
 *   silently dying.
 */
export type NetworkAuditStreamFrame =
  | { type: "audit_event"; event: NetworkAuditEvent }
  | { type: "no_store" };
