import Link from "next/link";
import { Button } from "@/components/ui/button";
import { MetisMark } from "@/components/brand";

/**
 * Custom 404 page (Next.js convention: `app/not-found.tsx`).
 *
 * Pre-existing behaviour: hitting any unknown route under `/` rendered
 * the built-in Next dev/prod 404 — text-only, no nav, no recovery
 * action. Users on stale links from old artifacts (chat transcripts
 * with renamed routes, old bookmarks) dead-ended.
 *
 * This page surfaces the METIS mark, a short explanation, and a
 * single primary action ("Back to home") so users can always return
 * to the constellation in one click. Keeps the footprint tiny — no
 * client JS, no dynamic content, no animations.
 *
 * M21 P3 #20.
 */
export default function NotFound() {
  return (
    <main className="relative z-10 flex min-h-screen flex-col items-center justify-center gap-6 px-6 py-16 text-center">
      <MetisMark size={80} title="Metis home" className="opacity-90" />
      <div className="space-y-2">
        <p className="font-display text-xs uppercase tracking-[0.32em] text-primary/85">
          404 — page not found
        </p>
        <h1 className="font-display text-balance text-3xl font-semibold tracking-[-0.03em] text-foreground sm:text-4xl">
          That route doesn&apos;t exist.
        </h1>
        <p className="mx-auto max-w-md text-pretty text-sm leading-7 text-muted-foreground">
          The link may be stale, the page may have moved, or the URL
          might just be off by a character. Head back to the
          constellation and try from there.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-3">
        <Link href="/">
          <Button>Back to home</Button>
        </Link>
        <Link href="/chat">
          <Button variant="outline">Open chat</Button>
        </Link>
      </div>
    </main>
  );
}
