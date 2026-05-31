"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  getHistory,
  sendMessage,
  triggerEvent,
  uploadCalendarFile,
  type Message,
} from "../../lib/api";
import InputBar from "./InputBar";
import MessageBubble from "./MessageBubble";

// Single-user app: one durable session so history (and scheduled briefings)
// persist across tabs and restarts.
const SESSION_ID = "default";

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingIndex, setStreamingIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<Message[]>([]);
  const retryRef = useRef<(() => void) | null>(null);

  messagesRef.current = messages;

  // Load any persisted conversation (including scheduled briefings) on mount.
  useEffect(() => {
    getHistory(SESSION_ID)
      .then((history) => {
        if (history.length) setMessages(history);
      })
      .catch(() => {
        /* first run / backend down — start empty */
      });
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const appendDonnaChunk = useCallback((chunk: string, streamIdx: number) => {
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

  // Remove a still-empty Donna placeholder after a failed exchange.
  const dropEmptyPlaceholder = useCallback((idx: number) => {
    setMessages((prev) => {
      const updated = [...prev];
      if (updated[idx] && !updated[idx].content) updated.splice(idx, 1);
      return updated;
    });
  }, []);

  const runSend = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isLoading) return;

      setError(null);
      retryRef.current = () => runSend(trimmed);

      const userMessage: Message = { role: "user", content: trimmed };
      const donnaPlaceholder: Message = { role: "donna", content: "" };
      setMessages((prev) => [...prev, userMessage, donnaPlaceholder]);
      const donnaIdx = messagesRef.current.length + 1;
      setIsLoading(true);
      setStreamingIndex(donnaIdx);

      let failed = false;
      try {
        await sendMessage(
          trimmed,
          SESSION_ID,
          (chunk) => appendDonnaChunk(chunk, donnaIdx),
          () => {
            setStreamingIndex(null);
            setIsLoading(false);
          },
          (msg) => {
            failed = true;
            setError(msg);
          }
        );
      } catch {
        failed = true;
        setError("Couldn't reach Donna. Make sure the backend is running.");
      } finally {
        setStreamingIndex(null);
        setIsLoading(false);
      }
      if (failed) dropEmptyPlaceholder(donnaIdx);
    },
    [isLoading, appendDonnaChunk, dropEmptyPlaceholder]
  );

  const handleSend = useCallback(() => {
    const text = input;
    setInput("");
    runSend(text);
  }, [input, runSend]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (isLoading) return;
      setError(null);
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
      } catch {
        setError("Couldn't read that file. Try a clear screenshot or an .ics export.");
        dropEmptyPlaceholder(idx);
        setMessages((prev) => {
          const updated = [...prev];
          if (updated[idx] && updated[idx].content === "Reading that…") updated.splice(idx, 1);
          return updated;
        });
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, dropEmptyPlaceholder]
  );

  const runTrigger = useCallback(
    async (event: "morning_briefing" | "eod_wrap") => {
      if (isLoading) return;

      setError(null);
      retryRef.current = () => runTrigger(event);

      const label =
        event === "morning_briefing" ? "Morning briefing" : "EOD wrap";
      const systemMsg: Message = { role: "user", content: `[Trigger: ${label}]` };
      const donnaPlaceholder: Message = { role: "donna", content: "" };
      setMessages((prev) => [...prev, systemMsg, donnaPlaceholder]);
      const donnaIdx = messagesRef.current.length + 1;
      setIsLoading(true);
      setStreamingIndex(donnaIdx);

      let failed = false;
      try {
        await triggerEvent(
          event,
          SESSION_ID,
          (chunk) => appendDonnaChunk(chunk, donnaIdx),
          () => {
            setStreamingIndex(null);
            setIsLoading(false);
          },
          (msg) => {
            failed = true;
            setError(msg);
          }
        );
      } catch {
        failed = true;
        setError("Couldn't reach Donna. Make sure the backend is running.");
      } finally {
        setStreamingIndex(null);
        setIsLoading(false);
      }
      if (failed) dropEmptyPlaceholder(donnaIdx);
    },
    [isLoading, appendDonnaChunk, dropEmptyPlaceholder]
  );

  const quickButtonStyle = {
    backgroundColor: "var(--surface-2)",
    color: "var(--muted)",
    border: "1px solid var(--border)",
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Quick-action buttons */}
      <div
        className="flex gap-2 px-4 py-2 border-b"
        style={{ borderColor: "var(--border)" }}
      >
        <button
          onClick={() => runTrigger("morning_briefing")}
          disabled={isLoading}
          className="text-xs px-3 py-1.5 rounded-lg transition-colors"
          style={{ ...quickButtonStyle, cursor: isLoading ? "not-allowed" : "pointer" }}
        >
          Morning Briefing
        </button>
        <button
          onClick={() => runTrigger("eod_wrap")}
          disabled={isLoading}
          className="text-xs px-3 py-1.5 rounded-lg transition-colors"
          style={{ ...quickButtonStyle, cursor: isLoading ? "not-allowed" : "pointer" }}
        >
          EOD Wrap
        </button>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-2">
            <div
              className="w-12 h-12 rounded-full flex items-center justify-center text-lg font-semibold"
              style={{ backgroundColor: "var(--accent)", color: "var(--accent-contrast)" }}
            >
              D
            </div>
            <p className="text-sm" style={{ color: "var(--muted)" }}>
              Hi. I&apos;m Donna. What do you need?
            </p>
          </div>
        )}

        {messages.map((msg, idx) => (
          <MessageBubble
            key={idx}
            message={msg}
            isStreaming={idx === streamingIndex}
          />
        ))}

        <div ref={bottomRef} />
      </div>

      {/* Error banner */}
      {error && (
        <div
          className="flex items-center justify-between px-4 py-2 text-xs border-t"
          style={{
            backgroundColor: "var(--surface-2)",
            borderColor: "var(--border)",
            color: "var(--muted)",
          }}
        >
          <span>{error}</span>
          {retryRef.current && (
            <button
              onClick={() => retryRef.current?.()}
              className="font-medium ml-3"
              style={{ color: "var(--accent)" }}
            >
              Retry
            </button>
          )}
        </div>
      )}

      {/* Input bar */}
      <InputBar
        value={input}
        onChange={setInput}
        onSend={handleSend}
        disabled={isLoading}
        onUpload={handleUpload}
      />
    </div>
  );
}
