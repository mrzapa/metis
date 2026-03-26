import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/gguf",
  useRouter: () => ({ replace: replaceMock }),
}));

const { default: GgufPage } = await import("./page");

describe("GgufPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to /settings?tab=models", () => {
    render(<GgufPage />);
    expect(replaceMock).toHaveBeenCalledWith("/settings?tab=models");
  });
});