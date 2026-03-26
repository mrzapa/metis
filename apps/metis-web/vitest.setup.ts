import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Clean up the React DOM after every test to prevent memory accumulation.
afterEach(() => {
  cleanup();
});

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

// In some environments (Vitest v4 on Windows when a --localstorage-file flag
// leaks into process.argv), jsdom initialises window.localStorage in a
// degraded state where setItem / getItem are not callable functions.  Guard
// against this so components that persist state via localStorage don't crash
// during rendering in tests.
if (typeof globalThis.localStorage?.setItem !== "function") {
  const _store: Record<string, string> = {};
  Object.defineProperty(globalThis, "localStorage", {
    value: {
      getItem: (key: string): string | null =>
        Object.prototype.hasOwnProperty.call(_store, key)
          ? (_store[key] as string)
          : null,
      setItem: (key: string, value: string): void => {
        _store[String(key)] = String(value);
      },
      removeItem: (key: string): void => {
        delete _store[key];
      },
      clear: (): void => {
        for (const k of Object.keys(_store)) delete _store[k];
      },
      key: (index: number): string | null =>
        Object.keys(_store)[index] ?? null,
      get length(): number {
        return Object.keys(_store).length;
      },
    } as Storage,
    writable: true,
    configurable: true,
  });
}

// ---------------------------------------------------------------------------
// Lightweight stubs for heavy animation / markdown rendering libraries.
//
// motion/react  — 200+ internal ESM modules (complex animation engine)
// react-markdown — unified + micromark + vfile + remark-* + rehype-* chain
//
// Loading either of these libraries individually causes V8 to parse, compile,
// and hold the full module graph in heap simultaneously (~4 GB total).
// Unit tests for component logic never need real animations or markdown
// rendering, so replacing them with trivial stubs eliminates the OOM without
// affecting any test assertion.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// @arrow-js/sandbox ships raw TypeScript source and pulls in quickjs-emscripten
// (2 MB WASM) + the full TypeScript compiler.  If the dynamic
// import("@arrow-js/sandbox") inside artifact-message-content.tsx ever fires
// without a mock, the process fills ~6 GB of heap in under 2 minutes.
//
// This global stub is the backstop for any test that doesn't provide its own
// vi.mock("@arrow-js/sandbox").  Tests that DO mock it (e.g.
// arrow-artifact-boundary.test.tsx) will override this stub with their own
// factory, which still fires instead of the real package.
// ---------------------------------------------------------------------------
vi.mock("@arrow-js/sandbox", () => ({
  sandbox: () => (parent: ParentNode): ParentNode => parent,
}));

vi.mock("motion/react", () => {
  // Use plain object exports only; Proxy-based mocks can conflict with Vitest's
  // own instrumentation in setup-time module loading.
  const passThrough = ({ children }: { children?: unknown }) => children ?? null;
  const animationControls = {
    start: () => Promise.resolve(),
    stop: () => undefined,
    set: () => undefined,
  };
  const motion = {
    div: passThrough,
    span: passThrough,
    p: passThrough,
    section: passThrough,
    article: passThrough,
    header: passThrough,
    footer: passThrough,
    nav: passThrough,
    main: passThrough,
    aside: passThrough,
    ul: passThrough,
    li: passThrough,
    button: passThrough,
    a: passThrough,
    form: passThrough,
    input: passThrough,
    textarea: passThrough,
    label: passThrough,
    h1: passThrough,
    h2: passThrough,
    h3: passThrough,
    img: passThrough,
    svg: passThrough,
    path: passThrough,
    circle: passThrough,
    rect: passThrough,
    line: passThrough,
    polyline: passThrough,
    polygon: passThrough,
    g: passThrough,
    defs: passThrough,
    linearGradient: passThrough,
    radialGradient: passThrough,
    stop: passThrough,
    clipPath: passThrough,
    mask: passThrough,
    foreignObject: passThrough,
  };
  return {
    motion,
    AnimatePresence: passThrough,
    useReducedMotion: () => false,
    useAnimation: () => animationControls,
  };
});

vi.mock("react-markdown", () => ({
  // Pass children through directly so text content is still in the DOM
  // and assertions like getByText("some text") continue to pass.
  default: ({ children }: { children: unknown }) => children,
}));

