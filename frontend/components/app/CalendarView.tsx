"use client";

import * as React from "react";
import Link from "next/link";
import { CalendarDays, ChevronLeft, ChevronRight, MapPin, Upload } from "lucide-react";
import { getEvents, type CalEvent } from "@/lib/api";
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
  }, [weekStart]);

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
                          <div
                            key={idx}
                            className={cn(
                              "absolute rounded-md border px-1.5 py-1 overflow-hidden text-[11px] leading-tight",
                              toneFor(p.ev)
                            )}
                            style={{
                              top,
                              height,
                              left: `calc(${p.lane * widthPct}% + 2px)`,
                              width: `calc(${widthPct}% - 4px)`,
                            }}
                            title={`${p.ev.title}${p.ev.location ? ` · ${p.ev.location}` : ""}`}
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
                          </div>
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
    </div>
  );
}
