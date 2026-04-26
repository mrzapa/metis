import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type {
  AnchorHTMLAttributes,
  HTMLAttributes,
  PropsWithChildren,
  ReactNode,
} from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchSession,
  fetchSettings,
  submitRunAction,
  updateSettings,
} from "@/lib/api";
import type { SessionDetail, SessionSummary } from "@/lib/api";
import type { NyxInstallAction, NyxInstallActionResult } from "@/lib/chat-types";

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

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    refresh: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/chat",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    createSession: vi.fn(),
    fetchSession: vi.fn(),
    fetchSettings: vi.fn(),
    queryDirect: vi.fn(),
    queryKnowledgeSearch: vi.fn(),
    queryRagStream: vi.fn(),
    submitRunAction: vi.fn(),
    updateSettings: vi.fn(),
  };
});

vi.mock("@/components/shell/page-chrome", () => ({
  PageChrome: ({
    title,
    actions,
    heroAside,
    children,
  }: PropsWithChildren<{
    title: string;
    actions?: ReactNode;
    heroAside?: ReactNode;
  }>) => (
    <div>
      <h1>{title}</h1>
      {actions}
      {heroAside}
      {children}
    </div>
  ),
}));

vi.mock("@/components/chat/resizable-panels", () => ({
  ResizablePanels: ({ panels }: { panels: Array<{ children: ReactNode }> }) => (
    <div>
      {panels.map((panel, index) => (
        <div key={index}>{panel.children}</div>
      ))}
    </div>
  ),
}));

vi.mock("@/components/chat/sessions-panel", () => ({
  SessionsPanel: ({ onSelect }: { onSelect: (id: string) => void }) => (
    <button type="button" onClick={() => onSelect("session-1")}>
      Load mocked session
    </button>
  ),
}));

vi.mock("@/components/chat/evidence-panel", () => ({
  EvidencePanel: () => <div data-testid="mock-evidence-panel" />,
}));

vi.mock("@/components/library/nyx-chat-entry", () => ({
  NyxChatEntry: () => <div data-testid="mock-nyx-chat-entry" />,
}));

vi.mock("@/components/chat/assistant-copy-actions", () => ({
  AssistantCopyActions: () => null,
}));

vi.mock("@/components/chat/artifacts/arrow-artifact-boundary", () => ({
  ArrowArtifactBoundary: ({ content }: { content: string }) => <div>{content}</div>,
}));

vi.mock("@/components/chat/index-picker-dialog", () => ({
  IndexPickerDialog: () => null,
}));

vi.mock("@/components/chat/model-status-dialog", () => ({
  ModelStatusDialog: () => null,
}));

vi.mock("@/components/ui/animated-lucide-icon", () => ({
  AnimatedLucideIcon: () => <span data-testid="mock-icon" />,
}));

vi.mock("@/components/ui/scroll-area", async () => {
  const React = await import("react");
  const ScrollArea = React.forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
    ({ children, ...props }, ref) => (
      <div ref={ref} {...props}>
        <div data-slot="scroll-area-viewport">{children}</div>
      </div>
    ),
  );
  ScrollArea.displayName = "MockScrollArea";
  return { ScrollArea };
});

const { default: ChatPage } = await import("./page");

const ACTION_PAYLOAD = {
  action_id: "nyx-install:abc123",
  action_type: "nyx_install" as const,
  proposal_token: "nyx-proposal:abc123",
  component_count: 1,
  component_names: ["glow-card"],
};

function createSessionSummary(overrides?: Partial<SessionSummary>): SessionSummary {
  return {
    session_id: "session-1",
    created_at: "2026-03-29T12:00:00Z",
    updated_at: "2026-03-29T12:00:00Z",
    title: "Nyx action session",
    summary: "",
    active_profile: "default",
    mode: "direct",
    index_id: "",
    llm_provider: "openai",
    llm_model: "gpt-5.4",
    ...overrides,
  };
}

function createNyxAction(): NyxInstallAction {
  return {
    action_id: ACTION_PAYLOAD.action_id,
    action_type: "nyx_install",
    label: "Approve Nyx install proposal",
    summary: "Approve installing Glow Card.",
    requires_approval: true,
    run_action_endpoint: "/v1/runs/run-nyx-action/actions",
    payload: ACTION_PAYLOAD,
    proposal: {
      schema_version: "1.0",
      proposal_token: ACTION_PAYLOAD.proposal_token,
      source: "nyx_runtime",
      run_id: "run-nyx-action",
      query: "Design a glowing card.",
      intent_type: "interface_pattern_selection",
      matched_signals: ["pattern:card"],
      component_names: ACTION_PAYLOAD.component_names,
      component_count: ACTION_PAYLOAD.component_count,
      components: [
        {
          component_name: "glow-card",
          title: "Glow Card",
        },
      ],
    },
  };
}

