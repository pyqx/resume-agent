"use client";

import { useState, useCallback } from "react";
import { listResumes } from "@/lib/api";
import { useResumeContext } from "@/contexts/ResumeContext";

const API = "http://127.0.0.1:8000";

export default function ResumeSelector() {
  const [resumes, setResumes] = useState<Array<{ id: string; version: number; updated_at: string; filename: string; name: string }>>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const resume = useResumeContext();

  const fetchList = useCallback(async () => {
    try {
      const data = await listResumes();
      setResumes(data.resumes || []);
    } catch {}
  }, []);

  const handleToggle = async () => {
    if (!isOpen) await fetchList();
    setIsOpen(!isOpen);
  };

  const handleSelect = async (id: string) => {
    setLoading(true);
    try {
      await resume.load(id);
      setIsOpen(false);
    } catch {}
    setLoading(false);
  };

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      const res = await fetch(`${API}/resume/${id}`, { method: "DELETE" });
      if (!res.ok) return;
      // Clear context if current resume was deleted
      if (id === resume.resumeId) {
        resume.clear();
      }
      // Re-fetch to update list
      await fetchList();
    } catch {}
  };

  const label = resume.resumeId ? "切换简历" : "选择已有简历";

  return (
    <div className="relative">
      <button
        onClick={handleToggle}
        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition"
      >
        {label}
        {resume.resumeId && <span className="text-xs text-green-600 ml-1">(已加载)</span>}
      </button>
      {isOpen && (
        <div className="absolute top-full mt-1 left-0 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto">
          {resumes.length === 0 ? (
            <p className="p-3 text-sm text-gray-400">暂无已上传的简历</p>
          ) : (
            resumes.map((r) => (
              <div
                key={r.id}
                className={`flex items-center group ${r.id === resume.resumeId ? "bg-blue-50" : ""}`}
              >
                <button
                  onClick={() => handleSelect(r.id)}
                  disabled={loading}
                  className="flex-1 text-left px-3 py-2 text-sm hover:bg-gray-50 transition truncate min-w-0"
                >
                  <span className="truncate block">
                    {(r.name || r.filename || `版本 ${r.version}`)}
                  </span>
                  <span className="text-xs text-gray-400">
                    {new Date(r.updated_at.endsWith("Z") || r.updated_at.includes("+") ? r.updated_at : r.updated_at + "Z").toLocaleDateString("zh-CN")}
                  </span>
                  {r.id === resume.resumeId && (
                    <span className="text-xs text-green-600 ml-1">当前</span>
                  )}
                </button>
                <button
                  onClick={(e) => handleDelete(e, r.id)}
                  className="px-2 py-2 text-gray-400 hover:text-red-500 hover:bg-gray-100 transition shrink-0"
                  title="删除简历"
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
