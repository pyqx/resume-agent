"use client";

import { useState, useEffect, useRef } from "react";
import MatchReportView from "@/components/match/MatchReport";
import { matchJD, parseJD } from "@/lib/api";
import { useResumeContext } from "@/contexts/ResumeContext";
import { usePageState } from "@/contexts/PageStateContext";

interface MatchPersist {
  jdText: string;
  report: Record<string, unknown> | null;
  parsedJD: Record<string, unknown> | null;
}

export default function MatchPage() {
  const { state: saved, updateState } = usePageState<MatchPersist>("match");
  const [jdText, setJdText] = useState(saved.jdText ?? "");
  const [report, setReport] = useState<Record<string, unknown> | null>(saved.report ?? null);
  const [parsedJD, setParsedJD] = useState<Record<string, unknown> | null>(saved.parsedJD ?? null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadPhase, setLoadPhase] = useState<"" | "parsing" | "matching">("");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resume = useResumeContext();

  // Sync to persistent store
  useEffect(() => { updateState({ jdText }); }, [jdText]);
  useEffect(() => { updateState({ report }); }, [report]);
  useEffect(() => { updateState({ parsedJD }); }, [parsedJD]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleMatch = async () => {
    if (!jdText.trim()) return;

    // Check if resume is loaded
    if (!resume.resumeId) {
      setError("请先在首页上传并加载简历");
      return;
    }

    setIsLoading(true);
    setError(null);
    setReport(null);
    setParsedJD(null);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      // Step 1: Parse JD
      setLoadPhase("parsing");
      const parsed = await parseJD(jdText);
      if (controller.signal.aborted) return;
      setParsedJD(parsed);

      // Step 2: Match against resume
      setLoadPhase("matching");
      const matchResult = await matchJD(jdText, resume.resumeId);
      if (controller.signal.aborted) return;
      setReport(matchResult);
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "操作失败");
    }
    setIsLoading(false);
    setLoadPhase("");
  };

  const hardReqs = (parsedJD?.hard_requirements as Array<Record<string, unknown>>) || [];
  const niceReqs = (parsedJD?.nice_to_have as Array<Record<string, unknown>>) || [];
  const keywords = (parsedJD?.keyword_frequency as Record<string, number>) || {};

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
          <div className="flex flex-col justify-end">
            <button
              onClick={handleMatch}
              disabled={!jdText.trim() || isLoading}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition"
            >
              {isLoading ? (loadPhase === "parsing" ? "解析中..." : "匹配中...") : "开始匹配"}
            </button>
          </div>
        </div>
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex flex-col items-center justify-center h-32 gap-2">
          <div className="animate-spin w-6 h-6 border-2 border-primary-600 border-t-transparent rounded-full" />
          <div className="text-sm text-gray-400">
            {loadPhase === "parsing" ? "正在解析岗位要求..." : "正在进行简历匹配分析..."}
          </div>
        </div>
      )}

      {/* Results: parsed JD + match report */}
      {!isLoading && (parsedJD || report) && (
        <div className="flex-1 overflow-y-auto p-4">
          {/* Parse result summary */}
          {parsedJD && (
            <>
              <div className="mb-4">
                <h2 className="text-lg font-bold mb-1">岗位解析</h2>
                <div className="flex gap-4 text-sm text-gray-500 mb-3">
                  {parsedJD.position_title && <span>职位：{String(parsedJD.position_title)}</span>}
                  {parsedJD.company && <span>公司：{String(parsedJD.company)}</span>}
                </div>
              </div>

              {hardReqs.length > 0 && (
                <div className="mb-4">
                  <h3 className="font-bold text-gray-800 mb-2">硬性要求 ({hardReqs.length})</h3>
                  <div className="flex flex-wrap gap-2">
                    {hardReqs.map((r, i) => (
                      <span key={i} className="text-sm bg-red-50 border border-red-100 text-red-700 rounded px-2.5 py-1">
                        {String(r.criterion)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {niceReqs.length > 0 && (
                <div className="mb-4">
                  <h3 className="font-bold text-gray-800 mb-2">加分项 ({niceReqs.length})</h3>
                  <div className="flex flex-wrap gap-2">
                    {niceReqs.map((r, i) => (
                      <span key={i} className="text-sm bg-amber-50 border border-amber-100 text-amber-700 rounded px-2.5 py-1">
                        {String(r.criterion)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {Object.keys(keywords).length > 0 && (
                <div className="mb-4">
                  <h3 className="font-bold text-gray-800 mb-2">关键词频率</h3>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(keywords)
                      .sort(([, a], [, b]) => (b as number) - (a as number))
                      .map(([k, v]) => (
                        <span key={k} className="text-xs bg-gray-100 rounded-full px-3 py-1">
                          {k} ({v})
                        </span>
                      ))}
                  </div>
                </div>
              )}

              <hr className="my-4 border-gray-200" />
            </>
          )}

          {/* Match report */}
          {report && <MatchReportView report={report} isLoading={false} />}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !parsedJD && !report && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-400">
            <p className="text-lg mb-2">开始分析匹配</p>
            <p className="text-sm">粘贴职位描述后点击"开始匹配"，自动解析岗位要求并与您的简历进行匹配分析。</p>
          </div>
        </div>
      )}
    </div>
  );
}