function createSessionDetail(): SessionDetail {
  return {
    summary: createSessionSummary(),
    feedback: [],
    traces: { "run-nyx-action": [] },
    messages: [
      {
        role: "assistant",
        content: "Use Glow Card.",
        ts: "2026-03-29T12:00:01Z",
        run_id: "run-nyx-action",
        sources: [],
        actions: [createNyxAction()],
      },
    ],
  };
}

function createNyxResult(
  overrides?: Partial<NyxInstallActionResult>,
): NyxInstallActionResult {
  return {
    run_id: "run-nyx-action",
    approved: true,
    status: "success",
    action_id: ACTION_PAYLOAD.action_id,
    action_type: "nyx_install",
    proposal_token: ACTION_PAYLOAD.proposal_token,
    component_names: ["glow-card"],
    component_count: 1,
    execution_status: "completed",
    installer: {
      command: ["pnpm", "ui:add:nyx", "glow-card"],
      cwd: "/workspace/apps/metis-web",
      package_script: "ui:add:nyx",
      returncode: 0,
      stdout_excerpt: "installed glow-card",
    },
    ...overrides,
  };
}

async function renderLoadedChatPage() {
  vi.mocked(fetchSettings).mockResolvedValue({ selected_mode: "Q&A" });
  vi.mocked(updateSettings).mockResolvedValue({});
  vi.mocked(fetchSession).mockResolvedValue(createSessionDetail());

  render(<ChatPage />);

  fireEvent.click(screen.getByRole("button", { name: "Load mocked session" }));

  expect(await screen.findByText("Approve Nyx install proposal")).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
}

describe("ChatPage Nyx action approvals", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
        takeRecords = vi.fn(() => []);
        root = null;
        rootMargin = "0px";
        thresholds: number[] = [];
      },
    );
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.localStorage.clear();
  });

  it("updates the rendered Nyx action card from approve responses", async () => {
    vi.mocked(submitRunAction).mockResolvedValue(
      createNyxResult({
        component_names: ["glow-card", "orbit-panel"],
        component_count: 2,
        installer: {
          command: ["pnpm", "ui:add:nyx", "glow-card", "orbit-panel"],
          cwd: "/workspace/apps/metis-web",
          package_script: "ui:add:nyx",
          returncode: 0,
          stdout_excerpt: "installed glow-card and orbit-panel",
        },
      }),
    );

    await renderLoadedChatPage();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(submitRunAction).toHaveBeenCalledWith("run-nyx-action", {
        approved: true,
        action_id: ACTION_PAYLOAD.action_id,
        action_type: ACTION_PAYLOAD.action_type,
        proposal_token: ACTION_PAYLOAD.proposal_token,
        payload: ACTION_PAYLOAD,
      });
    });

    expect(await screen.findByText("Installer completed")).toBeInTheDocument();
    expect(screen.getByText("2 components • exit 0")).toBeInTheDocument();
    expect(screen.getByText("installed glow-card and orbit-panel")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("updates the rendered Nyx action card from deny responses", async () => {
    vi.mocked(submitRunAction).mockResolvedValue(
      createNyxResult({
        approved: false,
        status: "declined",
        execution_status: "declined",
        component_names: ["glow-card", "orbit-panel", "signal-chip"],
        component_count: 3,
        installer: null,
      }),
    );

    await renderLoadedChatPage();

    fireEvent.click(screen.getByRole("button", { name: "Deny" }));

    await waitFor(() => {
      expect(submitRunAction).toHaveBeenCalledWith("run-nyx-action", {
        approved: false,
        action_id: ACTION_PAYLOAD.action_id,
        action_type: ACTION_PAYLOAD.action_type,
        proposal_token: ACTION_PAYLOAD.proposal_token,
        payload: ACTION_PAYLOAD,
      });
    });

    expect(await screen.findByText("Proposal declined")).toBeInTheDocument();
    expect(screen.getByText("3 components")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Deny" })).not.toBeInTheDocument();
  });
});