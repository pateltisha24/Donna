# Donna — Project → Product Roadmap

> Goal: turn Donna from an impressive project into a product people actually use to plan
> their day — and that makes a recruiter stop and think "this person solves real problems."
> Constraints are real and respected: free tiers only, Groq + Llama 3.3 70B (no paid models),
> student-scale deployment. We build to product quality *within* those constraints.

Phases are **capability layers**, not tasks. Each phase leaves Donna whole and shippable.
Do them in order; inside a phase, the items are roughly ordered too.

Legend: 🎯 outcome · 🧩 work items · 🏆 recruiter angle · ✅ done-when

---

## Phase 0 — Foundation hygiene & honest baseline  *(~half day)*

🎯 A clean repo and an honest starting line, so everything after is built on solid ground and
a recruiter who clones it sees a real codebase, not a 99%-junk tree.

🧩
| Item | Detail |
|---|---|
| Untrack `.venv/` | `git rm -r --cached .venv`; fix `.gitignore` (`venv/` ≠ `.venv/`). ~9.4k of 9.5k tracked files are virtualenv junk today. |
| Commit in-progress work | Phase-1 warm theme + the Phase-3 memory-recall fix are uncommitted. Land them as clean checkpoints. |
| Secret hygiene | Confirm no keys in tree; add a startup check that fails loudly if `GROQ_API_KEY`/Mongo URI missing. Rotate the Groq key (it's been in transcripts). |
| Kill dead code confusion | Decide fate of `sqlite_store.py` (tests use it; app uses Mongo). Either keep as the test backend deliberately, or remove. Document the choice. |
| Doc truth pass | Fix drift: `IMPROVEMENTS.md` says "Chroma removed" but it's used (embedded). README/DEPLOY mention a Chroma disk on Render. |

🏆 "I keep a clean, honest repo" is table stakes — but the *absence* of it is an instant red flag.
✅ `git ls-files | wc -l` is ~100s not ~9.5k; fresh clone runs; docs match reality.

---

## Phase 1 — Frontend & UX: the product surface

🎯 The first impression. Donna should *look and feel* like a product you'd pay for: a real app
shell with destinations, a warm distinctive brand, a pre-chat "here's your day" home, and polish
in every state (loading, empty, error, offline, cold-start). This is what a recruiter sees in 5s.

🧩 **1a. Theme & visual system** (partly done — finish it)
| Item | Detail |
|---|---|
| Land the warm theme | Amber primary already applied (uncommitted). Verify it reads "warm/decisive," not generic SaaS. |
| Signature accent | Pick ONE memorable accent beyond amber (e.g. a coral/teal) so Donna isn't "another violet AI app." Use it consistently for one thing (active state / Donna's voice). |
| Elevation system | 2–3 shadow tiers so chat / sidebar / calendar read as distinct planes. Today it's flat + one `.glass`. |
| Contrast/AA audit | Light-mode `muted-foreground` is borderline AA. Run a checker; fix failures. |
| Curated icon set | Replace the lucide grab-bag with a consistent, refined set (your stated preference). |
| Native dropdowns | Use native `<select>` for menus (your stated preference), styled to match. |

🧩 **1b. App shell & navigation** (structural — unlocks later phases)
| Item | Detail |
|---|---|
| Real left nav | Destinations: **Today** · **Chat** · **Calendar** · **Productivity** · **Settings**. Today there's only `/app` (chat) + a right sheet. Each later feature needs a home. |
| `/app` → "Today" home | Pre-chat dashboard: greeting, today's tasks + events at a glance, day-load summary, quick actions, "talk to Donna" CTA. Kills the empty-chat cliff. |
| Productivity page | Move `InsightsView` out of `RightPanel.tsx` into its own route with real charts (completion trends, time-by-category, streaks). |
| Calendar page (read-only grid) | A day/week time-block grid rendering existing tasks/events. The visual that makes Donna look like Motion/Sunsama. (Live 2-way sync comes in Phase 4.) |
| Settings maturity | Timezone, working hours, wake/EOD times, notification prefs, theme, account. Feeds the scheduler + agent. |

🧩 **1c. Interaction polish & states**
| Item | Detail |
|---|---|
| Optimistic UI | Instant task add/complete; reconcile on server response. |
| Streaming cursor | A real typing cursor on Donna's streamed tokens. |
| Task-complete animation | Satisfying check/strike micro-interaction. |
| Skeletons + cold-start state | Render skeletons; show a friendly "Donna's waking up…" during Render's ~30s cold start instead of looking broken. |
| Distinct empty/error states | Empty calendar, offline, rate-limited, no-tasks — each its own designed state, not a generic toast. |
| Guided first-run onboarding | First login: set name/timezone/working hours → one sample "talk to me." Reduces the empty-state cliff for new users. |