// Recharts can pull in a large graph of chart primitives and utilities.
// For unit tests, simple pass-through stubs are sufficient.
// The internal Proxy variable was a no-op spread (empty target) and has been
// removed to eliminate unnecessary Proxy surface area.
vi.mock("recharts", () => {
  const passthrough = ({ children }: { children?: unknown }) => children ?? null;
  const noop = () => null;
  return {
    ResponsiveContainer: passthrough,
    AreaChart: passthrough,
    BarChart: passthrough,
    LineChart: passthrough,
    PieChart: passthrough,
    RadarChart: passthrough,
    RadialBarChart: passthrough,
    ScatterChart: passthrough,
    ComposedChart: passthrough,
    XAxis: noop,
    YAxis: noop,
    CartesianGrid: noop,
    Tooltip: noop,
    Legend: noop,
    Line: noop,
    Bar: noop,
    Area: noop,
    Pie: noop,
    Radar: noop,
    Cell: noop,
  };
});

// D3 is a broad package surface.  Returning {} keeps imports lightweight in
// tests; components that use d3 heavily are mocked by individual test files.
// Note: the old Proxy-as-module-root with get:()=>noop intercepts the "then"
// key, making the factory result look like a thenable and confusing Vitest's
// async module-resolution path (which calls await on the factory return value).
vi.mock("d3", () => ({}));

// Some components still import framer-motion directly.
// Same passThrough fix as motion/react above — strings returned by the old
// Proxy get trap are not valid Proxy targets for Vitest's spy layer.
vi.mock("framer-motion", () => {
  const passThrough = ({ children }: { children?: unknown }) => children ?? null;
  const animationControls = {
    start: () => Promise.resolve(),
    stop: () => undefined,
    set: () => undefined,
  };
  const motion = {
    div: passThrough,
    span: passThrough,
    p: passThrough,
    section: passThrough,
    article: passThrough,
    header: passThrough,
    footer: passThrough,
    nav: passThrough,
    main: passThrough,
    aside: passThrough,
    ul: passThrough,
    li: passThrough,
    button: passThrough,
    a: passThrough,
    form: passThrough,
    input: passThrough,
    textarea: passThrough,
    label: passThrough,
    h1: passThrough,
    h2: passThrough,
    h3: passThrough,
    img: passThrough,
    svg: passThrough,
    path: passThrough,
    circle: passThrough,
    rect: passThrough,
    line: passThrough,
    polyline: passThrough,
    polygon: passThrough,
    g: passThrough,
    defs: passThrough,
    linearGradient: passThrough,
    radialGradient: passThrough,
    stop: passThrough,
    clipPath: passThrough,
    mask: passThrough,
    foreignObject: passThrough,
  };
  return {
    motion,
    AnimatePresence: passThrough,
    useAnimation: () => animationControls,
  };
});

// lucide-react: explicit plain-object stub enumerating all icons used across
// metis-web source files.  The previous Proxy-as-module-root crashed Vitest
// v4's spy instrumentation: it resolved each named export to `Icon`, then the
// spy layer accessed `Icon.<anyProp>` → undefined, then tried
// new Proxy(undefined, handler) → TypeError.
vi.mock("lucide-react", () => {
  const Icon = () => null;
  return {
    Activity: Icon,
    AlertCircle: Icon,
    AlertTriangle: Icon,
    Bot: Icon,
    Brain: Icon,
    Check: Icon,
    CheckCircle2: Icon,
    CheckIcon: Icon,
    ChevronDown: Icon,
    ChevronRightIcon: Icon,
    ChevronUp: Icon,
    Clock: Icon,
    ClipboardCopy: Icon,
    Copy: Icon,
    Cpu: Icon,
    Database: Icon,
    FileCheck: Icon,
    FileText: Icon,
    FolderOpen: Icon,
    HardDrive: Icon,
    Home: Icon,
    Info: Icon,
    LibraryBig: Icon,
    List: Icon,
    Loader2: Icon,
    MessageSquare: Icon,
    MessageSquarePlus: Icon,
    MoreHorizontal: Icon,
    NotebookText: Icon,
    Pause: Icon,
    Play: Icon,
    RefreshCw: Icon,
    RotateCcw: Icon,
    Search: Icon,
    SendHorizontal: Icon,
    Settings: Icon,
    Settings2: Icon,
    ShieldAlert: Icon,
    Square: Icon,
    ThumbsDown: Icon,
    ThumbsUp: Icon,
    Trash2: Icon,
    TriangleAlert: Icon,
    Upload: Icon,
    UploadCloud: Icon,
    WifiOff: Icon,
    X: Icon,
    XCircle: Icon,
    XIcon: Icon,
  };
});
