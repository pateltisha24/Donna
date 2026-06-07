"use client";

import * as React from "react";
import { AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import { useSearchParams, useRouter } from "next/navigation";
import {
  createChat,
  getHistory,
  sendMessage,
  titleChatFromMessage,
  triggerEvent,
  undoReplan,
  uploadCalendarFile,
  type Message,
} from "@/lib/api";
import { useChats } from "@/lib/useChats";
import { TopBar } from "./TopBar";
import { MessageBubble } from "./MessageBubble";
import { Composer } from "./Composer";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { EmptyState } from "./EmptyState";
import { type QuickAction } from "./QuickActions";
import { RightPanel } from "./RightPanel";

export function ChatExperience() {
  const router = useRouter();
  const params = useSearchParams();
  const panel = params.get("panel");
  const action = params.get("action");
  const ask = params.get("ask");
  // Guards so a prefilled prompt / emergency only fires once, even under
  // React strict-mode double-invocation in dev.
  const consumedParam = React.useRef(false);

  const { activeId, setActiveId, newChat, refresh, titleFromFirstMessage } = useChats();
  const chatId = activeId;
  // Tracks whether we've already auto-titled the current chat in this session.
  const titledRef = React.useRef<Set<string>>(new Set());

  const [messages, setMessages] = React.useState<Message[]>([]);
  const [input, setInput] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [streamingIndex, setStreamingIndex] = React.useState<number | null>(null);
  const [waitingFirstToken, setWaitingFirstToken] = React.useState(false);
  const [panelOpen, setPanelOpen] = React.useState(false);
  const [panelTab, setPanelTab] = React.useState<"schedule" | "tasks">("schedule");

  const scrollerRef = React.useRef<HTMLDivElement>(null);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const messagesRef = React.useRef<Message[]>([]);
  messagesRef.current = messages;

  // ---- Load history for the active chat ----------------------------------
  React.useEffect(() => {
    if (!chatId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    getHistory(chatId)
      .then((history) => {
        if (!cancelled) setMessages(history);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [chatId]);

  // ---- Open panel from URL param -----------------------------------------
  React.useEffect(() => {
    if (panel === "schedule" || panel === "tasks") {
      setPanelTab(panel);
      setPanelOpen(true);
      router.replace("/app/chat", { scroll: false });
    }
  }, [panel, router]);

  // ---- Auto-scroll on new content ----------------------------------------
  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, waitingFirstToken]);

  // ------------------------------------------------------------------
  // Sending
  // ------------------------------------------------------------------

  const appendChunk = React.useCallback((chunk: string, streamIdx: number) => {
    setWaitingFirstToken(false);
    setMessages((prev) => {
      const updated = [...prev];
      if (updated[streamIdx]) {
        updated[streamIdx] = {
          ...updated[streamIdx],
          content: updated[streamIdx].content + chunk,
        };
      }
      return updated;
    });
  }, []);

  const dropEmpty = React.useCallback((idx: number) => {
    setMessages((prev) => {
      const updated = [...prev];
      if (updated[idx] && !updated[idx].content) updated.splice(idx, 1);
      return updated;
    });
  }, []);

  const attachReplan = React.useCallback(
    (idx: number, replan: NonNullable<Message["replan"]>) => {
      setMessages((prev) => {
        const updated = [...prev];
        if (updated[idx]) updated[idx] = { ...updated[idx], replan };
        return updated;
      });
    },
    []
  );

  const handleUndoReplan = React.useCallback(async () => {
    await undoReplan();
    toast.success("Reverted — your day is back to how it was.");
  }, []);

  /** Resolve a chat id, creating one if there isn't an active chat yet. */
  const ensureChat = React.useCallback(async (): Promise<string> => {
    if (chatId) return chatId;
    const chat = await createChat();
    setActiveId(chat.id);
    await refresh();
    return chat.id;
  }, [chatId, setActiveId, refresh]);

  const maybeAutoTitle = React.useCallback(
    async (id: string, firstMessage: string) => {
      if (titledRef.current.has(id)) return;
      titledRef.current.add(id);
      // Only auto-title if this is the first user message of the chat.
      const userMessages = messagesRef.current.filter((m) => m.role === "user");
      if (userMessages.length > 1) return;
      try {
        await titleFromFirstMessage(id, firstMessage);
      } catch {
        // Silent — keep "New chat" if titling fails.
      }
    },
    [titleFromFirstMessage]
  );

  const runSend = React.useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      const sessionId = await ensureChat();

      const userMessage: Message = { role: "user", content: trimmed };
      const placeholder: Message = { role: "donna", content: "" };
      setMessages((prev) => [...prev, userMessage, placeholder]);
      const donnaIdx = messagesRef.current.length + 1;
      setIsLoading(true);
      setWaitingFirstToken(true);
      setStreamingIndex(donnaIdx);

      // Kick off AI title generation in the background — doesn't block the chat.
      maybeAutoTitle(sessionId, trimmed);

      let failed = false;
      try {
        await sendMessage(
          trimmed,
          sessionId,
          (chunk) => appendChunk(chunk, donnaIdx),
          (meta) => {
            setStreamingIndex(null);
            setWaitingFirstToken(false);
            setIsLoading(false);
            if (meta?.replan) attachReplan(donnaIdx, meta.replan);
          },
          (msg) => {
            failed = true;
            toast.error("Donna hit a problem", { description: msg });
          }
        );
      } catch {
        failed = true;
        toast.error("Couldn't reach Donna.", {
          description: "Make sure the backend is running.",
          action: { label: "Retry", onClick: () => runSend(trimmed) },
        });
      } finally {
        setStreamingIndex(null);
        setWaitingFirstToken(false);
        setIsLoading(false);
        // Refresh the chat list so last_message_at re-sorts it to the top.
        refresh();
      }
      if (failed) dropEmpty(donnaIdx);
    },
    [isLoading, appendChunk, dropEmpty, ensureChat, maybeAutoTitle, refresh, attachReplan]
  );

  const handleSend = () => {
    const text = input;
    setInput("");
    runSend(text);
  };

  const handleUpload = React.useCallback(
    async (file: File) => {
      if (isLoading) return;
      const note: Message = { role: "user", content: `📎 Uploaded ${file.name}` };
      const pending: Message = { role: "donna", content: "Reading that…" };
      setMessages((prev) => [...prev, note, pending]);
      const idx = messagesRef.current.length + 1;
      setIsLoading(true);
      try {
        const { message } = await uploadCalendarFile(file);
        setMessages((prev) => {
          const updated = [...prev];
          if (updated[idx]) updated[idx] = { ...updated[idx], content: message };
          return updated;
        });
        toast.success("File processed.");
      } catch {
        toast.error("Couldn't read that file.", {
          description: "Try a clearer screenshot or an .ics export.",
        });
        setMessages((prev) => {
          const updated = [...prev];
          if (updated[idx] && updated[idx].content === "Reading that…") updated.splice(idx, 1);
          return updated;
        });
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading]
  );

  const runTriggerAction = React.useCallback(
    async (event: "morning_briefing" | "eod_wrap") => {
      if (isLoading) return;
      const sessionId = await ensureChat();
      const label = event === "morning_briefing" ? "Morning briefing" : "EOD wrap";
      const systemMsg: Message = { role: "user", content: `✨ ${label}` };
      const placeholder: Message = { role: "donna", content: "" };
      setMessages((prev) => [...prev, systemMsg, placeholder]);
      const donnaIdx = messagesRef.current.length + 1;
      setIsLoading(true);
      setWaitingFirstToken(true);
      setStreamingIndex(donnaIdx);

      let failed = false;
      try {
        await triggerEvent(
          event,
          sessionId,
          (chunk) => appendChunk(chunk, donnaIdx),
          () => {
            setStreamingIndex(null);
            setWaitingFirstToken(false);
            setIsLoading(false);
          },
          (msg) => {
            failed = true;
            toast.error("Couldn't run that.", { description: msg });
          }
        );
      } catch {
        failed = true;
        toast.error("Couldn't reach Donna.");
      } finally {
        setStreamingIndex(null);
        setWaitingFirstToken(false);
        setIsLoading(false);
      }
      if (failed) dropEmpty(donnaIdx);
    },
    [isLoading, appendChunk, dropEmpty, ensureChat]
  );

  // ---- Emergency action / prefilled prompt from URL ----------------------
  // Today's quick actions deep-link here with ?ask=… or ?action=emergency.
  React.useEffect(() => {
    if (consumedParam.current) return;
    if (action === "emergency") {
      consumedParam.current = true;
      runSend("Something urgent just came up. Help me replan my day.");
      router.replace("/app/chat", { scroll: false });
    } else if (ask) {
      consumedParam.current = true;
      runSend(ask);
      router.replace("/app/chat", { scroll: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [action, ask]);

  const onQuick = (a: QuickAction) => {
    if (a === "morning_briefing" || a === "eod_wrap") runTriggerAction(a);
    else if (a === "emergency")
      runSend("Something urgent just came up. Help me replan my day.");
    else if (a === "what_now") runSend("What should I work on right now?");
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar
        onOpenPanel={() => setPanelOpen(true)}
        onQuickAction={onQuick}
        quickDisabled={isLoading}
      />

      <div
        ref={scrollerRef}
        className="flex-1 overflow-y-auto scroll-smooth"
      >
        <div className="max-w-3xl mx-auto w-full px-4 md:px-6 py-6">
          {messages.length === 0 ? (
            <EmptyState onPrompt={runSend} />
          ) : (
            <AnimatePresence initial={false}>
              {messages.map((msg, idx) => (
                <MessageBubble
                  key={idx}
                  message={msg}
                  isStreaming={idx === streamingIndex && !!msg.content}
                  onUndoReplan={handleUndoReplan}
                />
              ))}
              {waitingFirstToken && <ThinkingIndicator key="thinking" />}
            </AnimatePresence>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="max-w-3xl mx-auto w-full">
        <Composer
          value={input}
          onChange={setInput}
          onSend={handleSend}
          onUpload={handleUpload}
          disabled={isLoading}
          isLoading={isLoading}
        />
      </div>

      <RightPanel open={panelOpen} onOpenChange={setPanelOpen} initialTab={panelTab} />
    </div>
  );
}
