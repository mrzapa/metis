import { render, screen } from "@testing-library/react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "../chat-panel";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & { href: string; children?: ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/components/chat/index-picker-dialog", () => ({
  IndexPickerDialog: () => null,
}));

vi.mock("@/components/chat/model-status-dialog", () => ({
  ModelStatusDialog: () => null,
}));

describe("ChatPanel", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
      },
    );
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a Heretic shortcut that deep-links to models settings", () => {
    render(<ChatPanel messages={[]} sessionMeta={null} />);

    expect(screen.getByRole("link", { name: "Heretic" })).toHaveAttribute(
      "href",
      "/settings?tab=models&modelsTab=heretic",
    );
  });
});