🧩 **1d. Mobile & PWA**
| Item | Detail |
|---|---|
| Installable PWA | `manifest.json` + you already have `sw.js`/push → make it installable with an offline shell. "Works on my phone" is a huge demo moment. |
| Responsive pass | Audit chat, nav, calendar grid at mobile widths. |

🧩 **1e. Brand identity**
| Item | Detail |
|---|---|
| Wordmark + avatar | A real Donna logotype, refined avatar, favicon. A product has a face. |
| One signature moment | Design the hero interaction (built in Phase 2): typing "interview moved to 11, replan" makes calendar blocks visibly animate into new slots. This clip is your portfolio centerpiece. |

🏆 "I can design and build a polished, accessible, installable product front-end" — provable in 5 seconds of screen-share.
✅ Nav with 5 real destinations; `/app` opens to a useful "Today"; Productivity + Calendar pages exist; cold-start no longer looks broken; installable on a phone; AA passes.

---

## Phase 2 — Agent that acts: Donna's brain  *(the core differentiator)*

🎯 Today Donna *describes* a replan; a product *performs* it. This phase is the single biggest
"demo vs. product" leap and the centerpiece for an AI/ML recruiter. Stay on Groq/Llama 3.3 70B.

🧩 **2a. Native tool-calling** (modernize the agent)
| Item | Detail |
|---|---|
| Adopt Groq function-calling | Llama 3.3 70B supports native tools on Groq. Define real tools: `create_task`, `update_task`, `complete_task`, `move_task`, `create_event`, `move_event`, `delete_event`, `replan_day`. |
| Keep XML parser as fallback | The hand-rolled control-token parser becomes the resilient fallback path, not the primary. Frame: "I hardened the weak path *and* adopted the robust one." |
| Confirmation + diff UX | Actions return a structured diff ("moved 3 things, freed 11–12"); user confirms; **undo** restores prior state. |

🧩 **2b. Real emergency replan** (the hero feature)
| Item | Detail |
|---|---|
| `emergency_replan` mutates state | Instead of prose, it actually reschedules tasks/events around the new constraint, respecting working hours + priorities + conflicts. |
| Returns an actionable diff | Frontend animates blocks into new positions (the Phase-1 signature moment). |

🧩 **2c. Persistent memory wired into prompts** (started — finish)
| Item | Detail |
|---|---|
| Recall already wired + user-scoped | `_recall_memories()` injects relevant past snippets; the user_id write-path bug is fixed and verified. |
| "What Donna remembers" panel | Surface stored facts/preferences in the UI; let users view/edit/delete them. Trust + transparency + wow. |
| Memory write confirmations | When Donna learns something ("noted — you prefer deep work in mornings"), make it visible. |

🧩 **2d. Proactive intelligence**
| Item | Detail |
|---|---|
| Conflict + overload nudges | Donna notices double-bookings / an overloaded day and speaks up unprompted in briefings. |
| Smarter routing | Cache intent classification for trivial messages; run `update_memory` after the response so it never adds latency. |

🧩 **2e. Eval harness** (ML maturity signal)
| Item | Detail |
|---|---|
| 30–50 scripted conversations | Assert correct intent routing *and* that tasks/events actually get written. |
| Run in CI | Turns "I prompted an LLM" into "I measured and improved an LLM system." Recruiters love this. |
| Model fallback chain | If Groq rate-limits, degrade gracefully to a smaller Groq model. Shows reliability thinking under constraint. |

🏆 "Built a LangGraph agent with native tool-calling, per-user semantic memory, and an automated eval suite on Groq/Llama — and it *acts* on your calendar." That sentence survives scrutiny.
✅ "Replan my day" visibly moves real blocks with undo; memory panel shows/edits stored facts; eval suite green in CI.

---

## Phase 3 — Product-grade backend: trust, safety, scale

🎯 Make the multi-tenant claim *true* and the service safe to expose. Today the backend trusts a
client-supplied `X-User-Id` header — anyone can read anyone's data. A "product" can't ship that.

🧩 **3a. Real auth/authz** (un-defer this)
| Item | Detail |
|---|---|
| Verify a real credential | NextAuth issues a signed JWT → backend validates signature + expiry on every request → derive `user_id` from the verified token, never from a raw header. |
| Close the default-session leak | `/history?session_id=default` skips ownership checks; lock it down. |
| Account lifecycle | Data export + account deletion (product-grade, GDPR-friendly, recruiter-friendly). |

🧩 **3b. Fix the scheduler (privacy leak)**
| Item | Detail |
|---|---|
| Per-user jobs | `_run_scheduled` runs as the "default" user today; briefings/reminders must be generated per user. |
| Per-user push filtering | `get_subscriptions()` does `find({})` — it broadcasts one user's reminders to everyone. Filter by `user_id`. |
| Per-user timezone | One global TZ today; schedule in each user's tz. |

