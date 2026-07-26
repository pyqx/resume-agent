/** Typed API client for the Resume Agent backend.
 *
 * Regular API calls go through the Next.js rewrite (`/api/*` → backend) so
 * the browser stays same-origin. SSE streaming MUST go directly to the
 * backend because the Next.js proxy buffers streamed responses.
 */

import type {
  Resume,
  ResumeListResponse,
  SessionDetail,
  SessionListResponse,
  UploadResult,
} from "@/lib/types";

/** Backend origin for direct (non-proxied) calls, e.g. SSE. */
export const API_BASE: string =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

/** Same-origin prefix rewritten by next.config.js to the backend. */
const PROXY_PREFIX = "/api";

// ── Errors ─────────────────────────────────────────────────

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/** Human-readable message for any thrown error (prefers ApiError.detail). */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return err.detail;
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

/** Extract the backend's `{"detail": ...}` message from a failed response. */
async function extractDetail(res: Response): Promise<string> {
  const fallback = `请求失败 (HTTP ${res.status})`;
  try {
    const text = await res.text();
    if (!text) return fallback;
    try {
      const body = JSON.parse(text);
      const detail = body?.detail;
      if (typeof detail === "string" && detail) return detail;
      if (detail != null) return JSON.stringify(detail);
      return fallback;
    } catch {
      return text.slice(0, 300) || fallback;
    }
  } catch {
    return fallback;
  }
}

// ── Generic fetch wrapper (proxied) ────────────────────────

/**
 * Fetch a backend endpoint through the `/api` proxy.
 *
 * @param path Backend path starting with "/" (e.g. "/resume/").
 * @throws ApiError with the backend's Chinese `detail` message on non-2xx.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${PROXY_PREFIX}${path}`, init);
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "网络错误,请检查后端服务是否已启动");
  }
  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res));
  }
  const text = await res.text();
  if (!text) return undefined as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    // Endpoint returned plain text (e.g. markdown export).
    return text as unknown as T;
  }
}

// ── Time helpers ───────────────────────────────────────────

/**
 * Parse a backend timestamp as UTC.
 *
 * SQLite / Python emit naive UTC strings like "2026-07-26 12:00:00" (no
 * timezone). Parsing them bare makes JS treat them as *local* time, shifting
 * history by the UTC offset (+8h in China). Normalize to ISO and append "Z"
 * when no timezone is present.
 */
export function parseUtc(value: string): Date {
  if (!value) return new Date(NaN);
  let v = value.trim().replace(" ", "T");
  // JS Date only accepts up to millisecond precision; trim microseconds.
  v = v.replace(/(\.\d{3})\d+/, "$1");
  const hasTime = v.includes("T");
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(v);
  if (hasTime && !hasTz) v += "Z";
  return new Date(v);
}

/** Render a backend UTC timestamp as a short relative Chinese label. */
export function formatRelativeTime(value: string): string {
  const date = parseUtc(value);
  if (isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return date.toLocaleDateString("zh-CN");
}

// ── SSE streaming chat (direct to backend) ─────────────────

export interface SSEEvent {
  type: string;
  data: any;
}

export interface StreamChatRequest {
  message: string;
  session_id?: string;
  resume_id?: string;
  user_id?: string;
}

/**
 * POST /chat/stream and yield parsed SSE events.
 *
 * Connects directly to the backend (the Next proxy buffers SSE). Correctly
 * handles `event:`/`data:` framing: the `event:` line sets the type, blank
 * lines delimit frames (type is reset per frame), `:` comment lines are
 * ignored, and multi-line `data:` is joined with "\n".
 *
 * @param signal Optional AbortSignal — aborting truly cancels the fetch.
 */
export async function* streamChat(
  req: StreamChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "网络错误,无法连接后端服务");
  }

  if (!res.ok) {
    throw new ApiError(res.status, await extractDetail(res));
  }

  const reader = res.body?.getReader();
  if (!reader) throw new ApiError(0, "响应没有可读的流");

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEventType = "";
  let dataLines: string[] = [];

  // Build the pending frame's event (or null), then reset frame state.
  const flushFrame = (): SSEEvent | null => {
    const type = currentEventType;
    const lines = dataLines;
    // MUST reset per frame — a stale type must never leak into later frames.
    currentEventType = "";
    dataLines = [];
    if (lines.length === 0) return null; // per SSE spec: no data → no dispatch
    const raw = lines.join("\n");
    let data: unknown;
    try {
      data = JSON.parse(raw);
    } catch {
      data = raw;
    }
    return { type: type || "message", data };
  };

  const handleLine = (rawLine: string): SSEEvent | null => {
    const line = rawLine.endsWith("\r") ? rawLine.slice(0, -1) : rawLine;
    if (line === "") return flushFrame(); // blank line = frame boundary
    if (line.startsWith(":")) return null; // comment / keep-alive ping
    if (line.startsWith("event:")) {
      currentEventType = line.slice(6).trim();
      return null;
    }
    if (line.startsWith("data:")) {
      let value = line.slice(5);
      if (value.startsWith(" ")) value = value.slice(1);
      dataLines.push(value);
      return null;
    }
    return null; // unknown field — ignore
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        const evt = handleLine(line);
        if (evt) yield evt;
      }
    }
    // Stream ended: flush the decoder and any residual partial frame.
    buffer += decoder.decode();
    if (buffer.length > 0) {
      const evt = handleLine(buffer);
      if (evt) yield evt;
    }
    const trailing = flushFrame();
    if (trailing) yield trailing;
  } finally {
    reader.releaseLock();
  }
}

