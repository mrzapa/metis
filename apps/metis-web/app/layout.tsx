import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { SetupGuard } from "@/components/setup-guard";
import { DesktopReadyGuard } from "@/components/desktop-ready";
import { UiVariantBootstrap } from "@/components/ui-variant-bootstrap";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-display" });


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
    <html lang="en" className="dark" suppressHydrationWarning data-ui-variant="refined">
      <body className={`${inter.variable} ${spaceGrotesk.variable} min-h-screen bg-background font-sans text-foreground antialiased`}>
        <UiVariantBootstrap />
        {/* Persistent deep-space starfield — always behind all page content */}
        <div
          aria-hidden="true"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 0,
            pointerEvents: "none",
            backgroundColor: "#06080e",
            overflow: "hidden",
          }}
        >
          {/* Star layer 1 — fine stars, slow drift */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage:
                "radial-gradient(1px 1px at 15% 10%, rgba(255,255,255,0.70), transparent)," +
                "radial-gradient(1px 1px at 72% 22%, rgba(255,255,255,0.55), transparent)," +
                "radial-gradient(1.5px 1.5px at 38% 48%, rgba(173,198,255,0.60), transparent)," +
                "radial-gradient(1px 1px at 56% 18%, rgba(255,255,255,0.45), transparent)," +
                "radial-gradient(2px 2px at 82% 68%, rgba(255,255,255,0.62), transparent)," +
                "radial-gradient(1px 1px at 42% 80%, rgba(173,198,255,0.40), transparent)," +
                "radial-gradient(1.5px 1.5px at 63% 90%, rgba(255,255,255,0.50), transparent)," +
                "radial-gradient(1px 1px at 90% 40%, rgba(255,255,255,0.44), transparent)",
              backgroundRepeat: "repeat",
              backgroundSize: "420px 420px",
              animation: "starfield-drift 300s linear infinite",
            }}
          />
          {/* Star layer 2 — medium stars, different cadence */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage:
                "radial-gradient(1.5px 1.5px at 8% 30%, rgba(255,255,255,0.50), transparent)," +
                "radial-gradient(1px 1px at 48% 5%, rgba(200,215,255,0.60), transparent)," +
                "radial-gradient(2px 2px at 92% 55%, rgba(255,255,255,0.45), transparent)," +
                "radial-gradient(1px 1px at 25% 70%, rgba(173,198,255,0.50), transparent)," +
                "radial-gradient(1.5px 1.5px at 68% 38%, rgba(255,255,255,0.55), transparent)," +
                "radial-gradient(1px 1px at 35% 92%, rgba(255,255,255,0.40), transparent)",
              backgroundRepeat: "repeat",
              backgroundSize: "580px 580px",
              animation: "starfield-drift 420s linear infinite",
              animationDelay: "-40s",
            }}
          />
          {/* Star layer 3 — sparse bright stars */}
          <div
            style={{
              position: "absolute",
              inset: 0,
              backgroundImage:
                "radial-gradient(2px 2px at 22% 38%, rgba(255,255,255,0.65), transparent)," +
                "radial-gradient(1.5px 1.5px at 66% 12%, rgba(200,220,255,0.60), transparent)," +
                "radial-gradient(2.5px 2.5px at 88% 78%, rgba(255,255,255,0.55), transparent)," +
                "radial-gradient(1.5px 1.5px at 44% 62%, rgba(173,198,255,0.60), transparent)",
              backgroundRepeat: "repeat",
              backgroundSize: "780px 780px",
              animation: "starfield-drift 550s linear infinite",
              animationDelay: "-120s",
            }}
          />
          {/* Nebula blob — upper right, cyan tint */}
          <div
            style={{
              position: "absolute",
              top: "28%",
              right: "18%",
              width: "42vw",
              height: "32vw",
              borderRadius: "50%",
              background: "radial-gradient(ellipse at center, rgba(0,180,200,0.07) 0%, transparent 70%)",
              filter: "blur(64px)",
            }}
          />
          {/* Nebula blob — lower left, deeper cyan */}
          <div
            style={{
              position: "absolute",
              bottom: "22%",
              left: "12%",
              width: "32vw",
              height: "26vw",
              borderRadius: "50%",
              background: "radial-gradient(ellipse at center, rgba(0,150,180,0.06) 0%, transparent 70%)",
              filter: "blur(52px)",
            }}
          />
          {/* Nebula blob — upper centre, subtle indigo */}
          <div
            style={{
              position: "absolute",
              top: "8%",
              left: "32%",
              width: "28vw",
              height: "22vw",
              borderRadius: "50%",
              background: "radial-gradient(ellipse at center, rgba(0,100,160,0.05) 0%, transparent 70%)",
              filter: "blur(44px)",
            }}
          />
        </div>
        {/* All page content renders above the starfield */}
        <div className="relative" style={{ zIndex: 10 }}>
          <TooltipProvider>
            <DesktopReadyGuard>
              <SetupGuard>{children}</SetupGuard>
            </DesktopReadyGuard>
          </TooltipProvider>
        </div>
      </body>
    </html>
  );
}
