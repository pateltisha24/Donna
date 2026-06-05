"use client";

import * as React from "react";
import { Paperclip, Send, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onUpload?: (file: File) => void;
  disabled?: boolean;
  placeholder?: string;
  isLoading?: boolean;
}

export function Composer({
  value,
  onChange,
  onSend,
  onUpload,
  disabled = false,
  placeholder = "Message Donna…",
  isLoading = false,
}: ComposerProps) {
  const taRef = React.useRef<HTMLTextAreaElement>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);

  const handleKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value);
    const ta = taRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    }
  };

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onUpload) onUpload(file);
    e.target.value = "";
  };

  return (
    <div className="px-3 md:px-6 pb-4 pt-2">
      <div
        className={cn(
          "relative flex items-end gap-2 rounded-2xl border border-border bg-card pl-2 pr-2 py-2 shadow-sm transition-all",
          "focus-within:border-primary/60 focus-within:shadow-md focus-within:shadow-primary/10"
        )}
      >
        {onUpload && (
          <>
            <input
              ref={fileRef}
              type="file"
              // Extensions only — `text/calendar` MIME greys .ics files out
              // in the macOS picker on some browsers. The server validates.
              accept=".ics,.png,.jpg,.jpeg,.webp,.heic,.heif,image/*"
              onChange={handleFile}
              className="hidden"
            />
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={disabled}
                  aria-label="Upload calendar screenshot or .ics file"
                  className={cn(
                    "shrink-0 h-9 w-9 inline-flex items-center justify-center rounded-lg",
                    "text-muted-foreground hover:text-foreground hover:bg-accent transition-colors",
                    "disabled:opacity-50 disabled:cursor-not-allowed focus-ring"
                  )}
                >
                  <Paperclip className="h-[18px] w-[18px]" strokeWidth={1.75} />
                </button>
              </TooltipTrigger>
              <TooltipContent>Upload calendar screenshot or .ics</TooltipContent>
            </Tooltip>
          </>
        )}

        <textarea
          ref={taRef}
          rows={1}
          value={value}
          onChange={handleInput}
          onKeyDown={handleKey}
          disabled={disabled}
          placeholder={placeholder}
          className="flex-1 resize-none bg-transparent px-1 py-1.5 text-sm outline-none placeholder:text-muted-foreground min-h-[36px] max-h-[200px] leading-relaxed self-center"
        />

        <Button
          type="button"
          variant={value.trim() ? "default" : "secondary"}
          size="icon-sm"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          aria-label="Send message"
          className="shrink-0 h-9 w-9"
        >
          {isLoading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
        </Button>
      </div>
      <p className="text-[10px] text-muted-foreground mt-2 px-2 text-center">
        Press <kbd className="px-1 py-0.5 bg-muted rounded text-[10px]">Enter</kbd> to send,{" "}
        <kbd className="px-1 py-0.5 bg-muted rounded text-[10px]">Shift+Enter</kbd> for newline
      </p>
    </div>
  );
}
