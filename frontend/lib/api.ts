import { getSession } from "next-auth/react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Identity — every request to the backend carries an `X-User-Id` header.
// The id is the user's email (Google / email-password login) or the literal
// "demo" for the shared sandbox. The backend's `get_user_id` dependency uses
// it to scope every MongoStore instance to that user.
// ---------------------------------------------------------------------------

let _cachedUserId: string | null = null;
let _userIdPromise: Promise<string> | null = null;

/**
 * Reset the cached identity (call on sign-in / sign-out so the next request
 * resolves the new user). Called by the auth modal + ProfileMenu.
 */
export function clearUserIdCache(): void {
  _cachedUserId = null;
  _userIdPromise = null;
}

type SessionLike = { user?: { email?: string | null } } | null;

async function resolveUserId(): Promise<string> {
  try {
    if (typeof window === "undefined") return "demo";

    // If the user explicitly chose demo, short-circuit — no need to wait for
    // NextAuth to hit /api/auth/session.
    if (localStorage.getItem("donna_user") === "demo") return "demo";

    // Race the session call against a 1.5s deadline so the UI never hangs on
    // a slow / misconfigured auth endpoint. If it loses the race we fall back
    // to demo and the UI keeps moving; the next call may resolve the real id.
    const sessionPromise: Promise<SessionLike> = getSession()
      .then((s) => (s as SessionLike) ?? null)
      .catch(() => null);
    const timeoutPromise: Promise<SessionLike> = new Promise((resolve) => {
      setTimeout(() => resolve(null), 1500);
    });
    const session = await Promise.race([sessionPromise, timeoutPromise]);
    const email = session?.user?.email?.trim().toLowerCase();
    if (email) {
      try {
        localStorage.removeItem("donna_user");
      } catch {}
      return email;
    }
  } catch {
    // fall through
  }
  return "demo";
}

async function getCurrentUserId(): Promise<string> {
  if (_cachedUserId) return _cachedUserId;
  if (!_userIdPromise) {
    _userIdPromise = resolveUserId().then((id) => {
      _cachedUserId = id;
      return id;
    });
  }
  return _userIdPromise;
}

/**
 * Drop-in replacement for `fetch(API_URL + path, init)` that always injects
 * the X-User-Id header. Use this for every backend call.
 */
async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const userId = await getCurrentUserId();
  const headers = new Headers(init.headers || {});
  if (!headers.has("X-User-Id")) headers.set("X-User-Id", userId);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export interface ReplanData {
  changes: string[];
  undo: boolean;
}

export interface Message {
  role: "user" | "donna";
  content: string;
  replan?: ReplanData;
}

export interface DoneMeta {
  replan?: ReplanData;
}

export interface Task {
  id: number;
  title: string;
  description: string | null;
  deadline: string | null;
  duration_estimate: number | null;
  priority: "high" | "medium" | "low";
  status: "pending" | "in_progress" | "done" | "moved";
  date_assigned: string;
  tags: string[];
  recurrence: string;
  recurrence_days: string[];
}

export interface TaskFilters {
  q?: string;
  priority?: string;
  status?: string;
  date?: string;
  tag?: string;
}

export interface CalEvent {
  id: number;
  title: string;
  date: string;
  start_time: string;
  end_time: string | null;
  location: string;
  description: string;
  recurrence: string;
  recurrence_days: string[];
}

export interface DayStat {
  date: string;
  total: number;
  done: number;
}

export interface Analytics {
  days: DayStat[];
  total: number;
  done: number;
  completion_rate: number;
}

interface StreamHandlers {
  onChunk: (chunk: string) => void;
  onDone: (meta?: DoneMeta) => void;
  onError?: (message: string) => void;
}

