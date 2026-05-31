# Donna — Improvement Plan

> A working document describing the current problems, why they matter, and the concrete improvement that should be visible after each fix.
>
> **Model decision:** Staying on **Groq + Llama 3.3 70B** (free tier, fastest inference). Reliability gaps that would normally be solved by switching to a model with native tool use will instead be solved by **hardening our control-token parsing** (validation + retries).

---

## Implementation status (all complete)

**Part 1 — Fixes:** #1 real streaming · #2 SQLite sessions · #3 gated `update_memory` ·
#4 hardened parsing + retry · #5 scheduled-briefing delivery · #6 error UI ·
#7 pytest suite (78 tests) · #8 env-configurable CORS · #9 ChromaDB removed.

**Part 2 — Features:** A markdown rendering · B recurring tasks · D web push (VAPID) ·
E task search & filters · G light/dark theme · H weekly analytics.

_(C — conversation history sidebar — is partially covered by session persistence;
a full multi-session browser was not built since the app is single-session.)_

Verified: backend boots, all endpoints respond, real token streaming + persistence
confirmed against the live Groq key, frontend builds clean.

---

## Legend

- **Severity** — `P0` (blocks real use), `P1` (significant), `P2` (polish / nice-to-have)
- **Area** — Backend / Frontend / Infra / Agent

---

# Part 1 — Problems to Fix

### 1. Fake streaming `P0` · Backend / Agent

**Problem.**
The backend calls the Groq API and waits for the *entire* response to come back, then simulates streaming by splitting the finished text on spaces and sleeping 20ms between words (`api/routes.py → _stream_text`). The user does not see the first word until the full response has already been generated.

**Why it matters.**
This defeats the purpose of streaming. Time-to-first-token is the single biggest driver of perceived responsiveness in a chat app. Right now a long briefing makes Donna feel frozen, then dumps words at an artificial drip.

**Expected output after fix.**
- The backend uses Groq's native streaming API (`stream=True`) and forwards real tokens to the client as they are produced.
- Visible result: the first words of Donna's reply appear within a few hundred milliseconds, even for long responses. The 20ms artificial sleep is removed.
- Control tokens (`<TASKS_CONFIRMED>` etc.) must be buffered/stripped *before* reaching the client even while streaming — the user never sees raw tokens mid-stream.

---

### 2. In-memory sessions are lost on restart `P0` · Backend

**Problem.**
`_sessions: dict` in `api/routes.py` holds all conversation history in process memory. A backend restart (deploy, crash, container recycle) wipes every active conversation with no warning.

**Why it matters.**
Donna's whole value is continuity and context. Silently losing history breaks the core promise and confuses the user ("why did she forget what we just discussed?").

**Expected output after fix.**
- Session history is persisted to SQLite (a `sessions` / `messages` table) and reloaded on demand.
- Visible result: restart the backend mid-conversation, refresh the page, and the conversation continues seamlessly with full context intact.

---

### 3. `update_memory` runs after every message `P1` · Agent

**Problem.**
The `update_memory` node makes a *second* LLM call after every single exchange to extract profile facts — even for messages like "what's next?" that contain nothing to learn.

