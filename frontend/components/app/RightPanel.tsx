"use client";

import * as React from "react";
import Link from "next/link";
import { Trash2, Download, Calendar, ListTodo, LineChart } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  calendarIcsUrl,
  deleteEvent,
  getEvents,
  searchTasks,
  type CalEvent,
  type Task,
} from "@/lib/api";
import { cn, formatDayLabel } from "@/lib/utils";

type Tab = "schedule" | "tasks";

interface RightPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialTab?: Tab;
}

const PRIORITY_VARIANT: Record<string, "default" | "warning" | "secondary"> = {
  high: "default",
  medium: "warning",
  low: "secondary",
};

const STATUS_VARIANT: Record<string, "default" | "secondary" | "success" | "outline"> = {
  pending: "outline",
  in_progress: "default",
  done: "success",
  moved: "secondary",
};

export function RightPanel({ open, onOpenChange, initialTab = "schedule" }: RightPanelProps) {
  const [tab, setTab] = React.useState<Tab>(initialTab);

  React.useEffect(() => {
    if (open) setTab(initialTab);
  }, [open, initialTab]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="p-0 w-full sm:max-w-md flex flex-col">
        <SheetHeader>
          <SheetTitle>Workspace</SheetTitle>
        </SheetHeader>
        <div className="px-5 pt-4">
          <Tabs value={tab} onValueChange={(v) => setTab(v as Tab)}>
            <TabsList className="grid grid-cols-2 w-full">
              <TabsTrigger value="schedule" className="gap-1.5">
                <Calendar className="h-3.5 w-3.5" /> Schedule
              </TabsTrigger>
              <TabsTrigger value="tasks" className="gap-1.5">
                <ListTodo className="h-3.5 w-3.5" /> Tasks
              </TabsTrigger>
            </TabsList>
            <TabsContent value="schedule" className="mt-4">
              <ScheduleView active={open && tab === "schedule"} />
            </TabsContent>
            <TabsContent value="tasks" className="mt-4">
              <TaskView active={open && tab === "tasks"} />
            </TabsContent>
          </Tabs>

          {/* Insights moved to its own page — link out instead of duplicating. */}
          <Link
            href="/app/productivity"
            onClick={() => onOpenChange(false)}
            className="mt-4 flex items-center gap-2 rounded-lg border border-border bg-card/50 px-3 py-2.5 text-sm text-muted-foreground hover:text-foreground hover:border-primary/40 transition-colors"
          >
            <LineChart className="h-4 w-4 text-primary" />
            View your full productivity insights
          </Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Schedule
// ---------------------------------------------------------------------------

const DAY_LABEL: Record<string, string> = {
  mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
};

function recurrenceLabel(e: CalEvent): string {
  if (e.recurrence === "daily") return "Daily";
  if (e.recurrence === "weekdays") return "Weekdays";
  if (e.recurrence === "weekly")
    return "Weekly · " + e.recurrence_days.map((d) => DAY_LABEL[d] ?? d).join(", ");
  return "";
}

function ScheduleView({ active }: { active: boolean }) {
  const [events, setEvents] = React.useState<CalEvent[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    setLoading(true);
    getEvents(7)
      .then(setEvents)
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => {
    if (active) load();
  }, [active, load]);

  const remove = async (id: number) => {
    await deleteEvent(id);
    load();
  };

  const byDate: Record<string, CalEvent[]> = {};
  for (const e of events) (byDate[e.date] ??= []).push(e);
  const dates = Object.keys(byDate).sort();

  return (
    <ScrollArea className="h-[calc(100vh-200px)]">
      <div className="flex flex-col gap-3 pb-6 pr-1">
        <a
          href={calendarIcsUrl()}
          className="inline-flex items-center justify-center gap-2 text-xs px-3 py-2 rounded-md bg-accent text-accent-foreground hover:opacity-90 transition-opacity"
        >
          <Download className="h-3.5 w-3.5" />
          Export .ics (Apple Calendar)
        </a>

        {loading && <p className="text-sm text-muted-foreground text-center py-6">Loading…</p>}
        {!loading && events.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-6">
            No events yet. Upload a timetable screenshot or tell Donna about a meeting.
          </p>
        )}

        {dates.map((date) => (
          <div key={date}>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground mb-1.5">
              {formatDayLabel(date)}
            </p>
            <div className="space-y-1.5">
              {byDate[date].map((e) => (
                <div
                  key={`${e.id}-${date}`}
                  className="group flex items-start justify-between gap-2 rounded-lg border border-border bg-card px-3 py-2 hover:border-primary/40 transition-colors"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{e.title}</div>
                    <div className="text-xs text-muted-foreground mt-0.5">
                      {e.start_time}
                      {e.end_time ? `–${e.end_time}` : ""}
                      {e.location ? ` · ${e.location}` : ""}
                    </div>
                    {e.recurrence !== "none" && (
                      <Badge variant="outline" className="mt-1.5 text-[10px]">
                        {recurrenceLabel(e)}
                      </Badge>
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => remove(e.id)}
                    aria-label="Delete event"
                    className="opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Trash2 className="h-3.5 w-3.5 text-muted-foreground" />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}

// ---------------------------------------------------------------------------
// Tasks
// ---------------------------------------------------------------------------

function TaskView({ active }: { active: boolean }) {
  const [q, setQ] = React.useState("");
  const [priority, setPriority] = React.useState("");
  const [status, setStatus] = React.useState("");
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    setLoading(true);
    searchTasks({ q, priority, status })
      .then(setTasks)
      .catch(() => setTasks([]))
      .finally(() => setLoading(false));
  }, [q, priority, status]);

  React.useEffect(() => {
    if (active) load();
  }, [active, load]);

  const selectClass =
    "h-9 rounded-md border border-input bg-background px-2 text-sm flex-1 focus-ring";

  return (
    <ScrollArea className="h-[calc(100vh-200px)]">
      <div className="flex flex-col gap-3 pb-6 pr-1">
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search tasks…"
        />
        <div className="flex gap-2">
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
            className={selectClass}
          >
            <option value="">Any priority</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className={selectClass}
          >
            <option value="">Any status</option>
            <option value="pending">Pending</option>
            <option value="in_progress">In progress</option>
            <option value="done">Done</option>
            <option value="moved">Moved</option>
          </select>
        </div>

        {loading && <p className="text-sm text-muted-foreground text-center py-6">Loading…</p>}
        {!loading && tasks.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-6">No matching tasks.</p>
        )}

        <div className="space-y-2">
          {tasks.map((t) => (
            <div
              key={t.id}
              className="rounded-lg border border-border bg-card px-3 py-2.5 hover:border-primary/40 transition-colors"
            >
              <div className="flex items-start justify-between gap-2">
                <span
                  className={cn(
                    "text-sm font-medium",
                    t.status === "done" && "line-through text-muted-foreground"
                  )}
                >
                  {t.title}
                </span>
                <Badge variant={PRIORITY_VARIANT[t.priority] ?? "secondary"} className="capitalize shrink-0">
                  {t.priority}
                </Badge>
              </div>
              <div className="flex items-center gap-2 mt-1.5">
                <Badge variant={STATUS_VARIANT[t.status] ?? "outline"} className="text-[10px] capitalize">
                  {t.status.replace("_", " ")}
                </Badge>
                <span className="text-[11px] text-muted-foreground">
                  {formatDayLabel(t.date_assigned)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </ScrollArea>
  );
}

