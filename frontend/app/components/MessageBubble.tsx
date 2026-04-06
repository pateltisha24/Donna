"use client";

import React from "react";
import type { Message } from "../../lib/api";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export default function MessageBubble({
  message,
  isStreaming = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex w-full mb-4 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {/* Donna avatar */}
      {!isUser && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold mr-2 flex-shrink-0 mt-1"
          style={{ backgroundColor: "#7c6af7", color: "#fff" }}
        >
          D
        </div>
      )}

      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isUser ? "rounded-tr-sm" : "rounded-tl-sm"
        }`}
        style={{
          backgroundColor: isUser ? "#2d2d38" : "#1e1e28",
          color: "#e8e8f0",
          border: isUser ? "none" : "1px solid #2a2a33",
        }}
      >
        {/* Pre-wrap to preserve newlines from the LLM */}
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
        {isStreaming && (
          <span
            className="inline-block w-1.5 h-4 ml-0.5 animate-pulse rounded-sm"
            style={{ backgroundColor: "#7c6af7", verticalAlign: "text-bottom" }}
          />
        )}
      </div>

      {/* User avatar placeholder */}
      {isUser && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ml-2 flex-shrink-0 mt-1"
          style={{ backgroundColor: "#2a2a33", color: "#8888a0" }}
        >
          Y
        </div>
      )}
    </div>
  );
}
