import { describe, expect, it } from "vitest";
import { extractArrowArtifacts } from "@/lib/artifacts/extract-arrow-artifacts";

describe("extractArrowArtifacts", () => {
  it("returns no artifacts when payload is empty", () => {
    expect(extractArrowArtifacts(undefined)).toEqual({
      hasArtifacts: false,
      isValid: false,
      artifacts: [],
    });

    expect(extractArrowArtifacts([])).toEqual({
      hasArtifacts: false,
      isValid: false,
      artifacts: [],
    });
  });

  it("normalizes a valid artifact list", () => {
    const result = extractArrowArtifacts([
      {
        id: "  card-1  ",
        type: "  timeline  ",
        summary: "  Key milestones  ",
        path: "  artifacts/timeline.json  ",
        mime_type: "  application/json  ",
        payload: {
          items: [{ label: "Kickoff", detail: "Project started", occurred_at: "2026-03-01T00:00:00Z" }],
        },
        payload_bytes: 128,
        payload_truncated: false,
      },
    ]);

    expect(result.hasArtifacts).toBe(true);
    expect(result.isValid).toBe(true);
    expect(result.artifacts).toEqual([
      {
        id: "card-1",
        type: "timeline",
        summary: "Key milestones",
        path: "artifacts/timeline.json",
        mime_type: "application/json",
        payload: {
          items: [{ label: "Kickoff", detail: "Project started", occurred_at: "2026-03-01T00:00:00Z" }],
        },
        payload_bytes: 128,
        payload_truncated: false,
        render_kind: "runtime",
        runtime_eligible: true,
        runtime_skip_reason: undefined,
      },
    ]);
  });

  it("recognizes Nyx artifacts as structured renderers", () => {
    const result = extractArrowArtifacts([
      {
        id: "nyx_component_selection",
        type: "nyx_component_selection",
        summary: "Nyx selection",
        payload: {
          query: "Build me a glowing hero",
          intent_type: "ui_layout_request",
          confidence: 0.91,
          selected_components: [
            {
              component_name: "glow-card",
              title: "Glow Card",
              install_target: "@nyx/glow-card",
              registry_url: "https://nyxui.com/r/glow-card.json",
              targets: ["components/ui/glow-card.tsx"],
              preview_targets: ["components/ui/glow-card.tsx"],
              required_dependencies: ["clsx"],
              dependencies: ["tailwind-merge"],
              dev_dependencies: [],
              registry_dependencies: [],
              match_reasons: ["query hint: glow"],
            },
          ],
        },
      },
    ]);

    expect(result.isValid).toBe(true);
    expect(result.artifacts[0]?.render_kind).toBe("structured");
    expect(result.artifacts[0]?.runtime_eligible).toBe(false);
    expect(result.artifacts[0]?.runtime_skip_reason).toBeUndefined();
  });

  it("recognizes forecast reports as structured renderers", () => {
    const result = extractArrowArtifacts([
      {
        id: "forecast_report",
        type: "forecast_report",
        summary: "Revenue forecast",
        payload: {
          mapping: {
            file_path: "/tmp/revenue.csv",
            file_name: "revenue.csv",
            timestamp_column: "ds",
            target_column: "y",
            dynamic_covariates: ["promo"],
            static_covariates: [],
          },
          metadata: {
            horizon: 3,
            context_used: 12,
            model_backend: "timesfm-2.5-torch",
            model_id: "google/timesfm-2.5-200m-pytorch",
            xreg_mode: "xreg + timesfm",
          },
          history_points: [{ timestamp: "2026-01-01T00:00:00", value: 10 }],
          forecast_points: [{ timestamp: "2026-01-02T00:00:00", value: 11 }],
          quantiles: {
            p10: [{ timestamp: "2026-01-02T00:00:00", value: 9 }],
            p90: [{ timestamp: "2026-01-02T00:00:00", value: 13 }],
          },
          warnings: [],
        },
      },
    ]);

    expect(result.isValid).toBe(true);
    expect(result.artifacts[0]?.render_kind).toBe("structured");
    expect(result.artifacts[0]?.runtime_eligible).toBe(false);
    expect(result.artifacts[0]?.runtime_skip_reason).toBeUndefined();
  });

  it("marks unsupported types as runtime skipped", () => {
    const result = extractArrowArtifacts([
      {
        type: "markdown_blob",
        summary: "Rendered as fallback card",
        payload: { content: "hello" },
      },
    ]);

    expect(result.isValid).toBe(true);
    expect(result.artifacts[0]?.render_kind).toBe("fallback");
    expect(result.artifacts[0]?.runtime_eligible).toBe(false);
    expect(result.artifacts[0]?.runtime_skip_reason).toBe("unsupported_type");
  });

  it("marks truncated artifacts as runtime skipped", () => {
    const result = extractArrowArtifacts([
      {
        type: "timeline",
        payload: { items: [{ label: "Milestone" }] },
        payload_truncated: true,
      },
    ]);

    expect(result.isValid).toBe(true);
    expect(result.artifacts[0]?.render_kind).toBe("fallback");
    expect(result.artifacts[0]?.runtime_eligible).toBe(false);
    expect(result.artifacts[0]?.runtime_skip_reason).toBe("payload_truncated");
  });

  it("marks invalid supported payloads as runtime skipped", () => {
    const result = extractArrowArtifacts([
      {
        type: "timeline",
        payload: { items: [{ detail: "missing label" }] },
      },
    ]);

    expect(result.isValid).toBe(true);
    expect(result.artifacts[0]?.render_kind).toBe("fallback");
    expect(result.artifacts[0]?.runtime_eligible).toBe(false);
    expect(result.artifacts[0]?.runtime_skip_reason).toBe("invalid_payload");
  });

  it("flags malformed artifact payloads without throwing", () => {
    const result = extractArrowArtifacts([{ id: "a1", summary: "no type" }]);

    expect(result.hasArtifacts).toBe(true);
    expect(result.isValid).toBe(false);
    expect(result.artifacts).toEqual([]);
    expect(result.error).toContain("type");
  });
});
