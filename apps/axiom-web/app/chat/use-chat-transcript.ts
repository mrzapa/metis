"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type {
  ActionRequiredAction,
  ChatActionStatus,
  ChatMessage,
  ChatMessageContent,
  ChatMessageStatus,
  ChatRun,
  EvidenceSource,
} from "@/lib/chat-types";

interface ChatTranscriptState {
  messagesById: Record<string, ChatMessage>;
  messageOrder: string[];
  runsById: Record<string, ChatRun>;
  runOrder: string[];
}

const EMPTY_CHAT_TRANSCRIPT_STATE: ChatTranscriptState = {
  messagesById: {},
  messageOrder: [],
  runsById: {},
  runOrder: [],
};

interface RestorableStreamingRun {
  userMessage: ChatMessage;
  assistantMessage: ChatMessage;
  runId: string;
  sources: EvidenceSource[];
  pendingSources: EvidenceSource[];
}

function cloneTranscriptState(state: ChatTranscriptState): ChatTranscriptState {
  return {
    messagesById: { ...state.messagesById },
    messageOrder: [...state.messageOrder],
    runsById: { ...state.runsById },
    runOrder: [...state.runOrder],
  };
}

function appendMessage(state: ChatTranscriptState, message: ChatMessage): void {
  state.messagesById[message.id] = message;
  state.messageOrder.push(message.id);
}

function upsertRun(
  state: ChatTranscriptState,
  runId: string,
  updater: (run: ChatRun | undefined) => ChatRun,
): void {
  const existingRun = state.runsById[runId];
  state.runsById[runId] = updater(existingRun);
  if (!existingRun) {
    state.runOrder.push(runId);
  }
}

