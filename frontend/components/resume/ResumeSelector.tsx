"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useResumeContext } from "@/contexts/ResumeContext";

interface ResumeListItem {
  id: string;
  version?: number;
  updated_at?: string;
  filename?: string;
  name?: string;
}

/** 从 FastAPI 错误响应中提取中文 detail(本组件统一直接 fetch /api 代理)。 */
async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body: unknown = await res.json();
    const detail = (body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (detail !== undefined && detail !== null) return JSON.stringify(detail);
  } catch {
    /* 响应体不是 JSON */
  }
  return `请求失败(HTTP ${res.status})`;
}

/** 后端时间是 UTC 无时区字符串,解析前补 "Z";空值/异常值兜底。 */
function fmtDate(value?: string): string {
  if (!value || typeof value !== "string") return "";
  let v = value.trim().replace(" ", "T");
  v = v.replace(/(\.\d{3})\d+/, "$1"); // JS Date 只接受毫秒精度
  if (v.includes("T") && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(v)) v += "Z";
  const d = new Date(v);
  return isNaN(d.getTime()) ? value.slice(0, 10) : d.toLocaleDateString("zh-CN");
}

export default function ResumeSelector() {
  const [resumes, setResumes] = useState<ResumeListItem[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const resume = useResumeContext();

  const fetchList = useCallback(async () => {
    try {
      const res = await fetch("/api/resume/");
      if (!res.ok) throw new Error(await readErrorDetail(res));
      const data: unknown = await res.json();
      const list = (data as { resumes?: unknown })?.resumes;
      setResumes(Array.isArray(list) ? (list as ResumeListItem[]) : []);
      setMessage(null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "获取简历列表失败");
    }
  }, []);

  // 点击外部 / Esc 关闭下拉
  useEffect(() => {
    if (!isOpen) return;
    const onMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [isOpen]);

  const handleToggle = async () => {
    if (!isOpen) {
      setMessage(null);
      await fetchList();
    }
    setIsOpen((o) => !o);
  };

  const handleSelect = async (id: string) => {
    setLoading(true);
    try {
      await resume.load(id);
      setIsOpen(false);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "载入简历失败");
    }
    setLoading(false);
  };

  const handleDelete = async (e: React.MouseEvent, r: ResumeListItem) => {
    e.stopPropagation();
    const label = r.name || r.filename || r.id.slice(0, 8);
    if (!window.confirm(`确定删除简历「${label}」?此操作不可撤销。`)) return;
    try {
      const res = await fetch(`/api/resume/${encodeURIComponent(r.id)}`, { method: "DELETE" });
      if (!res.ok) {
        setMessage(await readErrorDetail(res));
        return;
      }
      // 删除的是当前简历时清空上下文
      if (r.id === resume.resumeId) {
        resume.clear();
      }
      await fetchList();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "删除失败,请稍后重试");
    }
  };

  const label = resume.resumeId ? "切换简历" : "选择已有简历";

  return (
    <div className="relative" ref={rootRef}>
      <button
        onClick={handleToggle}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition"
      >
        {label}
        {resume.resumeId && <span className="text-xs text-green-600 ml-1">(已加载)</span>}
      </button>
      {isOpen && (
        <div
          role="listbox"
          aria-label="已上传的简历"
          className="absolute top-full mt-1 left-0 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto"
        >
          {message && (
            <p className="p-3 text-sm text-red-500 border-b border-gray-100">{message}</p>
          )}
          {resumes.length === 0 ? (
            !message && <p className="p-3 text-sm text-gray-400">暂无已上传的简历</p>
          ) : (
            resumes.map((r) => (
              <div
                key={r.id}
                className={`flex items-center group ${r.id === resume.resumeId ? "bg-blue-50" : ""}`}
              >
                <button
                  role="option"
                  aria-selected={r.id === resume.resumeId}
                  onClick={() => handleSelect(r.id)}
                  disabled={loading}
                  className="flex-1 text-left px-3 py-2 text-sm hover:bg-gray-50 transition truncate min-w-0 disabled:opacity-50"
                >
                  <span className="truncate block">
                    {r.name || r.filename || `版本 ${r.version ?? "?"}`}
                  </span>
                  <span className="text-xs text-gray-400">{fmtDate(r.updated_at)}</span>
                  {r.id === resume.resumeId && (
                    <span className="text-xs text-green-600 ml-1">当前</span>
                  )}
                </button>
                <button
                  onClick={(e) => handleDelete(e, r)}
                  className="px-2 py-2 text-gray-400 hover:text-red-500 hover:bg-gray-100 transition shrink-0"
                  title="删除简历"
                  aria-label={`删除简历 ${r.name || r.filename || r.id.slice(0, 8)}`}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
