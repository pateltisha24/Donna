"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
          style={{ backgroundColor: "var(--accent)", color: "var(--accent-contrast)" }}
        >
          D
        </div>
      )}

      <div
        className={`max-w-[75%] px-4 py-3 rounded-2xl text-sm leading-relaxed ${
          isUser ? "rounded-tr-sm" : "rounded-tl-sm"
        }`}
        style={{
          backgroundColor: isUser ? "var(--user-bubble)" : "var(--surface-2)",
          color: "var(--text)",
          border: isUser ? "none" : "1px solid var(--border)",
        }}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        ) : (
          <div className="markdown break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}
        {isStreaming && (
          <span
            className="inline-block w-1.5 h-4 ml-0.5 animate-pulse rounded-sm"
            style={{ backgroundColor: "var(--accent)", verticalAlign: "text-bottom" }}
          />
        )}
      </div>

      {/* User avatar placeholder */}
      {isUser && (
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ml-2 flex-shrink-0 mt-1"
          style={{ backgroundColor: "var(--border)", color: "var(--muted)" }}
        >
          Y
        </div>
      )}
    </div>
  );
}
