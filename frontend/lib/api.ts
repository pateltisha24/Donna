const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface Message {
  role: "user" | "donna";
  content: string;
}

/**
 * Send a message to Donna and stream the response back word-by-word.
 * @param message     The user's message text
 * @param sessionId   Optional session identifier (defaults to "default")
 * @param onChunk     Called with each streamed text chunk
 * @param onDone      Called when streaming is complete
 */
export async function sendMessage(
  message: string,
  sessionId: string,
  onChunk: (chunk: string) => void,
  onDone: () => void
): Promise<void> {
  const res = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const reader = res.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    throw new Error("Response body is not readable");
  }

  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Process complete SSE lines
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? ""; // keep the last incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const rawData = line.slice(6).trim();
        if (!rawData) continue;
        try {
          const parsed = JSON.parse(rawData);
          if (parsed.chunk !== undefined) {
            onChunk(parsed.chunk);
          } else if (parsed.done) {
            onDone();
          }
        } catch {
          // Ignore parse errors
        }
      }
    }
  }

  onDone();
}

/**
 * Manually trigger morning briefing or EOD wrap.
 */
export async function triggerEvent(
  event: "morning_briefing" | "eod_wrap",
  sessionId: string,
  onChunk: (chunk: string) => void,
  onDone: () => void
): Promise<void> {
  const res = await fetch(`${API_URL}/trigger`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, session_id: sessionId }),
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  const reader = res.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) throw new Error("Response body is not readable");

  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const rawData = line.slice(6).trim();
        if (!rawData) continue;
        try {
          const parsed = JSON.parse(rawData);
          if (parsed.chunk !== undefined) {
            onChunk(parsed.chunk);
          } else if (parsed.done) {
            onDone();
          }
        } catch {
          // Ignore
        }
      }
    }
  }

  onDone();
}
