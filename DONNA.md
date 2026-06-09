# Donna — The Complete Guide

> **Donna is an AI chief of staff that runs your day.** You talk to her in plain
> English; she plans your tasks, manages your calendar, remembers what matters to
> you, replans the moment something urgent lands — and *actually performs* those
> actions instead of just describing them.
>
> This document explains everything: what Donna is, how she works, what we built,
> and *why* we made each choice. It's written to be understood end-to-end —
> whether you're a teammate, a recruiter, or future-you.

---

## 1. The one-paragraph version

Donna is a conversational productivity assistant. A **Next.js** web app talks to a
**FastAPI** backend over a streaming connection. The backend runs a **LangGraph**
state machine — a small "brain" that figures out what you want and routes it to the
right specialist behaviour (add tasks, manage calendar, replan, brief you on your
day, etc.). The language model is **Llama 3.3 70B served by Groq** (fast and free),
with **Llama 4 Scout** for reading screenshots of timetables. Data lives in
**MongoDB**; **ChromaDB** powers semantic memory. The defining trait: Donna uses
**native tool-calling** to take real actions on your data, and she's personalised by
**persistent memory** of who you are.

---

## 2. The problem & why Donna exists

Most "AI assistants" are chatbots — they *talk about* helping you but don't *do*
anything. Calendar/productivity tools that actually act (Motion, Sunsama, Reclaim)
are powerful but expensive, and they're drag-and-drop apps, not conversations.

**Donna's bet:** the most natural way to run your day is to *talk* to someone who
knows you and can act on your behalf. So Donna is:

- **Conversational-first** — you just tell her things.
- **Action-taking** — "cancel my 3pm" actually deletes it; "replan my day" actually
  moves your tasks.
- **Personalised** — she remembers your role, hours, goals, and past context.
- **Free to run** — built entirely on free tiers (Groq + Llama, MongoDB Atlas free,
  Vercel/Render free), which is a real engineering constraint we designed around.

The persona is **Donna Paulsen from *Suits*** — warm, sharp, decisive. That's the
voice the whole product is tuned to.

---

## 3. High-level architecture

```
  ┌──────────────────────┐         streaming (SSE)        ┌───────────────────────────┐
  │   Next.js frontend   │  ───────────────────────────▶  │     FastAPI backend       │
  │  (Vercel)            │   X-User-Id identifies user    │     (Render)              │
  │                      │  ◀───────────────────────────  │                           │
  │  Today / Chat /      │     token-by-token reply       │  ┌─────────────────────┐  │
  │  Calendar /          │                                │  │  LangGraph "brain"  │  │
  │  Productivity /      │                                │  │  (state machine)    │  │
  │  Settings            │                                │  └─────────┬───────────┘  │
  └──────────────────────┘                                │            │              │
                                                           │     Groq / Llama 3.3 70B  │
                                                           │     Llama 4 Scout (vision)│
                                                           │            │              │
                                                           │   ┌────────┴─────────┐    │
                                                           │   │ MongoDB  ChromaDB │    │
                                                           │   │ (data)   (memory) │    │
                                                           │   └──────────────────┘    │
                                                           │   APScheduler + Web Push  │
                                                           └───────────────────────────┘
```

---

## 4. Tech stack (and why each piece)

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js 14** (App Router), React, TypeScript, Tailwind | Modern, fast, great DX; App Router gives us clean per-page routes. |
| UI system | shadcn-style components, **Framer Motion**, `lucide-react` | Consistent, accessible primitives; tasteful motion. |
| Auth (frontend) | **NextAuth** (Google + email/password) | Standard, handles Google OAuth + sessions. |
| Backend | **FastAPI** + Uvicorn | Async, typed, streaming-friendly, Python (same language as the AI stack). |
| Agent framework | **LangGraph** | Models the assistant as a state machine of nodes — clean way to route intents and keep behaviour modular. |
| LLM | **Groq + Llama 3.3 70B** | Fastest inference available, **free** tier. Quality gaps are solved by engineering (validation/retries), not by paying for a bigger model. |
| Vision | **Groq + Llama 4 Scout** | Reads screenshots of timetables into structured events. Free, multimodal. |
| Database | **MongoDB (Atlas)** | Flexible document store for tasks/events/profiles/chats; free tier. |
| Semantic memory | **ChromaDB** (embedded) | Vector search over past messages so Donna can recall relevant moments. |
| Scheduling | **APScheduler** | Fires morning/EOD briefings and event reminders. |
| Notifications | **Web Push (VAPID)** | Browser push reminders, no app store needed. |

