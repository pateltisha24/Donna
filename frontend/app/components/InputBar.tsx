"use client";

import React, { useRef } from "react";

interface InputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
}

export default function InputBar({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = "Message Donna…",
}: InputBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) {
        onSend();
      }
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    // Auto-resize
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
    }
  };

  return (
    <div
      className="flex items-end gap-3 px-4 py-3 border-t"
      style={{ borderColor: "#2a2a33", backgroundColor: "#1a1a1f" }}
    >
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        className="flex-1 resize-none rounded-xl px-4 py-3 text-sm outline-none transition-colors"
        style={{
          backgroundColor: "#0f0f11",
          color: "#e8e8f0",
          border: "1px solid #2a2a33",
          minHeight: "44px",
          maxHeight: "160px",
          lineHeight: "1.5",
          // placeholder color
        }}
      />

      <button
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all"
        style={{
          backgroundColor:
            disabled || !value.trim() ? "#2a2a33" : "#7c6af7",
          color: disabled || !value.trim() ? "#8888a0" : "#fff",
          cursor: disabled || !value.trim() ? "not-allowed" : "pointer",
        }}
        aria-label="Send message"
      >
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          width="16"
          height="16"
        >
          <line x1="22" y1="2" x2="11" y2="13" />
          <polygon points="22 2 15 22 11 13 2 9 22 2" />
        </svg>
      </button>
    </div>
  );
}
