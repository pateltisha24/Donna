# Donna

> **Your AI Chief of Staff.** A multi-agent personal secretary that plans your day, runs your calendar, remembers what matters, and replans the moment something urgent lands.

[![Live demo](https://img.shields.io/badge/demo-donna--ashen.vercel.app-7c6af7?style=flat-square)](https://donna-ashen.vercel.app)
[![Tests](https://img.shields.io/badge/tests-78%20passing-22c55e?style=flat-square)](#testing)
[![License](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)

Donna is a LangGraph orchestration of **four specialist agents** on top of Groq's Llama 3.3 70B. She reads your timetable from a screenshot, remembers your working style across sessions, surfaces calendar conflicts before you double-book yourself, and re-sequences your day on demand when life happens.

```
"Something just came up — interview moved to 11am. Replan."
"On it. Pushing standup notes to async, moving the LangGraph block to 3pm,
 and blocking 10:30–10:55 for last-minute prep. Recruiter call shifted to
 tomorrow 4pm — Maya is still on for 7."
```

---

## Highlights

- **Four specialist agents** with a single LangGraph state machine — task reasoning, scheduling, replanning, and tool execution, each with its own failure-recovery strategy.
- **Conflict-resolution layer** that detects overlapping events at write time, not after the user has been double-booked.
- **Preference-aware persistent memory** — profile, working style, and procrastination patterns flow into every system prompt.
- **Dynamic emergency replan** — a dedicated node assesses urgency vs. existing load and produces a calm new plan without losing committed work.
- **Real-time streaming** with tolerant control-token parsing and single-shot retry — structured payloads are never silently dropped.
- **Vision ingestion** of timetable screenshots via Groq's Llama 4 Scout multimodal model.
- **Multi-chat** with AI-titled conversations, inline rename, delete, search.
- **Web Push** reminders 15 minutes before each event, plus a scheduled morning briefing and end-of-day wrap.
- **Multi-user auth** — Google OAuth, email/password (bcrypt), and a shared demo sandbox.

---

## Architecture

```
Vercel (Next.js 14)                  Render (FastAPI + Docker)
  ┌──────────────┐  fetch / SSE        ┌──────────────────────────────┐
  │ Landing /    │ ──────────────────► │ /chat   /trigger             │
  │ /app  chat   │                     │ /tasks  /events              │
  │ /about       │                     │ /chats  (CRUD + AI title)    │
  │ /api/auth/*  │  Google + email/pw  │ /auth/{register,login,oauth} │
  │ (NextAuth)   │ ──────────────────► │ /recall (semantic)           │
  └──────────────┘                     │ /agents (metadata)           │
                                       │                              │
                                       │  ┌────────────────────────┐  │
                                       │  │ LangGraph              │  │
                                       │  │ ├─ TaskReasoningAgent  │  │
                                       │  │ ├─ SchedulingAgent     │  │
                                       │  │ ├─ ReplanningAgent     │  │
                                       │  │ └─ ToolExecutionAgent  │  │
                                       │  └────────────────────────┘  │
                                       │                              │
                                       │  ┌────────────────────────┐  │
   MongoDB Atlas ◄───── reads/writes ──┤  │ MongoStore             │  │
   (durable)                           │  │ users, chats, messages │  │
                                       │  │ tasks, events, profile │  │
                                       │  │ push_subs, app_state   │  │
                                       │  └────────────────────────┘  │
                                       │                              │
                                       │  ChromaDB    ─── /tmp        │
                                       │  APScheduler ─── briefings   │
                                       │  Web Push    ─── VAPID       │
                                       └──────────────────────────────┘
```

### The four agents

| Agent | Owns | Recovery strategy |
|---|---|---|
| **Task Reasoning** | `classify_intent`, `task_input`, `task_update` | Tolerant control-token parser with regex + JSON repair; single-shot retry on malformed model output. |
| **Scheduling** | `morning_briefing`, `eod_wrap`, `calendar`, APScheduler | Materialises recurring task and event templates on read. Vision (Llama 4 Scout) for timetable screenshots. |
| **Replanning** | `emergency_replan`, EOD rollover | Combines real-time priority assessment with profile-aware preference signals (working style, procrastination patterns). |
| **Tool Execution** | Web Push (VAPID), `.ics` import/export, screenshot OCR, conflict detection | Validates every structured payload against a schema *before* any mutation hits the database. |

---

## Tech stack

**Backend** — Python 3.11, FastAPI, LangGraph, Groq SDK (Llama 3.3 70B + Llama 4 Scout vision), MongoDB (Atlas), ChromaDB (semantic recall), APScheduler, pywebpush (VAPID), bcrypt, pytest.

**Frontend** — Next.js 14 (App Router), TypeScript, Tailwind CSS, shadcn-style design system, Radix UI primitives, lucide-react, framer-motion, sonner toasts, NextAuth (Google OAuth + Credentials), react-markdown.

**Infra** — Docker (multi-stage), Render (backend), Vercel (frontend), MongoDB Atlas (M0 free), GitHub.

---

## Quick start (local dev)

### Prerequisites

- Python 3.11+ and pip
- Node 18+ and npm
- A MongoDB Atlas cluster (free M0 is fine) with `0.0.0.0/0` network access
- A free [Groq API key](https://console.groq.com/keys)
- *(Optional)* Google OAuth client credentials for sign-in with Google

### 1. Clone & install

```bash
git clone https://github.com/pateltisha24/Donna.git
cd Donna

# Backend
cd backend
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..
```

### 2. Configure secrets

Create `.env` at the project root (backend reads it):

```bash
cp .env.example .env
# Fill in:
#   GROQ_API_KEY=...
#   MONGODB_URI=mongodb+srv://...
#   MONGODB_DB=Donna
#   VAPID_PUBLIC_KEY=...   (npx web-push generate-vapid-keys)
#   VAPID_PRIVATE_KEY=...
```

Create `frontend/.env.local` (frontend reads it):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=                   # openssl rand -base64 32
GOOGLE_CLIENT_ID=                  # optional
GOOGLE_CLIENT_SECRET=              # optional
```

### 3. Run

```bash
# Terminal 1
cd backend && uvicorn main:app --reload

# Terminal 2
cd frontend && npm run dev
```

Open <http://localhost:3000>. Click **Sign in** → **Continue as demo user** to skip auth and dive in.

### With Docker

```bash
docker compose up --build
```

Same ports (`8000` and `3000`). The compose file mounts a `./data` volume so the ChromaDB index survives container restarts locally.

---

## Project structure

```
Donna/
├── backend/                    # FastAPI service
│   ├── agent/                  # LangGraph nodes + agents
│   │   ├── agents.py           # Four-agent metadata for /agents
│   │   ├── graph.py            # State machine wiring
│   │   ├── nodes.py            # Node implementations
│   │   ├── prompts.py          # System prompts per intent
│   │   ├── parsing.py          # Tolerant control-token parser
│   │   ├── vision.py           # Llama 4 Scout screenshot OCR
│   │   └── ics.py              # .ics import/export
│   ├── api/routes.py           # FastAPI endpoints
│   ├── memory/
│   │   ├── mongo_store.py      # Primary store (users/chats/tasks/events)
│   │   ├── semantic_store.py   # ChromaDB semantic recall
│   │   └── chroma_store.py     # Profile store (Mongo-backed alias)
│   ├── models/                 # Pydantic + dataclass models
│   ├── notify/push.py          # Web Push delivery (VAPID)
│   ├── scheduler/jobs.py       # APScheduler cron jobs
│   ├── tests/                  # 78 pytest cases
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                   # Next.js 14 app
│   ├── app/                    # App Router pages
│   │   ├── (landing)/          # / — marketing landing
│   │   ├── app/                # /app — chat + sidebar
│   │   ├── about/              # /about — architecture page
│   │   ├── api/auth/[...]/     # NextAuth handler
│   │   └── icon.svg            # Favicon
│   ├── components/
│   │   ├── ui/                 # shadcn-style primitives
│   │   ├── app/                # Chat, sidebar, topbar, profile menu
│   │   ├── auth/LoginModal.tsx # Modal login + register
│   │   └── landing/            # Hero + nav
│   ├── lib/
│   │   ├── api.ts              # Backend client (SSE streaming)
│   │   ├── auth.ts             # NextAuth config (Google + Credentials)
│   │   ├── useChats.tsx        # Multi-chat state hook
│   │   └── utils.ts            # cn() + date helpers
│   ├── Dockerfile              # Multi-stage standalone build
│   └── next.config.js
├── render.yaml                 # Render Blueprint (backend deploy)
├── docker-compose.yml          # Local dev with Docker
├── DEPLOY.md                   # Full deploy runbook
├── IMPROVEMENTS.md             # Engineering journal
└── .env.example                # All env vars documented
```

---

## Testing

```bash
cd backend
pytest -q
```

**78 tests** cover:

- Control-token parsing (valid + malformed)
- Task CRUD against a temp database
- Intent classification routing
- ICS import/export
- Recurrence materialisation
- Conflict detection
- Stream filter (control tokens stripped from SSE before reaching the client)

---

## Deploy

See [`DEPLOY.md`](DEPLOY.md) for the full runbook. Short version:

1. **Backend → Render** — connect the repo, use the included `render.yaml` Blueprint, paste secrets in the dashboard.
2. **Frontend → Vercel** — import the same repo, set Root Directory to `frontend`, add env vars.
3. **Close the loop** — update `CORS_ALLOW_ORIGINS` on Render and Google OAuth redirect URI to the Vercel domain.

Live demo: <https://donna-ashen.vercel.app>

---

## Engineering journal

[`IMPROVEMENTS.md`](IMPROVEMENTS.md) is a working log of every problem found, why it mattered, and the visible result after the fix. Most are now resolved; the file remains as a record of the engineering trade-offs (e.g. staying on Groq + Llama 3.3 70B and hardening control-token parsing instead of switching models).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

Built by [Tisha Patel](https://github.com/pateltisha24). Inspired by Donna Paulsen from *Suits* — warm, sharp, decisive.