/** Read an SSE response body, dispatching {chunk} / {done} / {error} events. */
async function readSSE(res: Response, handlers: StreamHandlers): Promise<void> {
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error("Response body is not readable");

  const decoder = new TextDecoder();
  let buffer = "";
  let doneMeta: DoneMeta = {};

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const rawData = line.slice(6).trim();
      if (!rawData) continue;
      try {
        const parsed = JSON.parse(rawData);
        if (parsed.chunk !== undefined) {
          handlers.onChunk(parsed.chunk);
        } else if (parsed.error) {
          handlers.onError?.(parsed.error);
        } else if (parsed.done) {
          if (parsed.replan) doneMeta = { replan: parsed.replan };
          handlers.onDone(doneMeta);
        }
      } catch {
        // Ignore malformed SSE lines.
      }
    }
  }
  handlers.onDone(doneMeta);
}

/** Send a message to Donna and stream the response back. */
export async function sendMessage(
  message: string,
  sessionId: string,
  onChunk: (chunk: string) => void,
  onDone: (meta?: DoneMeta) => void,
  onError?: (message: string) => void
): Promise<void> {
  const res = await apiFetch(`/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });
  await readSSE(res, { onChunk, onDone, onError });
}

/** Manually trigger morning briefing or EOD wrap. */
export async function triggerEvent(
  event: "morning_briefing" | "eod_wrap",
  sessionId: string,
  onChunk: (chunk: string) => void,
  onDone: (meta?: DoneMeta) => void,
  onError?: (message: string) => void
): Promise<void> {
  const res = await apiFetch(`/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, session_id: sessionId }),
  });
  await readSSE(res, { onChunk, onDone, onError });
}

/** Revert the most recent emergency replan. */
export async function undoReplan(): Promise<{ reverted: number }> {
  const res = await apiFetch(`/replan/undo`, { method: "POST" });
  if (!res.ok) throw new Error(`Undo failed: ${res.status}`);
  return res.json();
}

