"use client";

import { Button } from "@/components/ui/button";
import { IndexBuildStudio } from "@/components/library/index-build-studio";
import { PageChrome } from "@/components/shell/page-chrome";
import Link from "next/link";
import { MessageSquare } from "lucide-react";

export default function LibraryPage() {
  return (
    <PageChrome
      eyebrow="Library"
      title="Build your knowledge base"
      description="Import documents, create retrieval indexes, and move into grounded conversations. Axiom chunks, embeds, and indexes your files for fast semantic search."
      actions={
        <Link href="/chat">
          <Button variant="outline" className="gap-2">
            <MessageSquare className="size-4" />
            Go to chat
          </Button>
        </Link>
      }
    >
      <IndexBuildStudio />
    </PageChrome>
  );
}
