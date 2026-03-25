import { markdownToPlainText } from "@/lib/chat-copy";
import type { EvidenceSource } from "@/lib/chat-types";

const SLIDE_WIDTH_CHARS = 980;
const SOURCE_SLIDE_WIDTH_CHARS = 380;
const SOURCES_PER_SLIDE = 3;

export interface ChatPptxExportInput {
  answer: string;
  sources: EvidenceSource[];
  mode?: string;
  title?: string;
  fileName?: string;
  generatedAt?: Date;
}

function safeValue(value: string | null | undefined): string {
  return String(value ?? "").trim();
}

function compactWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function truncate(value: string, maxLength: number): string {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}…`;
}

function chunkByLength(paragraphs: string[], maxLength: number): string[] {
  const chunks: string[] = [];
  let current = "";

  for (const paragraph of paragraphs) {
    const candidate = current ? `${current}\n\n${paragraph}` : paragraph;
    if (candidate.length <= maxLength) {
      current = candidate;
      continue;
    }

    if (current) {
      chunks.push(current);
      current = "";
    }

    if (paragraph.length <= maxLength) {
      current = paragraph;
      continue;
    }

    let remaining = paragraph;
    while (remaining.length > maxLength) {
      const splitAt = remaining.lastIndexOf(" ", maxLength);
      const index = splitAt > maxLength * 0.65 ? splitAt : maxLength;
      chunks.push(remaining.slice(0, index).trim());
      remaining = remaining.slice(index).trim();
    }
    current = remaining;
  }

  if (current) {
    chunks.push(current);
  }

  return chunks;
}

function answerSections(answerMarkdown: string): string[] {
  const plainText = markdownToPlainText(answerMarkdown);
  const normalized = plainText.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return ["No answer text was provided."];
  }
  const paragraphs = normalized
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
  return chunkByLength(paragraphs, SLIDE_WIDTH_CHARS);
}

function sourceLabel(source: EvidenceSource): string {
  const title = compactWhitespace(safeValue(source.title));
  const file = compactWhitespace(safeValue(source.source));

  if (title && file && title !== file) {
    return `${title} (${file})`;
  }

  return title || file || "Untitled source";
}

function sourceMeta(source: EvidenceSource): string {
  const hints = [
    safeValue(source.section_hint),
    safeValue(source.breadcrumb),
    safeValue(source.locator),
    safeValue(source.file_path),
    safeValue(source.timestamp),
  ]
    .map(compactWhitespace)
    .filter(Boolean)
    .filter((value, index, items) => items.indexOf(value) === index);

  return hints.join(" | ");
}

function sanitizeFileName(value: string): string {
  const safe = value
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "-")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();

  return safe || "axiom-export";
}

export async function exportChatAnswerAsPptx(input: ChatPptxExportInput): Promise<void> {
  const { default: PptxGenJS } = await import("pptxgenjs");

  const deck = new PptxGenJS();
  deck.layout = "LAYOUT_WIDE";
  deck.author = "Axiom";
  deck.company = "Axiom";
  deck.subject = "Chat export";
  deck.title = input.title ?? "Axiom Chat Export";

  const now = input.generatedAt ?? new Date();
  const modeLabel = safeValue(input.mode) || "Q&A";

  const titleSlide = deck.addSlide();
  titleSlide.addText(input.title ?? "Axiom Chat Export", {
    x: 0.6,
    y: 0.65,
    w: 12.1,
    h: 0.8,
    bold: true,
    fontSize: 31,
    color: "1F2937",
  });
  titleSlide.addText(`Mode: ${modeLabel}`, {
    x: 0.6,
    y: 1.65,
    w: 6.5,
    h: 0.32,
    fontSize: 13,
    color: "334155",
  });
  titleSlide.addText(`Generated: ${now.toLocaleString()}`, {
    x: 0.6,
    y: 2.0,
    w: 6.5,
    h: 0.32,
    fontSize: 12,
    color: "64748B",
  });
  titleSlide.addText(`Sources attached: ${input.sources.length}`, {
    x: 0.6,
    y: 2.35,
    w: 6.5,
    h: 0.32,
    fontSize: 12,
    color: "64748B",
  });

  const answerChunks = answerSections(input.answer);
  for (const [index, chunk] of answerChunks.entries()) {
    const slide = deck.addSlide();
    slide.addText(index === 0 ? "Summary" : `Summary (cont. ${index + 1})`, {
      x: 0.6,
      y: 0.4,
      w: 12.1,
      h: 0.48,
      bold: true,
      fontSize: 22,
      color: "0F172A",
    });
    slide.addText(chunk, {
      x: 0.72,
      y: 1.08,
      w: 11.85,
      h: 5.7,
      fontSize: 16,
      color: "1E293B",
      valign: "top",
      breakLine: true,
      margin: 0,
      fit: "shrink",
    });
  }

  if (input.sources.length > 0) {
    const appendixIntro = deck.addSlide();
    appendixIntro.addText("Sources Appendix", {
      x: 0.6,
      y: 0.75,
      w: 12.1,
      h: 0.65,
      bold: true,
      fontSize: 30,
      color: "111827",
    });
    appendixIntro.addText(
      "The following slides capture the source labels, context hints, and supporting snippets used in this response.",
      {
        x: 0.6,
        y: 1.9,
        w: 11.8,
        h: 1.2,
        fontSize: 15,
        color: "334155",
        breakLine: true,
      },
    );

    for (let index = 0; index < input.sources.length; index += SOURCES_PER_SLIDE) {
      const sourceSlice = input.sources.slice(index, index + SOURCES_PER_SLIDE);
      const slide = deck.addSlide();
      slide.addText(
        `Sources ${index + 1}-${index + sourceSlice.length} of ${input.sources.length}`,
        {
          x: 0.6,
          y: 0.4,
          w: 12.1,
          h: 0.44,
          bold: true,
          fontSize: 19,
          color: "0F172A",
        },
      );

      let y = 0.95;
      sourceSlice.forEach((source, offset) => {
        const sourceNumber = index + offset + 1;
        const snippet = truncate(compactWhitespace(safeValue(source.snippet)), SOURCE_SLIDE_WIDTH_CHARS);
        const meta = sourceMeta(source);

        slide.addText(`S${sourceNumber} [${source.sid}] ${sourceLabel(source)}`, {
          x: 0.72,
          y,
          w: 11.8,
          h: 0.36,
          bold: true,
          fontSize: 12,
          color: "1D4ED8",
        });

        if (meta) {
          slide.addText(meta, {
            x: 0.9,
            y: y + 0.33,
            w: 11.5,
            h: 0.34,
            fontSize: 10,
            color: "475569",
            fit: "shrink",
            breakLine: true,
          });
        }

        slide.addText(snippet || "No snippet available.", {
          x: 0.9,
          y: y + 0.65,
          w: 11.5,
          h: 1.18,
          fontSize: 11,
          color: "0F172A",
          valign: "top",
          breakLine: true,
          fit: "shrink",
        });

        y += 2.05;
      });
    }
  }

  const fallbackTitle = safeValue(input.title) || `${modeLabel}-export`;
  const resolvedFileName = `${sanitizeFileName(input.fileName ?? fallbackTitle)}.pptx`;
  await deck.writeFile({ fileName: resolvedFileName });
}