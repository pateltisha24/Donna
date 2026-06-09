"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Circle,
  Clock,
  Flame,
  ListTodo,
  MessageSquare,
  Sparkles,
  Sun,
} from "lucide-react";
import {
  getEvents,
  getInsights,
  getMe,
  searchTasks,
  type CalEvent,
  type Insights,
  type Task,
} from "@/lib/api";
import { TopBar } from "./TopBar";
import { ContributionHeatmap } from "./ContributionHeatmap";
import { cn } from "@/lib/utils";

function greeting(d: Date): string {
  const h = d.getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function todayISO(): string {
  return new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD, local
}

export function TodayView() {
  const now = React.useMemo(() => new Date(), []);
  const [name, setName] = React.useState<string>("");
  const [tasks, setTasks] = React.useState<Task[]>([]);
  const [events, setEvents] = React.useState<CalEvent[]>([]);
  const [insights, setInsights] = React.useState<Insights | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [needsProfile, setNeedsProfile] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    const today = todayISO();
    Promise.allSettled([
      getMe(),
      searchTasks({ date: today }),
      getEvents(1),
      getInsights(77), // ~11 weeks for the momentum glance
    ]).then(([me, t, e, ins]) => {
      if (cancelled) return;
      if (me.status === "fulfilled") {
        setName(me.value.profile?.name || "");
        // Nudge first-time users to fill in basics so Donna stops assuming.
        const p = me.value.profile;
        setNeedsProfile(!(p?.occupation || "").trim() && !(p?.working_style || "").trim());
      }
      if (t.status === "fulfilled") setTasks(t.value);
      if (e.status === "fulfilled") {
        setEvents(e.value.filter((ev) => ev.date === today));
      }
      if (ins.status === "fulfilled") setInsights(ins.value);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const done = tasks.filter((t) => t.status === "done").length;
  const pending = tasks.filter((t) => t.status !== "done");
  const completion = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  const dateLabel = now.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-5xl px-4 md:px-8 py-8">
          {/* Greeting */}
          <div className="mb-8">
            <p className="text-sm text-muted-foreground flex items-center gap-1.5">
              <Sun className="h-3.5 w-3.5 text-primary" /> {dateLabel}
            </p>
            <h1 className="text-3xl font-semibold tracking-tight mt-1">
              {greeting(now)}
              {name ? `, ${name.split(" ")[0]}` : ""}.
            </h1>
            <p className="text-muted-foreground mt-1.5">
              {loading
                ? "Pulling your day together…"
                : tasks.length || events.length
                ? "Here's what your day looks like."
                : "A clean slate. Tell Donna what's on your plate."}
            </p>
          </div>

          {/* First-run nudge: a filled profile means Donna assumes less. */}
          {!loading && needsProfile && (
            <Link
              href="/app/settings"
              className="group mb-8 flex items-center gap-3 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 transition hover:bg-primary/10"
            >
              <div className="h-9 w-9 shrink-0 rounded-lg bg-primary/15 flex items-center justify-center">
                <Sparkles className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium">Finish setting up your profile</p>
                <p className="text-xs text-muted-foreground">
                  Tell Donna your role, hours, and how you work — so she plans for you instead of guessing.
                </p>
              </div>
              <ArrowRight className="h-4 w-4 text-primary ml-auto shrink-0 transition group-hover:translate-x-0.5" />
            </Link>
          )}

          {/* At a glance */}
          <div className="grid grid-cols-3 gap-3 md:gap-4 mb-8">
            <StatCard
              icon={ListTodo}
              label="Tasks today"
              value={loading ? "—" : String(tasks.length)}
              hint={tasks.length ? `${pending.length} to go` : "none yet"}
            />
            <StatCard
              icon={CalendarDays}
              label="Events today"
              value={loading ? "—" : String(events.length)}
              hint={events.length ? "on your calendar" : "nothing scheduled"}
            />
            <StatCard
              icon={CheckCircle2}
              label="Completed"
              value={loading ? "—" : `${completion}%`}
              hint={tasks.length ? `${done}/${tasks.length} done` : "—"}
            />
          </div>

          {/* Quick actions */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
            <ActionCard
              href="/app/chat?ask=Give%20me%20my%20morning%20briefing"
              icon={Sparkles}
              title="Morning briefing"
              body="Donna walks you through the day"
            />
            <ActionCard
              href="/app/chat?ask=What%20should%20I%20work%20on%20right%20now%3F"
              icon={Clock}
              title="What now?"
              body="Decide the next best thing"
            />
            <ActionCard
              href="/app/chat"
              icon={MessageSquare}
              title="Talk to Donna"
              body="Plan, add tasks, or replan"
            />
          </div>

          {/* Momentum glance — your recent productivity at a glance */}
          {insights && insights.summary.total > 0 && (
            <Link
              href="/app/productivity"
              className="group block rounded-xl border border-border bg-card shadow-elev-1 hover:shadow-elev-2 hover:border-primary/40 transition-all p-5 mb-8"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <Flame className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium">Your momentum</span>
                  {insights.summary.current_streak > 0 && (
                    <span className="text-xs text-muted-foreground">
                      · {insights.summary.current_streak}-day streak
                    </span>
                  )}
                </div>
                <span className="text-xs text-muted-foreground group-hover:text-foreground transition-colors">
                  View productivity →
                </span>
              </div>
              <div className="overflow-x-auto">
                <ContributionHeatmap
                  daily={insights.daily}
                  metric="done"
                  cell={11}
                  showWeekdays={false}
                  showMonths
                />
              </div>
            </Link>
          )}

          {/* Two columns: schedule + focus */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <SectionCard
              title="Today's schedule"
              icon={CalendarDays}
              href="/app/calendar"
              empty={!loading && events.length === 0}
              emptyText="No events today. Upload a screenshot or .ics in chat to fill it in."
              loading={loading}
            >
              {events.map((ev) => (
                <div key={ev.id} className="flex items-center gap-3 py-2">
                  <span className="text-xs font-mono text-primary w-14 shrink-0">
                    {ev.start_time || "--:--"}
                  </span>
                  <span className="text-sm truncate">{ev.title}</span>
                  {ev.location && (
                    <span className="text-xs text-muted-foreground ml-auto truncate">
                      {ev.location}
                    </span>
                  )}
                </div>
              ))}
            </SectionCard>

            <SectionCard
              title="Today's focus"
              icon={ListTodo}
              href="/app/chat"
              empty={!loading && tasks.length === 0}
              emptyText="No tasks yet. Tell Donna what you need to get done today."
              loading={loading}
            >
              {tasks.map((t) => (
                <div key={t.id} className="flex items-center gap-3 py-2">
                  {t.status === "done" ? (
                    <CheckCircle2 className="h-4 w-4 text-success shrink-0" />
                  ) : (
                    <Circle className="h-4 w-4 text-muted-foreground shrink-0" />
                  )}
                  <span
                    className={cn(
                      "text-sm truncate",
                      t.status === "done" && "line-through text-muted-foreground"
                    )}
                  >
                    {t.title}
                  </span>
                  <PriorityDot priority={t.priority} />
                </div>
              ))}
            </SectionCard>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-elev-1">
      <div className="flex items-center gap-2 text-muted-foreground mb-2">
        <Icon className="h-4 w-4" />
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-2xl font-semibold tracking-tight">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>
    </div>
  );
}

function ActionCard({
  href,
  icon: Icon,
  title,
  body,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-xl border border-border bg-card p-4 shadow-elev-1 hover:shadow-elev-2 hover:border-primary/40 transition-all"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="h-9 w-9 rounded-lg bg-accent/60 flex items-center justify-center group-hover:bg-accent transition-colors">
          <Icon className="h-4 w-4 text-primary" />
        </div>
        <ArrowRight className="h-4 w-4 text-muted-foreground/0 group-hover:text-muted-foreground transition-colors" />
      </div>
      <p className="font-medium text-sm">{title}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{body}</p>
    </Link>
  );
}

function SectionCard({
  title,
  icon: Icon,
  href,
  children,
  empty,
  emptyText,
  loading,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  children: React.ReactNode;
  empty: boolean;
  emptyText: string;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-card shadow-elev-1 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">{title}</span>
        </div>
        <Link
          href={href}
          className="text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          Open
        </Link>
      </div>
      <div className="px-4 py-2 min-h-[120px]">
        {loading ? (
          <div className="space-y-2 py-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-5 rounded bg-muted/60 animate-pulse" style={{ width: `${80 - i * 15}%` }} />
            ))}
          </div>
        ) : empty ? (
          <p className="text-sm text-muted-foreground py-6 text-center">{emptyText}</p>
        ) : (
          <div className="divide-y divide-border/60">{children}</div>
        )}
      </div>
    </div>
  );
}

function PriorityDot({ priority }: { priority: Task["priority"] }) {
  const color =
    priority === "high"
      ? "bg-destructive"
      : priority === "medium"
      ? "bg-warning"
      : "bg-muted-foreground/40";
  return <span className={cn("ml-auto h-2 w-2 rounded-full shrink-0", color)} title={`${priority} priority`} />;
}
