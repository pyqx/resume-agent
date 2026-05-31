/** Typed API client for the Resume Agent backend.
 *
 * SSE streaming goes directly to the backend (port 8000) to avoid
 * Next.js proxy buffering. Regular API calls go through Next.js rewrite.
 */
const API_BASE = "/api";
const BACKEND_BASE = "http://127.0.0.1:8000";

export interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: number;
}

export async function uploadResume(file: File): Promise<{
  resume_id: string;
  resume: Record<string, unknown>;
  metadata: Record<string, unknown>;
}> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/resume/upload`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getResume(resumeId: string) {
  const res = await fetch(`${API_BASE}/resume/${resumeId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listResumes() {
  const res = await fetch(`${API_BASE}/resume/`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function parseJD(jdText: string) {
  const res = await fetch(`${API_BASE}/jd/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function matchJD(jdText: string, resumeId?: string) {
  const res = await fetch(`${API_BASE}/jd/match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jd_text: jdText, resume_id: resumeId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function exportMarkdown(resumeId?: string) {
  const res = await fetch(`${API_BASE}/export/markdown`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

export async function exportHTML(resumeId?: string) {
  const res = await fetch(`${API_BASE}/export/html`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ resume_id: resumeId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.text();
}

export async function* streamChat(
  message: string,
  sessionId?: string,
): AsyncGenerator<SSEEvent> {
  // MUST go directly to backend — Next.js proxy buffers SSE streams
  const res = await fetch(`${BACKEND_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  });

  if (!res.ok) throw new Error(await res.text());

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data:")) {
        const data = line.slice(5).trim();
        if (data) {
          try {
            yield JSON.parse(data);
          } catch {
            // non-JSON data, skip
          }
        }
      }
    }
  }
}
