import { act, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
  NetworkAuditEvent,
  NetworkAuditProvider,
  NetworkAuditStreamFrame,
  RecentCountResponse,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/settings/privacy",
  useSearchParams: () => new URLSearchParams(),
}));

// Lightweight PageChrome stub — avoids pulling in the WebGPUCompanionProvider
// and MetisCompanionDock (each drags hundreds of modules and unrelated side
// effects into this test).
vi.mock("@/components/shell/page-chrome", () => ({
  PageChrome: ({
    title,
    description,
    children,
  }: {
    title: string;
    description: string;
    children: React.ReactNode;
  }) => (
    <div>
      <h1>{title}</h1>
      <p>{description}</p>
      <div>{children}</div>
    </div>
  ),
}));

// Capture the stream listener so the test can fire SSE frames on demand.
const streamListeners: Array<(frame: NetworkAuditStreamFrame) => void> = [];
const streamStatusListeners: Array<
  (status: "connecting" | "open" | "reconnecting" | "closed") => void
> = [];
const streamUnsubscribers: Array<() => void> = [];

vi.mock("@/lib/api", async () => {
  return {
    fetchNetworkAuditEvents: vi.fn(),
    fetchNetworkAuditProviders: vi.fn(),
    fetchNetworkAuditRecentCount: vi.fn(),
    subscribeNetworkAuditStream: vi.fn(
      (
        listener: (frame: NetworkAuditStreamFrame) => void,
        options?: {
          onStatusChange?: (
            status: "connecting" | "open" | "reconnecting" | "closed",
          ) => void;
        },
      ) => {
        streamListeners.push(listener);
        if (options?.onStatusChange) {
          streamStatusListeners.push(options.onStatusChange);
        }
        const unsub = vi.fn(() => {
          const idx = streamListeners.indexOf(listener);
          if (idx >= 0) streamListeners.splice(idx, 1);
        });
        streamUnsubscribers.push(unsub);
        return unsub;
      },
    ),
  };
});

// Import after the mocks are installed.
const api = await import("@/lib/api");
const fetchNetworkAuditEvents = api.fetchNetworkAuditEvents as ReturnType<
  typeof vi.fn
>;
const fetchNetworkAuditProviders = api.fetchNetworkAuditProviders as ReturnType<
  typeof vi.fn
>;
const fetchNetworkAuditRecentCount =
  api.fetchNetworkAuditRecentCount as ReturnType<typeof vi.fn>;

const { default: PrivacySettingsPage } = await import("../page");

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeEvent(overrides: Partial<NetworkAuditEvent> = {}): NetworkAuditEvent {
  return {
    id: "event-1",
    timestamp: "2026-04-19T12:34:56Z",
    method: "POST",
    url_host: "api.openai.com",
    url_path_prefix: "/v1/chat/completions",
    query_params_stored: false,
    provider_key: "openai",
    trigger_feature: "chat.direct",
    size_bytes_in: 1024,
    size_bytes_out: 512,
    latency_ms: 320,
    status_code: 200,
    user_initiated: true,
    blocked: false,
    source: "sdk_invocation",
    ...overrides,
  };
}

