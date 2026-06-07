"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import type { InsightDay } from "@/lib/api";

export type HeatMetric = "done" | "focus";

// Map a metric value to one of 5 intensity levels. Thresholds are tuned for a
// personal day: a handful of completed tasks (or ~2h focus) reads as a "full"
// day. Level 0 is an empty/quiet day.
function levelFor(value: number, metric: HeatMetric): 0 | 1 | 2 | 3 | 4 {
  if (value <= 0) return 0;
  if (metric === "focus") {
    // minutes
    if (value < 30) return 1;
    if (value < 90) return 2;
    if (value < 180) return 3;
    return 4;
  }
  // completed task count
  if (value <= 1) return 1;
  if (value <= 3) return 2;
  if (value <= 5) return 3;
  return 4;
}

const LEVEL_CLASS: Record<number, string> = {
  0: "bg-muted/50",
  1: "bg-primary/25",
  2: "bg-primary/45",
  3: "bg-primary/70",
  4: "bg-primary",
};

function metricValue(d: InsightDay, metric: HeatMetric): number {
  return metric === "focus" ? d.focus_min : d.done;
}

function fmtMinutes(m: number): string {
  if (!m) return "0m";
  const h = Math.floor(m / 60);
  const min = m % 60;
  return h ? `${h}h${min ? ` ${min}m` : ""}` : `${min}m`;
}

function fmtDate(iso: string): string {
  const [y, mo, day] = iso.split("-").map(Number);
  return new Date(y, mo - 1, day).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["", "Mon", "", "Wed", "", "Fri", ""];

interface Week {
  days: (InsightDay | null)[]; // 7 entries, Sun..Sat; null = padding
}

/**
 * GitHub / Claude-style contribution grid. `daily` is a dense day series; we
 * pack it into week-columns aligned to Sunday and colour each cell by intensity.
 */
export function ContributionHeatmap({
  daily,
  metric = "done",
  onSelectDay,
  selectedDate,
  cell = 13,
  showMonths = true,
  showWeekdays = true,
}: {
  daily: InsightDay[];
  metric?: HeatMetric;
  onSelectDay?: (d: InsightDay) => void;
  selectedDate?: string | null;
  cell?: number; // px size of each square
  showMonths?: boolean;
  showWeekdays?: boolean;
}) {
  const { weeks, monthLabels } = React.useMemo(() => {
    if (!daily.length) return { weeks: [] as Week[], monthLabels: [] as (string | null)[] };

    const byDate = new Map(daily.map((d) => [d.date, d]));
    const parse = (iso: string) => {
      const [y, m, dd] = iso.split("-").map(Number);
      return new Date(y, m - 1, dd);
    };
    const start = parse(daily[0].date);
    const end = parse(daily[daily.length - 1].date);

    // Back up to the Sunday on/before the first day.
    const gridStart = new Date(start);
    gridStart.setDate(gridStart.getDate() - gridStart.getDay());

    const weeks: Week[] = [];
    const monthLabels: (string | null)[] = [];
    let cursor = new Date(gridStart);
    let lastMonth = -1;

    while (cursor <= end) {
      const week: Week = { days: [] };
      const weekFirstMonth = cursor.getMonth();
      for (let i = 0; i < 7; i++) {
        const iso = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}-${String(
          cursor.getDate()
        ).padStart(2, "0")}`;
        const within = cursor >= start && cursor <= end;
        week.days.push(within ? byDate.get(iso) ?? { date: iso, total: 0, done: 0, planned_min: 0, focus_min: 0 } : null);
        cursor.setDate(cursor.getDate() + 1);
      }
      // Label the column when its month differs from the previous column's.
      if (weekFirstMonth !== lastMonth) {
        monthLabels.push(MONTHS[weekFirstMonth]);
        lastMonth = weekFirstMonth;
      } else {
        monthLabels.push(null);
      }
      weeks.push(week);
    }
    return { weeks, monthLabels };
  }, [daily]);

  if (!weeks.length) return null;

  const gap = 3;

  return (
    <div className="inline-flex flex-col gap-1.5 text-muted-foreground">
      {showMonths && (
        <div className="flex" style={{ marginLeft: showWeekdays ? 30 : 0, gap }}>
          {monthLabels.map((m, i) => (
            <div key={i} className="text-[10px]" style={{ width: cell }}>
              {m && <span className="-ml-0.5 inline-block whitespace-nowrap">{m}</span>}
            </div>
          ))}
        </div>
      )}
      <div className="flex" style={{ gap }}>
        {showWeekdays && (
          <div className="flex flex-col mr-1.5" style={{ gap }}>
            {WEEKDAYS.map((w, i) => (
              <div
                key={i}
                className="text-[10px] flex items-center justify-end pr-1"
                style={{ height: cell, width: 24 }}
              >
                {w}
              </div>
            ))}
          </div>
        )}
        <div className="flex" style={{ gap }}>
          {weeks.map((week, wi) => (
            <div key={wi} className="flex flex-col" style={{ gap }}>
              {week.days.map((d, di) => {
                if (!d) return <div key={di} style={{ width: cell, height: cell }} />;
                const value = metricValue(d, metric);
                const level = levelFor(value, metric);
                const isSelected = selectedDate === d.date;
                const label = `${fmtDate(d.date)} — ${d.done}/${d.total} done · ${fmtMinutes(d.focus_min)} focus`;
                return (
                  <button
                    key={di}
                    type="button"
                    title={label}
                    aria-label={label}
                    onClick={() => onSelectDay?.(d)}
                    className={cn(
                      "rounded-[3px] transition-transform hover:scale-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      LEVEL_CLASS[level],
                      isSelected && "ring-2 ring-foreground ring-offset-1 ring-offset-background"
                    )}
                    style={{ width: cell, height: cell }}
                  />
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Legend: Less □□□□ More */
export function HeatmapLegend({ metric }: { metric: HeatMetric }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <span>Less</span>
      {[0, 1, 2, 3, 4].map((l) => (
        <span key={l} className={cn("h-3 w-3 rounded-[3px]", LEVEL_CLASS[l])} />
      ))}
      <span>More</span>
      <span className="ml-1 opacity-70">
        ({metric === "focus" ? "focus time" : "tasks completed"})
      </span>
    </div>
  );
}
