"use client";

import * as React from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { DonnaAvatar, UserAvatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import type { Message } from "@/lib/api";
import { ReplanCard } from "./ReplanCard";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
  onUndoReplan?: () => Promise<void>;
}

export function MessageBubble({ message, isStreaming = false, onUndoReplan }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const replan = message.replan;
  // When a structured replan card is shown, drop the redundant text diff that
  // Donna appended (kept in content so reloaded history still reads complete).
  const displayContent = replan
    ? message.content.split(/\n*\*\*Here's what I shifted:\*\*/)[0].trim()
    : message.content;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className={cn("flex w-full mb-5 gap-3", isUser ? "justify-end" : "justify-start")}
    >
      {!isUser && <DonnaAvatar size="sm" className="mt-1" />}

      <div
        className={cn(
          "max-w-[78%] px-4 py-3 text-sm leading-relaxed shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground rounded-2xl rounded-tr-sm"
            : "bg-card border border-border text-card-foreground rounded-2xl rounded-tl-sm"
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        ) : (
          <div className="markdown break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{displayContent}</ReactMarkdown>
          </div>
        )}
        {isStreaming && (
          <span
            className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom rounded-sm bg-primary animate-pulse"
            aria-hidden
          />
        )}
        {replan && replan.changes.length > 0 && (
          <ReplanCard
            changes={replan.changes}
            canUndo={replan.undo}
            onUndo={onUndoReplan ?? (async () => {})}
          />
        )}
      </div>

      {isUser && <UserAvatar size="sm" initial="Y" className="mt-1" />}
    </motion.div>
  );
}
