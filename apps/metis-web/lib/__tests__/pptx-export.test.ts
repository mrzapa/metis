import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EvidenceSource } from "@/lib/chat-types";

const addTextMock = vi.fn();
const addSlideMock = vi.fn();
const writeFileMock = vi.fn();
const deckInstances: Array<Record<string, unknown>> = [];

const PptxGenJSMock = vi.fn(function PptxGenJSMock(this: Record<string, unknown>) {
  this.addSlide = addSlideMock;
  this.writeFile = writeFileMock;
  this.layout = "";
  this.author = "";
  this.company = "";
  this.subject = "";
  this.title = "";
  deckInstances.push(this);
});

vi.mock("pptxgenjs", () => ({
  default: PptxGenJSMock,
}));

vi.mock("@/lib/chat-copy", () => ({
  markdownToPlainText: vi.fn((value: string) => value),
}));

const { exportChatAnswerAsPptx } = await import("@/lib/export/pptx");
const { default: PptxGenJS } = await import("pptxgenjs");

function buildSource(overrides: Partial<EvidenceSource> = {}): EvidenceSource {
  return {
    sid: "S-1",
    source: "docs/spec.md",
    snippet: "Source evidence snippet",
    title: "Spec",
    score: 0.98,
    breadcrumb: "Docs > Spec",
    section_hint: "Section A",
    locator: "L12",
    file_path: "docs/spec.md",
    timestamp: "2026-03-25T10:00:00Z",
    ...overrides,
  };
}

describe("exportChatAnswerAsPptx", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    deckInstances.length = 0;
    addTextMock.mockReset();
    writeFileMock.mockReset();
    addSlideMock.mockImplementation(() => ({
      addText: addTextMock,
    }));
    writeFileMock.mockResolvedValue(undefined);
  });

  it("instantiates PptxGenJS and writes a .pptx file", async () => {
    await exportChatAnswerAsPptx({
      answer: "Short answer",
      sources: [],
      fileName: "My Export",
    });

    expect(PptxGenJS).toHaveBeenCalledTimes(1);
    expect(writeFileMock).toHaveBeenCalledWith({ fileName: "my-export.pptx" });
  });

  it("adds source path metadata to source slides when sources are present", async () => {
    await exportChatAnswerAsPptx({
      answer: "Summary",
      sources: [buildSource()],
      mode: "Evidence Pack",
      fileName: "evidence-pack",
    });

    const textCalls = addTextMock.mock.calls.map(([text]) => String(text));
    expect(textCalls).toContain("Sources Appendix");
    expect(textCalls.some((value) => value.includes("docs/spec.md"))).toBe(true);
    expect(textCalls.some((value) => value.includes("S1 [S-1] Spec (docs/spec.md)"))).toBe(true);
  });
});