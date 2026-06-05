"use client";

import * as React from "react";
import { Sun, Moon, Zap, ListTodo } from "lucide-react";
import { cn } from "@/lib/utils";

export type QuickAction = "morning_briefing" | "eod_wrap" | "emergency" | "what_now";

interface QuickActionsProps {
  onTrigger: (action: QuickAction) => void;
  disabled?: boolean;
}

type IconCmp = React.ComponentType<React.SVGProps<SVGSVGElement>>;

const ACTIONS: {
  id: QuickAction;
  label: string;
  short: string;
  icon: IconCmp;
  accent: string;
}[] = [
  { id: "morning_briefing", label: "Morning Briefing", short: "Morning", icon: Sun, accent: "hsl(38 92% 55%)" },
  { id: "what_now", label: "What now?", short: "What now?", icon: ListTodo, accent: "hsl(252 80% 68%)" },
  { id: "emergency", label: "Emergency Replan", short: "Emergency", icon: Zap, accent: "hsl(0 75% 60%)" },
  { id: "eod_wrap", label: "EOD Wrap", short: "EOD", icon: Moon, accent: "hsl(220 70% 65%)" },
];

export function QuickActions({ onTrigger, disabled }: QuickActionsProps) {
  return (
    <div className="flex items-center gap-1.5 px-1">
      {ACTIONS.map((a) => {
        const Icon = a.icon;
        return (
          <button
            key={a.id}
            onClick={() => onTrigger(a.id)}
            disabled={disabled}
            title={a.label}
            className={cn(
              "group inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-border bg-card/60 text-[12px] font-medium text-muted-foreground transition-all whitespace-nowrap",
              "hover:border-primary/40 hover:text-foreground hover:bg-accent/40",
              "disabled:opacity-50 disabled:cursor-not-allowed"
            )}
          >
            <Icon
              className="h-3.5 w-3.5 transition-transform group-hover:scale-110"
              style={{ color: a.accent }}
            />
            <span className="hidden lg:inline">{a.label}</span>
            <span className="lg:hidden">{a.short}</span>
          </button>
        );
      })}
    </div>
  );
}
