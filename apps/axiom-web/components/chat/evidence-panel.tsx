"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { EvidenceSource } from "@/lib/api";
import { FileText, List, Activity } from "lucide-react";
import { EvidenceSourceCard } from "@/components/chat/evidence-source-card";

interface EvidencePanelProps {
  sources: EvidenceSource[];
}

export function EvidencePanel({ sources }: EvidencePanelProps) {
  return (
    <div className="flex h-full flex-col">
      <Tabs defaultValue="sources" className="flex h-full flex-col">
        {/* Tab bar */}
        <div className="shrink-0 border-b px-3 pt-2">
          <TabsList variant="line" className="h-8">
            <TabsTrigger value="sources" className="gap-1 text-xs">
              <FileText className="size-3" />
              Sources
            </TabsTrigger>
            <TabsTrigger value="outline" className="gap-1 text-xs">
              <List className="size-3" />
              Outline
            </TabsTrigger>
            <TabsTrigger value="trace" className="gap-1 text-xs">
              <Activity className="size-3" />
              Trace
            </TabsTrigger>
          </TabsList>
        </div>

        {/* Sources tab */}
        <TabsContent value="sources" className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="space-y-2 p-3">
              {sources.length === 0 && (
                <p className="py-8 text-center text-xs text-muted-foreground">
                  No sources yet. Sources will appear here when the assistant
                  references documents.
                </p>
              )}

              {sources.map((src) => (
                <EvidenceSourceCard key={src.sid} source={src} />
              ))}
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Outline tab */}
        <TabsContent value="outline" className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-3">
              <p className="py-8 text-center text-xs text-muted-foreground">
                Outline will show the structure of the current conversation.
              </p>
            </div>
          </ScrollArea>
        </TabsContent>

        {/* Trace tab */}
        <TabsContent value="trace" className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-3">
              <p className="py-8 text-center text-xs text-muted-foreground">
                Trace will show retrieval and reasoning steps.
              </p>
            </div>
          </ScrollArea>
        </TabsContent>
      </Tabs>
    </div>
  );
}