---

## 5. The frontend — what the user sees

The app lives under `/app` with a persistent **left navigation rail** and five
real destinations (this replaced an older chat-only layout where everything was
crammed into a pop-out panel):

| Page | Route | What it does |
|---|---|---|
| **Today** | `/app` | The home dashboard. Greeting, "here's your day," at-a-glance stats (tasks, events, completion), a **momentum heatmap** glance, today's schedule + focus list, and quick actions. Shows a **profile-setup nudge** for new users. |
| **Chat** | `/app/chat` | The conversation with Donna. Streams her reply token-by-token, renders markdown, shows a typing indicator, and renders a **replan diff card with Undo** when she replans. |
| **Calendar** | `/app/calendar` | A **week grid** (time-blocked, like Google/Motion). Events are positioned by their real times, overlapping events sit side-by-side, there's a "now" line, week navigation, and **click-to-edit / delete** events. |
| **Productivity** | `/app/productivity` | A **GitHub/Claude-style contribution heatmap** of your productivity over ~11 weeks, plus streak, completion %, focus hours, "where your time goes" by category, and a per-day drill-down. |
| **Settings** | `/app/settings` | Your **profile** (name, role/occupation, school/company, working style, wake/EOD times), theme, notifications, and "what Donna remembers" (view/forget stored facts). |

**Design language:** warm, dark-first theme built on a **warm amber** primary
(deliberately *not* the generic violet every AI startup uses), a 3-tier elevation
system, and an original illustrated **Donna avatar** as the brand face. The visual
goal is "a product you'd pay for" in the first five seconds.

**Identity:** every API call carries an `X-User-Id` header (the user's email, or
`demo` for the sandbox). The backend scopes all data to that user.

---

## 6. The backend — the API surface

The FastAPI app exposes ~30 endpoints. The important ones:

| Endpoint | Purpose |
|---|---|
| `POST /chat` | The main conversation. Streams Donna's reply (SSE). |
| `POST /trigger` | Manually fire a morning briefing or EOD wrap. |
| `GET /tasks`, `GET /search` | Read/filter tasks. |
| `GET /events`, `PATCH /events/{id}`, `DELETE /events/{id}` | Read / edit / delete calendar events. |
| `GET /insights` | The productivity data (daily series, categories, summary). |
| `POST /replan/undo` | Revert the most recent emergency replan. |
| `POST /upload` | Parse a screenshot or `.ics` file into events. |
| `GET /calendar.ics` | Export your calendar to Apple/Google Calendar. |
| `GET/PATCH /me`, `/me/settings`, `/me/forget` | Read/update profile; forget a remembered fact. |
| `GET/POST/PATCH/DELETE /chats…` | Manage conversations. |
| `GET /history` | Load a conversation's messages. |
| `POST /push/subscribe`, `/push/unsubscribe`, `GET /push/vapid-public-key` | Web push. |
| `POST /auth/register`, `/auth/login`, `/auth/oauth-upsert` | Account auth. |
| `GET /health` | Liveness + Mongo connectivity. |

---

## 7. The agent "brain" — how Donna decides what to do

Donna's intelligence is a **LangGraph state machine**. Think of it as a flowchart
the message travels through:

```
START
  → check_onboarding ──(new user?)──→ onboarding ─┐
  │                                                │
  └──(known user)──→ classify_intent               │
                          │                         │
        ┌─────────────────┼─────────────────────┐  │
        ▼     ▼     ▼      ▼      ▼     ▼    ▼   ▼  │
   morning  task  task  calendar emerg general profile eod
   briefing input update          replan checkin update wrap
        └─────────────────┴─────────────────────┘  │
                          ▼                         │
                     update_memory  ◀───────────────┘
                          ▼
                         END
```

**Step by step:**
1. **check_onboarding** — Is this user set up? If not, route to onboarding.
2. **classify_intent** — The model reads the message and picks one label: are you
   adding tasks? updating one? talking calendar? need a replan? just checking in?
   sharing personal info? want a briefing/wrap?
3. **The intent node** does the work for that case (details below).
4. **update_memory** — After every turn, Donna quietly stores the exchange so she
   can recall it later, and saves any profile facts.

