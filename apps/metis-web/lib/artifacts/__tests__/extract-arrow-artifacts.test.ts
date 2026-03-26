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
        runtime_eligible: true,
        runtime_skip_reason: undefined,
      },
    ]);
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
