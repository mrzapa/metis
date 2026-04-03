"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  buildNyxChatSeed,
  buildNyxComponentHref,
  getNyxComponentPreviewHref,
  seedNyxChatPrompt,
} from "@/components/library/nyx-shared";
import { PageChrome } from "@/components/shell/page-chrome";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { useArrowState } from "@/hooks/use-arrow-state";
import {
  fetchNyxComponentDetail,
  type NyxCatalogComponentDetail,
} from "@/lib/api";

function formatByteSize(contentBytes: number): string {
  if (contentBytes < 1024) {
    return `${contentBytes} B`;
  }

  if (contentBytes < 1024 * 1024) {
    return `${(contentBytes / 1024).toFixed(1)} KB`;
  }

  return `${(contentBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function renderDependencyGroup(title: string, dependencies: string[]) {
  if (dependencies.length === 0) {
    return null;
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
        {title}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {dependencies.map((dependency) => (
          <Badge key={`${title}:${dependency}`} variant="outline">
            {dependency}
          </Badge>
        ))}
      </div>
    </div>
  );
}

function DetailHeroAside({ detail }: { detail: NyxCatalogComponentDetail | null }) {
  if (!detail) {
    return (
      <div className="space-y-3">
        <p className="text-sm leading-relaxed text-muted-foreground">
          Loading component preview from the local Nyx API…
        </p>
      </div>
    );
  }

  const previewHref = getNyxComponentPreviewHref(detail.component_name);

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
            Install target
          </p>
          <p className="mt-2 break-all font-mono text-xs text-foreground">
            {detail.install_target}
          </p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
            File footprint
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
            {detail.file_count}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Target file{detail.file_count === 1 ? "" : "s"} in the registry item.
          </p>
        </div>
      </div>

      {previewHref ? (
        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
            Preview route
          </p>
          <p className="mt-2 break-all font-mono text-xs text-foreground">
            {buildNyxComponentHref(detail.component_name)}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Featured preview route generated at build time for the static export.
          </p>
        </div>
      ) : null}
    </div>
  );
}

interface NyxComponentDetailPageProps {
  componentName: string;
}

export function NyxComponentDetailPage({
  componentName,
}: NyxComponentDetailPageProps) {
  const router = useRouter();
  const [detail, setDetail] = useArrowState<NyxCatalogComponentDetail | null>(null);
  const [error, setError] = useArrowState<string | null>(null);
  const [isLoading, setIsLoading] = useArrowState(true);
  const [refreshToken, setRefreshToken] = useArrowState(0);

  useEffect(() => {
    let ignore = false;

    setError(null);
    setIsLoading(true);

    fetchNyxComponentDetail(componentName)
      .then((response) => {
        if (ignore) {
          return;
        }

        setDetail(response);
      })
      .catch((nextError) => {
        if (ignore) {
          return;
        }

        setError(
          nextError instanceof Error
            ? nextError.message
            : "Failed to load the Nyx component detail.",
        );
      })
      .finally(() => {
        if (ignore) {
          return;
        }

        setIsLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, [componentName, refreshToken, setDetail, setError, setIsLoading]);

  const handleUseInChat = () => {
    if (!detail) {
      return;
    }

    seedNyxChatPrompt(buildNyxChatSeed(detail));
    router.push("/chat");
  };

  return (
    <PageChrome
      eyebrow="Nyx Preview"
      title={detail?.title ?? componentName}
      description={
        detail
          ? detail.curated_description || detail.description
          : "Inspecting the local Nyx preview payload for this component."
      }
      actions={
        <>
          <Link
            href="/library"
            className={buttonVariants({ size: "sm", variant: "outline" })}
          >
            Back to catalog
          </Link>
          {detail ? (
            <Button type="button" size="sm" onClick={handleUseInChat}>
              Use in chat
            </Button>
          ) : null}
        </>
      }
      heroAside={<DetailHeroAside detail={detail} />}
    >
      {error && !detail ? (
        <EmptyState
          title="Nyx preview unavailable"
          description={error}
          action={
            <div className="flex flex-wrap items-center justify-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setRefreshToken((current) => current + 1)}
              >
                Retry preview
              </Button>
              <Link
                href="/library"
                className={buttonVariants({ size: "sm", variant: "outline" })}
              >
                Return to catalog
              </Link>
            </div>
          }
        />
      ) : null}

      {!error && !detail && isLoading ? (
        <div className="space-y-3 rounded-2xl border border-white/10 bg-black/10 px-5 py-5">
          <p className="text-sm font-medium text-foreground">
            Loading component preview…
          </p>
          <p className="text-sm text-muted-foreground">
            Fetching install targets, dependency metadata, and file footprint from
            the local Metis Nyx API.
          </p>
        </div>
      ) : null}

      {detail ? (
        <div className="space-y-4">
          {error ? (
            <div
              className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-foreground"
              role="alert"
            >
              Showing the last successful preview response. {error}
            </div>
          ) : null}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
            <Card>
              <CardHeader>
                <CardTitle>Install footprint</CardTitle>
                <CardDescription>
                  This preview comes from Metis&apos;s local Nyx API and shows the
                  concrete surface area a prompt would need to account for.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
                      Source
                    </p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Badge variant="outline">{detail.source}</Badge>
                      <Badge variant="outline">{detail.component_type}</Badge>
                    </div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
                      Registry item
                    </p>
                    <p className="mt-2 break-all font-mono text-xs text-foreground">
                      {detail.registry_url}
                    </p>
                  </div>
                </div>

                <div className="space-y-3">
                  <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
                    Target files
                  </p>
                  <div className="space-y-3">
                    {detail.files.map((file) => (
                      <div
                        key={`${file.path}:${file.target}`}
                        className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="font-mono text-xs text-foreground">
                            {file.target || file.path}
                          </p>
                          <Badge variant="outline">{file.file_type}</Badge>
                        </div>
                        <p className="mt-2 break-all text-xs text-muted-foreground">
                          Source path: {file.path}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          Approx. size: {formatByteSize(file.content_bytes)}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>Dependency context</CardTitle>
                  <CardDescription>
                    Use these groups to understand what the local Nyx API says this
                    component needs before it can be incorporated into Metis.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {renderDependencyGroup(
                    "Required in Metis",
                    detail.required_dependencies,
                  )}
                  {renderDependencyGroup("Runtime", detail.dependencies)}
                  {renderDependencyGroup(
                    "Registry dependencies",
                    detail.registry_dependencies,
                  )}
                  {renderDependencyGroup("Dev", detail.dev_dependencies)}
                  {detail.required_dependencies.length === 0 &&
                  detail.dependencies.length === 0 &&
                  detail.registry_dependencies.length === 0 &&
                  detail.dev_dependencies.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No dependency metadata was included for this component.
                    </p>
                  ) : null}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Prompt-ready handoff</CardTitle>
                  <CardDescription>
                    Seed chat with a prompt that already includes the install target,
                    curated description, and file targets from this preview.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4">
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-foreground">
                      {buildNyxChatSeed(detail)}
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <Button type="button" onClick={handleUseInChat}>
                      Use in chat
                    </Button>
                    <a
                      href={detail.source_repo}
                      target="_blank"
                      rel="noreferrer"
                      className={buttonVariants({ size: "default", variant: "outline" })}
                    >
                      Open source repo
                    </a>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      ) : null}
    </PageChrome>
  );
}