import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  redirect: vi.fn(),
}));

const { redirect } = await import("next/navigation");
const { default: BrainPage } = await import("./page");

describe("BrainPage", () => {
  it("redirects legacy /brain route to the landing view", () => {
    BrainPage();
    expect(redirect).toHaveBeenCalledWith("/");
  });
});
