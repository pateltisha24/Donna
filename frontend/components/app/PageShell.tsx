"use client";

import * as React from "react";
import { TopBar } from "./TopBar";

/**
 * Standard frame for a top-level destination (Today, Calendar, Productivity).
 * Renders the shared TopBar plus a scrollable, width-constrained content area
 * so every page lines up with the same rhythm.
 */
export function PageShell({
  children,
  width = "wide",
}: {
  children: React.ReactNode;
  width?: "wide" | "narrow";
}) {
  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar />
      <div className="flex-1 overflow-y-auto">
        <div
          className={
            "mx-auto w-full px-4 md:px-8 py-8 " +
            (width === "narrow" ? "max-w-2xl" : "max-w-5xl")
          }
        >
          {children}
        </div>
      </div>
    </div>
  );
}

/** Page title + optional subtitle + optional right-aligned actions. */
export function PageHeader({
  title,
  subtitle,
  icon: Icon,
  actions,
}: {
  title: string;
  subtitle?: string;
  icon?: React.ComponentType<{ className?: string }>;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-8">
      <div className="flex items-start gap-3 min-w-0">
        {Icon && (
          <div className="h-10 w-10 rounded-xl bg-accent/60 flex items-center justify-center shrink-0">
            <Icon className="h-5 w-5 text-primary" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {subtitle && (
            <p className="text-sm text-muted-foreground mt-1">{subtitle}</p>
          )}
        </div>
      </div>
      {actions && <div className="shrink-0">{actions}</div>}
    </div>
  );
}

/** Friendly empty / placeholder state used across destinations. */
export function EmptyPanel({
  icon: Icon,
  title,
  body,
  action,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center text-center rounded-xl border border-dashed border-border bg-card/30 px-6 py-12">
      <div className="h-11 w-11 rounded-full bg-accent/50 flex items-center justify-center mb-3">
        <Icon className="h-5 w-5 text-muted-foreground" />
      </div>
      <p className="font-medium">{title}</p>
      <p className="text-sm text-muted-foreground mt-1 max-w-sm">{body}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
