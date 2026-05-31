"use client";

import React, { useRef } from "react";

interface InputBarProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  placeholder?: string;
  onUpload?: (file: File) => void;
}

export default function InputBar({
  value,
  onChange,
  onSend,
  disabled = false,
  placeholder = "Message Donna…",
  onUpload,
}: InputBarProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onUpload) onUpload(file);
    e.target.value = ""; // allow re-uploading the same file
  };

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
      style={{ borderColor: "var(--border)", backgroundColor: "var(--surface)" }}
    >
      {onUpload && (
        <>
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.ics,text/calendar"
            onChange={handleFile}
            className="hidden"
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={disabled}
            title="Upload a calendar screenshot or .ics file"
            aria-label="Upload calendar"
            className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-colors"
            style={{
              backgroundColor: "var(--bg)",
              color: "var(--muted)",
              border: "1px solid var(--border)",
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
            </svg>
          </button>
        </>
      )}

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
          backgroundColor: "var(--bg)",
          color: "var(--text)",
          border: "1px solid var(--border)",
          minHeight: "44px",
          maxHeight: "160px",
          lineHeight: "1.5",
        }}
      />

      <button
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center transition-all"
        style={{
          backgroundColor:
            disabled || !value.trim() ? "var(--border)" : "var(--accent)",
          color: disabled || !value.trim() ? "var(--muted)" : "var(--accent-contrast)",
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
