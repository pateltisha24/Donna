"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { ArrowRight, ArrowUp, Check, Plus, RotateCcw, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

type Kind = "added" | "moved" | "bumped" | "changed";

function classify(change: string): Kind {
  const c = change.toLowerCase();
  if (c.startsWith("added")) return "added";
  if (c.startsWith("moved")) return "moved";
  if (c.startsWith("bumped")) return "bumped";
  return "changed";
}

const META: Record<Kind, { icon: React.ComponentType<{ className?: string }>; tone: string; label: string }> = {
  added: { icon: Plus, tone: "text-[hsl(152_55%_45%)] bg-[hsl(152_55%_45%/0.12)]", label: "Added" },
  moved: { icon: ArrowRight, tone: "text-[hsl(220_70%_62%)] bg-[hsl(220_70%_62%/0.12)]", label: "Moved" },
  bumped: { icon: ArrowUp, tone: "text-[hsl(36_92%_50%)] bg-[hsl(36_92%_50%/0.12)]", label: "Bumped" },
  changed: { icon: Sparkles, tone: "text-primary bg-primary/12", label: "Changed" },
};

export function ReplanCard({
  changes,
  canUndo,
  onUndo,
}: {
  changes: string[];
  canUndo: boolean;
  onUndo: () => Promise<void>;
}) {
  const [state, setState] = React.useState<"idle" | "undoing" | "undone">("idle");

  const handleUndo = async () => {
    if (state !== "idle") return;
    setState("undoing");
    try {
      await onUndo();
      setState("undone");
    } catch {
      setState("idle");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className="mt-3 rounded-xl border border-border bg-card/80 shadow-elev-2 overflow-hidden"
    >
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border/70 bg-accent/30">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
        <span className="text-xs font-semibold tracking-wide uppercase text-muted-foreground">
          Day replanned
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">
          {changes.length} change{changes.length === 1 ? "" : "s"}
        </span>
      </div>

      <ul className="px-3 py-2.5 space-y-1.5">
        {changes.map((change, i) => {
          const kind = classify(change);
          const { icon: Icon, tone, label } = META[kind];
          // Strip the leading verb so the badge isn't redundant with the text.
          const text = change.replace(/^(Added task |Added |Moved |Bumped )/i, "");
          return (
            <motion.li
              key={i}
              initial={{ opacity: 0, x: -6 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.08 * i + 0.1, duration: 0.25 }}
              className={cn(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-1.5",
                state === "undone" && "opacity-50 line-through"
              )}
            >
              <span className={cn("flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold shrink-0", tone)}>
                <Icon className="h-3 w-3" />
                {label}
              </span>
              <span className="text-sm text-foreground/90 truncate">{text}</span>
            </motion.li>
          );
        })}
      </ul>

      {canUndo && (
        <div className="px-3 pb-2.5">
          <button
            onClick={handleUndo}
            disabled={state !== "idle"}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
              state === "undone"
                ? "text-[hsl(152_55%_45%)]"
                : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
            )}
          >
            {state === "undone" ? (
              <>
                <Check className="h-3.5 w-3.5" /> Reverted
              </>
            ) : (
              <>
                <RotateCcw className={cn("h-3.5 w-3.5", state === "undoing" && "animate-spin")} />
                {state === "undoing" ? "Undoing…" : "Undo replan"}
              </>
            )}
          </button>
        </div>
      )}
    </motion.div>
  );
}
