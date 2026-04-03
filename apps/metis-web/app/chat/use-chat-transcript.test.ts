import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useChatTranscript } from "@/app/chat/use-chat-transcript";
import type {
  ChatMessageContent,
  NyxInstallAction,
  NyxInstallActionResult,
} from "@/lib/chat-types";

function createNyxAction(): NyxInstallAction {
  return {
    action_id: "action-1",
    action_type: "nyx_install",
    label: "Install Nyx components",
    summary: "Install glow-card",
    requires_approval: true,
    run_action_endpoint: "/v1/runs/run-1/actions",
    payload: {
      action_id: "action-1",
      action_type: "nyx_install",
      proposal_token: "proposal-1",
      component_count: 1,
      component_names: ["glow-card"],
    },
    proposal: {
      schema_version: "1.0",
      proposal_token: "proposal-1",
      component_names: ["glow-card"],
      component_count: 1,
      components: [
        {
          component_name: "glow-card",
          title: "Glow Card",
        },
      ],
    },
  };
}

function createNyxResult(
  overrides?: Partial<NyxInstallActionResult>,
): NyxInstallActionResult {
  return {
    run_id: "run-1",
    approved: true,
    status: "success",
    action_id: "action-1",
    action_type: "nyx_install",
    proposal_token: "proposal-1",
    component_names: ["glow-card"],
    component_count: 1,
    execution_status: "completed",
    installer: {
      command: ["pnpm", "dlx", "shadcn@latest", "add", "@nyx/glow-card"],
      cwd: "/workspace",
      package_script: "ui:add:nyx",
      returncode: 0,
      stdout_excerpt: "installed",
    },
    ...overrides,
  };
}

describe("useChatTranscript", () => {
  it("reconstructs a Nyx action card from persisted session messages", () => {
    const { result } = renderHook(() => useChatTranscript());
    const action = createNyxAction();
    const actionResult = createNyxResult({
      approved: false,
      status: "error",
      execution_status: "failed",
      failure_code: "installer_error",
    });
    const sessionMessages: ChatMessageContent[] = [
      {
        role: "user",
        content: "Install glow-card",
        ts: "2026-03-24T00:00:00Z",
        run_id: "",
        sources: [],
      },
      {
        role: "assistant",
        content: "I found a component that matches.",
        ts: "2026-03-24T00:00:01Z",
        run_id: "run-1",
        sources: [],
        actions: [action],
        action_result: actionResult,
      },
    ];

    act(() => {
      result.current.setSessionMessages(sessionMessages);
    });

    expect(result.current.messages).toHaveLength(3);
    expect(result.current.getRun("run-1")?.status).toBe("action_required");

    const actionMessage = result.current.messages[2];
    expect(actionMessage?.actionRequired).toBeDefined();
    expect(actionMessage?.actionRequired?.action).toEqual(action);
    expect(actionMessage?.actionRequired?.status).toBe("failed");
    expect(actionMessage?.actionRequired?.result).toEqual(actionResult);
  });

  it("attaches live Nyx final actions and keeps assistant action results in sync", () => {
    const { result } = renderHook(() => useChatTranscript());
    const action = createNyxAction();
    const actionResult = createNyxResult();

    const userMessage = result.current.createMessage({
      role: "user",
      content: "Install glow-card",
      ts: "2026-03-24T00:00:00Z",
      run_id: "",
      sources: [],
    });
    const assistantMessage = result.current.createMessage(
      {
        role: "assistant",
        content: "",
        ts: "2026-03-24T00:00:01Z",
        run_id: "run-1",
        sources: [],
      },
      { status: "streaming" },
    );

    act(() => {
      result.current.restoreStreamingRun({
        userMessage,
        assistantMessage,
        runId: "run-1",
        sources: [],
        pendingSources: [],
      });
    });

    act(() => {
      result.current.finalizeRun(
        "run-1",
        "I can install that for you.",
        [],
        undefined,
        [action],
      );
    });

    const actionMessageId = result.current.getRun("run-1")?.action_message_id;
    expect(actionMessageId).toBeTruthy();
    expect(result.current.getRun("run-1")?.status).toBe("action_required");

    const actionMessage = result.current.getMessage(actionMessageId!);
    expect(actionMessage?.actionRequired?.action).toEqual(action);
    expect(actionMessage?.actionRequired?.status).toBe("pending");

    act(() => {
      result.current.setActionResult(actionMessageId!, actionResult);
    });

    expect(result.current.getMessage(actionMessageId!)?.actionRequired?.result).toEqual(
      actionResult,
    );
    expect(result.current.getMessage(assistantMessage.id)?.action_result).toEqual(
      actionResult,
    );
  });
});