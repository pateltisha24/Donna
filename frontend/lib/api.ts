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

async function resolveUserId(): Promise<string> {
  try {
    if (typeof window !== "undefined") {
      // A signed-in NextAuth session always wins. Falls through to demo only
      // if no session AND no demo marker, so brand-new visitors land in demo.
      const session = await getSession();
      const email = session?.user?.email?.trim().toLowerCase();
      if (email) {
        try {
          localStorage.removeItem("donna_user"); // clear stale demo marker
        } catch {}
        return email;
      }
      if (localStorage.getItem("donna_user") === "demo") return "demo";
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
  return apiFetch(`${path}`, { ...init, headers });
}

export interface Message {
  role: "user" | "donna";
  content: string;
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
  onDone: () => void;
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
          handlers.onDone();
        }
      } catch {
        // Ignore malformed SSE lines.
      }
    }
  }
  handlers.onDone();
}

/** Send a message to Donna and stream the response back. */
export async function sendMessage(
  message: string,
  sessionId: string,
  onChunk: (chunk: string) => void,
  onDone: () => void,
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
  onDone: () => void,
  onError?: (message: string) => void
): Promise<void> {
  const res = await apiFetch(`/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, session_id: sessionId }),
  });
  await readSSE(res, { onChunk, onDone, onError });
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

/** Upcoming calendar events over the next `days` days. */
export async function getEvents(days = 7): Promise<CalEvent[]> {
  const res = await apiFetch(`/events?days=${days}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Delete an event. */
export async function deleteEvent(id: number): Promise<void> {
  await apiFetch(`/events/${id}`, { method: "DELETE" });
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
  const res = await fetch(
    `${API_URL}/recall?q=${encodeURIComponent(query)}&limit=${limit}`
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
  const res = await fetch(
    `${API_URL}/history?session_id=${encodeURIComponent(sessionId)}`
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
  wake_time: string;
  eod_time: string;
  major_goals_short: string[];
  major_goals_long: string[];
  preferences: string[];
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
