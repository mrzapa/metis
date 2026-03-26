import type { EvidenceSource } from "@/lib/chat-types";

function normalizeLineEndings(value: string): string {
  return value.replace(/\r\n/g, "\n");
}

function collapseBlankLines(value: string): string {
  return value.replace(/\n{3,}/g, "\n\n").trim();
}

function cleanSourceValue(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function normalizeMarkdownForCopy(markdown: string): string {
  return normalizeLineEndings(markdown).trim();
}

export function markdownToPlainText(markdown: string): string {
  let text = normalizeMarkdownForCopy(markdown);

  text = text.replace(/```([\s\S]*?)```/g, (_match, code: string) => {
    return `\n${code.trim()}\n`;
  });
  text = text.replace(/`([^`]+)`/g, "$1");
  text = text.replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1");
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)");
  text = text.replace(/^#{1,6}\s+/gm, "");
  text = text.replace(/^\s*>\s?/gm, "");
  text = text.replace(/^\s*[-+*]\s+/gm, "• ");
  text = text.replace(/^\s*(\d+)\.\s+/gm, "$1. ");
  text = text.replace(/(\*\*|__)(?=\S)([\s\S]*?\S)\1/g, "$2");
  text = text.replace(/(\*|_)(?=\S)([\s\S]*?\S)\1/g, "$2");
  text = text.replace(/~~(?=\S)([\s\S]*?\S)~~/g, "$1");
  text = text.replace(/^(-{3,}|\*{3,}|_{3,})$/gm, "");

  return collapseBlankLines(text);
}

function formatSourceLabel(source: EvidenceSource): string {
  const title = cleanSourceValue(source.title);
  const file = cleanSourceValue(source.source);

  if (title && file && title !== file) {
    return `${title} (${file})`;
  }

  return title || file || "Untitled source";
}

function formatSourceHint(source: EvidenceSource): string {
  const hints = [source.section_hint, source.breadcrumb, source.locator]
    .map((value) => cleanSourceValue(String(value ?? "")))
    .filter(Boolean)
    .filter((value, index, values) => values.indexOf(value) === index);

  return hints.join(" | ");
}

export function formatSourcesForCopy(sources: EvidenceSource[]): string {
  if (sources.length === 0) {
    return "Sources\n- None attached.";
  }

  return [
    "Sources",
    ...sources.map((source, index) => {
      const label = formatSourceLabel(source);
      const hint = formatSourceHint(source);

      return hint
        ? `S${index + 1}. ${label} — ${hint}`
        : `S${index + 1}. ${label}`;
    }),
  ].join("\n");
}

export function formatAnswerWithSourcesForCopy(
  markdown: string,
  sources: EvidenceSource[],
): string {
  const answer = markdownToPlainText(markdown);
  const appendix = formatSourcesForCopy(sources);

  if (!answer) {
    return appendix;
  }

  return `${answer}\n\n${appendix}`;
}
