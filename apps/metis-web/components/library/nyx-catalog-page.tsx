"use client";

import type { ChangeEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { startTransition, useDeferredValue, useEffect } from "react";
import {
  buildNyxChatSeed,
  buildNyxComponentHref,
  FEATURED_NYX_COMPONENTS,
  getNyxComponentPreviewHref,
  seedNyxChatPrompt,
} from "@/components/library/nyx-shared";
import { PageChrome } from "@/components/shell/page-chrome";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { useArrowState } from "@/hooks/use-arrow-state";
import {
  fetchNyxCatalog,
  type NyxCatalogComponentSummary,
  type NyxCatalogSearchResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const NYX_CATALOG_LIMIT = 24;

function renderDependencyBadges(dependencies: string[]) {
  if (dependencies.length === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        No additional dependencies declared.
      </span>
    );
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {dependencies.map((dependency) => (
        <Badge key={dependency} variant="outline">
          {dependency}
        </Badge>
      ))}
    </div>
  );
}

function CatalogHeroAside({
  isLoading,
  matched,
  total,
}: {
  isLoading: boolean;
  matched: number;
  total: number;
}) {
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
            Catalog
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
            {total || "-"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Curated Nyx components exposed through the local Metis API.
          </p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-black/10 px-4 py-4">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
            Match set
          </p>
          <p className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
            {isLoading ? "…" : matched}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Filtered results ready to inspect or seed into chat.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/70">
          Stable preview routes
        </p>
        <div className="grid gap-2">
          {FEATURED_NYX_COMPONENTS.map((component) => (
            <Link
              key={component.componentName}
              href={buildNyxComponentHref(component.componentName)}
              className={cn(
                "rounded-xl border border-white/10 bg-black/10 px-3 py-3 transition-colors duration-200",
                "hover:border-primary/30 hover:bg-white/5",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <span className="text-sm font-medium text-foreground">
                  {component.title}
                </span>
                <span className="text-xs font-medium text-primary/80">
                  Preview
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                {component.description}
              </p>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

export function NyxCatalogPage() {
  const router = useRouter();
  const [catalog, setCatalog] = useArrowState<NyxCatalogSearchResponse | null>(null);
  const [error, setError] = useArrowState<string | null>(null);
  const [isLoading, setIsLoading] = useArrowState(true);
  const [query, setQuery] = useArrowState("");
  const [refreshToken, setRefreshToken] = useArrowState(0);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    let ignore = false;

    setError(null);
    setIsLoading(true);

    fetchNyxCatalog(deferredQuery, { limit: NYX_CATALOG_LIMIT })
      .then((response) => {
        if (ignore) {
          return;
        }

        setCatalog(response);
      })
      .catch((nextError) => {
        if (ignore) {
          return;
        }

        setError(
          nextError instanceof Error
            ? nextError.message
            : "Failed to load the Nyx catalog.",
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
  }, [deferredQuery, refreshToken, setCatalog, setError, setIsLoading]);

  const handleSearchChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextQuery = event.target.value;

    startTransition(() => {
      setQuery(nextQuery);
    });
  };

  const handleUseInChat = (component: NyxCatalogComponentSummary) => {
    seedNyxChatPrompt(buildNyxChatSeed(component));
    router.push("/chat");
  };

  const matchedCount = catalog?.matched ?? 0;
  const totalCount = catalog?.total ?? 0;
  const hasResults = (catalog?.items.length ?? 0) > 0;
  const pendingQuery = query !== deferredQuery;

  return (
    <PageChrome
      eyebrow="Library"
      title="Browse Nyx UI inside Metis"
      description="Search the curated Nyx subset, inspect what Metis can install today, and open featured preview routes for selected demo components."
      actions={
        <>
          <Badge variant="outline">
            {isLoading && !catalog
              ? "Loading local Nyx catalog…"
              : `${matchedCount} of ${totalCount || matchedCount} matched`}
          </Badge>
          <Badge variant="outline">Local API</Badge>
          <Link
            href="/chat"
            className={buttonVariants({ size: "sm", variant: "outline" })}
          >
            Open chat
          </Link>
        </>
      }
      heroAside={
        <CatalogHeroAside
          isLoading={isLoading}
          matched={matchedCount}
          total={totalCount}
        />
      }
    >
      <div className="space-y-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <h2 className="text-xl font-semibold tracking-tight text-foreground">
              Curated Nyx catalog
            </h2>
            <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
              This surface is backed by Metis&apos;s local Nyx API. Inspect each card
              for install targets, dependencies, and file footprint before you
              prompt for integration work.
            </p>
          </div>

          <div className="w-full max-w-lg space-y-2">
            <label
              htmlFor="nyx-catalog-search"
              className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80"
            >
              Find a component
            </label>
            <Input
              id="nyx-catalog-search"
              placeholder="Search glow-card, music-player, scanner…"
              value={query}
              onChange={handleSearchChange}
            />
            <p className="text-xs text-muted-foreground">
              {pendingQuery || isLoading
                ? "Refreshing results from the local Nyx catalog…"
                : hasResults
                  ? `${matchedCount} result${matchedCount === 1 ? "" : "s"} ready to preview.`
                  : "No components match the current search."}
            </p>
          </div>
        </div>

        {error && catalog ? (
          <div
            className="rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-foreground"
            role="alert"
          >
            Showing the last successful catalog response. {error}
          </div>
        ) : null}

        {error && !catalog ? (
          <EmptyState
            title="Nyx catalog unavailable"
            description={error}
            action={
              <Button
                type="button"
                variant="outline"
                onClick={() => setRefreshToken((current) => current + 1)}
              >
                Retry catalog fetch
              </Button>
            }
          />
        ) : null}

        {!error && !hasResults && !isLoading ? (
          <EmptyState
            title="No Nyx components matched"
            description="Try a broader keyword or open one of the stable preview routes from the right-hand panel."
            action={
              <Button type="button" variant="outline" onClick={() => setQuery("")}>
                Clear search
              </Button>
            }
          />
        ) : null}

        {hasResults ? (
          <div className="grid gap-4 xl:grid-cols-2">
            {catalog?.items.map((component) => {
              const previewHref = getNyxComponentPreviewHref(component.component_name);

              return (
                <Card key={component.component_name} className="h-full">
                  <CardHeader>
                    <div>
                      <CardTitle>{component.title}</CardTitle>
                      <CardDescription className="mt-1">
                        {component.curated_description || component.description}
                      </CardDescription>
                    </div>
                    <CardAction>
                      <Badge variant="outline">{component.component_type}</Badge>
                    </CardAction>
                  </CardHeader>

                  <CardContent className="space-y-4">
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
                          Install target
                        </p>
                        <p className="mt-2 break-all font-mono text-xs text-foreground">
                          {component.install_target}
                        </p>
                      </div>
                      <div className="rounded-xl border border-white/10 bg-black/10 px-3 py-3">
                        <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
                          File targets
                        </p>
                        <p className="mt-2 text-sm text-foreground">
                          {component.file_count} file{component.file_count === 1 ? "" : "s"}
                        </p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          {component.targets.slice(0, 2).join(" • ") || "No target metadata"}
                        </p>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <p className="text-xs font-medium uppercase tracking-[0.18em] text-primary/80">
                        Required dependencies
                      </p>
                      {renderDependencyBadges(component.required_dependencies)}
                    </div>
                  </CardContent>

                  <CardFooter className="justify-between gap-3">
                    {previewHref ? (
                      <Link
                        href={previewHref}
                        className={buttonVariants({ size: "sm", variant: "outline" })}
                      >
                        Preview component
                      </Link>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Preview routes are generated for featured components only.
                      </p>
                    )}
                    <Button type="button" size="sm" onClick={() => handleUseInChat(component)}>
                      Use in chat
                    </Button>
                  </CardFooter>
                </Card>
              );
            })}
          </div>
        ) : null}
      </div>
    </PageChrome>
  );
}