🧩 **3c. Safety & robustness**
| Item | Detail |
|---|---|
| Rate limiting | Per-IP + per-user (slowapi/Redis token bucket); throttle + lockout on `/auth/login`; protect `/chat` from draining the Groq quota. |
| Input caps | Max message length, upload size cap, content-type allowlist (prevent memory DoS via huge image). |
| Non-enumerable IDs | Stop exposing sequential integer task IDs; use UUID/ObjectId. |
| Idempotency | Persist the user message before the LLM call so a mid-stream disconnect can't lose history. |

🧩 **3d. Observability & CI**
| Item | Detail |
|---|---|
| Structured logging + request IDs | Replace bare `logging.info`. |
| Error tracking | Sentry (free tier). |
| Tests repointed to Mongo | Current ~100 tests hit `SqliteStore` (dead path). Use `mongomock`; add auth + per-user isolation tests. |
| CI | GitHub Actions: lint + tests + eval suite on every push. |
| Cold-start mitigation | Keep-alive ping (cron) so the free tier doesn't sleep; pairs with Phase-1 "waking up" UX. |

🏆 "Multi-tenant, JWT-secured, rate-limited FastAPI service with CI, error tracking, and per-user isolation." Currently that sentence isn't true; after this phase it is.
✅ A forged `X-User-Id` gets 401; user A provably can't read user B (test); scheduler pushes only your own reminders; CI green.

---

## Phase 4 — Google Calendar: two-way sync  *(makes it "real")*

🎯 Every competitor that matters syncs Google Calendar both ways. This is table stakes for the
category and a strong real-world-skills signal (OAuth, sync, conflict reconciliation). Depends on
Phase 2 (agent acting on calendar) + Phase 3 (auth/OAuth infra).

🧩
| Item | Detail |
|---|---|
| Google OAuth connect | "Connect Google Calendar" in Settings; store refresh tokens securely. |
| Two-way sync | Pull external events into Donna's grid; push Donna-created events out; reconcile edits/deletes. |
| Conflict handling | Reuse existing `/conflicts` logic; surface double-bookings across synced + local. |
| Live calendar grid | The Phase-1 read-only grid becomes live and editable, reflecting synced events; drag-to-move writes back. |
| Keep .ics path | `.ics` import/export + screenshot→events (Groq vision, llama-4-scout) stay as the no-credentials fallback. |

🏆 "Two-way Google Calendar sync with conflict reconciliation" — the line that moves Donna from "chatbot" to "calendar product."
✅ Create an event in Google → appears in Donna; "replan" in Donna → updates Google; conflicts flagged.

---

## Phase 5 — Wow layer & growth

🎯 The differentiators that make Donna memorable and shareable, plus the frictionless path that
lets a recruiter *try it in one click*.

🧩
| Item | Detail |
|---|---|
| One-click recruiter demo | Polished, seeded "try without signup" mode (you already have a `demo` user). A recruiter clicks and is instantly in a believable, populated day. Possibly the single highest-ROI item for your goal. |
| ⌘K command palette | Keyboard-first command bar (Akiflow's signature) — fast and impressive. |
| Voice input | Web Speech API (free): "talk to Donna." Big demo moment. |
| Signature replan animation | Polish the Phase-2 diff into the portfolio hero clip. |
| Smart notifications | Notify only when genuinely useful (conflict, free slot opened), never spam. |
| Weekly review ritual | Sunday "plan your week" + Friday "how'd it go" — the Sunsama-style calm ritual, conversational. |
| Integrations inbox (stretch) | Pull tasks from Gmail/Slack/Todoist into Donna. This is the "people actually use it daily" layer. |

🏆 The clips and the one-click demo are what you actually show in the interview.
✅ Recruiter can try a populated Donna in one click; ⌘K + voice work; replan clip is recordable.

---

## Sequencing notes & dependencies

- **Phase 0 is immediate** (half a day) and unblocks a clean story.
- **Phase 1 first** is deliberate: first impressions are visual, and the app shell creates *homes*
  for every later feature. It can proceed without backend auth changes.
- **Phase 2 is the differentiator** — if time is short, Phase 1 + Phase 2 + the Phase-5 one-click
  demo is the minimum that wins an interview.
- **Phase 3 (auth) is a hard gate before any public launch** — fine to demo before it, never to
  open to real users before it.
- **Phase 4 depends on 2 + 3.**

## Open decisions for Tisha
1. **Timeline** — is there still a near-term interview deadline (memory said ~2026-06-08)? If yes,
   we compress to Phase 1 + the Phase-2 replan + Phase-5 demo, and defer 3/4.
2. **JWT auth** — previously deferred for speed. Un-defer into Phase 3 now that the goal is a real
   product? (Recommended: yes, but it's not needed to demo.)
3. **Scope of "all the paid features"** — confirm the Phase-4/5 integrations (Google, Gmail/Slack/
   Todoist) are in scope, or trim to Google-only for now.
