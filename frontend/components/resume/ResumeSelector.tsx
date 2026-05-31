"use client";

import { useState } from "react";
import { listResumes } from "@/lib/api";
import { useResumeContext } from "@/contexts/ResumeContext";

export default function ResumeSelector() {
  const [resumes, setResumes] = useState<Array<{ id: string; version: number; updated_at: string; filename: string; name: string }>>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState(false);
  const resume = useResumeContext();

  const fetchList = async () => {
    if (fetched) return;
    try {
      const data = await listResumes();
      setResumes(data.resumes || []);
      setFetched(true);
    } catch {}
  };

  const handleToggle = () => {
    if (!isOpen) fetchList();
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

  return (
    <div className="relative">
      <button
        onClick={handleToggle}
        className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition"
      >
        {resume.resumeId ? "切换简历" : "选择已有简历"}
        {resume.resumeId && <span className="text-xs text-green-600 ml-1">(已加载)</span>}
      </button>
      {isOpen && (
        <div className="absolute top-full mt-1 left-0 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto">
          {resumes.length === 0 ? (
            <p className="p-3 text-sm text-gray-400">暂无已上传的简历</p>
          ) : (
            resumes.map((r) => (
              <button
                key={r.id}
                onClick={() => handleSelect(r.id)}
                disabled={loading}
                className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition ${
                  r.id === resume.resumeId ? "bg-blue-50 font-medium" : ""
                }`}
              >
                <span className="truncate">{(r.name || r.filename || `版本 ${r.version}`)}</span>
                <span className="text-xs text-gray-400 ml-2 shrink-0">
                  {new Date(r.updated_at + "Z").toLocaleDateString("zh-CN")}
                </span>
                {r.id === resume.resumeId && (
                  <span className="text-xs text-green-600 ml-2 shrink-0">当前</span>
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
