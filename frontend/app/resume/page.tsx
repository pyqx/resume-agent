"use client";

import Link from "next/link";
import { useState, useRef } from "react";
import ResumeEditor from "@/components/resume/ResumeEditor";
import ResumeSelector from "@/components/resume/ResumeSelector";
import { useResumeContext } from "@/contexts/ResumeContext";
import { exportMarkdown } from "@/lib/api";

export default function ResumePage() {
  const resume = useResumeContext();
  const [downloading, setDownloading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExportMarkdown = async () => {
    setDownloading(true);
    try {
      const md = await exportMarkdown(resume.resumeId || undefined);
      const blob = new Blob([md], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "resume.md";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert("导出失败：" + (err instanceof Error ? err.message : "未知错误"));
    }
    setDownloading(false);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      await resume.upload(file);
    } catch (err) {
      alert("上传失败：" + (err instanceof Error ? err.message : "未知错误"));
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold">简历编辑器</h1>
          <ResumeSelector />
          <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.md,.txt"
            onChange={handleFileUpload} className="hidden" />
          <button onClick={() => fileInputRef.current?.click()}
            className="text-xs border border-gray-300 px-2 py-0.5 rounded hover:bg-gray-50">
            上传新简历
          </button>
          <Link
            href="/resume/versions"
            className="text-xs text-primary-600 hover:text-primary-700 border border-primary-300 px-2 py-0.5 rounded"
          >
            版本管理
          </Link>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleExportMarkdown}
            disabled={downloading || !resume.resumeData}
            className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition"
          >
            导出 Markdown
          </button>
          <button
            onClick={() => alert("PDF 导出需要服务端渲染支持。")}
            disabled={!resume.resumeData}
            className="px-4 py-2 border border-gray-300 text-sm rounded-lg hover:bg-gray-50 disabled:opacity-50 transition"
          >
            导出 PDF
          </button>
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        <ResumeEditor
          resumeData={resume.resumeData}
          isLoading={resume.isLoading}
        />
      </div>
    </div>
  );
}
