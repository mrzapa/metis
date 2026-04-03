import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import {
  buildNyxComponentHref,
  FEATURED_NYX_COMPONENTS,
} from "@/components/library/nyx-shared";
import { cn } from "@/lib/utils";

export function NyxChatEntry() {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
          Nyx UI
        </p>
        <h2 className="text-lg font-semibold text-foreground">
          Browse components before you prompt
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Open the local Nyx catalog, inspect install targets and dependencies,
          then jump back into chat with a seeded prompt when you know which UI
          surface you want.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <Link
          href="/library"
          className={buttonVariants({ size: "sm", variant: "default" })}
        >
          Browse catalog
        </Link>
        <Link
          href={buildNyxComponentHref("glow-card")}
          className={buttonVariants({ size: "sm", variant: "outline" })}
        >
          Preview glow-card
        </Link>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/70">
          Featured previews
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
                  Open preview
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