"use client";

import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { DonnaAvatar } from "@/components/ui/avatar";

export function ThinkingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="flex items-start gap-3 mb-5"
    >
      <DonnaAvatar size="sm" animated />
      <div className="flex items-center gap-2 px-4 py-3 rounded-2xl rounded-tl-sm bg-card border border-border shadow-sm">
        <div className="flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-primary animate-pulse-dot" />
          <span
            className="h-2 w-2 rounded-full bg-primary animate-pulse-dot"
            style={{ animationDelay: "150ms" }}
          />
          <span
            className="h-2 w-2 rounded-full bg-primary animate-pulse-dot"
            style={{ animationDelay: "300ms" }}
          />
        </div>
        <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
          <Sparkles className="h-3 w-3 text-primary" /> Donna is thinking…
        </span>
      </div>
    </motion.div>
  );
}
