import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const { NyxChatEntry } = await import("../nyx-chat-entry");

describe("NyxChatEntry", () => {
  it("renders browse and stable preview entry points", () => {
    render(<NyxChatEntry />);

    expect(screen.getByRole("link", { name: /Browse catalog/i })).toHaveAttribute(
      "href",
      "/library",
    );
    expect(screen.getByRole("link", { name: /Preview glow-card/i })).toHaveAttribute(
      "href",
      "/library/glow-card",
    );
    expect(screen.getByRole("link", { name: /GitHub Repo Card/i })).toHaveAttribute(
      "href",
      "/library/github-repo-card",
    );
  });
});