"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useResumeContext } from "@/contexts/ResumeContext";

const NAV_ITEMS = [
  { href: "/", label: "首页", icon: "🏠" },
  { href: "/resume", label: "简历编辑", icon: "📄" },
  { href: "/resume/versions", label: "版本管理", icon: "🔀" },
  { href: "/match", label: "JD匹配", icon: "🎯" },
  { href: "/interview", label: "面试准备", icon: "💬" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const resume = useResumeContext();
  const [sessions, setSessions] = useState<Array<{ id: string; title: string; updated_at: string; message_count: number }>>([]);

  const fetchSessions = async () => {
    try {
      const res = await fetch("/api/sessions/");
      const data = await res.json();
      setSessions(data.sessions || []);
    } catch {}
  };

  useEffect(() => {
    fetchSessions();
  }, [pathname]);

  useEffect(() => {
    const interval = setInterval(fetchSessions, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="w-16 md:w-56 bg-gray-900 text-white flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-700">
        <h1 className="hidden md:block text-lg font-bold">简历助手</h1>
        <h1 className="md:hidden text-lg font-bold text-center">RA</h1>
        {resume.resumeId && (
          <p className="hidden md:block text-xs text-green-400 mt-1 truncate">简历已加载</p>
        )}
      </div>
      <nav className="flex-1 py-2 overflow-y-auto">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center gap-3 px-4 py-3 text-sm transition ${
              pathname === item.href
                ? "bg-primary-600 text-white"
                : "text-gray-300 hover:bg-gray-800"
            }`}
          >
            <span className="text-lg">{item.icon}</span>
            <span className="hidden md:inline">{item.label}</span>
          </Link>
        ))}

        {/* Conversation history — always visible */}
        <hr className="border-gray-700 my-2 mx-4" />
        <div className="px-4 py-2">
          <span className="hidden md:block text-xs text-gray-500 uppercase">对话历史</span>
        </div>
        {sessions.length === 0 ? (
          <p className="px-4 py-2 text-xs text-gray-600 hidden md:block">暂无对话记录</p>
        ) : (
          sessions.slice(0, 20).map((s) => (
            <div key={s.id} className="flex items-center group">
              <Link
                href={`/?session=${s.id}`}
                onClick={() => fetchSessions()}
                className="flex items-center gap-2 px-4 py-2 text-xs text-gray-400 hover:bg-gray-800 transition truncate flex-1"
              >
                <span className="hidden md:inline truncate flex-1">{s.title}</span>
                <span className="hidden md:inline text-gray-600">
                  {s.message_count > 0 && `${s.message_count}`}
                </span>
              </Link>
              <button
                onClick={async (e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  try {
                    await fetch(`/api/sessions/${s.id}`, { method: "DELETE" });
                    fetchSessions();
                  } catch {}
                }}
                className="hidden md:block px-2 py-2 text-gray-600 hover:text-red-400 hover:bg-gray-800 transition shrink-0"
                title="删除对话"
              >
                ×
              </button>
            </div>
          ))
        )}
      </nav>
    </aside>
  );
}
