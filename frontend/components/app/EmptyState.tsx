"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Sparkles, Calendar, ListTodo, Zap } from "lucide-react";
import { DonnaAvatar } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  onPrompt: (prompt: string) => void;
}

const SUGGESTIONS = [
  {
    icon: Sparkles,
    title: "Give me my morning briefing",
    subtitle: "See what today looks like at a glance",
    prompt: "Good morning. Give me my morning briefing.",
  },
  {
    icon: ListTodo,
    title: "Plan my day",
    subtitle: "Help me decide what to work on first",
    prompt: "Help me plan my day. What should I tackle first?",
  },
  {
    icon: Calendar,
    title: "Add an event",
    subtitle: "Try: \"Team standup Tue & Thu at 10am\"",
    prompt: "I have a team standup every Tuesday and Thursday at 10am.",
  },
  {
    icon: Zap,
    title: "Emergency replan",
    subtitle: "Something urgent just came up",
    prompt: "Something urgent just came up. Help me replan.",
  },
];

export function EmptyState({ onPrompt }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-full px-4 py-12">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="text-center max-w-lg"
      >
        <DonnaAvatar size="xl" animated className="mx-auto mb-5" />
        <h2 className="text-2xl font-semibold tracking-tight mb-2">
          Hi, I&apos;m Donna.
        </h2>
        <p className="text-muted-foreground text-sm leading-relaxed mb-8">
          Your AI Chief of Staff. I&apos;ll manage your tasks, run your calendar,
          remember what matters, and replan when things change.
        </p>
      </motion.div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-xl w-full">
        {SUGGESTIONS.map((s, i) => {
          const Icon = s.icon;
          return (
            <motion.button
              key={s.title}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + i * 0.05 }}
              onClick={() => onPrompt(s.prompt)}
              className={cn(
                "text-left px-4 py-3 rounded-xl border border-border bg-card hover:border-primary/40 hover:bg-accent/30 transition-all group"
              )}
            >
              <div className="flex items-start gap-3">
                <span className="h-8 w-8 rounded-lg bg-accent/60 flex items-center justify-center shrink-0">
                  <Icon className="h-4 w-4 text-primary" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {s.title}
                  </p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {s.subtitle}
                  </p>
                </div>
              </div>
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
