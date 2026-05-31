"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import ChatPanel from "@/components/chat/ChatPanel";
import ResumeEditor from "@/components/resume/ResumeEditor";
import ResumeSelector from "@/components/resume/ResumeSelector";
import { useResumeContext } from "@/contexts/ResumeContext";

interface Message {
  role: "user" | "agent";
  content: string;
  timestamp?: number;
}

const BACKEND = "http://127.0.0.1:8000";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const resume = useResumeContext();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const searchParams = useSearchParams();

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await resume.upload(file);
      setMessages((m) => [...m, {
        role: "agent",
        content: `已解析简历：${file.name}。可以让我帮您分析和优化具体内容。`,
        timestamp: Date.now() / 1000,
      }]);
    } catch (err) {
      setMessages((m) => [...m, {
        role: "agent",
        content: `解析失败 ${file.name}：${err instanceof Error ? err.message : "未知错误"}`,
        timestamp: Date.now() / 1000,
      }]);
    }
  };

  const handleSendMessage = useCallback(async (content: string) => {
    setMessages((m) => [...m, { role: "user", content, timestamp: Date.now() / 1000 }]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${BACKEND}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: content,
          resume_id: resume.resumeId || undefined,
          session_id: sessionId || undefined,
          working_state: resume.resumeId ? { resume_loaded: true, resume_id: resume.resumeId } : undefined,
        }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let currentEventType = "";
      let finalResponse = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("event:")) {
            currentEventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            const raw = line.slice(5).trim();
            if (!raw) continue;
            try {
              const data = JSON.parse(raw);

              if (currentEventType === "session_created") {
                setSessionId(data.session_id);
              }

              if (currentEventType === "plan_complete") {
                try {
                  const parsed = JSON.parse(data.raw_response || "");
                  if (parsed.action === "tool" && parsed.reasoning) {
                    setMessages((m) => [...m, {
                      role: "agent",
                      content: `思考中: ${parsed.reasoning}`,
                      timestamp: Date.now() / 1000,
                    }]);
                  }
                } catch {}
              }

              if (currentEventType === "final") {
                finalResponse = data.response || "(Agent 返回为空)";
              }
            } catch {}
          }
        }
      }

      if (finalResponse) {
        setMessages((m) => [...m, {
          role: "agent",
          content: finalResponse,
          timestamp: Date.now() / 1000,
        }]);
      } else {
        setMessages((m) => [...m, {
          role: "agent",
          content: "(Agent 返回为空)",
          timestamp: Date.now() / 1000,
        }]);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setMessages((m) => [...m, {
          role: "agent",
          content: `请求失败：${err instanceof Error ? err.message : "未知错误"}`,
          timestamp: Date.now() / 1000,
        }]);
      }
    } finally {
      setIsStreaming(false);
    }
  }, [resume.resumeId, sessionId]);

  // Load historical session from URL param
  useEffect(() => {
    const sessionParam = searchParams.get("session");
    if (sessionParam && sessionParam !== sessionId) {
      fetch(`/api/sessions/${sessionParam}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.messages) {
            setMessages(data.messages.map((m: { role: string; content: string; created_at: string }) => ({
              role: m.role as "user" | "agent",
              content: m.content,
              timestamp: new Date(m.created_at).getTime() / 1000,
            })));
          }
          setSessionId(sessionParam);
          // Restore resume from session if present
          if (data.resume_id && !resume.resumeId) {
            resume.load(data.resume_id).catch(() => {});
          }
        })
        .catch(console.error);
    }
  }, [searchParams, sessionId, resume.resumeId]);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0 border-r">
        <div className="p-3 border-b flex items-center gap-3">
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.md,.txt"
            onChange={handleFileUpload} className="hidden" />
          <button onClick={() => fileInputRef.current?.click()}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition">
            上传简历
          </button>
          <ResumeSelector />
          {resume.resumeId && <span className="text-xs text-green-600">简历已加载 ✓</span>}
          {resume.error && <span className="text-xs text-red-500">{resume.error}</span>}
        </div>
        <ChatPanel onSendMessage={handleSendMessage} isStreaming={isStreaming} messages={messages} />
      </div>
      <div className="w-96 shrink-0">
        <ResumeEditor resumeData={resume.resumeData} isLoading={resume.isLoading} />
      </div>
    </div>
  );
}
