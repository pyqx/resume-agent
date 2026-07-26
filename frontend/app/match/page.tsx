"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import MatchReportView, { type MatchReportData } from "@/components/match/MatchReport";
import { useResumeContext } from "@/contexts/ResumeContext";
import { usePageState } from "@/contexts/PageStateContext";

interface KeywordCoverageData {
  coverage_rate: number | null;
  matched_keywords: string[];
  missing_keywords: string[];
}

interface MatchPersist {
  jdText: string;
  report: MatchReportData | null;
  keywords: KeywordCoverageData | null;
}

/** 从 FastAPI 错误响应中提取中文 detail(本页统一直接 fetch /api 代理)。 */
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

export default function MatchPage() {
  const { state: saved, updateState } = usePageState<MatchPersist>("match");
  const [jdText, setJdText] = useState(saved.jdText ?? "");
  const [report, setReport] = useState<MatchReportData | null>(saved.report ?? null);
  const [keywords, setKeywords] = useState<KeywordCoverageData | null>(saved.keywords ?? null);
  const [isLoading, setIsLoading] = useState(false);
  const [loadPhase, setLoadPhase] = useState<"" | "parsing" | "scoring">("");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const resume = useResumeContext();

  // 同步到跨页面持久化存储
  useEffect(() => { updateState({ jdText }); }, [jdText]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ report }); }, [report]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ keywords }); }, [keywords]); // eslint-disable-line react-hooks/exhaustive-deps

  // 卸载时中止仍在进行的请求
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleMatch = async () => {
    if (!jdText.trim() || isLoading || !resume.resumeId) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsLoading(true);
    setLoadPhase("parsing");
    setError(null);
    setReport(null);
    setKeywords(null);

    // 单次请求内部先解析再逐条评分;解析通常在数秒内完成,之后切换文案。
    const phaseTimer = setTimeout(() => setLoadPhase("scoring"), 8000);

    try {
      // 只调一次 /jd/match:响应自带 jd_requirements(岗位解析结果)
      const res = await fetch("/api/jd/match", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jd_text: jdText, resume_id: resume.resumeId }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      const data = (await res.json()) as MatchReportData;
      setReport(data);

      // 用解析出的关键词请求覆盖率(辅助信息,失败不影响主报告)
      const kws = Object.keys(data.jd_requirements?.keyword_frequency ?? {});
      if (kws.length > 0) {
        try {
          const kres = await fetch("/api/jd/keywords", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ keywords: kws, resume_id: resume.resumeId }),
            signal: controller.signal,
          });
          if (kres.ok) {
            setKeywords((await kres.json()) as KeywordCoverageData);
          }
        } catch {
          /* 覆盖率获取失败时静默,主报告已可用 */
        }
      }
    } catch (err) {
      if (controller.signal.aborted) return; // 页面已卸载/重新发起,不再更新状态
      setError(err instanceof Error ? err.message : "匹配失败,请稍后重试");
    } finally {
      clearTimeout(phaseTimer);
      if (!controller.signal.aborted) {
        setIsLoading(false);
        setLoadPhase("");
      }
    }
  };

  const jd = report?.jd_requirements;
  const hardReqs = jd?.hard_requirements ?? [];
  const niceReqs = jd?.nice_to_have ?? [];
  const keywordFreq = jd?.keyword_frequency ?? {};

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
              disabled={!jdText.trim() || isLoading || !resume.resumeId}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition"
            >
              {isLoading
                ? loadPhase === "parsing" ? "解析中..." : "逐条评分中..."
                : "开始匹配"}
            </button>
          </div>
        </div>
        {!resume.resumeId && (
          <p className="text-sm text-amber-600 mt-2">
            尚未选择简历,请先
            <Link href="/" className="text-primary-600 underline mx-1">去首页上传</Link>
            或选择已有简历后再匹配。
          </p>
        )}
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex flex-col items-center justify-center h-32 gap-2">
          <div className="animate-spin w-6 h-6 border-2 border-primary-600 border-t-transparent rounded-full" />
          <div className="text-sm text-gray-400">
            {loadPhase === "parsing"
              ? "正在解析岗位要求..."
              : "正在对照简历逐条评分...(条目较多时需要一点时间)"}
          </div>
        </div>
      )}

      {/* Results: parsed JD (from report.jd_requirements) + keyword coverage + match report */}
      {!isLoading && report && (
        <div className="flex-1 overflow-y-auto p-4">
          {jd && (
            <>
              <div className="mb-4">
                <h2 className="text-lg font-bold mb-1">岗位解析</h2>
                <div className="flex gap-4 text-sm text-gray-500 mb-3 flex-wrap">
                  {jd.position_title && <span>职位:{jd.position_title}</span>}
                  {jd.company && <span>公司:{jd.company}</span>}
                </div>
              </div>

              {hardReqs.length > 0 && (
                <div className="mb-4">
                  <h3 className="font-bold text-gray-800 mb-2">硬性要求 ({hardReqs.length})</h3>
                  <div className="flex flex-wrap gap-2">
                    {hardReqs.map((r, i) => (
                      <span key={i} className="text-sm bg-red-50 border border-red-100 text-red-700 rounded px-2.5 py-1">
                        {r.criterion}
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
                        {r.criterion}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {Object.keys(keywordFreq).length > 0 && (
                <div className="mb-4">
                  <h3 className="font-bold text-gray-800 mb-2">关键词频率</h3>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(keywordFreq)
                      .sort(([, a], [, b]) => b - a)
                      .map(([k, v]) => (
                        <span key={k} className="text-xs bg-gray-100 rounded-full px-3 py-1">
                          {k} ({v})
                        </span>
                      ))}
                  </div>
                </div>
              )}
            </>
          )}

          {/* 关键词覆盖卡片 */}
          {keywords && (
            <div className="mb-4 bg-white border border-gray-200 rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <h3 className="font-bold text-gray-800">关键词覆盖</h3>
                {keywords.coverage_rate !== null && (
                  <span className="text-sm text-gray-500">
                    覆盖率 {Math.round(keywords.coverage_rate)}%
                  </span>
                )}
              </div>
              {keywords.missing_keywords.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-gray-500 mb-1.5">
                    简历中缺失的关键词(建议在符合事实的前提下自然融入简历):
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {keywords.missing_keywords.map((k) => (
                      <span key={k} className="text-xs bg-red-50 border border-red-200 text-red-700 rounded-full px-2.5 py-1">
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {keywords.matched_keywords.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-1.5">简历已覆盖:</p>
                  <div className="flex flex-wrap gap-2">
                    {keywords.matched_keywords.map((k) => (
                      <span key={k} className="text-xs bg-green-50 border border-green-200 text-green-700 rounded-full px-2.5 py-1">
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {keywords.matched_keywords.length === 0 && keywords.missing_keywords.length === 0 && (
                <p className="text-sm text-gray-400">该 JD 未提取到可分析的关键词。</p>
              )}
            </div>
          )}

          <hr className="my-4 border-gray-200" />

          {/* 匹配报告 */}
          <MatchReportView report={report} />
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !report && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-gray-400 max-w-md px-4">
            <p className="text-lg mb-2">开始分析匹配</p>
            <p className="text-sm">
              粘贴职位描述后点击&quot;开始匹配&quot;,一次请求即可同时获得岗位解析与简历匹配报告。
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