**Why it matters.**
Doubles LLM calls (latency + rate-limit pressure on Groq's free tier) for the majority of turns where there's nothing to extract.

**Expected output after fix.**
- Memory extraction only runs when there's plausibly something to learn (e.g., gated by intent, or by a cheap heuristic/keyword pre-check before spending an LLM call).
- Visible result: response latency on simple turns ("what's next?", "mark that done") drops noticeably; profile-learning still fires on messages that actually contain new facts.

---

### 4. Fragile control-token parsing can silently drop data `P0` · Agent

**Problem.**
Task creation, completion, and profile updates all depend on the LLM emitting perfectly-formed XML-like tokens (`<TASKS_CONFIRMED>[...]</TASKS_CONFIRMED>`). If the model emits malformed JSON or a missing closing tag, the mutation is silently skipped — the user is told "Got it!" but nothing was saved.

**Why it matters.**
This is a *correctness* bug that erodes trust. A task assistant that occasionally forgets to save tasks — without telling anyone — is worse than no assistant. Since we're staying on Llama (weaker at structured output than a frontier model), this risk is real, not theoretical.

**Expected output after fix.**
- Robust parsing: tolerant extraction (regex + JSON repair), and explicit **validation** of the parsed payload against the `Task` / `UserProfile` schema.
- On parse/validation failure: a single **retry** with a corrective prompt, and if it still fails, a visible fallback ("I couldn't save that cleanly — can you rephrase?") instead of a false success.
- Unit tests covering malformed-token cases.
- Visible result: tasks are never silently dropped; failures are surfaced, not swallowed.

---

### 5. The scheduler fires but nobody sees it `P1` · Backend / Frontend / Infra

**Problem.**
`morning_briefing_job` and `eod_wrap_job` run on schedule, generate a briefing, and log the first 120 characters. The user only sees it if they happen to have the app open and look. There is no delivery mechanism.

**Why it matters.**
This is a headline feature that doesn't actually function end-to-end. A scheduled briefing the user never receives is dead code.

**Expected output after fix.**
- Generated briefings are persisted as messages in the relevant session so they appear when the user next opens the app.
- (Stretch) Browser push notification (Web Push API) so the user is actively notified at wake/EOD time.
- Visible result: at the scheduled time, a fresh briefing message is waiting in the conversation when the user opens Donna (and, with push, they get a notification).

---

### 6. No error feedback in the UI `P1` · Frontend

**Problem.**
API errors are caught in `lib/api.ts` but nothing is shown to the user. On failure, Donna simply goes silent.

**Why it matters.**
A silent failure is indistinguishable from a hang. The user doesn't know whether to wait, retry, or reload.

**Expected output after fix.**
- A visible, non-blocking error state in the chat ("Something went wrong — tap to retry").
- Visible result: kill the backend, send a message, and the UI clearly shows the failure with a retry affordance instead of an infinite spinner / silence.

---

### 7. No tests `P1` · Infra

**Problem.**
Zero test files in the repo. The most fragile logic (control-token parsing, intent classification, SQLite task CRUD) has no safety net.

**Why it matters.**
Every change risks silent regressions in exactly the areas (parsing, persistence) where bugs are hardest to notice.

**Expected output after fix.**
- A `pytest` suite covering: control-token parsing (valid + malformed), task CRUD against a temp SQLite DB, and intent classification routing.
- Visible result: `pytest` runs green; intentionally breaking the parser turns a test red.

---

### 8. CORS is wide open `P2` · Infra

**Problem.**
`allow_origins=["*"]` in `main.py`.

**Why it matters.**
Fine for local dev, but should be locked to known origins before any deployment.

**Expected output after fix.**
- Allowed origins read from an env var, defaulting to `localhost` for dev.
- Visible result: requests from unlisted origins are rejected in a production config.

---

### 9. ChromaDB is overkill for a single document `P2` · Infra / Backend

**Problem.**
The user profile is stored as one JSON document (`id="profile"`). No semantic/vector search ever happens — ChromaDB is acting as an over-engineered key-value store, while requiring a whole extra Docker service.

**Why it matters.**
Added operational complexity (a service that can fail to start, the 5-retry/2s backoff workaround in `chroma_store.py` is evidence of this) for zero functional benefit.

**Expected output after fix.**
- Profile stored in SQLite (or a flat JSON file) behind the same `ChromaStore`-style interface so callers don't change.
- The ChromaDB service is removed from `docker-compose.yml`.
- Visible result: one fewer container, faster/more reliable startup, identical behavior. (Revisit a vector DB only if/when we add real semantic search over conversation history.)

---

# Part 2 — Features to Add

> Ordered roughly by value-to-effort. These build on the fixes above.

### A. Markdown rendering in chat `P1` · Frontend
Donna's responses already use bullets and headers; they currently render as raw text. Add `react-markdown` to `MessageBubble`.
**Visible result:** briefings and lists render as formatted markdown instead of plain text with stray asterisks.

### B. Recurring tasks `P1` · Backend / Agent
Support "every Monday: standup". Add a recurrence field to the task model + expansion logic when fetching a day's tasks.
**Visible result:** a recurring task automatically appears on each matching day without re-entry.

### C. Conversation history `P1` · Frontend / Backend
Builds on fix #2. A sidebar to browse and resume past sessions.
**Visible result:** the user can scroll back through previous days' conversations, not just the current one.

### D. Browser push notifications `P1` · Frontend / Backend
Completes fix #5. Web Push so scheduled briefings reach the user when the app is closed.
**Visible result:** a notification at wake time even if Donna isn't open.

### E. Task search & filters `P2` · Frontend / Backend
Search by keyword, filter by priority / date / tag.
**Visible result:** a search box that filters the task list live.

### F. Calendar sync `P2` · Backend / Integrations
Google Calendar / Outlook import so meetings become tasks automatically.
**Visible result:** today's calendar events show up in Donna's task list without manual entry.

### G. Light mode / theme toggle `P2` · Frontend
Currently dark-only.
**Visible result:** a toggle that switches between light and dark themes.

### H. Weekly analytics `P2` · Backend / Frontend
Completion rate, productivity trends over time.
**Visible result:** a simple dashboard showing tasks completed per day/week.

---

# Suggested Sequencing

1. **Reliability first** — #4 (control-token hardening) + #7 (tests). These protect everything else.
2. **Continuity** — #2 (persist sessions), then #5 (scheduler delivery), then C/D (history + push).
3. **Responsiveness** — #1 (real streaming) + #3 (gate update_memory).
4. **UX polish** — #6 (error UI), A (markdown), G (themes).
5. **Cleanup / hardening** — #9 (drop ChromaDB), #8 (CORS).
6. **New capabilities** — B (recurring), E (search), F (calendar), H (analytics).
