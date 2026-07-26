"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import ChatPanel from "@/components/chat/ChatPanel";
import ResumeEditor from "@/components/resume/ResumeEditor";
import ResumeSelector from "@/components/resume/ResumeSelector";
import { useResumeContext } from "@/contexts/ResumeContext";
import { usePageState } from "@/contexts/PageStateContext";
import { getErrorMessage, parseUtc, sessionsApi, streamChat } from "@/lib/api";
import type { ChatEvent, ChatMessage } from "@/lib/types";

interface ChatPersist {
  messages: ChatMessage[];
  sessionId: string | null;
}

const EMPTY_MESSAGES: ChatMessage[] = [];

/** Reasoning-chain event types worth showing in the UI. */
const COLLECTED_EVENTS = new Set([
  "act_start",
  "tool_call",
  "tool_result",
  "checkpoint_restored",
  "plan_error",
]);

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `m-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function nowSeconds(): number {
  return Date.now() / 1000;
}

function ChatHome() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const resume = useResumeContext();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const searchParams = useSearchParams();
  const router = useRouter();

  const { state, updateState, hydrated } = usePageState<ChatPersist>("chat");
  const messages = state.messages ?? EMPTY_MESSAGES;
  const sessionId = state.sessionId ?? null;

  // Refs mirror persisted state so the async SSE loop never reads stale
  // closures (several events can arrive between React re-renders).
  const messagesRef = useRef<ChatMessage[]>(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const sessionIdRef = useRef<string | null>(sessionId);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);
  const resumeRef = useRef(resume);
  useEffect(() => {
    resumeRef.current = resume;
  });

  const setMessages = useCallback(
    (updater: (prev: ChatMessage[]) => ChatMessage[]) => {
      const next = updater(messagesRef.current);
      messagesRef.current = next;
      updateState({ messages: next });
    },
    [updateState],
  );

  const setSessionId = useCallback(
    (sid: string | null) => {
      sessionIdRef.current = sid;
      updateState({ sessionId: sid });
    },
    [updateState],
  );

  // Abort any in-flight SSE stream when leaving the page.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const input = e.target;
    const file = input.files?.[0];
    // Reset immediately — otherwise picking the same file a second time
    // fires no change event.
    input.value = "";
    if (!file) return;
    setBanner(null);
    try {
      const result = await resume.upload(file);
      const notes: string[] = [...(result.metadata?.warnings ?? [])];
      if (result.metadata?.text_truncated) {
        notes.push("简历文本过长,超出部分未参与解析");
      }
      let content = `已解析简历「${file.name}」,可以让我帮您分析和优化具体内容。`;
      if (notes.length > 0) {
        content += `\n\n解析提示:\n${notes.map((n) => `- ${n}`).join("\n")}`;
      }
      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "agent", content, timestamp: nowSeconds() },
      ]);
    } catch (err) {
      setBanner(getErrorMessage(err, `「${file.name}」解析失败`));
    }
  };

  const handleSendMessage = useCallback(
    async (content: string) => {
      if (isStreaming) return;
      const controller = new AbortController();
      abortRef.current = controller;
      setIsStreaming(true);
      setBanner(null);

      setMessages((prev) => [
        ...prev,
        { id: newId(), role: "user", content, timestamp: nowSeconds() },
      ]);

      const agentMsgId = newId();
      const events: ChatEvent[] = [];

      const upsertAgent = (patch: Partial<ChatMessage>) => {
        setMessages((prev) => {
          const idx = prev.findIndex((m) => m.id === agentMsgId);
          if (idx === -1) {
            return [
              ...prev,
              {
                id: agentMsgId,
                role: "agent" as const,
                content: "",
                timestamp: nowSeconds(),
                ...patch,
              },
            ];
          }
          const next = [...prev];
          next[idx] = { ...next[idx], ...patch };
          return next;
        });
      };

      // Cap tool payloads: events are persisted to sessionStorage and only a
      // short snippet is ever rendered.
      const capValue = (value: unknown, max = 500): unknown => {
        if (value == null) return value;
        try {
          const text = typeof value === "string" ? value : JSON.stringify(value);
          return text.length > max ? `${text.slice(0, max)}…` : value;
        } catch {
          return "(无法序列化的内容)";
        }
      };

      const pushEvent = (type: string, data: Record<string, unknown>) => {
        if (type === "tool_result" && data.data != null) {
          data = { ...data, data: capValue(data.data) };
        }
        if (type === "tool_call" && data.params != null) {
          data = { ...data, params: capValue(data.params) };
        }
        events.push({ type, data });
        upsertAgent({ events: [...events] });
      };

      let gotFinal = false;
      let fatalError = false;

      try {
        const stream = streamChat(
          {
            message: content,
            session_id: sessionIdRef.current || undefined,
            resume_id: resumeRef.current.resumeId || undefined,
          },
          controller.signal,
        );

        for await (const evt of stream) {
          const data: Record<string, unknown> =
            evt.data && typeof evt.data === "object" ? evt.data : {};

          if (evt.type === "session_created") {
            const sid = data.session_id;
            if (typeof sid === "string" && sid && sid !== sessionIdRef.current) {
              setSessionId(sid);
              // Keep the URL in sync so the sidebar can highlight the
              // active session and refreshes stay on it.
              router.replace(`/?session=${sid}`, { scroll: false });
            }
          } else if (evt.type === "plan_complete") {
            // Structured fields (action/reasoning/tools) — raw_response is
            // display-only and must NOT be JSON.parsed.
            if (data.action === "tool") {
              pushEvent("plan_complete", {
                action: data.action,
                reasoning: data.reasoning,
                tools: data.tools,
              });
            }
          } else if (evt.type === "error") {
            // Fatal: the backend aborts the stream after this event.
            fatalError = true;
            upsertAgent({
              content: String(data.error || "Agent 处理出错,请稍后重试"),
              isError: true,
              events: events.length > 0 ? [...events] : undefined,
            });
            break;
          } else if (evt.type === "final") {
            gotFinal = true;
            upsertAgent({
              content: String(data.response || "(Agent 返回为空)"),
              timestamp: nowSeconds(),
            });
          } else if (COLLECTED_EVENTS.has(evt.type)) {
            pushEvent(evt.type, data);
          }
          // plan_start / context_assembled / plan_decision / observe_* are
          // progress noise — intentionally not rendered.
        }

        if (!gotFinal && !fatalError && !controller.signal.aborted) {
          upsertAgent({
            content: "连接中断,未收到完整回复,请重试。",
            isError: true,
          });
        }
      } catch (err) {
        if (controller.signal.aborted) {
          upsertAgent({
            content: "(已停止生成)",
            events: events.length > 0 ? [...events] : undefined,
          });
        } else {
          upsertAgent({
            content: `请求失败:${getErrorMessage(err, "未知错误")}`,
            isError: true,
          });
        }
      } finally {
        setIsStreaming(false);
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [isStreaming, router, setMessages, setSessionId],
  );

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // Load a historical session when ?session= differs from current state.
  // Waits for sessionStorage hydration so a refresh restores the local copy
  // (which still has reasoning-chain events) instead of re-fetching.
  const sessionParam = searchParams.get("session");
  useEffect(() => {
    if (!hydrated || !sessionParam) return;
    if (sessionParam === sessionIdRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const data = await sessionsApi.get(sessionParam);
        if (cancelled) return;
        setMessages(() =>
          (data.messages ?? []).map((m) => ({
            id: `h-${m.id}`,
            role: m.role === "agent" ? ("agent" as const) : ("user" as const),
            content: m.content,
            timestamp: parseUtc(m.created_at).getTime() / 1000,
          })),
        );
        setSessionId(data.session_id);
        setBanner(null);
        if (data.resume_id && !resumeRef.current.resumeId) {
          resumeRef.current.load(data.resume_id).catch((err) => {
            if (!cancelled) {
              setBanner(getErrorMessage(err, "会话关联的简历加载失败"));
            }
          });
        }
      } catch (err) {
        if (!cancelled) {
          setBanner(getErrorMessage(err, "加载历史会话失败"));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [hydrated, sessionParam, setMessages, setSessionId]);

  return (
    <div className="flex h-full">
      <div className="flex-1 flex flex-col min-w-0 border-r">
        <div className="p-3 border-b flex items-center gap-3 flex-wrap">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.doc,.md,.markdown,.txt"
            onChange={handleFileUpload}
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={resume.isLoading}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {resume.isLoading ? "解析中..." : "上传简历"}
          </button>
          <ResumeSelector />
          {resume.resumeId && (
            <span className="text-xs text-green-600">简历已加载 ✓</span>
          )}
          {resume.error && (
            <span className="text-xs text-red-500 inline-flex items-center gap-1">
              {resume.error}
              <button
                onClick={resume.clearError}
                aria-label="关闭错误提示"
                className="px-1 text-red-400 hover:text-red-600"
              >
                ×
              </button>
            </span>
          )}
        </div>
        {banner && (
          <div
            role="alert"
            className="px-4 py-2 bg-red-50 border-b border-red-200 text-sm text-red-700 flex items-center justify-between gap-2"
          >
            <span className="min-w-0 break-words">{banner}</span>
            <button
              onClick={() => setBanner(null)}
              aria-label="关闭提示"
              className="shrink-0 text-red-400 hover:text-red-600"
            >
              ×
            </button>
          </div>
        )}
        <ChatPanel
          onSendMessage={handleSendMessage}
          onStop={handleStop}
          isStreaming={isStreaming}
          messages={messages}
        />
      </div>
      <div className="w-96 shrink-0 hidden lg:block">
        <ResumeEditor resumeData={resume.resumeData} isLoading={resume.isLoading} />
      </div>
    </div>
  );
}

export default function Home() {
  // useSearchParams must live under a Suspense boundary (Next.js build
  // requirement for static rendering).
  return (
    <Suspense
      fallback={<div className="p-6 text-sm text-gray-400">加载中...</div>}
    >
      <ChatHome />
    </Suspense>
  );
}
