import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render } from "@testing-library/react";

import { useHashScroll } from "../use-hash-scroll";

function Harness({ ready }: { ready: boolean }) {
  useHashScroll(ready);
  return (
    <div>
      <section id="alpha">Alpha</section>
      <section id="beta">Beta</section>
    </div>
  );
}

describe("useHashScroll", () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    scrollIntoView.mockClear();
    // jsdom doesn't implement scrollIntoView; assign a stub so the
    // hook's call is observable.
    Element.prototype.scrollIntoView = scrollIntoView;
    // requestAnimationFrame in jsdom is async-ish; collapse it to
    // sync so the test reads naturally.
    vi.spyOn(window, "requestAnimationFrame").mockImplementation(
      (cb: FrameRequestCallback) => {
        cb(0);
        return 0;
      },
    );
  });

  afterEach(() => {
    window.history.replaceState(null, "", window.location.pathname);
    vi.restoreAllMocks();
  });

  it("scrolls to the hash target once ready flips true", () => {
    window.history.replaceState(null, "", "#beta");
    const { rerender } = render(<Harness ready={false} />);
    expect(scrollIntoView).not.toHaveBeenCalled();

    rerender(<Harness ready />);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("is a no-op when the hash is empty", () => {
    window.history.replaceState(null, "", window.location.pathname);
    render(<Harness ready />);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("is a no-op when the hash points to an unknown id", () => {
    window.history.replaceState(null, "", "#nonexistent");
    render(<Harness ready />);
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it("re-scrolls on hashchange events while mounted", () => {
    window.history.replaceState(null, "", "#alpha");
    render(<Harness ready />);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    act(() => {
      window.history.replaceState(null, "", "#beta");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });

  it("removes the hashchange listener on unmount", () => {
    window.history.replaceState(null, "", "#alpha");
    const { unmount } = render(<Harness ready />);
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    unmount();

    act(() => {
      window.history.replaceState(null, "", "#beta");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });
});