/** Search/filter tasks. */
export async function searchTasks(filters: TaskFilters): Promise<Task[]> {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v) params.set(k, v);
  });
  const res = await apiFetch(`/search?${params.toString()}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Fetch completion analytics over the last `days` days. */
export async function getAnalytics(days = 7): Promise<Analytics> {
  const res = await apiFetch(`/analytics?days=${days}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export interface InsightDay {
  date: string;
  total: number;
  done: number;
  planned_min: number;
  focus_min: number;
}

export interface InsightCategory {
  name: string;
  count: number;
  done: number;
  minutes: number;
}

export interface Insights {
  range: { start: string; end: string; days: number };
  daily: InsightDay[];
  categories: InsightCategory[];
  summary: {
    total: number;
    done: number;
    completion_rate: number;
    focus_minutes: number;
    active_days: number;
    current_streak: number;
    best_day: string | null;
    best_day_done: number;
  };
}

/** Rich productivity analytics (heatmap + time-by-category + summary). */
export async function getInsights(days = 140): Promise<Insights | null> {
  const res = await apiFetch(`/insights?days=${days}`);
  if (!res.ok) return null;
  return res.json();
}

/** Upload a screenshot or .ics file; backend parses it into events. */
export async function uploadCalendarFile(
  file: File
): Promise<{ created: CalEvent[]; message: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await apiFetch(`/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

/** Upcoming calendar events over `days` days, optionally from a `start` date. */
export async function getEvents(days = 7, start?: string): Promise<CalEvent[]> {
  const qs = new URLSearchParams({ days: String(days) });
  if (start) qs.set("start", start);
  const res = await apiFetch(`/events?${qs.toString()}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Delete an event. */
export async function deleteEvent(id: number): Promise<void> {
  await apiFetch(`/events/${id}`, { method: "DELETE" });
}

/** Edit an event (partial fields). */
export async function updateEvent(
  id: number,
  patch: Partial<Omit<CalEvent, "id">>
): Promise<void> {
  const res = await apiFetch(`/events/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`Update failed: ${res.status}`);
}

/** URL to download all events as an .ics for Apple Calendar. */
export function calendarIcsUrl(): string {
  return `${API_URL}/calendar.ics`;
}

/** Get the server's VAPID public key (and whether push is configured). */
export async function getVapidKey(): Promise<{ key: string; enabled: boolean }> {
  const res = await apiFetch(`/push/vapid-public-key`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Register a browser push subscription with the backend. */
export async function subscribePush(sub: PushSubscriptionJSON): Promise<void> {
  await apiFetch(`/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub),
  });
}

/** Remove a push subscription from the backend. */
export async function unsubscribePush(endpoint: string): Promise<void> {
  await apiFetch(`/push/unsubscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint }),
  });
}

export interface RecallResult {
  document: string;
  role: string | null;
  session_id: string | null;
  ts: string | null;
  score: number | null;
}

/** Semantic recall over indexed assistant messages (ChromaDB). */
export async function recall(query: string, limit = 5): Promise<RecallResult[]> {
  const res = await apiFetch(
    `/recall?q=${encodeURIComponent(query)}&limit=${limit}`
  );
  if (!res.ok) return [];
  const data = await res.json();
  return (data.results ?? []) as RecallResult[];
}

export interface AgentInfo {
  name: string;
  summary: string;
  nodes: string[];
  tools: string[];
}

/** Fetch the four-agent metadata for the About page. */
export async function getAgents(): Promise<AgentInfo[]> {
  const res = await apiFetch(`/agents`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.agents ?? []) as AgentInfo[];
}

/** Load persisted conversation history for a session. */
export async function getHistory(sessionId: string): Promise<Message[]> {
  // MUST use apiFetch — /history is user-scoped, so without the X-User-Id header
  // the backend can't confirm ownership and returns an empty conversation.
  const res = await apiFetch(
    `/history?session_id=${encodeURIComponent(sessionId)}`
  );
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  const data = await res.json();
  return (data.messages ?? []).map((m: { role: string; content: string }) => ({
    role: m.role === "assistant" ? "donna" : "user",
    content: m.content,
  }));
}

// ---------------------------------------------------------------------------
// Chats — multi-conversation
// ---------------------------------------------------------------------------

export interface Chat {
  id: string;
  user_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  archived: boolean;
}

export async function listChats(): Promise<Chat[]> {
  const res = await apiFetch(`/chats`);
  if (!res.ok) return [];
  const data = await res.json();
  return (data.chats ?? []) as Chat[];
}

export async function createChat(title?: string): Promise<Chat> {
  const res = await apiFetch(`/chats`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error(`Create chat failed: ${res.status}`);
  return res.json();
}

export async function renameChat(id: string, title: string): Promise<void> {
  await apiFetch(`/chats/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export async function deleteChat(id: string): Promise<void> {
  await apiFetch(`/chats/${id}`, { method: "DELETE" });
}

export async function titleChatFromMessage(
  id: string,
  firstMessage: string
): Promise<string> {
  const res = await apiFetch(`/chats/${id}/title`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ first_message: firstMessage }),
  });
  if (!res.ok) return "";
  const data = await res.json();
  return (data.title as string) || "";
}

// ---------------------------------------------------------------------------
// Me / settings
// ---------------------------------------------------------------------------

export interface UserProfile {
  name: string;
  occupation: string;
  institution: string;
  working_style: string;
  procrastination_patterns?: string;
  wake_time: string;
  eod_time: string;
  major_goals_short: string[];
  major_goals_long: string[];
  preferences: string[];
  known_priorities?: string[];
  known_people?: Record<string, string>;
  notes?: string[];
}

/** Remove one thing Donna remembers (a preference, person, goal, note…). */
export async function forgetMemory(
  field: string,
  value?: string
): Promise<UserProfile | null> {
  const res = await apiFetch(`/me/forget`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return (data.profile ?? null) as UserProfile | null;
}

export async function getMe(): Promise<{ user_id: string; profile: UserProfile }> {
  const res = await apiFetch(`/me`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function updateSettings(patch: Partial<UserProfile>): Promise<UserProfile | null> {
  const res = await apiFetch(`/me/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) return null;
  const data = await res.json();
  return (data.profile ?? null) as UserProfile | null;
}
