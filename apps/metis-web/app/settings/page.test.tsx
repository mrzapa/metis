import React from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({
    get: () => null,
  }),
}));

vi.mock("@/components/ui/button", () => ({
  Button: (props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    size?: string;
    variant?: string;
  }) => {
    const { children, size, variant, ...buttonProps } = props;
    void size;
    void variant;
    return <button {...buttonProps}>{children}</button>;
  },
}));

vi.mock("@/components/ui/input", () => ({
  Input: (props: React.InputHTMLAttributes<HTMLInputElement>) => <input {...props} />,
}));

vi.mock("@/components/ui/textarea", () => ({
  Textarea: (props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea {...props} />,
}));

vi.mock("@/components/ui/separator", () => ({
  Separator: () => <hr />,
}));

vi.mock("@/components/ui/tabs", () => ({
  Tabs: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsList: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TabsTrigger: (props: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    value?: string;
  }) => {
    const { children, value, ...buttonProps } = props;
    void value;
    return <button {...buttonProps}>{children}</button>;
  },
}));

vi.mock("@/components/ui/animated-lucide-icon", () => ({
  AnimatedLucideIcon: () => <span data-testid="mock-icon" />,
}));

vi.mock("@/components/ui/tooltip", () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipProvider: ({ children }: React.PropsWithChildren) => <>{children}</>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

vi.mock("@/components/shell/page-chrome", () => ({
  PageChrome: ({
    children,
    title,
  }: React.PropsWithChildren<{ title: string }>) => (
    <div>
      <h1>{title}</h1>
      {children}
    </div>
  ),
}));

vi.mock("@/components/gguf/gguf-models-panel", () => ({
  GgufModelsPanel: () => <div>GGUF models panel</div>,
}));

vi.mock("lucide-react", () => {
  const Icon = () => null;
  return {
    AlertCircle: Icon,
    CheckCircle2: Icon,
    HelpCircle: Icon,
    Info: Icon,
    Loader2: Icon,
    RotateCcw: Icon,
    Search: Icon,
    TriangleAlert: Icon,
  };
});

vi.mock("@/lib/api", () => ({
  fetchAssistantSettings: vi.fn(),
  fetchSettings: vi.fn(),
  updateAssistantSettings: vi.fn(),
  updateSettings: vi.fn(),
}));

const { fetchAssistantSettings, fetchSettings } = await import("@/lib/api");
const { default: SettingsPage } = await import("./page");

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchSettings).mockResolvedValue({});
    vi.mocked(fetchAssistantSettings).mockResolvedValue({
      assistant_identity: {},
      assistant_policy: {},
      assistant_runtime: {},
    } as Awaited<ReturnType<typeof fetchAssistantSettings>>);
  });

  it("does not render the interface-direction section", async () => {
    render(<SettingsPage />);

    expect(await screen.findByText("Low-level settings")).toBeInTheDocument();
    expect(screen.queryByText("Interface direction")).not.toBeInTheDocument();
    expect(screen.queryByText("Switch the live treatment for panes, toggles, sliders, and the chat composer.")).not.toBeInTheDocument();
    expect(screen.queryByText("Motion")).not.toBeInTheDocument();
  });
});
