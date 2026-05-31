"use client";

import { useState } from "react";
import MatchReportView from "@/components/match/MatchReport";
import { matchJD, parseJD } from "@/lib/api";
import { useResumeContext } from "@/contexts/ResumeContext";

export default function MatchPage() {
  const [jdText, setJdText] = useState("");
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resume = useResumeContext();

  const handleMatch = async () => {
    if (!jdText.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await matchJD(jdText, resume.resumeId || undefined);
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "匹配失败");
    }
    setIsLoading(false);
  };

  const handleParse = async () => {
    if (!jdText.trim()) return;
    setIsLoading(true);
    setError(null);
    try {
      const result = await parseJD(jdText);
      setReport(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "解析失败");
    }
    setIsLoading(false);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold mb-3">JD 匹配分析</h1>
        <div className="flex gap-3">
          <textarea
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="在此粘贴完整的职位描述..."
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-500"
            rows={4}
          />
          <div className="flex flex-col gap-2">
            <button
              onClick={handleParse}
              disabled={!jdText.trim() || isLoading}
              className="px-4 py-2 border border-gray-300 text-sm rounded-lg hover:bg-gray-50 disabled:opacity-50 transition"
            >
              解析JD
            </button>
            <button
              onClick={handleMatch}
              disabled={!jdText.trim() || isLoading}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition"
            >
              开始匹配
            </button>
          </div>
        </div>
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
      </div>

      <div className="flex-1 overflow-hidden">
        <MatchReportView report={report} isLoading={isLoading} />
      </div>
    </div>
  );
}
