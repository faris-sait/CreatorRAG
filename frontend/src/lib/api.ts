import type { Citation, PairStatus, Transcript } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function jsonHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (API_KEY) h["X-API-Key"] = API_KEY;
  return h;
}

export async function submitVideos(
  youtube_url: string,
  instagram_url: string,
  exact_yt_timestamps = false,
): Promise<{ pair_id: string; a_video_id: string; b_video_id: string }> {
  const res = await fetch(`${API}/api/videos`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ youtube_url, instagram_url, exact_yt_timestamps }),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail || `Submit failed (${res.status})`);
  }
  return res.json();
}

/** Proxy a CDN thumbnail through the backend (Instagram blocks hotlinking). */
export function proxiedImage(url?: string | null): string | undefined {
  if (!url) return undefined;
  return `${API}/api/image?url=${encodeURIComponent(url)}`;
}

/** Persisted thumbnail for a video (survives CDN URL expiry). */
export function videoThumbnail(videoId: string): string {
  return `${API}/api/videos/${videoId}/thumbnail`;
}

export async function getPairStatus(pairId: string): Promise<PairStatus> {
  const res = await fetch(`${API}/api/pairs/${pairId}`);
  if (!res.ok) throw new Error(`Status failed (${res.status})`);
  return res.json();
}

export async function getTranscript(videoId: string): Promise<Transcript> {
  const res = await fetch(`${API}/api/videos/${videoId}/transcript`);
  if (!res.ok) throw new Error(`Transcript failed (${res.status})`);
  return res.json();
}

export interface ChatHandlers {
  onToken: (text: string) => void;
  onSources: (sources: Citation[]) => void;
  onDone: () => void;
  onError: (message: string) => void;
}

/**
 * POST /api/chat returns an SSE stream. EventSource only supports GET, so we
 * read the response body ourselves and parse the `event:`/`data:` frames.
 */
export async function streamChat(
  pairId: string,
  sessionId: string,
  message: string,
  handlers: ChatHandlers,
): Promise<void> {
  const res = await fetch(`${API}/api/chat`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ pair_id: pairId, session_id: sessionId, message }),
  });
  if (!res.ok || !res.body) {
    handlers.onError(`Chat failed (${res.status})`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (frame: string) => {
    const lines = frame.split("\n");
    let event = "message";
    let data = "";
    for (const line of lines) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
    }
    if (!data) return;
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(data);
    } catch {
      return;
    }
    if (event === "token") handlers.onToken((parsed.text as string) || "");
    else if (event === "sources")
      handlers.onSources((parsed.sources as Citation[]) || []);
    else if (event === "done") handlers.onDone();
    else if (event === "error")
      handlers.onError((parsed.message as string) || "Unknown error");
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE frames are separated by a blank line.
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      dispatch(frame);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}
