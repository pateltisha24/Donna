"use client";

import * as React from "react";
import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight, MapPin, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { getEvents, updateEvent, deleteEvent, type CalEvent } from "@/lib/api";
import { TopBar } from "./TopBar";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Visible window of the day, in hours. Events outside still clamp into view.
const DAY_START = 7;
const DAY_END = 22;
const HOUR_H = 52; // px per hour
const GUTTER = 56; // px width of the time gutter

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function toMin(t: string | null): number | null {
  if (!t) return null;
  const [h, m] = t.split(":").map(Number);
  if (Number.isNaN(h)) return null;
  return h * 60 + (m || 0);
}

function isoOf(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate()
  ).padStart(2, "0")}`;
}

function startOfWeek(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  x.setDate(x.getDate() - x.getDay()); // back to Sunday
  return x;
}

function fmtHour(h: number): string {
  if (h === 0 || h === 24) return "12 AM";
  if (h === 12) return "12 PM";
  return h < 12 ? `${h} AM` : `${h - 12} PM`;
}

interface Positioned {
  ev: CalEvent;
  startMin: number;
  endMin: number;
  lane: number;
  lanes: number;
}

// Greedy lane packing within a day so overlapping events sit side by side.
function layoutDay(events: CalEvent[]): Positioned[] {
  const timed = events
    .map((ev) => {
      const startMin = toMin(ev.start_time);
      if (startMin == null) return null;
      const endRaw = toMin(ev.end_time);
      const endMin = endRaw && endRaw > startMin ? endRaw : startMin + 60;
      return { ev, startMin, endMin } as Positioned;
    })
    .filter((x): x is Positioned => x !== null)
    .sort((a, b) => a.startMin - b.startMin);

  // Split into clusters of transitively-overlapping events.
  const out: Positioned[] = [];
  let cluster: Positioned[] = [];
  let clusterEnd = -1;

  const flush = () => {
    if (!cluster.length) return;
    const laneEnds: number[] = [];
    for (const item of cluster) {
      let placed = false;
      for (let i = 0; i < laneEnds.length; i++) {
        if (laneEnds[i] <= item.startMin) {
          item.lane = i;
          laneEnds[i] = item.endMin;
          placed = true;
          break;
        }
      }
      if (!placed) {
        item.lane = laneEnds.length;
        laneEnds.push(item.endMin);
      }
    }
    for (const item of cluster) item.lanes = laneEnds.length;
    out.push(...cluster);
    cluster = [];
    clusterEnd = -1;
  };

  for (const item of timed) {
    if (cluster.length && item.startMin >= clusterEnd) flush();
    cluster.push(item);
    clusterEnd = Math.max(clusterEnd, item.endMin);
  }
  flush();
  return out;
}

const EVENT_TONES = [
  "bg-primary/20 border-primary/50 text-foreground",
  "bg-[hsl(168_45%_42%/0.18)] border-[hsl(168_45%_45%/0.5)] text-foreground",
  "bg-[hsl(220_60%_60%/0.18)] border-[hsl(220_60%_62%/0.5)] text-foreground",
];

function toneFor(ev: CalEvent): string {
  // Stable tone per title so the same event keeps its colour across the week.
  let h = 0;
  for (const c of ev.title) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return EVENT_TONES[h % EVENT_TONES.length];
}

export function CalendarView() {
  const [weekStart, setWeekStart] = React.useState<Date>(() => startOfWeek(new Date()));
  const [events, setEvents] = React.useState<CalEvent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [editing, setEditing] = React.useState<CalEvent | null>(null);
  const [reloadKey, setReloadKey] = React.useState(0);

  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getEvents(7, isoOf(weekStart))
      .then((evs) => !cancelled && setEvents(evs))
      .catch(() => !cancelled && setEvents([]))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [weekStart, reloadKey]);

  const reload = React.useCallback(() => setReloadKey((k) => k + 1), []);

  const days = React.useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) => {
        const d = new Date(weekStart);
        d.setDate(d.getDate() + i);
        return d;
      }),
    [weekStart]
  );

  const byDay = React.useMemo(() => {
    const map = new Map<string, CalEvent[]>();
    for (const ev of events) {
      const arr = map.get(ev.date) ?? [];
      arr.push(ev);
      map.set(ev.date, arr);
    }
    return map;
  }, [events]);

  const hours = Array.from({ length: DAY_END - DAY_START + 1 }, (_, i) => DAY_START + i);
  const bodyHeight = (DAY_END - DAY_START) * HOUR_H;
  const todayIso = isoOf(new Date());

  const rangeLabel = (() => {
    const end = new Date(weekStart);
    end.setDate(end.getDate() + 6);
    const sameMonth = weekStart.getMonth() === end.getMonth();
    const opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
    return `${weekStart.toLocaleDateString(undefined, opts)} – ${end.toLocaleDateString(
      undefined,
      sameMonth ? { day: "numeric", year: "numeric" } : { ...opts, year: "numeric" }
    )}`;
  })();

  const shiftWeek = (delta: number) => {
    const d = new Date(weekStart);
    d.setDate(d.getDate() + delta * 7);
    setWeekStart(d);
  };

  // "Now" line position (only drawn on today's column).
  const nowMin = (() => {
    const n = new Date();
    return n.getHours() * 60 + n.getMinutes();
  })();
  const nowTop = ((nowMin - DAY_START * 60) / 60) * HOUR_H;
  const nowVisible = nowMin >= DAY_START * 60 && nowMin <= DAY_END * 60;

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar />
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-6xl px-4 md:px-8 py-6">
          {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-accent/60 flex items-center justify-center">
                <CalendarDays className="h-5 w-5 text-primary" />
              </div>
              <div>
                <h1 className="text-xl font-semibold tracking-tight">Calendar</h1>
                <p className="text-sm text-muted-foreground">{rangeLabel}</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => setWeekStart(startOfWeek(new Date()))}>
                Today
              </Button>
              <div className="flex items-center rounded-lg border border-border">
                <button
                  onClick={() => shiftWeek(-1)}
                  className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="Previous week"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="w-px h-5 bg-border" />
                <button
                  onClick={() => shiftWeek(1)}
                  className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="Next week"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
              <Button asChild variant="ghost" size="sm">
                <Link href="/app/chat">
                  <Upload className="h-4 w-4" /> Add
                </Link>
              </Button>
            </div>
          </div>

          {/* Grid */}
          <div className="rounded-xl border border-border bg-card shadow-elev-1 overflow-hidden">
            {/* Day headers */}
            <div className="flex border-b border-border" style={{ paddingLeft: GUTTER }}>
              {days.map((d) => {
                const iso = isoOf(d);
                const isToday = iso === todayIso;
                return (
                  <div key={iso} className="flex-1 text-center py-2.5 border-l border-border/60">
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      {WEEKDAYS[d.getDay()]}
                    </div>
                    <div
                      className={cn(
                        "mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full text-sm font-medium",
                        isToday ? "bg-primary text-primary-foreground" : "text-foreground"
                      )}
                    >
                      {d.getDate()}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Body */}
            <div className="relative flex" style={{ height: bodyHeight }}>
              {/* Hour gutter + gridlines */}
              <div className="absolute inset-0" style={{ left: GUTTER }}>
                {hours.map((h, i) => (
                  <div
                    key={h}
                    className="absolute left-0 right-0 border-t border-border/40"
                    style={{ top: i * HOUR_H }}
                  />
                ))}
              </div>
              <div className="absolute top-0 bottom-0 left-0" style={{ width: GUTTER }}>
                {hours.slice(0, -1).map((h, i) => (
                  <div
                    key={h}
                    className="absolute right-2 -translate-y-1/2 text-[10px] text-muted-foreground"
                    style={{ top: (i + 1) * HOUR_H }}
                  >
                    {fmtHour(h + 1)}
                  </div>
                ))}
              </div>

              {/* Day columns */}
              <div className="flex w-full" style={{ marginLeft: GUTTER }}>
                {days.map((d) => {
                  const iso = isoOf(d);
                  const positioned = layoutDay(byDay.get(iso) ?? []);
                  const isToday = iso === todayIso;
                  return (
                    <div key={iso} className="relative flex-1 border-l border-border/60">
                      {isToday && nowVisible && (
                        <div className="absolute left-0 right-0 z-20 pointer-events-none" style={{ top: nowTop }}>
                          <div className="h-px bg-primary" />
                          <div className="absolute -left-1 -top-1 h-2 w-2 rounded-full bg-primary" />
                        </div>
                      )}
                      {positioned.map((p, idx) => {
                        const top = Math.max(0, ((p.startMin - DAY_START * 60) / 60) * HOUR_H);
                        const height = Math.max(
                          18,
                          ((Math.min(p.endMin, DAY_END * 60) - p.startMin) / 60) * HOUR_H - 2
                        );
                        const widthPct = 100 / p.lanes;
                        return (
                          <button
                            key={idx}
                            onClick={() => setEditing(p.ev)}
                            className={cn(
                              "absolute rounded-md border px-1.5 py-1 overflow-hidden text-[11px] leading-tight text-left",
                              "cursor-pointer hover:brightness-110 hover:ring-1 hover:ring-primary/50 transition",
                              toneFor(p.ev)
                            )}
                            style={{
                              top,
                              height,
                              left: `calc(${p.lane * widthPct}% + 2px)`,
                              width: `calc(${widthPct}% - 4px)`,
                            }}
                            title={`${p.ev.title}${p.ev.location ? ` · ${p.ev.location}` : ""} — click to edit`}
                          >
                            <div className="font-medium truncate">{p.ev.title}</div>
                            {height > 30 && (
                              <div className="opacity-70 truncate">
                                {p.ev.start_time}
                                {p.ev.end_time ? `–${p.ev.end_time}` : ""}
                              </div>
                            )}
                            {height > 52 && p.ev.location && (
                              <div className="opacity-70 truncate flex items-center gap-0.5 mt-0.5">
                                <MapPin className="h-2.5 w-2.5" /> {p.ev.location}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {loading && (
            <p className="text-xs text-muted-foreground mt-3 text-center">Loading week…</p>
          )}
          {!loading && events.length === 0 && (
            <p className="text-sm text-muted-foreground mt-4 text-center">
              No events this week. Add one by uploading a screenshot or .ics in chat.
            </p>
          )}
        </div>
      </div>

      {editing && (
        <EventEditor
          event={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

const DAY_OPTS = [
  { v: "sun", l: "S" }, { v: "mon", l: "M" }, { v: "tue", l: "T" },
  { v: "wed", l: "W" }, { v: "thu", l: "T" }, { v: "fri", l: "F" }, { v: "sat", l: "S" },
];

function EventEditor({
  event,
  onClose,
  onSaved,
}: {
  event: CalEvent;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = React.useState(event.title);
  const [date, setDate] = React.useState(event.date);
  const [start, setStart] = React.useState(event.start_time || "09:00");
  const [end, setEnd] = React.useState(event.end_time || "");
  const [location, setLocation] = React.useState(event.location || "");
  const [recurrence, setRecurrence] = React.useState(event.recurrence || "none");
  const [days, setDays] = React.useState<string[]>(event.recurrence_days || []);
  const [busy, setBusy] = React.useState(false);

  const toggleDay = (d: string) =>
    setDays((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));

  const save = async () => {
    setBusy(true);
    try {
      await updateEvent(event.id, {
        title: title.trim() || event.title,
        date,
        start_time: start,
        end_time: end || null,
        location,
        recurrence,
        recurrence_days: recurrence === "weekly" ? days : [],
      });
      toast.success("Event updated.");
      onSaved();
    } catch {
      toast.error("Couldn't update the event.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    setBusy(true);
    try {
      await deleteEvent(event.id);
      toast.success("Event deleted.");
      onSaved();
    } catch {
      toast.error("Couldn't delete the event.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-border bg-card shadow-elev-3 p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold tracking-tight">Edit event</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-3">
          <Field label="Title">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm"
            />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Date">
              <input type="date" value={date} onChange={(e) => setDate(e.target.value)}
                className="w-full h-9 px-2 rounded-md border border-input bg-background text-sm" />
            </Field>
            <Field label="Start">
              <input type="time" value={start} onChange={(e) => setStart(e.target.value)}
                className="w-full h-9 px-2 rounded-md border border-input bg-background text-sm" />
            </Field>
            <Field label="End">
              <input type="time" value={end} onChange={(e) => setEnd(e.target.value)}
                className="w-full h-9 px-2 rounded-md border border-input bg-background text-sm" />
            </Field>
          </div>
          <Field label="Location">
            <input value={location} onChange={(e) => setLocation(e.target.value)}
              className="w-full h-9 px-3 rounded-md border border-input bg-background text-sm" />
          </Field>
          <Field label="Repeats">
            <select value={recurrence} onChange={(e) => setRecurrence(e.target.value)}
              className="w-full h-9 px-2 rounded-md border border-input bg-background text-sm">
              <option value="none">Does not repeat</option>
              <option value="daily">Daily</option>
              <option value="weekdays">Weekdays (Mon–Fri)</option>
              <option value="weekly">Weekly on…</option>
            </select>
          </Field>
          {recurrence === "weekly" && (
            <div className="flex gap-1.5">
              {DAY_OPTS.map((d) => (
                <button
                  key={d.v}
                  onClick={() => toggleDay(d.v)}
                  className={cn(
                    "h-8 w-8 rounded-full text-xs font-medium border transition",
                    days.includes(d.v)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-input text-muted-foreground hover:text-foreground"
                  )}
                >
                  {d.l}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between mt-5">
          <Button variant="ghost" size="sm" onClick={remove} disabled={busy}
            className="text-destructive hover:text-destructive">
            <Trash2 className="h-4 w-4" /> Delete
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onClose} disabled={busy}>Cancel</Button>
            <Button size="sm" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <label className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}
