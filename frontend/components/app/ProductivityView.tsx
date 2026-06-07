"use client";

import * as React from "react";
import {
  Flame,
  CheckCircle2,
  Timer,
  CalendarRange,
  LineChart,
  Tag,
  Trophy,
} from "lucide-react";
import { getInsights, type Insights, type InsightDay } from "@/lib/api";
import { PageShell, PageHeader } from "./PageShell";
import {
  ContributionHeatmap,
  HeatmapLegend,
  type HeatMetric,
} from "./ContributionHeatmap";
import { cn } from "@/lib/utils";

function fmtHours(min: number): string {
  if (!min) return "0h";
  const h = min / 60;
  return h >= 10 ? `${Math.round(h)}h` : `${h.toFixed(1).replace(/\.0$/, "")}h`;
}

function fmtDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

// A small palette for category bars — warm-leaning to sit with the amber theme.
const CAT_COLORS = [
  "hsl(28 80% 55%)",
  "hsl(168 55% 45%)",
  "hsl(220 70% 62%)",
  "hsl(280 55% 62%)",
  "hsl(340 65% 60%)",
  "hsl(48 85% 55%)",
];

export function ProductivityView() {
  const [data, setData] = React.useState<Insights | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [metric, setMetric] = React.useState<HeatMetric>("done");
  const [selected, setSelected] = React.useState<InsightDay | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    getInsights(140)
      .then((d) => {
        if (cancelled) return;
        setData(d);
        // Default the drill-down to the most recent day.
        if (d?.daily?.length) setSelected(d.daily[d.daily.length - 1]);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  const s = data?.summary;
  const weeks = data ? Math.round(data.range.days / 7) : 0;

  return (
    <PageShell>
      <PageHeader
        icon={LineChart}
        title="Productivity"
        subtitle="Where your time goes, and how your week is actually going."
      />

      {loading ? (
        <LoadingState />
      ) : !data ? (
        <p className="text-sm text-muted-foreground">Couldn&apos;t load your insights right now.</p>
      ) : (
        <div className="space-y-6">
          {/* Summary stats */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard
              icon={Flame}
              label="Current streak"
              value={`${s!.current_streak}d`}
              hint={s!.current_streak ? "keep it going" : "complete a task today"}
              accent
            />
            <StatCard
              icon={CheckCircle2}
              label="Completion"
              value={`${Math.round(s!.completion_rate * 100)}%`}
              hint={`${s!.done}/${s!.total} tasks`}
            />
            <StatCard
              icon={Timer}
              label="Focus time"
              value={fmtHours(s!.focus_minutes)}
              hint="on completed work"
            />
            <StatCard
              icon={CalendarRange}
              label="Active days"
              value={String(s!.active_days)}
              hint={`of last ${data.range.days}`}
            />
          </div>

          {/* Heatmap */}
          <div className="rounded-xl border border-border bg-card shadow-elev-1 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <div>
                <h2 className="text-sm font-semibold">Your last {weeks} weeks</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Each square is a day. Click one to see the detail.
                </p>
              </div>
              <MetricToggle metric={metric} onChange={setMetric} />
            </div>

            <div className="overflow-x-auto pb-1">
              <ContributionHeatmap
                daily={data.daily}
                metric={metric}
                selectedDate={selected?.date}
                onSelectDay={setSelected}
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 mt-4">
              <HeatmapLegend metric={metric} />
              {s!.best_day && (
                <span className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                  <Trophy className="h-3.5 w-3.5 text-primary" />
                  Best day: {fmtDate(s!.best_day)} ({s!.best_day_done} done)
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Selected day */}
            <DayDetail day={selected} />
            {/* Where time goes */}
            <CategoryBreakdown categories={data.categories} />
          </div>
        </div>
      )}
    </PageShell>
  );
}

function MetricToggle({
  metric,
  onChange,
}: {
  metric: HeatMetric;
  onChange: (m: HeatMetric) => void;
}) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5 text-xs">
      {(
        [
          ["done", "Completed"],
          ["focus", "Focus time"],
        ] as const
      ).map(([key, label]) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={cn(
            "px-3 py-1.5 rounded-md font-medium transition-colors",
            metric === key
              ? "bg-card text-foreground shadow-elev-1"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  accent,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint: string;
  accent?: boolean;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border bg-card p-4 shadow-elev-1",
        accent ? "border-primary/30" : "border-border"
      )}
    >
      <div className="flex items-center gap-2 text-muted-foreground mb-2">
        <Icon className={cn("h-4 w-4", accent && "text-primary")} />
        <span className="text-xs font-medium uppercase tracking-wider">{label}</span>
      </div>
      <p className="text-2xl font-semibold tracking-tight">{value}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{hint}</p>
    </div>
  );
}

function DayDetail({ day }: { day: InsightDay | null }) {
  return (
    <div className="rounded-xl border border-border bg-card shadow-elev-1 p-5">
      <h3 className="text-sm font-semibold mb-3">
        {day ? fmtDate(day.date) : "Pick a day"}
      </h3>
      {!day || day.total === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">
          {day ? "Nothing scheduled this day." : "Click a square in the heatmap."}
        </p>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <MiniStat label="Scheduled" value={String(day.total)} />
            <MiniStat label="Completed" value={String(day.done)} />
            <MiniStat label="Focus" value={fmtHours(day.focus_min)} />
          </div>
          <div>
            <div className="flex justify-between text-xs text-muted-foreground mb-1.5">
              <span>Completion</span>
              <span>{Math.round((day.done / day.total) * 100)}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${(day.done / day.total) * 100}%` }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/40 px-3 py-2.5 text-center">
      <p className="text-lg font-semibold tracking-tight">{value}</p>
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground mt-0.5">{label}</p>
    </div>
  );
}

function CategoryBreakdown({
  categories,
}: {
  categories: Insights["categories"];
}) {
  const total = categories.reduce((sum, c) => sum + c.minutes, 0);
  const onlyUntagged =
    categories.length === 0 || (categories.length === 1 && categories[0].name === "Untagged");

  return (
    <div className="rounded-xl border border-border bg-card shadow-elev-1 p-5">
      <div className="flex items-center gap-2 mb-4">
        <Tag className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Where your time goes</h3>
      </div>

      {total === 0 ? (
        <p className="text-sm text-muted-foreground py-6 text-center">
          No time logged yet. Give tasks a duration and Donna will track it.
        </p>
      ) : (
        <>
          {/* Segmented allocation bar */}
          <div className="flex h-3 w-full rounded-full overflow-hidden mb-4">
            {categories.map((c, i) => (
              <div
                key={c.name}
                style={{
                  width: `${(c.minutes / total) * 100}%`,
                  background: CAT_COLORS[i % CAT_COLORS.length],
                }}
                title={`${c.name}: ${fmtHours(c.minutes)}`}
              />
            ))}
          </div>

          <ul className="space-y-2.5">
            {categories.slice(0, 6).map((c, i) => (
              <li key={c.name} className="flex items-center gap-3 text-sm">
                <span
                  className="h-2.5 w-2.5 rounded-full shrink-0"
                  style={{ background: CAT_COLORS[i % CAT_COLORS.length] }}
                />
                <span className="capitalize truncate">{c.name}</span>
                <span className="ml-auto text-muted-foreground tabular-nums">
                  {fmtHours(c.minutes)}
                </span>
                <span className="text-xs text-muted-foreground/70 w-10 text-right tabular-nums">
                  {Math.round((c.minutes / total) * 100)}%
                </span>
              </li>
            ))}
          </ul>

          {onlyUntagged && (
            <p className="text-[11px] text-muted-foreground mt-4 leading-relaxed">
              Tip: when you tell Donna what a task is about (e.g. &quot;thesis&quot;, &quot;recruiting&quot;,
              &quot;workout&quot;), she tags it — and this breaks down by category.
            </p>
          )}
        </>
      )}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-24 rounded-xl bg-muted/50 animate-pulse" />
        ))}
      </div>
      <div className="h-44 rounded-xl bg-muted/50 animate-pulse" />
    </div>
  );
}
