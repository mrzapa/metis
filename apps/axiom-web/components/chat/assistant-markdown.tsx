"use client";

import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";

interface AssistantMarkdownProps {
  content: string;
  className?: string;
}

export function AssistantMarkdown({ content, className }: AssistantMarkdownProps) {
  if (!content) {
    return null;
  }

  return (
    <div
      className={cn(
        "break-words text-sm leading-relaxed",
        "[&>*:first-child]:mt-0",
        "[&>*:last-child]:mb-0",
        "[&_p]:my-3",
        "[&_p]:whitespace-pre-wrap",
        "[&_ul]:my-3",
        "[&_ul]:list-disc",
        "[&_ul]:pl-6",
        "[&_ul]:space-y-1.5",
        "[&_ol]:my-3",
        "[&_ol]:list-decimal",
        "[&_ol]:pl-6",
        "[&_ol]:space-y-1.5",
        "[&_li]:pl-1",
        "[&_li>p]:my-0",
        "[&_pre]:my-3",
        "[&_pre]:overflow-x-auto",
        "[&_pre]:rounded-md",
        "[&_pre]:bg-background/80",
        "[&_pre]:px-3",
        "[&_pre]:py-2.5",
        "[&_pre]:font-mono",
        "[&_pre]:text-[13px]",
        "[&_pre]:leading-6",
        "[&_pre_code]:bg-transparent",
        "[&_pre_code]:p-0",
        "[&_pre_code]:text-inherit",
        "[&_code]:rounded",
        "[&_code]:bg-background/80",
        "[&_code]:px-1",
        "[&_code]:py-0.5",
        "[&_code]:font-mono",
        "[&_code]:text-[13px]",
        "[&_a]:font-medium",
        "[&_a]:text-primary",
        "[&_a]:underline",
        "[&_a]:decoration-primary/40",
        "[&_a]:underline-offset-2",
        className,
      )}
    >
      <ReactMarkdown skipHtml>{content}</ReactMarkdown>
    </div>
  );
}
