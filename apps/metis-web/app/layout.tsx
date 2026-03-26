import type { Metadata } from "next";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SetupGuard } from "@/components/setup-guard";
import { DesktopReadyGuard } from "@/components/desktop-ready";

const uiVariantBootstrap = `(() => {
  try {
    let stored = window.localStorage.getItem("metis-ui-variant");
    if (!stored) {
      const legacy = window.localStorage.getItem("metis-ui-variant");
      if (legacy) {
        window.localStorage.setItem("metis-ui-variant", legacy);
        window.localStorage.removeItem("metis-ui-variant");
        stored = legacy;
      }
    }
    const variant = stored === "refined" || stored === "motion" || stored === "bold" ? stored : "refined";
    document.documentElement.dataset.uiVariant = variant;
  } catch {
    document.documentElement.dataset.uiVariant = "refined";
  }
})();`;

export const metadata: Metadata = {
  title: "METIS AI",
  description: "A local-first frontier AI workspace for chat, retrieval, and knowledge building.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: uiVariantBootstrap }} />
      </head>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <TooltipProvider>
          <DesktopReadyGuard>
            <SetupGuard>{children}</SetupGuard>
          </DesktopReadyGuard>
        </TooltipProvider>
      </body>
    </html>
  );
}
