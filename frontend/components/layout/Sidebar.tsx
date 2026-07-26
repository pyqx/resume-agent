"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useResumeContext } from "@/contexts/ResumeContext";
import { usePageState } from "@/contexts/PageStateContext";
import { ApiError, checkHealth, formatRelativeTime, getErrorMessage, sessionsApi } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";

const NAV_ITEMS = [
  { href: "/", label: "首页", icon: "🏠" },
  { href: "/match", label: "JD匹配", icon: "🎯" },
  { href: "/interview", label: "面试准备", icon: "💬" },
  { href: "/github", label: "GitHub 分析", icon: "🐙" },
];

// Matches the backend's default page size for GET /sessions/.
const SESSION_LIMIT = 50;

function SidebarInner() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const resume = useResumeContext();
  const { state: chatState, clearState: clearChatState } =
    usePageState<{ sessionId: string | null }>("chat");
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [connError, setConnError] = useState<string | null>(null);

  const currentSessionId = pathname === "/" ? searchParams.get("session") : null;

  const fetchSessions = useCallback(async () => {
    try {
      const data = await sessionsApi.list(SESSION_LIMIT);
      setSessions(data.sessions ?? []);
      setConnError(null);
    } catch {
      // Distinguish "backend down" from a sessions-specific failure.
      const reachable = await checkHealth();
      setConnError(reachable ? "对话记录加载失败" : "后端未连接");
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions, pathname, currentSessionId]);

  useEffect(() => {
    const interval = setInterval(fetchSessions, 15000);
    return () => clearInterval(interval);
  }, [fetchSessions]);

  const handleNewChat = () => {
    clearChatState();
    router.push("/");
  };

  const handleDelete = async (session: SessionSummary) => {
    if (!window.confirm(`确定删除对话「${session.title || "未命名"}」?此操作不可恢复。`)) {
      return;
    }
    try {
      await sessionsApi.delete(session.id);
    } catch (err) {
      // 404 = already gone on the backend; anything else is worth surfacing.
      if (!(err instanceof ApiError && err.status === 404)) {
        window.alert(getErrorMessage(err, "删除对话失败"));
        return;
      }
    }
    // If the deleted conversation is the one open (in the URL) or the one
    // held in the chat page's persisted state, wipe that state so the chat
    // page starts clean, and drop the ?session= param.
    if (session.id === currentSessionId || session.id === chatState.sessionId) {
      clearChatState();
      if (pathname === "/") {
        router.push("/");
      }
    }
    fetchSessions();
  };

  return (
    <aside className="w-16 md:w-56 bg-gray-900 text-white flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-700">
        <h1 className="hidden md:block text-lg font-bold">简历助手</h1>
        <h1 className="md:hidden text-lg font-bold text-center" title="简历助手">
          RA
        </h1>
        {resume.resumeId && (
          <p className="hidden md:block text-xs text-green-400 mt-1 truncate">
            简历已加载
          </p>
        )}
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              title={item.label}
              aria-label={item.label}
              aria-current={active ? "page" : undefined}
              className={`flex items-center gap-3 px-4 py-3 text-sm transition ${
                active ? "bg-primary-600 text-white" : "text-gray-300 hover:bg-gray-800"
              }`}
            >
              <span className="text-lg" aria-hidden="true">
                {item.icon}
              </span>
              <span className="hidden md:inline">{item.label}</span>
            </Link>
          );
        })}

        {/* 对话历史 */}
        <hr className="border-gray-700 my-2 mx-4" />
        <div className="px-4 py-2 flex items-center justify-between">
          <span className="hidden md:block text-xs text-gray-500 uppercase">
            对话历史
          </span>
          <button
            onClick={handleNewChat}
            title="新建对话"
            aria-label="新建对话"
            className="text-xs text-gray-300 hover:text-white border border-gray-600 hover:border-gray-400 rounded px-2 py-1 transition"
          >
            <span className="md:hidden">＋</span>
            <span className="hidden md:inline">＋ 新建对话</span>
          </button>
        </div>
        {connError ? (
          <p className="px-4 py-2 text-xs text-amber-400" role="status">
            {connError}
          </p>
        ) : sessions.length === 0 ? (
          <p className="px-4 py-2 text-xs text-gray-600 hidden md:block">
            暂无对话记录
          </p>
        ) : (
          sessions.slice(0, SESSION_LIMIT).map((s) => {
            const active = s.id === currentSessionId;
            const title = s.title || "未命名对话";
            return (
              <div
                key={s.id}
                className={`flex items-center group ${
                  active ? "bg-gray-800 border-l-2 border-primary-500" : ""
                }`}
              >
                <Link
                  href={`/?session=${s.id}`}
                  title={title}
                  aria-label={`打开对话:${title}`}
                  aria-current={active ? "true" : undefined}
                  className={`flex items-center gap-2 px-4 py-2 text-xs transition min-w-0 flex-1 ${
                    active ? "text-white" : "text-gray-400 hover:bg-gray-800"
                  }`}
                >
                  <span className="md:hidden" aria-hidden="true">
                    💬
                  </span>
                  <span className="hidden md:block min-w-0 flex-1">
                    <span className="block truncate">{title}</span>
                    <span className="block text-[10px] text-gray-500">
                      {formatRelativeTime(s.updated_at)}
                      {s.message_count > 0 && ` · ${s.message_count} 条`}
                    </span>
                  </span>
                </Link>
                <button
                  onClick={() => handleDelete(s)}
                  title="删除对话"
                  aria-label={`删除对话:${title}`}
                  className="px-1.5 py-1.5 text-gray-500 hover:text-red-400 hover:bg-gray-800 transition shrink-0"
                >
                  ×
                </button>
              </div>
            );
          })
        )}
      </nav>
    </aside>
  );
}

export default function Sidebar() {
  // useSearchParams requires a Suspense boundary during static rendering.
  return (
    <Suspense
      fallback={<aside className="w-16 md:w-56 bg-gray-900 shrink-0" aria-hidden="true" />}
    >
      <SidebarInner />
    </Suspense>
  );
}
