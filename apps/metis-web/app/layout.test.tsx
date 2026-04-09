import React from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/font/google", () => ({
  Inter: () => ({ variable: "--font-sans" }),
  Space_Grotesk: () => ({ variable: "--font-display" }),
}));

vi.mock("@/components/ui/tooltip", () => ({
  TooltipProvider: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

vi.mock("@/components/setup-guard", () => ({
  SetupGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

vi.mock("@/components/desktop-ready", () => ({
  DesktopReadyGuard: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

const { default: RootLayout } = await import("./layout");

describe("RootLayout", () => {
  it("pins the UI variant to motion", () => {
    const layout = RootLayout({ children: <div>child</div> });

    expect(layout.props["data-ui-variant"]).toBe("motion");
  });
});