// ── Resume API ─────────────────────────────────────────────

export const resumeApi = {
  upload(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);
    return apiFetch<UploadResult>("/resume/upload", {
      method: "POST",
      body: formData,
    });
  },

  get(resumeId: string): Promise<Resume> {
    return apiFetch<Resume>(`/resume/${encodeURIComponent(resumeId)}`);
  },

  list(): Promise<ResumeListResponse> {
    return apiFetch<ResumeListResponse>("/resume/");
  },

  delete(resumeId: string): Promise<{ deleted: string }> {
    return apiFetch<{ deleted: string }>(
      `/resume/${encodeURIComponent(resumeId)}`,
      { method: "DELETE" },
    );
  },

  updateEntry(
    resumeId: string,
    entryId: string,
    updates: Record<string, unknown>,
  ): Promise<{ entry_id: string; updated_fields: string[] }> {
    return apiFetch(
      `/resume/${encodeURIComponent(resumeId)}/entry/${encodeURIComponent(entryId)}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates),
      },
    );
  },

  deleteEntry(resumeId: string, entryId: string): Promise<{ deleted: string }> {
    return apiFetch(
      `/resume/${encodeURIComponent(resumeId)}/entry/${encodeURIComponent(entryId)}`,
      { method: "DELETE" },
    );
  },
};

// ── Sessions API ───────────────────────────────────────────

export const sessionsApi = {
  list(limit = 50): Promise<SessionListResponse> {
    return apiFetch<SessionListResponse>(`/sessions/?limit=${limit}`);
  },

  get(sessionId: string): Promise<SessionDetail> {
    return apiFetch<SessionDetail>(`/sessions/${encodeURIComponent(sessionId)}`);
  },

  delete(sessionId: string): Promise<{ deleted: string }> {
    return apiFetch<{ deleted: string }>(
      `/sessions/${encodeURIComponent(sessionId)}`,
      { method: "DELETE" },
    );
  },
};

/** Lightweight backend reachability check (GET /health).
 *
 * Connects directly (not via the Next proxy): when the backend is down the
 * proxy answers 500 itself, which would look "reachable". A direct fetch
 * failing at the network level is the real signal.
 */
export async function checkHealth(): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    // 503 = degraded but the backend is up and answering.
    return res.ok || res.status === 503;
  } catch {
    return false;
  }
}

// ── Legacy named exports (kept for pages migrating separately) ──

export function uploadResume(file: File): Promise<UploadResult> {
  return resumeApi.upload(file);
}

export function getResume(resumeId: string): Promise<Resume> {
  return resumeApi.get(resumeId);
}

export function listResumes(): Promise<ResumeListResponse> {
  return resumeApi.list();
}

export function parseJD(jdText: string): Promise<Record<string, unknown>> {
  return apiFetch("/jd/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText }),
  });
}

export function matchJD(
  jdText: string,
  resumeId?: string,
): Promise<Record<string, unknown>> {
  return apiFetch("/jd/match", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText, resume_id: resumeId }),
  });
}