export function useChatTranscript() {
  const [state, setState] = useState<ChatTranscriptState>(EMPTY_CHAT_TRANSCRIPT_STATE);
  const messageIdRef = useRef(0);

  const nextMessageId = useCallback(() => `message-${messageIdRef.current++}`, []);

  const createMessage = useCallback(
    (
      message: ChatMessageContent,
      overrides?: Partial<ChatMessage>,
    ): ChatMessage => ({
      ...message,
      id: nextMessageId(),
      status: "complete",
      ...overrides,
    }),
    [nextMessageId],
  );

  const restoreStreamingRun = useCallback(
    ({
      userMessage,
      assistantMessage,
      runId,
      sources,
      pendingSources,
    }: RestorableStreamingRun) => {
      setState(() => {
        const nextState = cloneTranscriptState(EMPTY_CHAT_TRANSCRIPT_STATE);
        appendMessage(nextState, userMessage);
        appendMessage(nextState, assistantMessage);
        upsertRun(nextState, runId, () => ({
          run_id: runId,
          assistant_message_id: assistantMessage.id,
          status: "streaming",
          sources,
          pending_sources: pendingSources,
        }));
        return nextState;
      });
    },
    [],
  );

  const setSessionMessages = useCallback(
    (messages: ChatMessageContent[]) => {
      setState(() => {
        const nextState = cloneTranscriptState(EMPTY_CHAT_TRANSCRIPT_STATE);

        for (const message of messages) {
          const chatMessage = createMessage(message);
          appendMessage(nextState, chatMessage);

          if (chatMessage.role !== "assistant" || !chatMessage.run_id) {
            continue;
          }

          upsertRun(nextState, chatMessage.run_id, () => ({
            run_id: chatMessage.run_id,
            assistant_message_id: chatMessage.id,
            status: "complete",
            sources: chatMessage.sources,
            pending_sources: [],
          }));
        }

        return nextState;
      });
    },
    [createMessage],
  );

  const reset = useCallback(() => {
    setState(cloneTranscriptState(EMPTY_CHAT_TRANSCRIPT_STATE));
  }, []);

  const appendMessages = useCallback((messages: ChatMessage[]) => {
    setState((previousState) => {
      const nextState = cloneTranscriptState(previousState);

      for (const message of messages) {
        appendMessage(nextState, message);
      }

      return nextState;
    });
  }, []);

  const appendCompletedRunMessage = useCallback((message: ChatMessage) => {
    setState((previousState) => {
      const nextState = cloneTranscriptState(previousState);
      appendMessage(nextState, message);

      if (message.role === "assistant" && message.run_id) {
        upsertRun(nextState, message.run_id, () => ({
          run_id: message.run_id,
          assistant_message_id: message.id,
          status: message.status === "error" ? "error" : "complete",
          sources: message.sources,
          pending_sources: [],
        }));
      }

      return nextState;
    });
  }, []);

  const bindRunToAssistantMessage = useCallback(
    (runId: string, assistantMessageId: string) => {
      setState((previousState) => {
        const assistantMessage = previousState.messagesById[assistantMessageId];
        if (!assistantMessage) {
          return previousState;
        }

        const nextState = cloneTranscriptState(previousState);
        nextState.messagesById[assistantMessageId] = {
          ...assistantMessage,
          run_id: runId,
        };

        upsertRun(nextState, runId, (existingRun) => ({
          run_id: runId,
          assistant_message_id: assistantMessageId,
          action_message_id: existingRun?.action_message_id,
          status: "streaming",
          sources: existingRun?.sources ?? [],
          pending_sources: existingRun?.pending_sources ?? [],
        }));

        return nextState;
      });
    },
    [],
  );

  const setRunPendingSources = useCallback((runId: string, sources: EvidenceSource[]) => {
    setState((previousState) => {
      const run = previousState.runsById[runId];
      if (!run) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.runsById[runId] = {
        ...run,
        pending_sources: sources,
        status: "streaming",
      };
      return nextState;
    });
  }, []);

  const appendRunToken = useCallback((runId: string, token: string) => {
    setState((previousState) => {
      const run = previousState.runsById[runId];
      if (!run) {
        return previousState;
      }

      const assistantMessage = previousState.messagesById[run.assistant_message_id];
      if (!assistantMessage) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[assistantMessage.id] = {
        ...assistantMessage,
        content: `${assistantMessage.content}${token}`,
        run_id: runId,
        status: "streaming",
      };
      nextState.runsById[runId] = {
        ...run,
        status: "streaming",
      };
      return nextState;
    });
  }, []);

  const finalizeRun = useCallback((runId: string, answerText: string, sources: EvidenceSource[]) => {
    setState((previousState) => {
      const run = previousState.runsById[runId];
      if (!run) {
        return previousState;
      }

      const assistantMessage = previousState.messagesById[run.assistant_message_id];
      if (!assistantMessage) {
        return previousState;
      }

      const finalSources =
        sources.length > 0 ? sources : run.pending_sources;
      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[assistantMessage.id] = {
        ...assistantMessage,
        content: answerText,
        run_id: runId,
        sources: finalSources,
        status: "complete",
      };
      nextState.runsById[runId] = {
        ...run,
        status: "complete",
        sources: finalSources,
        pending_sources: finalSources,
      };
      return nextState;
    });
  }, []);

  const markRunActionRequired = useCallback(
    (runId: string, action: ActionRequiredAction, timestamp: string) => {
      setState((previousState) => {
        const run = previousState.runsById[runId];
        if (!run) {
          return previousState;
        }

        const assistantMessage = previousState.messagesById[run.assistant_message_id];
        if (!assistantMessage) {
          return previousState;
        }

        const nextState = cloneTranscriptState(previousState);
        nextState.messagesById[assistantMessage.id] = {
          ...assistantMessage,
          content: assistantMessage.content.trim()
            ? assistantMessage.content
            : "Action required — see below.",
          status: "complete",
        };

        const actionMessageId = nextMessageId();
        appendMessage(nextState, {
          id: actionMessageId,
          role: "assistant",
          content: "",
          ts: timestamp,
          run_id: runId,
          sources: [],
          status: "complete",
          actionRequired: {
            action,
            status: "pending",
          },
        });
        nextState.runsById[runId] = {
          ...run,
          action_message_id: actionMessageId,
          status: "action_required",
        };

        return nextState;
      });
    },
    [nextMessageId],
  );

  const markRunError = useCallback((runId: string, message: string) => {
    setState((previousState) => {
      const run = previousState.runsById[runId];
      if (!run) {
        return previousState;
      }

      const assistantMessage = previousState.messagesById[run.assistant_message_id];
      if (!assistantMessage) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[assistantMessage.id] = {
        ...assistantMessage,
        content: assistantMessage.content.trim() ? assistantMessage.content : message,
        run_id: runId,
        status: "error",
      };
      nextState.runsById[runId] = {
        ...run,
        status: "error",
      };
      return nextState;
    });
  }, []);

  const markMessageError = useCallback((messageId: string, message: string) => {
    setState((previousState) => {
      const chatMessage = previousState.messagesById[messageId];
      if (!chatMessage) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[messageId] = {
        ...chatMessage,
        content: chatMessage.content.trim() ? chatMessage.content : message,
        status: "error",
      };
      return nextState;
    });
  }, []);

  const setMessageStatus = useCallback(
    (messageId: string, status: ChatMessageStatus) => {
      setState((previousState) => {
        const message = previousState.messagesById[messageId];
        if (!message) {
          return previousState;
        }

        const nextState = cloneTranscriptState(previousState);
        nextState.messagesById[messageId] = {
          ...message,
          status,
        };
        return nextState;
      });
    },
    [],
  );

  const markRunAborted = useCallback((runId: string) => {
    setState((previousState) => {
      const run = previousState.runsById[runId];
      if (!run) {
        return previousState;
      }

      const assistantMessage = previousState.messagesById[run.assistant_message_id];
      if (!assistantMessage) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[assistantMessage.id] = {
        ...assistantMessage,
        status: assistantMessage.status === "streaming" ? "aborted" : assistantMessage.status,
      };
      nextState.runsById[runId] = {
        ...run,
        status: "aborted",
      };
      return nextState;
    });
  }, []);

  const markMessageAborted = useCallback((messageId: string) => {
    setState((previousState) => {
      const message = previousState.messagesById[messageId];
      if (!message) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[messageId] = {
        ...message,
        status: message.status === "streaming" ? "aborted" : message.status,
      };
      return nextState;
    });
  }, []);

  const setActionStatus = useCallback((messageId: string, status: ChatActionStatus) => {
    setState((previousState) => {
      const message = previousState.messagesById[messageId];
      if (!message?.actionRequired) {
        return previousState;
      }

      const nextState = cloneTranscriptState(previousState);
      nextState.messagesById[messageId] = {
        ...message,
        actionRequired: {
          ...message.actionRequired,
          status,
        },
      };
      return nextState;
    });
  }, []);

  const messages = useMemo(
    () => state.messageOrder.map((messageId) => state.messagesById[messageId]).filter(Boolean),
    [state.messageOrder, state.messagesById],
  );

  const latestRunId = state.runOrder.at(-1) ?? null;
  const latestRun = latestRunId ? state.runsById[latestRunId] : null;
  const runIdsNewestFirst = useMemo(
    () => [...state.runOrder].reverse(),
    [state.runOrder],
  );

  const latestSources = latestRun?.sources ?? [];
  const latestAnswer = latestRun
    ? state.messagesById[latestRun.assistant_message_id]?.content ?? ""
    : "";

  const getMessage = useCallback(
    (messageId: string) => state.messagesById[messageId],
    [state.messagesById],
  );

  return {
    createMessage,
    restoreStreamingRun,
    setSessionMessages,
    reset,
    appendMessages,
    appendCompletedRunMessage,
    bindRunToAssistantMessage,
    setRunPendingSources,
    appendRunToken,
    finalizeRun,
    markRunActionRequired,
    markRunError,
    markMessageError,
    setMessageStatus,
    markRunAborted,
    markMessageAborted,
    setActionStatus,
    getMessage,
    getRun: (runId: string) => state.runsById[runId],
    messages,
    latestRunId,
    latestSources,
    latestAnswer,
    runIdsNewestFirst,
  };
}
