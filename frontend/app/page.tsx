import { Suspense } from "react";
import Link from "next/link";
import {
  Sparkles,
  Brain,
  Calendar,
  Zap,
  ShieldCheck,
  MessageSquare,
  CheckCircle2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { DonnaAvatar } from "@/components/ui/avatar";
import { GithubIcon } from "@/components/ui/icons";
import { LandingNav, LandingCta } from "@/components/landing/LandingNav";

const GITHUB_URL = "https://github.com/pateltisha24/Donna";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      {/* Nav */}
      <header className="sticky top-0 z-30 border-b border-border/60 bg-background/70 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto flex items-center justify-between px-4 md:px-6 h-14">
          <div className="flex items-center gap-2.5">
            <DonnaAvatar size="sm" />
            <span className="font-semibold tracking-tight">Donna</span>
            <Badge variant="outline" className="hidden sm:inline-flex ml-2 text-[10px]">
              v1.0
            </Badge>
          </div>
          <Suspense fallback={null}>
            <LandingNav />
          </Suspense>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-grid pointer-events-none" />
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-primary/20 rounded-full blur-[120px] pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-4 md:px-6 pt-20 pb-24 text-center">
          <div className="inline-flex items-center gap-2 mb-6 px-3 py-1 rounded-full border border-border bg-card/60 backdrop-blur text-xs font-medium animate-fade-in">
            <Sparkles className="h-3 w-3 text-primary" />
            Multi-agent · LangGraph · Groq Llama 3.3 70B
          </div>

          <h1 className="text-4xl sm:text-5xl md:text-6xl font-semibold tracking-tight mb-6 leading-[1.05] animate-fade-in-up">
            Your AI <span className="text-gradient">Chief of Staff</span>,
            <br className="hidden sm:inline" /> not just another chatbot.
          </h1>

          <p className="text-base md:text-lg text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed animate-fade-in-up [animation-delay:80ms]">
            Donna is a multi-agent personal secretary that plans your day, runs your
            calendar, remembers what matters to you, and replans the moment something
            urgent lands.
          </p>

          <Suspense fallback={null}>
            <LandingCta variant="hero" />
          </Suspense>

          <p className="text-xs text-muted-foreground mt-6">
            No sign-up required for the demo. Continue as a sandboxed user.
          </p>
        </div>

        {/* Screenshot mock */}
        <div className="relative max-w-5xl mx-auto px-4 md:px-6 pb-20">
          <div className="rounded-2xl border border-border bg-card overflow-hidden shadow-2xl shadow-primary/10">
            <div className="flex items-center gap-1.5 px-4 py-2.5 border-b border-border bg-card">
              <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]" />
              <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]" />
              <span className="text-[11px] text-muted-foreground ml-3 font-mono">
                donna.app / chat
              </span>
            </div>
            <div className="p-6 md:p-8 bg-background/60">
              <div className="flex items-start gap-3 mb-5">
                <DonnaAvatar size="md" animated />
                <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 max-w-md">
                  <p className="text-sm">
                    <strong>Good morning, Tisha.</strong> You have 4 things today:
                    your standup at 10, a recruiter call at 2, the LangGraph deep-dive
                    you said you&apos;d ship by Friday, and dinner with Maya at 7.
                    Want to start with the recruiter prep?
                  </p>
                </div>
              </div>
              <div className="flex justify-end mb-5">
                <div className="rounded-2xl rounded-tr-sm bg-primary text-primary-foreground px-4 py-3 max-w-sm">
                  <p className="text-sm">
                    Something just came up — interview moved to 11am. Replan.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3">
                <DonnaAvatar size="md" />
                <div className="rounded-2xl rounded-tl-sm border border-border bg-card px-4 py-3 max-w-md">
                  <p className="text-sm">
                    On it. Pushing standup notes to async, moving the LangGraph
                    block to 3pm, and blocking 10:30–10:55 for last-minute prep.
                    Recruiter call shifted to tomorrow 4pm — Maya is still on for 7.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-6xl mx-auto px-4 md:px-6 py-20">
        <div className="text-center mb-14">
          <Badge variant="outline" className="mb-3">
            Four specialized agents
          </Badge>
          <h2 className="text-3xl md:text-4xl font-semibold tracking-tight mb-4">
            Architected like a real Chief of Staff
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto">
            A LangGraph orchestration of four specialist agents with a conflict-resolution layer, persistent
            memory, and dynamic replanning.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <FeatureCard
            icon={Brain}
            title="Task Reasoning Agent"
            description="Parses your messy thoughts into structured tasks with priority, duration, and recurrence. Confirms before saving."
          />
          <FeatureCard
            icon={Calendar}
            title="Scheduling Agent"
            description="Owns your morning briefing, EOD wrap, and calendar. Reads timetable screenshots with vision and exports to Apple Calendar."
          />
          <FeatureCard
            icon={Zap}
            title="Replanning Agent"
            description="When something urgent lands, Donna re-sequences your day, rolls incomplete work to tomorrow, and tells you exactly what shifts."
          />
          <FeatureCard
            icon={ShieldCheck}
            title="Tool Execution Agent"
            description="Web push reminders, .ics import/export, screenshot OCR via Groq Llama 4 Scout. Tools are validated before they fire."
          />
        </div>
      </section>

      {/* Differentiators */}
      <section className="max-w-6xl mx-auto px-4 md:px-6 py-20 border-t border-border">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Highlight
            icon={MessageSquare}
            title="Conflict resolution layer"
            body="When a new event overlaps an existing one — or two tasks both fight for prime time — Donna surfaces the conflict and lets you choose, instead of silently double-booking."
          />
          <Highlight
            icon={Brain}
            title="Persistent, preference-aware memory"
            body="Stores your profile, working style, and procrastination patterns in SQLite. Semantic recall over chat history with ChromaDB so Donna remembers context, not just facts."
          />
          <Highlight
            icon={Zap}
            title="Dynamic emergency replan"
            body="A dedicated replan node assesses urgency vs. existing load and produces a calm, decisive new plan — without losing the work you already did."
          />
        </div>
      </section>

      {/* Tech */}
      <section className="max-w-6xl mx-auto px-4 md:px-6 py-20 border-t border-border text-center">
        <h3 className="text-2xl font-semibold tracking-tight mb-3">Built on production-grade tooling</h3>
        <p className="text-muted-foreground mb-8">Containerised. Tested. Observable. Deployable.</p>
        <div className="flex flex-wrap justify-center gap-2">
          {[
            "LangGraph",
            "Groq API · Llama 3.3 70B",
            "ChromaDB",
            "SQLite",
            "FastAPI",
            "Next.js 14",
            "Docker",
            "Web Push (VAPID)",
            "APScheduler",
            "pytest",
          ].map((t) => (
            <Badge key={t} variant="outline" className="px-3 py-1.5 text-xs">
              {t}
            </Badge>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-4xl mx-auto px-4 md:px-6 py-20 text-center">
        <div className="relative rounded-2xl border border-border bg-gradient-to-br from-card via-card to-accent/30 p-10 overflow-hidden">
          <div className="absolute inset-0 bg-grid opacity-30 pointer-events-none" />
          <div className="relative">
            <CheckCircle2 className="h-8 w-8 text-primary mx-auto mb-4" />
            <h3 className="text-2xl md:text-3xl font-semibold tracking-tight mb-3">
              Meet your new Chief of Staff
            </h3>
            <p className="text-muted-foreground mb-7 max-w-xl mx-auto">
              Try the live demo — no sign-up required. It takes 30 seconds to see the
              difference between Donna and a chatbot.
            </p>
            <Suspense fallback={null}>
              <LandingCta variant="footer" />
            </Suspense>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="max-w-6xl mx-auto px-4 md:px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <DonnaAvatar size="sm" />
            <span>Donna · An AI personal secretary</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/about" className="hover:text-foreground transition-colors">
              How it works
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-foreground transition-colors flex items-center gap-1.5"
            >
              <GithubIcon className="h-3.5 w-3.5" />
              GitHub
            </a>
          </div>
        </div>
      </footer>
    </main>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="group relative rounded-xl border border-border bg-card p-6 hover:border-primary/40 transition-all hover:shadow-lg hover:shadow-primary/5">
      <div className="flex items-start gap-4">
        <div className="h-10 w-10 rounded-lg bg-accent/60 flex items-center justify-center shrink-0 group-hover:bg-accent transition-colors">
          <Icon className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h3 className="font-semibold mb-1.5 tracking-tight">{title}</h3>
          <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
        </div>
      </div>
    </div>
  );
}

function Highlight({
  icon: Icon,
  title,
  body,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
}) {
  return (
    <div className="space-y-3">
      <div className="h-9 w-9 rounded-lg bg-accent/60 flex items-center justify-center">
        <Icon className="h-4 w-4 text-primary" />
      </div>
      <h3 className="font-semibold tracking-tight">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{body}</p>
    </div>
  );
}
