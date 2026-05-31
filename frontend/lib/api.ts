const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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
  const res = await fetch(`${API_URL}/chat`, {
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
  const res = await fetch(`${API_URL}/trigger`, {
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
  const res = await fetch(`${API_URL}/search?${params.toString()}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Fetch completion analytics over the last `days` days. */
export async function getAnalytics(days = 7): Promise<Analytics> {
  const res = await fetch(`${API_URL}/analytics?days=${days}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Upload a screenshot or .ics file; backend parses it into events. */
export async function uploadCalendarFile(
  file: File
): Promise<{ created: CalEvent[]; message: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/upload`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

/** Upcoming calendar events over the next `days` days. */
export async function getEvents(days = 7): Promise<CalEvent[]> {
  const res = await fetch(`${API_URL}/events?days=${days}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Delete an event. */
export async function deleteEvent(id: number): Promise<void> {
  await fetch(`${API_URL}/events/${id}`, { method: "DELETE" });
}

/** URL to download all events as an .ics for Apple Calendar. */
export function calendarIcsUrl(): string {
  return `${API_URL}/calendar.ics`;
}

/** Get the server's VAPID public key (and whether push is configured). */
export async function getVapidKey(): Promise<{ key: string; enabled: boolean }> {
  const res = await fetch(`${API_URL}/push/vapid-public-key`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

/** Register a browser push subscription with the backend. */
export async function subscribePush(sub: PushSubscriptionJSON): Promise<void> {
  await fetch(`${API_URL}/push/subscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub),
  });
}

/** Remove a push subscription from the backend. */
export async function unsubscribePush(endpoint: string): Promise<void> {
  await fetch(`${API_URL}/push/unsubscribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint }),
  });
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
