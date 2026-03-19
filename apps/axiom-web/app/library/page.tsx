"use client";

import { Button } from "@/components/ui/button";
import { IndexBuildStudio } from "@/components/library/index-build-studio";
import { PageChrome } from "@/components/shell/page-chrome";
import { Badge } from "@/components/ui/badge";
import Link from "next/link";

export default function LibraryPage() {
  return (
    <PageChrome
      eyebrow="Knowledge Intake"
      title="Shape your knowledge base before you ask anything."
      description="Import documents, build retrieval indexes, and move straight into grounded conversations without losing the flow."
      actions={
        <>
          <Badge variant="outline">Upload, local paths, or desktop file picker</Badge>
          <Link href="/chat">
            <Button variant="outline">Go to chat</Button>
          </Link>
        </>
      }
      heroAside={
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Library posture
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            Start small, validate answers early, then expand the corpus once the retrieval loop feels trustworthy.
          </p>
        </div>
      }
    >
      <IndexBuildStudio />
    </PageChrome>
  );
}
