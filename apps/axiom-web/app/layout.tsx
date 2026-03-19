import type { Metadata } from "next";
import { Atkinson_Hyperlegible, Exo, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SetupGuard } from "@/components/setup-guard";
import { DesktopReadyGuard } from "@/components/desktop-ready";

const bodyFont = Atkinson_Hyperlegible({
  subsets: ["latin"],
  weight: ["400", "700"],
  display: "swap",
  variable: "--font-body",
});

const displayFont = Exo({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-heading",
});

const monoFont = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-code",
});

export const metadata: Metadata = {
  title: "Axiom",
  description: "A cinematic local-first AI workspace for research, retrieval, and knowledge building.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${bodyFont.variable} ${displayFont.variable} ${monoFont.variable} min-h-screen bg-background font-sans text-foreground antialiased`}
      >
        <TooltipProvider>
          <DesktopReadyGuard>
            <SetupGuard>{children}</SetupGuard>
          </DesktopReadyGuard>
        </TooltipProvider>
      </body>
    </html>
  );
}
