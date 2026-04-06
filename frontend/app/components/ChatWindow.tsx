"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { sendMessage, triggerEvent, type Message } from "../../lib/api";
import InputBar from "./InputBar";
import MessageBubble from "./MessageBubble";

// Stable session ID for this browser tab
const SESSION_ID =
  typeof window !== "undefined"
    ? (sessionStorage.getItem("donna_session") ||
      (() => {
        const id = `session_${Date.now()}`;
        sessionStorage.setItem("donna_session", id);
        return id;
      })())
    : "default";

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [streamingIndex, setStreamingIndex] = useState<number | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<Message[]>([]);

  // Keep ref in sync
  messagesRef.current = messages;

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const appendDonnaChunk = useCallback(
    (chunk: string, streamIdx: number) => {
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
    },
    []
  );

  const handleSend = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = { role: "user", content: input.trim() };
    const donnaPlaceholder: Message = { role: "donna", content: "" };

    setMessages((prev) => [...prev, userMessage, donnaPlaceholder]);
    // messagesRef.current still holds the pre-update snapshot here, so the
    // donna placeholder lands at currentLength + 1 (user=+0, donna=+1).
    const donnaIdx = messagesRef.current.length + 1;
    setInput("");
    setIsLoading(true);
    setStreamingIndex(donnaIdx);

    try {
      await sendMessage(
        userMessage.content,
        SESSION_ID,
        (chunk) => appendDonnaChunk(chunk, donnaIdx),
        () => {
          setStreamingIndex(null);
          setIsLoading(false);
        }
      );
    } catch (err) {
      setMessages((prev) => {
        const updated = [...prev];
        if (updated[donnaIdx]) {
          updated[donnaIdx] = {
            ...updated[donnaIdx],
            content:
              "Something went wrong connecting to Donna. Make sure the backend is running.",
          };
        }
        return updated;
      });
      setStreamingIndex(null);
      setIsLoading(false);
    }
  }, [input, isLoading, appendDonnaChunk]);

  const handleTrigger = useCallback(
    async (event: "morning_briefing" | "eod_wrap") => {
      if (isLoading) return;

      const label =
        event === "morning_briefing" ? "Morning briefing" : "EOD wrap";
      const systemMsg: Message = {
        role: "user",
        content: `[Trigger: ${label}]`,
      };
      const donnaPlaceholder: Message = { role: "donna", content: "" };

      setMessages((prev) => [...prev, systemMsg, donnaPlaceholder]);
      const donnaIdx = messagesRef.current.length;
      setIsLoading(true);
      setStreamingIndex(donnaIdx);

      try {
        await triggerEvent(
          event,
          SESSION_ID,
          (chunk) => appendDonnaChunk(chunk, donnaIdx),
          () => {
            setStreamingIndex(null);
            setIsLoading(false);
          }
        );
      } catch {
        setStreamingIndex(null);
        setIsLoading(false);
      }
    },
    [isLoading, appendDonnaChunk]
  );

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Quick-action buttons */}
      <div
        className="flex gap-2 px-4 py-2 border-b"
        style={{ borderColor: "#2a2a33" }}
      >
        <button
          onClick={() => handleTrigger("morning_briefing")}
          disabled={isLoading}
          className="text-xs px-3 py-1.5 rounded-lg transition-colors"
          style={{
            backgroundColor: "#1e1e28",
            color: "#8888a0",
            border: "1px solid #2a2a33",
            cursor: isLoading ? "not-allowed" : "pointer",
          }}
        >
          Morning Briefing
        </button>
        <button
          onClick={() => handleTrigger("eod_wrap")}
          disabled={isLoading}
          className="text-xs px-3 py-1.5 rounded-lg transition-colors"
          style={{
            backgroundColor: "#1e1e28",
            color: "#8888a0",
            border: "1px solid #2a2a33",
            cursor: isLoading ? "not-allowed" : "pointer",
          }}
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
              style={{ backgroundColor: "#7c6af7", color: "#fff" }}
            >
              D
            </div>
            <p className="text-sm" style={{ color: "#8888a0" }}>
              Hi. I'm Donna. What do you need?
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

      {/* Input bar */}
      <InputBar
        value={input}
        onChange={setInput}
        onSend={handleSend}
        disabled={isLoading}
      />
    </div>
  );
}
