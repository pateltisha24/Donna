"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  calendarIcsUrl,
  deleteEvent,
  getAnalytics,
  getEvents,
  searchTasks,
  type Analytics,
  type CalEvent,
  type Task,
} from "../../lib/api";

type Tab = "schedule" | "tasks" | "insights";

const PRIORITY_COLORS: Record<string, string> = {
  high: "#e0566a",
  medium: "#d8a23a",
  low: "#5aa0e0",
};

export default function TaskPanel() {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("schedule");

  // Tasks tab state
  const [q, setQ] = useState("");
  const [priority, setPriority] = useState("");
  const [status, setStatus] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);

  // Schedule tab state
  const [events, setEvents] = useState<CalEvent[]>([]);

  // Insights tab state
  const [analytics, setAnalytics] = useState<Analytics | null>(null);

  const loadTasks = useCallback(() => {
    searchTasks({ q, priority, status })
      .then(setTasks)
      .catch(() => setTasks([]));
  }, [q, priority, status]);

  const loadEvents = useCallback(() => {
    getEvents(7).then(setEvents).catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    if (open && tab === "tasks") loadTasks();
  }, [open, tab, loadTasks]);

  useEffect(() => {
    if (open && tab === "schedule") loadEvents();
  }, [open, tab, loadEvents]);

  useEffect(() => {
    if (open && tab === "insights") {
      getAnalytics(7).then(setAnalytics).catch(() => setAnalytics(null));
    }
  }, [open, tab]);

  const removeEvent = async (id: number) => {
    await deleteEvent(id);
    loadEvents();
  };

  const selectStyle = {
    backgroundColor: "var(--bg)",
    color: "var(--text)",
    border: "1px solid var(--border)",
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs px-3 py-1.5 rounded-lg transition-colors"
        style={{
          backgroundColor: "var(--surface-2)",
          color: "var(--muted)",
          border: "1px solid var(--border)",
        }}
      >
        Tasks
      </button>

      {open && (
        <div
          className="fixed inset-0 z-40 flex justify-end"
          style={{ backgroundColor: "rgba(0,0,0,0.4)" }}
          onClick={() => setOpen(false)}
        >
          <div
            className="w-full max-w-md h-full flex flex-col"
            style={{ backgroundColor: "var(--surface)", borderLeft: "1px solid var(--border)" }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-4 py-3 border-b"
              style={{ borderColor: "var(--border)" }}
            >
              <div className="flex gap-2">
                {(["schedule", "tasks", "insights"] as Tab[]).map((t) => (
                  <button
                    key={t}
                    onClick={() => setTab(t)}
                    className="text-sm px-3 py-1 rounded-lg capitalize transition-colors"
                    style={{
                      backgroundColor: tab === t ? "var(--accent)" : "transparent",
                      color: tab === t ? "var(--accent-contrast)" : "var(--muted)",
                    }}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close panel"
                style={{ color: "var(--muted)" }}
                className="text-lg px-2"
              >
                ✕
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-4">
              {tab === "schedule" ? (
                <ScheduleView events={events} onDelete={removeEvent} />
              ) : tab === "tasks" ? (
                <div className="flex flex-col gap-3">
                  <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Search tasks…"
                    className="rounded-lg px-3 py-2 text-sm outline-none"
                    style={selectStyle}
                  />
                  <div className="flex gap-2">
                    <select
                      value={priority}
                      onChange={(e) => setPriority(e.target.value)}
                      className="flex-1 rounded-lg px-2 py-2 text-sm outline-none"
                      style={selectStyle}
                    >
                      <option value="">Any priority</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                    <select
                      value={status}
                      onChange={(e) => setStatus(e.target.value)}
                      className="flex-1 rounded-lg px-2 py-2 text-sm outline-none"
                      style={selectStyle}
                    >
                      <option value="">Any status</option>
                      <option value="pending">Pending</option>
                      <option value="in_progress">In progress</option>
                      <option value="done">Done</option>
                      <option value="moved">Moved</option>
                    </select>
                  </div>

                  {tasks.length === 0 && (
                    <p className="text-sm text-center mt-6" style={{ color: "var(--muted)" }}>
                      No matching tasks.
                    </p>
                  )}
                  {tasks.map((t) => (
                    <div
                      key={t.id}
                      className="rounded-lg px-3 py-2"
                      style={{ backgroundColor: "var(--surface-2)", border: "1px solid var(--border)" }}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className="text-sm"
                          style={{
                            color: "var(--text)",
                            textDecoration: t.status === "done" ? "line-through" : "none",
                            opacity: t.status === "done" ? 0.6 : 1,
                          }}
                        >
                          {t.title}
                        </span>
                        <span
                          className="text-[10px] uppercase px-1.5 py-0.5 rounded"
                          style={{ color: PRIORITY_COLORS[t.priority], border: `1px solid ${PRIORITY_COLORS[t.priority]}` }}
                        >
                          {t.priority}
                        </span>
                      </div>
                      <div className="text-xs mt-1" style={{ color: "var(--muted)" }}>
                        {t.date_assigned} · {t.status.replace("_", " ")}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <InsightsView analytics={analytics} />
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

const DAY_LABEL: Record<string, string> = {
  mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
};

function recurrenceLabel(e: CalEvent): string {
  if (e.recurrence === "daily") return "Daily";
  if (e.recurrence === "weekdays") return "Weekdays";
  if (e.recurrence === "weekly") {
    return "Weekly · " + e.recurrence_days.map((d) => DAY_LABEL[d] ?? d).join(", ");
  }
  return e.date;
}

function ScheduleView({
  events,
  onDelete,
}: {
  events: CalEvent[];
  onDelete: (id: number) => void;
}) {
  // Group by date for the agenda.
  const byDate: Record<string, CalEvent[]> = {};
  for (const e of events) (byDate[e.date] ??= []).push(e);
  const dates = Object.keys(byDate).sort();

  return (
    <div className="flex flex-col gap-3">
      <a
        href={calendarIcsUrl()}
        className="text-xs px-3 py-2 rounded-lg text-center transition-colors"
        style={{ backgroundColor: "var(--accent)", color: "var(--accent-contrast)" }}
      >
        Add to Apple Calendar (.ics)
      </a>

      {events.length === 0 && (
        <p className="text-sm text-center mt-6" style={{ color: "var(--muted)" }}>
          No events yet. Upload a timetable screenshot or tell Donna about a meeting.
        </p>
      )}

      {dates.map((date) => (
        <div key={date}>
          <p className="text-xs font-semibold mb-1" style={{ color: "var(--muted)" }}>
            {date}
          </p>
          {byDate[date].map((e) => (
            <div
              key={`${e.id}-${date}`}
              className="rounded-lg px-3 py-2 mb-1.5 flex items-start justify-between gap-2"
              style={{ backgroundColor: "var(--surface-2)", border: "1px solid var(--border)" }}
            >
              <div>
                <div className="text-sm" style={{ color: "var(--text)" }}>
                  {e.title}
                </div>
                <div className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                  {e.start_time}
                  {e.end_time ? `–${e.end_time}` : ""}
                  {e.location ? ` · ${e.location}` : ""}
                  {e.recurrence !== "none" ? ` · ${recurrenceLabel(e)}` : ""}
                </div>
              </div>
              <button
                onClick={() => onDelete(e.id)}
                aria-label="Delete event"
                className="text-xs px-1.5"
                style={{ color: "var(--muted)" }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

function InsightsView({ analytics }: { analytics: Analytics | null }) {
  if (!analytics) {
    return <p className="text-sm" style={{ color: "var(--muted)" }}>Loading…</p>;
  }
  const maxTotal = Math.max(1, ...analytics.days.map((d) => d.total));

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Tasks" value={analytics.total} />
        <Stat label="Done" value={analytics.done} />
        <Stat label="Rate" value={`${Math.round(analytics.completion_rate * 100)}%`} />
      </div>

      <div>
        <p className="text-xs mb-2" style={{ color: "var(--muted)" }}>
          Last {analytics.days.length} days
        </p>
        <div className="flex items-end gap-1.5 h-32">
          {analytics.days.map((d) => (
            <div key={d.date} className="flex-1 flex flex-col items-center justify-end h-full gap-1">
              <div className="w-full flex flex-col justify-end h-full">
                <div
                  className="w-full rounded-t"
                  style={{
                    height: `${(d.total / maxTotal) * 100}%`,
                    backgroundColor: "var(--border)",
                    position: "relative",
                  }}
                >
                  <div
                    className="w-full rounded-t absolute bottom-0"
                    style={{
                      height: d.total ? `${(d.done / d.total) * 100}%` : "0%",
                      backgroundColor: "var(--accent)",
                    }}
                  />
                </div>
              </div>
              <span className="text-[9px]" style={{ color: "var(--muted)" }}>
                {d.date.slice(5)}
              </span>
            </div>
          ))}
        </div>
        <p className="text-[10px] mt-2" style={{ color: "var(--muted)" }}>
          Filled bar = completed, full bar = total scheduled.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div
      className="rounded-lg px-3 py-2 text-center"
      style={{ backgroundColor: "var(--surface-2)", border: "1px solid var(--border)" }}
    >
      <div className="text-lg font-semibold" style={{ color: "var(--text)" }}>
        {value}
      </div>
      <div className="text-[10px] uppercase" style={{ color: "var(--muted)" }}>
        {label}
      </div>
    </div>
  );
}
