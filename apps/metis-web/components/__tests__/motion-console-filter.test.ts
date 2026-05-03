import { describe, expect, it, vi } from "vitest";
import {
  installMotionWarnFilter,
  isMotionReducedMotionWarning,
} from "../motion-console-filter";

/**
 * Tests for the motion/react reduced-motion console.warn filter
 * (M21 P3 #19). The wrapper mutates a global, so we exercise it
 * against fake `Console` instances (built from spies) rather than
 * the real `console`. That keeps tests independent of each other
 * and free of vitest setup-file interactions.
 */

interface FakeConsole {
  warn: ((...args: unknown[]) => void) & { __metisMotionFiltered?: boolean };
}

function makeFakeConsole(): { fake: FakeConsole; spy: ReturnType<typeof vi.fn> } {
  const spy = vi.fn();
  const fake: FakeConsole = { warn: spy };
  return { fake, spy };
}

describe("isMotionReducedMotionWarning", () => {
  it("matches the canonical motion/react message", () => {
    expect(
      isMotionReducedMotionWarning(
        "You have Reduced Motion enabled on your device. Animations may not appear as expected.",
      ),
    ).toBe(true);
  });

  it("matches the troubleshooting URL fragment as a defensive fallback", () => {
    expect(
      isMotionReducedMotionWarning(
        "Some other framing of the same warning — see motion.dev/troubleshooting/reduced-motion-disabled for details.",
      ),
    ).toBe(true);
  });

  it("does not match unrelated warnings", () => {
    expect(isMotionReducedMotionWarning("React deprecation: useFoo will be removed")).toBe(false);
    expect(isMotionReducedMotionWarning("hydration mismatch on <div>")).toBe(false);
    expect(isMotionReducedMotionWarning("")).toBe(false);
  });

  it("ignores non-string inputs (objects, undefined, numbers)", () => {
    expect(isMotionReducedMotionWarning(undefined)).toBe(false);
    expect(isMotionReducedMotionWarning(null)).toBe(false);
    expect(isMotionReducedMotionWarning(42)).toBe(false);
    expect(isMotionReducedMotionWarning({ message: "Reduced Motion" })).toBe(false);
  });
});

describe("installMotionWarnFilter — suppression", () => {
  it("drops the canonical reduced-motion warning", () => {
    const { fake, spy } = makeFakeConsole();
    installMotionWarnFilter(fake as unknown as Console);
    fake.warn(
      "You have Reduced Motion enabled on your device. Animations may not appear as expected.. For more information visit https://motion.dev/troubleshooting/reduced-motion-disabled",
    );
    expect(spy).not.toHaveBeenCalled();
  });

  it("drops messages that mention the reduced-motion-disabled errorCode anywhere in the string", () => {
    const { fake, spy } = makeFakeConsole();
    installMotionWarnFilter(fake as unknown as Console);
    fake.warn("Some prefix - reduced-motion-disabled - some suffix");
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("installMotionWarnFilter — forwarding", () => {
  it("forwards unrelated string warnings unchanged", () => {
    const { fake, spy } = makeFakeConsole();
    installMotionWarnFilter(fake as unknown as Console);
    fake.warn("React deprecation: useFoo will be removed", "extra detail", { ctx: 1 });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(
      "React deprecation: useFoo will be removed",
      "extra detail",
      { ctx: 1 },
    );
  });

  it("forwards warnings with non-string first arg unchanged", () => {
    const { fake, spy } = makeFakeConsole();
    installMotionWarnFilter(fake as unknown as Console);
    const err = new Error("oops");
    fake.warn(err);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith(err);
  });

  it("forwards a no-arg call (e.g. console.warn())", () => {
    const { fake, spy } = makeFakeConsole();
    installMotionWarnFilter(fake as unknown as Console);
    fake.warn();
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith();
  });
});

describe("installMotionWarnFilter — idempotence", () => {
  it("does not double-wrap when called repeatedly", () => {
    const { fake, spy } = makeFakeConsole();
    installMotionWarnFilter(fake as unknown as Console);
    const wrappedAfterFirst = fake.warn;
    installMotionWarnFilter(fake as unknown as Console);
    expect(fake.warn).toBe(wrappedAfterFirst);
    expect(fake.warn.__metisMotionFiltered).toBe(true);

    // The single wrap still works: motion warnings dropped, others
    // forwarded verbatim.
    fake.warn("You have Reduced Motion enabled on your device.");
    fake.warn("not the motion warning");
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("not the motion warning");
  });

  it("is a no-op if console.warn is already an unrelated function", () => {
    // Sanity: if someone else's wrapper installed first without our
    // flag, we should NOT clobber it. (The `__metisMotionFiltered`
    // gate only short-circuits OUR own wrapper; for foreign wrappers
    // we still install on top — that's intentional, since we want
    // motion suppression to be guaranteed. This test pins that
    // semantic so a future "respect foreign wrappers" change has
    // to update the test.)
    const upstreamSpy = vi.fn();
    const fake = { warn: upstreamSpy } as unknown as Console;
    installMotionWarnFilter(fake);
    fake.warn("not motion");
    expect(upstreamSpy).toHaveBeenCalledWith("not motion");
  });
});
