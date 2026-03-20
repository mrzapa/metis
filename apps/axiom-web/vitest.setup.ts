import "@testing-library/jest-dom/vitest";

if (!globalThis.requestAnimationFrame) {
  globalThis.requestAnimationFrame = (callback: FrameRequestCallback): number =>
    window.setTimeout(() => callback(performance.now()), 0);
}

if (!globalThis.cancelAnimationFrame) {
  globalThis.cancelAnimationFrame = (handle: number): void => {
    window.clearTimeout(handle);
  };
}

if (
  typeof SVGElement !== "undefined" &&
  !("setPointerCapture" in SVGElement.prototype)
) {
  SVGElement.prototype.setPointerCapture = () => {};
}

if (
  typeof SVGElement !== "undefined" &&
  !("releasePointerCapture" in SVGElement.prototype)
) {
  SVGElement.prototype.releasePointerCapture = () => {};
}
