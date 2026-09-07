/**
 * SSE parser for the backend's `/query?stream=true` endpoint.
 *
 * Frames look like:
 *   event: grounding
 *   data: {"sourceChunks":[...]}
 *
 * We reconstruct `{ type, payload }` and dispatch typed {@link StreamEvent}s.
 */
import type { StreamEvent } from "./types";

const KNOWN = new Set(["start", "grounding", "token", "analysis", "suggestions", "final", "error"]);

export async function consumeSSE(
  res: Response,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (!res.body) throw new Error("stream: response has no body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      if (signal?.aborted) break;
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const raw = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        dispatch(raw, onEvent);
        sep = buffer.indexOf("\n\n");
      }
    }
    if (buffer.trim()) dispatch(buffer, onEvent);
  } finally {
    reader.releaseLock();
  }
}

function dispatch(raw: string, onEvent: (e: StreamEvent) => void): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length || !KNOWN.has(event)) return;
  try {
    const payload = JSON.parse(dataLines.join("\n"));
    onEvent({ type: event, payload } as StreamEvent);
  } catch (err) {
    console.warn("stream: bad frame", err);
  }
}
