"use client";

import { useEffect, useState } from "react";
import { fetchAssistantStatus } from "@/lib/api";
import type { AssistantSnapshot, AssistantStatus } from "@/lib/api";
import { HudPanel } from "../HudPanel";
import { Loader2 } from "lucide-react";

interface HealthPanelProps {
  snapshot: AssistantSnapshot | null;
}

export function HealthPanel({ snapshot }: HealthPanelProps) {
  const [status, setStatus] = useState<AssistantStatus | null>(snapshot?.status ?? null);
  const [loading, setLoading] = useState(!snapshot?.status);

  useEffect(() => {
    if (snapshot?.status) {
      setStatus(snapshot.status);
      setLoading(false);
      return;
    }
    fetchAssistantStatus()
      .then(setStatus)
      .catch(() => setStatus(null))
      .finally(() => setLoading(false));
  }, [snapshot]);

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {/* Runtime status */}
      <HudPanel title="What I See — Runtime">
        {loading ? (
          <div className="flex items-center gap-2" style={{ color: "var(--hud-text-dim)" }}>
            <Loader2 className="size-3.5 animate-spin" />
            <span className="text-[12px]">Loading…</span>
          </div>
        ) : !status ? (
          <p className="text-[12px]" style={{ color: "var(--hud-error)" }}>
            Unable to fetch status
          </p>
        ) : (
          <div className="space-y-2.5">
            <StatusRow
              label="Companion"
              value={status.state || "unknown"}
              ok={status.state === "idle" || status.state === "active"}
            />
            <StatusRow
              label="Runtime ready"
              value={status.runtime_ready ? "ready" : "not ready"}
              ok={status.runtime_ready}
            />
            <StatusRow
              label="Runtime source"
              value={status.runtime_source || "—"}
              ok={!!status.runtime_source}
            />
            <StatusRow
              label="Paused"
              value={status.paused ? "yes" : "no"}
              ok={!status.paused}
              invertOk
            />
            <StatusRow
              label="Bootstrap"
              value={status.bootstrap_state || "—"}
              ok={status.bootstrap_state === "complete" || status.bootstrap_state === "none"}
            />
          </div>
        )}
      </HudPanel>

      {/* Configuration */}
      <HudPanel title="Configuration">
        <div className="space-y-2.5">
          {snapshot?.runtime && (
            <>
              <ConfigRow label="Provider" value={snapshot.runtime.provider || "—"} />
              <ConfigRow label="Model" value={snapshot.runtime.model || "—"} />
              {snapshot.runtime.local_gguf_model_path && (
                <ConfigRow
                  label="GGUF model"
                  value={snapshot.runtime.local_gguf_model_path.split("/").pop() ?? "—"}
                />
              )}
              {snapshot.runtime.local_gguf_context_length > 0 && (
                <ConfigRow
                  label="Context length"
                  value={`${snapshot.runtime.local_gguf_context_length.toLocaleString()} tokens`}
                />
              )}
            </>
          )}
          {snapshot?.policy && (
            <>
              <div className="border-t pt-2" style={{ borderColor: "var(--hud-border)" }}>
                <ConfigRow
                  label="Reflection backend"
                  value={snapshot.policy.reflection_backend || "—"}
                />
                <ConfigRow
                  label="Reflection cooldown"
                  value={`${snapshot.policy.reflection_cooldown_seconds}s`}
                />
              </div>
            </>
          )}
        </div>

        {status?.latest_summary && (
          <div className="mt-4 space-y-1">
            <p className="text-[10px] uppercase tracking-[0.15em]" style={{ color: "var(--hud-text-dim)" }}>
              Latest reflection summary
            </p>
            <p className="text-[12px] leading-relaxed" style={{ color: "var(--hud-text)" }}>
              {status.latest_summary}
            </p>
          </div>
        )}

        {status?.last_reflection_at && (
          <p className="mt-2 text-[11px]" style={{ color: "var(--hud-text-dim)" }}>
            Last reflected:{" "}
            {new Date(status.last_reflection_at).toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        )}
      </HudPanel>
    </div>
  );
}

function StatusRow({
  label,
  value,
  ok,
  invertOk,
}: {
  label: string;
  value: string;
  ok: boolean;
  invertOk?: boolean;
}) {
  const isGood = invertOk ? !ok : ok;
  return (
    <div className="flex items-center justify-between gap-2 text-[12px]">
      <span style={{ color: "var(--hud-text-dim)" }}>{label}</span>
      <span
        className="flex items-center gap-1.5 font-medium"
        style={{ color: isGood ? "var(--hud-success)" : "var(--hud-warning)" }}
      >
        <span
          className="size-1.5 rounded-full"
          style={{ background: isGood ? "var(--hud-success)" : "var(--hud-warning)" }}
        />
        {value}
      </span>
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2 text-[12px]">
      <span style={{ color: "var(--hud-text-dim)" }}>{label}</span>
      <span className="truncate text-right font-mono text-[11px]" style={{ color: "var(--hud-text)" }}>
        {value}
      </span>
    </div>
  );
}
