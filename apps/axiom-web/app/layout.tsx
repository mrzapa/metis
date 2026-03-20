import type { Metadata } from "next";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SetupGuard } from "@/components/setup-guard";
import { DesktopReadyGuard } from "@/components/desktop-ready";

export const metadata: Metadata = {
  title: "AXIOM | Frontier RAG AI",
  description: "A local-first frontier AI workspace for chat, retrieval, and knowledge building.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
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
