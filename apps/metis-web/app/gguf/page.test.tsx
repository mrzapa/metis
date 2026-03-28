import { beforeEach, describe, expect, it, vi } from "vitest";

const redirectMock = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: redirectMock,
}));

const { default: GgufPage } = await import("./page");

describe("GgufPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("redirects to /settings?tab=models", () => {
    GgufPage();
    expect(redirectMock).toHaveBeenCalledWith("/settings?tab=models");
  });
});