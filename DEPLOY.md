# Deploying Donna

Two pieces deploy independently:

- **Backend** (FastAPI + LangGraph + Mongo + Chroma) → **Render** (Docker).
- **Frontend** (Next.js 14 + NextAuth) → **Vercel**.

Primary data lives in **MongoDB Atlas**; ChromaDB's small semantic-recall index lives on a 1 GB Render disk.

Total time: **~25 minutes** end-to-end if you have GitHub / Render / Vercel / Atlas / Google Cloud accounts.

---

## Pre-flight

### 1. Rotate the Groq API key

The current `.env` key has been on multiple machines + in chat transcripts. Burn it:

1. <https://console.groq.com/keys> → revoke the existing key.
2. Create a new key. Stash it in a password manager.
3. Paste it into Render's env UI later — never commit it.

### 2. MongoDB Atlas — already set up

You should already have:
- An M0 (free) cluster.
- A database named **`Donna`** (case-sensitive).
- A DB user with `readWrite` on `Donna`.
- **Network Access → 0.0.0.0/0** (so Render can reach it).
- A connection string of the form `mongodb+srv://USER:PASS@CLUSTER.mongodb.net/?retryWrites=true&w=majority&appName=Donna`.

### 3. Generate Web Push (VAPID) keys

```bash
cd frontend && npx web-push generate-vapid-keys
```

Copy the **Public** and **Private** keys.

### 4. Generate a NextAuth secret

```bash
openssl rand -base64 32
```

Save it as `NEXTAUTH_SECRET`.

### 5. Create a Google OAuth client

1. <https://console.cloud.google.com> → APIs & Services → Credentials → Create OAuth Client ID.
2. Application type: **Web application**.
3. **Authorised redirect URIs:**
   - `http://localhost:3000/api/auth/callback/google` (local dev)
   - `https://YOUR_VERCEL_DOMAIN/api/auth/callback/google` (add after Vercel gives you the domain)
4. Copy the **Client ID** and **Client Secret**.

---

## Backend → Render

1. **Push the repo to GitHub** (private is fine).
2. <https://dashboard.render.com> → **New → Blueprint** → connect this repo.
3. Render reads [`render.yaml`](render.yaml) and provisions one Docker service + a 1 GB persistent disk at `/data`.
4. In the service's **Environment** tab, paste the secrets marked `sync: false`:

   | Key | Value |
   |---|---|
   | `GROQ_API_KEY` | (the freshly rotated key) |
   | `MONGODB_URI` | (Atlas connection string) |
   | `VAPID_PUBLIC_KEY` | (from pre-flight #3) |
   | `VAPID_PRIVATE_KEY` | (from pre-flight #3) |

5. Leave `MONGODB_DB=Donna` and the other non-secret values as defaults from `render.yaml`.
6. First deploy is ~4 min (Chroma pulls onnxruntime).
7. Smoke-test: `curl https://YOUR-SERVICE.onrender.com/health` → `{"status":"ok","mongo":true}`.

> **Free-tier note:** Render free web services spin down after 15 min idle (~30 s cold start). Fine for an interview demo. The disk stays mounted across deploys.

---

## Frontend → Vercel

1. <https://vercel.com/new> → import the same GitHub repo.
2. **Root directory:** `frontend`.
3. **Framework preset:** Next.js (auto-detected).
4. **Environment variables** (Project Settings → Environment Variables):

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://YOUR-RENDER-SERVICE.onrender.com` |
   | `NEXTAUTH_URL` | `https://YOUR-VERCEL-DOMAIN` |
   | `NEXTAUTH_SECRET` | (from pre-flight #4) |
   | `GOOGLE_CLIENT_ID` | (from pre-flight #5) |
   | `GOOGLE_CLIENT_SECRET` | (from pre-flight #5) |

5. Deploy. First build ~2 min.

---

## Post-deploy (the closing loop)

These three only become clear once Vercel hands you the final domain:

1. **Google OAuth** — back in Google Cloud Console, add `https://YOUR-VERCEL-DOMAIN/api/auth/callback/google` to Authorised Redirect URIs.
2. **Render CORS** — edit `CORS_ALLOW_ORIGINS` to include the Vercel URL (e.g. `https://donna.vercel.app,http://localhost:3000`). Render auto-restarts the service.
3. **Vercel `NEXTAUTH_URL`** — make sure it matches the production domain (not the preview URL).

### Smoke test

- Visit `https://YOUR-VERCEL-DOMAIN/` → landing page renders.
- Click **Sign in** → modal opens.
- **Continue as demo user** → `/app` loads, "+ New chat" creates a chat in Atlas.
- Send a message → streaming response, AI titles the chat.
- **Sign in with Google** → returns to `/app` as your Google account.
- **Register** (email + password) → auto-signs you in.
- **Sign out** → lands on `/?signedOut=1` with modal forced open.

---

## Local development

```bash
# Backend
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env  # then fill MONGODB_URI, GROQ_API_KEY, VAPID_*, GOOGLE_*
uvicorn main:app --reload

# Frontend (second terminal)
cd frontend
cp .env.local.example .env.local  # if this file ever gets committed; otherwise the existing .env.local
npm install
npm run dev
```

Both run on default ports (8000 / 3000). CORS is preconfigured for localhost.

---

## Architecture quick-reference

```
Vercel (Next.js)                  Render (FastAPI + Docker)
  ┌──────────────┐  fetch / SSE     ┌───────────────────────────┐
  │ Landing /    │ ───────────────► │ /chat   /trigger          │
  │ /app  chat   │                  │ /tasks  /events           │
  │ /about       │                  │ /chats (CRUD + AI title)  │
  │ /api/auth/*  │                  │ /auth/{register,login}    │
  │ (NextAuth)   │                  │ /recall (semantic)        │
  └──────┬───────┘                  │ /agents (metadata)        │
         │                          │                           │
         │ Google OAuth +           │ LangGraph                 │
         │ Credentials              │  ├─ TaskReasoning         │
         │                          │  ├─ Scheduling            │
         │                          │  ├─ Replanning            │
         │                          │  └─ ToolExecution         │
         │                          │                           │
         │                          │ ┌─────────────────────┐   │
         └──────── reads/writes ───►│ │ MongoDB Atlas       │   │
                                    │ │  users, chats,      │   │
                                    │ │  messages, tasks,   │   │
                                    │ │  events, profiles,  │   │
                                    │ │  push_subs,         │   │
                                    │ │  app_state          │   │
                                    │ └─────────────────────┘   │
                                    │ Chroma → /data (disk)     │
                                    │ APScheduler               │
                                    └───────────────────────────┘
```

---

## Cost (free-tier)

| | Free tier | Notes |
|---|---|---|
| Render (web + 1 GB disk) | $0 | Spins down idle |
| Vercel | $0 | Generous for personal projects |
| MongoDB Atlas (M0) | $0 | 512 MB storage |
| Groq | $0 | Free tier rate limits per minute |
| Google OAuth | $0 | Free up to standard quotas |
| **Total** | **$0** | |
