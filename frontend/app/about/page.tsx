import Link from "next/link";
import {
  ArrowLeft,
  Brain,
  Calendar,
  Zap,
  ShieldCheck,
  Database,
  GitBranch,
} from "lucide-react";
import { GithubIcon } from "@/components/ui/icons";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { DonnaAvatar } from "@/components/ui/avatar";

const AGENTS = [
  {
    name: "Task Reasoning Agent",
    icon: Brain,
    nodes: ["classify_intent", "task_input", "task_update"],
    summary:
      "Parses free-form messages into structured tasks, classifies the intent of every turn, and updates task state (done / in-progress / moved) without dropping fidelity.",
    detail:
      "Uses a low-temperature classifier and a tolerant control-token parser with single-shot retry — so tasks are never silently dropped on malformed model output.",
  },
  {
    name: "Scheduling Agent",
    icon: Calendar,
    nodes: ["morning_briefing", "eod_wrap", "calendar", "APScheduler"],
    summary:
      "Owns the user's day: morning briefing, end-of-day wrap, calendar events, recurring rules, and time-of-day reminders.",
    detail:
      "Materialises recurring task and event templates on read. Schedules per-event web push reminders 15 minutes before each occurrence. Reads timetable screenshots via Groq Llama 4 Scout vision.",
  },
  {
    name: "Replanning Agent",
    icon: Zap,
    nodes: ["emergency_replan", "EOD rollover"],
    summary:
      "When something urgent lands, re-sequences the day's tasks against existing load and surfaces a calm, decisive plan. Rolls incomplete work to tomorrow at EOD.",
    detail:
      "Combines real-time priority assessment with profile-aware preference signals (working style, procrastination patterns) so the replan respects how the user actually works.",
  },
  {
    name: "Tool Execution Agent",
    icon: ShieldCheck,
    nodes: ["vision (OCR)", ".ics import / export", "Web Push (VAPID)"],
    summary:
      "Side-effect layer. Validates every structured payload against a schema before any mutation hits the database.",
    detail:
      "Conflict-resolution checks run here: overlapping events, double-booked task windows, and stale state. Failures surface as visible fallbacks, never as silent drops.",
  },
];

export default function AboutPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/70 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto flex items-center justify-between px-4 md:px-6 h-14">
          <Link href="/" className="flex items-center gap-2.5">
            <ArrowLeft className="h-4 w-4 text-muted-foreground" />
            <DonnaAvatar size="sm" />
            <span className="font-semibold tracking-tight">Donna</span>
          </Link>
          <div className="flex items-center gap-2">
            <a
              href="https://github.com/pateltisha24/Donna"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Button variant="ghost" size="icon-sm" aria-label="GitHub">
                <GithubIcon className="h-4 w-4" />
              </Button>
            </a>
            <Link href="/app">
              <Button variant="shimmer" size="sm">
                Try the demo
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <section className="max-w-5xl mx-auto px-4 md:px-6 pt-14 pb-10">
        <Badge variant="outline" className="mb-4">
          Architecture
        </Badge>
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight mb-4">
          How Donna actually works
        </h1>
        <p className="text-muted-foreground max-w-2xl leading-relaxed">
          Donna is a multi-agent LangGraph orchestration over Groq&apos;s Llama 3.3 70B.
          Every user message flows through onboarding gating, intent classification, a
          specialist agent, and a memory-update step. Tools mutate state only after
          their payload validates against a strict schema.
        </p>
      </section>

      {/* Topology */}
      <section className="max-w-5xl mx-auto px-4 md:px-6 pb-14">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-primary" /> Agent topology
            </CardTitle>
            <CardDescription>
              The compiled LangGraph state machine. Every turn passes through it.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <pre className="text-[11px] sm:text-xs font-mono leading-relaxed text-muted-foreground overflow-x-auto rounded-lg border border-border bg-muted/40 p-4">
{`              START
                │
                ▼
       ┌────────────────┐
       │ check_onboarding│
       └───────┬────────┘
        new?   │   returning
        ┌──────┴──────┐
        ▼             ▼
  ┌──────────┐  ┌─────────────────┐
  │onboarding│  │ classify_intent │
  └────┬─────┘  └───────┬─────────┘
       │                │
       │       ┌────────┴────────────────────────────┐
       │       │                                     │
       ▼       ▼                                     ▼
       Task Reasoning      Scheduling          Replanning   Tool Exec
       ─ task_input        ─ morning_briefing  ─ emergency  ─ calendar
       ─ task_update       ─ eod_wrap            _replan    ─ profile_update
                                                            ─ general_checkin
       └────────────────────┬────────────────────────────────┘
                            ▼
                     ┌─────────────┐
                     │update_memory│  (gated — only when there's something to learn)
                     └──────┬──────┘
                            ▼
                           END`}
            </pre>
          </CardContent>
        </Card>
      </section>

      {/* Agents */}
      <section className="max-w-5xl mx-auto px-4 md:px-6 pb-14">
        <h2 className="text-2xl font-semibold tracking-tight mb-1">The four specialist agents</h2>
        <p className="text-muted-foreground mb-6 text-sm">Each agent owns a slice of the graph and a specific failure-recovery strategy.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {AGENTS.map((a) => {
            const Icon = a.icon;
            return (
              <Card key={a.name} className="hover:border-primary/40 transition-colors">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <span className="h-8 w-8 rounded-lg bg-accent/60 flex items-center justify-center shrink-0">
                      <Icon className="h-4 w-4 text-primary" />
                    </span>
                    {a.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-foreground">{a.summary}</p>
                  <p className="text-sm text-muted-foreground leading-relaxed">{a.detail}</p>
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {a.nodes.map((n) => (
                      <Badge key={n} variant="secondary" className="text-[10px] font-mono">
                        {n}
                      </Badge>
                    ))}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Persistence */}
      <section className="max-w-5xl mx-auto px-4 md:px-6 pb-14">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" /> Memory & persistence
            </CardTitle>
            <CardDescription>How Donna remembers you across turns and restarts.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm leading-relaxed">
            <p>
              <strong>SQLite</strong> stores tasks, events, sessions, push subscriptions, and the user profile.
              All state survives restarts, so a deploy or crash never loses the conversation.
            </p>
            <p>
              <strong>ChromaDB</strong> indexes assistant responses for semantic recall — when you ask
              &quot;remember when we talked about X?&quot;, Donna actually searches your history rather than
              keyword-matching.
            </p>
            <p>
              <strong>Profile-aware scheduling</strong> means wake/EOD times, working style, and procrastination
              patterns all flow into every system prompt — so suggestions match how you actually work.
            </p>
          </CardContent>
        </Card>
      </section>

      {/* Tech stack */}
      <section className="max-w-5xl mx-auto px-4 md:px-6 pb-20">
        <h2 className="text-lg font-semibold mb-3">Tech stack</h2>
        <div className="flex flex-wrap gap-2">
          {[
            "LangGraph",
            "Groq · Llama 3.3 70B",
            "Llama 4 Scout (vision)",
            "ChromaDB",
            "SQLite",
            "FastAPI",
            "Next.js 14",
            "Tailwind CSS",
            "Docker",
            "Web Push (VAPID)",
            "APScheduler",
            "pytest (78 tests)",
          ].map((t) => (
            <Badge key={t} variant="outline" className="px-3 py-1.5 text-xs">
              {t}
            </Badge>
          ))}
        </div>
      </section>
    </main>
  );
}