**Why a state machine?** It keeps each behaviour modular and testable, makes the
routing explicit, and is the standard modern pattern for agents — much cleaner than
one giant prompt trying to do everything.

> **A subtle but important detail we fixed:** LangGraph only carries state fields
> that are *declared* in its schema. The user's identity (`user_id`) wasn't
> declared, so it was being silently dropped — meaning every conversation ran as a
> generic "default" user (wrong profile, wrong data). Declaring `user_id`,
> `session_id`, and `replan` in the state schema fixed a real multi-tenancy bug.

---

## 8. How Donna takes *actions* — the core differentiator

This is the most important part, and the best interview story.

**The old way (fragile):** Donna used to hide structured data inside her normal
reply as tagged text (e.g. a `<TASKS_CONFIRMED>[…]</TASKS_CONFIRMED>` block) and we
parsed it back out with pattern-matching. The weaker free model sometimes formatted
that block slightly wrong, and the action would silently fail.

**The new way (robust): native tool-calling.** The model is given a set of real
**tools** (functions) it can call with clean, typed arguments. Donna decides whether
to call one, hands us structured data through the channel the model is *built* for,
we execute it against the database, then she **narrates** a warm confirmation. This
is the **decide → act → narrate** loop.

The tools Donna can call:

| Tool | Action |
|---|---|
| `create_tasks` | Add to-dos (title, duration, priority, recurrence). |
| `mark_tasks_done` | Complete tasks. |
| `move_tasks` | Push tasks to another day. |
| `reprioritize_tasks` | Change task priorities. |
| `create_events` | Add timed calendar events. |
| `cancel_events` | Delete/cancel events (she's given the event IDs to target). |
| `update_profile` | Save facts you shared about yourself. |

**Safeguards we built around it:**
- **Confirm-first:** she won't save until you've actually confirmed.
- **Dedup guard:** re-confirming the same task won't create duplicates.
- **Validation + fallback:** tool arguments are re-validated; if tool-calling ever
  errors, she falls back to the old parsing path — so reliability only ever goes up.

**Why this matters:** "it talks about adding a task" vs "it added the task, reliably,
the way modern production agents do." That's the difference between a demo and a
product.

---

## 9. Memory — why Donna feels personal

Donna has two kinds of memory:

1. **Profile (structured facts):** name, role, school/company, working style, wake/
   EOD times, goals, known people, preferences. You can fill this in via the
   **Settings form** (so she doesn't have to guess), and she also learns facts
   mid-conversation via the `update_profile` tool. You can view and **forget**
   anything she's stored.
2. **Semantic recall (relevant moments):** every message is embedded into ChromaDB.
   When you talk to her, she retrieves the most *relevant* snippets of past
   conversation and folds them into her context — scoped to *your* history only. The
   profile gives her stable facts; recall gives her relevant memories.

**Why both:** facts make her accurate ("you're a CS student at UB"); recall makes her
feel continuous ("like you mentioned about your thesis last week").

---

## 10. Calendar & vision

- **Week grid:** the Calendar page renders events as time-blocks, handles
  overlapping events side-by-side, draws a "now" line, and supports
  **click-to-edit and delete**.
- **Two ways in:** you can *tell* Donna ("add CS410 Tue & Thu 11–12:15") and she
  creates the events, or you can **upload a screenshot** of a timetable — Llama 4
  Scout reads it into structured events — or import an **`.ics`** file.
- **Export:** `/calendar.ics` lets you subscribe from Apple/Google Calendar.
- **Conflict detection:** when a new event overlaps an existing one, Donna flags it
  instead of silently double-booking.

---

## 11. Insights — the productivity heatmap

The Productivity page is a signature visual: a **contributions-style heatmap**
(like GitHub's or Claude's) where each square is a day, shaded by how much you got
done. Alongside it: current **streak**, **completion %**, **focus hours**, **active
days**, your **best day**, and a **"where your time goes"** breakdown by category.
A compact version appears on the Today page as a momentum glance.

A nice product detail: the streak doesn't reset just because *today* isn't finished
yet — an incomplete today doesn't break a run (it counts from yesterday), which is
how a humane streak should behave.

---

## 12. Emergency replan — Donna that acts under pressure

When you say "something urgent came up, replan my day," Donna doesn't just describe a
plan — she **performs** it: she reprioritises today's tasks, pushes what won't fit to
tomorrow, and adds the new urgent item, all using the action tools. Then she returns
a **diff** of exactly what changed, rendered as a card in chat with a one-click
**Undo** (we snapshot the prior state so a replan is fully reversible).

---

## 13. Proactive side — scheduler & notifications

- **APScheduler** fires a **morning briefing** and **end-of-day wrap** at your set
  hours, plus **reminders** before calendar events.
- **Web Push (VAPID)** delivers those as browser notifications.

---

## 14. Data model (MongoDB collections)

| Collection | Holds |
|---|---|
| `tasks` | To-dos: title, date, priority, status, duration, tags, recurrence. |
| `events` | Timed events: title, date, start/end, location, recurrence. |
| `profiles` | The structured user profile. |
| `chats` / `sessions` | Conversation list + their message histories. |
| `app_state` | Per-user flags (e.g. onboarding complete, last replan snapshot). |
| `push_subscriptions` | Browser push endpoints. |
| `counters` | Auto-incrementing IDs for tasks/events. |
| `users` | Auth records (email/password hashes, OAuth). |

Everything is scoped by `user_id` so users only ever see their own data.

---

## 15. The project → product journey (what we built, in order)

Donna started as a solid *project* and is being turned into a *product*. The work is
organised into capability phases:

- **Phase 0 — Hygiene:** clean repo, honest docs, committed baseline.
- **Phase 1 — Frontend & UX:** the real app shell (5 destinations), warm theme +
  elevation, the Today dashboard, the **Productivity heatmap**, the **Calendar week
  grid**, the illustrated **Donna avatar**, and polish (adaptive formatting, fixing
  the double-bubble while she "thinks").
- **Phase 2 — Agent that acts:** migrated every action to **native tool-calling**
  (tasks, calendar, profile), built the **real emergency replan with diff + undo**,
  wired **semantic memory** into prompts, and made replies **format adaptively**
  (bullets for lists, prose for conversation). Also fixed several real bugs found in
  testing: the `user_id`-dropped-by-LangGraph multi-tenancy bug, an onboarding crash
  on empty profile fields, event **cancellation** not actually deleting, and the
  Schedule/Tasks panel being buried in chat.
- **Phase 3 (next) — Product-grade backend:** real JWT auth, per-user scheduler,
  rate limiting, observability, CI.
- **Phase 4 (planned) — Two-way Google Calendar sync.**
- **Phase 5 (planned) — Wow layer:** one-click recruiter demo, command palette,
  voice ("talk to Donna"), weekly review ritual.

---

## 16. Known limitations & honest roadmap

Being upfront about debt is part of being product-minded:

- **Authentication is cooperative, not enforced.** The backend currently trusts the
  `X-User-Id` header rather than verifying a signed token. NextAuth protects the
  frontend, but real backend **JWT verification** is the top Phase-3 item before any
  public launch.
- **The scheduler is effectively single-user** today (briefings/reminders aren't
  fully per-user). Phase 3 fixes this.
- **No rate limiting yet** — `/chat` and `/auth/login` need throttling.
- **No automated eval suite yet** — a set of scripted conversations that assert the
  agent routes correctly and actually saves data is planned (great ML-maturity
  signal).
- **Vision extraction is best-effort** — a free vision model occasionally misreads a
  timetable column; prompts are tightened but it's not perfect.

---

## 17. Running it locally

```bash
# Backend (needs MONGODB_URI + GROQ_API_KEY in .env)
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev   # http://localhost:3000

# Populate the demo account with a lived-in history
cd backend && python scripts/enrich_demo.py
```

The demo user (`demo`) works with no sign-up — a sandboxed, pre-populated account.

---

## 18. Talking points (the 30-second pitch)

- "Donna is an AI chief of staff you **talk to** — she plans your day, runs your
  calendar, remembers you, and **actually takes the actions** instead of just
  describing them."
- "Under the hood it's a **LangGraph agent** on **Groq/Llama 3.3 70B** using
  **native tool-calling** to mutate real data, with a control-token fallback so
  reliability only goes up — all on **free infrastructure**."
- "It has **persistent memory** (a structured profile + semantic recall), a real
  **emergency replan with undo**, a **calendar that reads your screenshots**, and a
  **productivity heatmap** — and I found and fixed real multi-tenancy and agent bugs
  along the way."

---

*Donna — built to make running your day feel like having someone who's got you.*