function makeProvider(
  overrides: Partial<NetworkAuditProvider> = {},
): NetworkAuditProvider {
  return {
    key: "openai",
    display_name: "OpenAI",
    category: "llm",
    kill_switch_setting_key: "provider_block_llm",
    blocked: false,
    events_7d: 12,
    last_call_at: "2026-04-19T12:20:00Z",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Default mock responses (reset between tests)
// ---------------------------------------------------------------------------

function stubDefaults(): void {
  fetchNetworkAuditRecentCount.mockResolvedValue({
    count: 0,
    window_seconds: 300,
  } satisfies RecentCountResponse);
  fetchNetworkAuditProviders.mockResolvedValue([]);
  fetchNetworkAuditEvents.mockResolvedValue([]);
}

beforeEach(() => {
  streamListeners.length = 0;
  streamStatusListeners.length = 0;
  streamUnsubscribers.length = 0;
  stubDefaults();
});

afterEach(() => {
  vi.clearAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PrivacySettingsPage — structure", () => {
  it("renders the three section headings on mount", async () => {
    render(<PrivacySettingsPage />);

    // Wait for async effects to flush. The headings are static and appear
    // on the very first render, but findByRole also awaits any pending
    // promises so we don't leave effects mid-flight across tests.
    expect(
      await screen.findByRole("heading", { level: 2, name: /airplane mode/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /providers/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /live event feed/i }),
    ).toBeInTheDocument();
  });
});

describe("PrivacySettingsPage — Section 1 (airplane / recent count)", () => {
  it("populates the indicator from the mocked recent-count response", async () => {
    fetchNetworkAuditRecentCount.mockResolvedValue({
      count: 7,
      window_seconds: 300,
    });

    render(<PrivacySettingsPage />);

    await waitFor(() => {
      expect(fetchNetworkAuditRecentCount).toHaveBeenCalled();
    });

    const indicator = await screen.findByText("7");
    expect(indicator).toBeInTheDocument();
    expect(screen.getByText(/in the last 5m/i)).toBeInTheDocument();
  });

  it("renders the airplane toggle disabled with a Phase 5c note", async () => {
    render(<PrivacySettingsPage />);

    const toggle = (await screen.findByLabelText(
      /enable airplane mode/i,
    )) as HTMLInputElement;
    expect(toggle).toBeDisabled();
    expect(
      screen.getByText(/toggle available in the next update \(phase 5c\)/i),
    ).toBeInTheDocument();
  });
});

describe("PrivacySettingsPage — Section 2 (providers matrix)", () => {
  it("populates the provider matrix rows from the mocked response", async () => {
    fetchNetworkAuditProviders.mockResolvedValue([
      makeProvider({ key: "openai", display_name: "OpenAI", events_7d: 12 }),
      makeProvider({
        key: "anthropic",
        display_name: "Anthropic",
        events_7d: 3,
        last_call_at: null,
        blocked: true,
        category: "llm",
      }),
    ]);

    render(<PrivacySettingsPage />);

    await screen.findByText("OpenAI");
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
  });

  it("renders 'Never' for providers with last_call_at null", async () => {
    fetchNetworkAuditProviders.mockResolvedValue([
      makeProvider({
        key: "pinecone",
        display_name: "Pinecone",
        events_7d: 0,
        last_call_at: null,
      }),
    ]);

    render(<PrivacySettingsPage />);

    await screen.findByText("Pinecone");
    expect(screen.getByText("Never")).toBeInTheDocument();
  });

  it("filters out the 'unclassified' provider defensively", async () => {
    fetchNetworkAuditProviders.mockResolvedValue([
      makeProvider({ key: "openai", display_name: "OpenAI" }),
      makeProvider({
        key: "unclassified",
        display_name: "Unclassified",
        events_7d: 99,
      }),
    ]);

    render(<PrivacySettingsPage />);

    await screen.findByText("OpenAI");
    expect(screen.queryByText("Unclassified")).not.toBeInTheDocument();
  });

  it("sorts providers by events_7d DESC, then alphabetically", async () => {
    fetchNetworkAuditProviders.mockResolvedValue([
      makeProvider({
        key: "zeta",
        display_name: "Zeta",
        events_7d: 5,
      }),
      makeProvider({
        key: "alpha",
        display_name: "Alpha",
        events_7d: 5,
      }),
      makeProvider({
        key: "beta",
        display_name: "Beta",
        events_7d: 42,
      }),
    ]);

    render(<PrivacySettingsPage />);

    await screen.findByText("Beta");

    const table = screen
      .getByRole("heading", { level: 2, name: /providers/i })
      .closest("section") as HTMLElement;
    const rows = within(table).getAllByRole("row");
    // row[0] is <thead>; order after that is data rows in sorted order.
    const dataRowTexts = rows.slice(1).map((row) => row.textContent ?? "");
    // Beta (42) comes before Alpha (5) which comes before Zeta (5).
    const betaIdx = dataRowTexts.findIndex((t) => t.includes("Beta"));
    const alphaIdx = dataRowTexts.findIndex((t) => t.includes("Alpha"));
    const zetaIdx = dataRowTexts.findIndex((t) => t.includes("Zeta"));
    expect(betaIdx).toBeGreaterThanOrEqual(0);
    expect(alphaIdx).toBeGreaterThanOrEqual(0);
    expect(zetaIdx).toBeGreaterThanOrEqual(0);
    expect(betaIdx).toBeLessThan(alphaIdx);
    expect(alphaIdx).toBeLessThan(zetaIdx);
  });
});

describe("PrivacySettingsPage — Section 3 (live event feed)", () => {
  it("populates the event feed from the mocked events response on mount", async () => {
    fetchNetworkAuditEvents.mockResolvedValue([
      makeEvent({ id: "ev-1", trigger_feature: "rss.poll" }),
    ]);

    render(<PrivacySettingsPage />);

    await screen.findByText("rss.poll");
    expect(fetchNetworkAuditEvents).toHaveBeenCalled();
  });

  it("appends a new event when the mocked SSE emits an audit_event frame", async () => {
    fetchNetworkAuditEvents.mockResolvedValue([
      makeEvent({ id: "ev-initial", trigger_feature: "chat.direct" }),
    ]);

    render(<PrivacySettingsPage />);

    await screen.findByText("chat.direct");

    // Fire a new event through the SSE subscription.
    expect(streamListeners.length).toBeGreaterThan(0);
    act(() => {
      streamListeners[0]!({
        type: "audit_event",
        event: makeEvent({
          id: "ev-live",
          trigger_feature: "news.fetch",
          timestamp: "2026-04-19T12:35:00Z",
        }),
      });
    });

    expect(await screen.findByText("news.fetch")).toBeInTheDocument();
  });

  it("preserves streamed events when the initial hydrate resolves", async () => {
    // Regression for PR #521 Codex P1: mount races two effects —
    // fetchNetworkAuditEvents and subscribeNetworkAuditStream. If an
    // audit_event frame arrives before the hydrate snapshot resolves,
    // a replace-style setEvents(snapshot) would silently drop it. The
    // merge-and-dedupe hydrate path keeps the streamed row visible.
    let resolveHydrate: (rows: NetworkAuditEvent[]) => void = () => undefined;
    fetchNetworkAuditEvents.mockImplementation(
      () =>
        new Promise<NetworkAuditEvent[]>((resolve) => {
          resolveHydrate = resolve;
        }),
    );

    render(<PrivacySettingsPage />);

    // SSE subscribe fires synchronously on mount — wait for the listener
    // to register before firing a frame through it.
    await waitFor(() => expect(streamListeners.length).toBeGreaterThan(0));

    // A live event arrives before the hydrate resolves. appendEvent()
    // puts it in the buffer.
    act(() => {
      streamListeners[0]!({
        type: "audit_event",
        event: makeEvent({
          id: "ev-live-race",
          trigger_feature: "live.before.hydrate",
          timestamp: "2026-04-19T13:00:00Z",
        }),
      });
    });
    expect(
      await screen.findByText("live.before.hydrate"),
    ).toBeInTheDocument();

    // Now the hydrate resolves with a historical snapshot.
    await act(async () => {
      resolveHydrate([
        makeEvent({
          id: "ev-hydrate-1",
          trigger_feature: "historical.one",
          timestamp: "2026-04-19T12:30:00Z",
        }),
      ]);
    });

    // Both the historical row AND the pre-hydrate streamed row must
    // render. A replace-style assignment would have dropped the
    // streamed row.
    expect(
      await screen.findByText("historical.one"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("live.before.hydrate"),
    ).toBeInTheDocument();
  });

  it("dedupes by id when hydrate overlaps with streamed events", async () => {
    // If the backend's snapshot happens to include an event that was
    // also delivered via SSE (common when stream and snapshot overlap),
    // the id-based dedupe keeps only one copy.
    let resolveHydrate: (rows: NetworkAuditEvent[]) => void = () => undefined;
    fetchNetworkAuditEvents.mockImplementation(
      () =>
        new Promise<NetworkAuditEvent[]>((resolve) => {
          resolveHydrate = resolve;
        }),
    );

    render(<PrivacySettingsPage />);
    await waitFor(() => expect(streamListeners.length).toBeGreaterThan(0));

    act(() => {
      streamListeners[0]!({
        type: "audit_event",
        event: makeEvent({
          id: "ev-overlap",
          trigger_feature: "overlap.event",
          timestamp: "2026-04-19T13:00:00Z",
        }),
      });
    });
    await screen.findByText("overlap.event");

    // Hydrate also contains the same id.
    await act(async () => {
      resolveHydrate([
        makeEvent({
          id: "ev-overlap",
          trigger_feature: "overlap.event",
          timestamp: "2026-04-19T13:00:00Z",
        }),
      ]);
    });

    // Still exactly one row for this trigger — not two.
    const cells = screen.getAllByText("overlap.event");
    expect(cells.length).toBe(1);
  });

  it("shows 'Audit store unavailable' banner on a no_store frame", async () => {
    render(<PrivacySettingsPage />);

    await waitFor(() => expect(streamListeners.length).toBeGreaterThan(0));

    act(() => {
      streamListeners[0]!({ type: "no_store" });
    });

    expect(
      await screen.findByText(/audit store unavailable/i),
    ).toBeInTheDocument();
  });

  it("shows a Store-unavailable status badge when no_store is received", async () => {
    render(<PrivacySettingsPage />);
    await waitFor(() => expect(streamListeners.length).toBeGreaterThan(0));

    act(() => {
      streamListeners[0]!({ type: "no_store" });
    });

    // Both the banner ("Audit store unavailable") and the status pill
    // ("Store unavailable") should render. Pin specifically to the pill.
    expect(
      await screen.findByText(/^Store unavailable$/),
    ).toBeInTheDocument();
  });

  it("renders a 'Connecting…' status on first mount before any frame arrives", async () => {
    render(<PrivacySettingsPage />);
    // The status badge is rendered synchronously on first render.
    expect(screen.getByText(/connecting…/i)).toBeInTheDocument();
  });

  it("flips to 'Live' after the first audit_event frame arrives", async () => {
    render(<PrivacySettingsPage />);
    await waitFor(() => expect(streamListeners.length).toBeGreaterThan(0));

    act(() => {
      streamListeners[0]!({
        type: "audit_event",
        event: makeEvent({ id: "ev-live-1" }),
      });
    });

    expect(await screen.findByText(/^Live$/)).toBeInTheDocument();
  });
});

describe("PrivacySettingsPage — Section 3 (reconnect signal)", () => {
  it("shows a 'Reconnecting…' state when the subscriber reports reconnecting", async () => {
    render(<PrivacySettingsPage />);
    await waitFor(() => expect(streamStatusListeners.length).toBeGreaterThan(0));

    act(() => {
      streamStatusListeners[0]!("reconnecting");
    });

    expect(await screen.findByText(/reconnecting…/i)).toBeInTheDocument();
  });

  it("stays on 'Connecting…' when no frames arrive", async () => {
    render(<PrivacySettingsPage />);
    // Even after effects have flushed and the subscriber is attached,
    // without any frames we stay on the initial status.
    await waitFor(() => expect(streamListeners.length).toBeGreaterThan(0));
    expect(screen.getByText(/connecting…/i)).toBeInTheDocument();
  });
});
