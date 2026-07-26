"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useResumeContext } from "@/contexts/ResumeContext";
import { usePageState } from "@/contexts/PageStateContext";

interface Question {
  question: string;
  technology?: string;
  targets_entry?: string;
  skill_targeted?: string;
  dimension?: string;
}

interface InterviewData {
  star_deep_dives?: Question[];
  technical_follow_ups?: Question[];
  behavioral?: Question[];
  pressure_tests?: Question[];
  company_specific_tips?: string[];
  most_likely_questions?: string[];
}

interface IntroData {
  short_version?: string;
  short_duration_seconds?: number;
  long_version?: string;
  long_duration_seconds?: number;
  key_messages?: string[];
  delivery_tips?: string[];
}

interface WeaknessData {
  concern?: string;
  risk_level?: string;
  honest_narrative?: string;
  sample_response?: string;
  resume_fix?: string;
}

type TabKey = "questions" | "intro" | "weaknesses";

interface InterviewPersist {
  questions: InterviewData | null;
  intro: IntroData | null;
  weaknesses: WeaknessData[];
  activeTab: TabKey;
  jdText: string;
}

/** risk_level 映射;未知/缺失值兜底,避免 "undefined" 泄漏进 className 与导出文件。 */
const RISK_META: Record<string, { label: string; card: string; badge: string }> = {
  high: { label: "高风险", card: "border-red-400 bg-red-50", badge: "bg-red-200 text-red-800" },
  medium: { label: "中风险", card: "border-amber-400 bg-amber-50", badge: "bg-amber-200 text-amber-800" },
  low: { label: "低风险", card: "border-blue-400 bg-blue-50", badge: "bg-blue-200 text-blue-800" },
};

function riskMeta(level?: string) {
  return RISK_META[level ?? ""] ?? {
    label: "未评级",
    card: "border-gray-300 bg-gray-50",
    badge: "bg-gray-200 text-gray-600",
  };
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

function datestamp(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}${mm}${dd}`;
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // 延迟释放,避免部分浏览器取消尚未开始的下载
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** basename 不含扩展名;导出文件名自动带时间戳,如 面试问题_20260726.md */
function downloadMarkdown(basename: string, content: string) {
  triggerDownload(
    new Blob([content], { type: "text/markdown;charset=utf-8" }),
    `${basename}_${datestamp()}.md`,
  );
}

/** LLM 输出偶尔把字符串列表包成 {question: "..."} 对象;渲染前统一取文本,
 *  同时兼容 sessionStorage 里已持久化的旧数据。 */
function asText(item: unknown): string {
  if (typeof item === "string") return item;
  if (item && typeof item === "object") {
    const obj = item as Record<string, unknown>;
    const text = obj.question ?? obj.tip ?? obj.text;
    if (typeof text === "string") return text;
  }
  return "";
}

function questionsToMarkdown(q: InterviewData): string {
  const lines: string[] = ["# 面试问题\n"];
  if (q.most_likely_questions?.length) {
    lines.push("## 最可能被问到的问题\n", ...q.most_likely_questions.map((s) => `- ${asText(s)}`), "");
  }
  if (q.star_deep_dives?.length) {
    lines.push("## STAR 深挖追问\n", ...q.star_deep_dives.map((s) => `- ${s.question}${s.dimension ? `(${s.dimension})` : ""}`), "");
  }
  if (q.technical_follow_ups?.length) {
    lines.push("## 技术深度追问\n", ...q.technical_follow_ups.map((s) => `- ${s.question}${s.technology ? `(${s.technology})` : ""}`), "");
  }
  if (q.behavioral?.length) {
    lines.push("## 行为面试题\n", ...q.behavioral.map((s) => `- ${s.question}${s.skill_targeted ? `(${s.skill_targeted})` : ""}`), "");
  }
  if (q.pressure_tests?.length) {
    lines.push("## 压力测试题\n", ...q.pressure_tests.map((s) => `- ${s.question}`), "");
  }
  if (q.company_specific_tips?.length) {
    lines.push("## 公司针对性建议\n", ...q.company_specific_tips.map((t) => `- ${asText(t)}`), "");
  }
  return lines.join("\n");
}

function introToMarkdown(i: IntroData): string {
  return [
    "# 自我介绍\n",
    `## 短版(约${i.short_duration_seconds || 60}秒)\n${i.short_version || ""}\n`,
    `## 长版(约${i.long_duration_seconds || 180}秒)\n${i.long_version || ""}\n`,
    i.key_messages?.length ? "## 核心信息点\n" + i.key_messages.map((m) => `- ${m}`).join("\n") : "",
    i.delivery_tips?.length ? "\n## 表达技巧\n" + i.delivery_tips.map((t) => `- ${t}`).join("\n") : "",
  ].filter(Boolean).join("\n");
}

function weaknessesToMarkdown(ws: WeaknessData[]): string {
  const lines = ["# 简历弱点分析与应对\n"];
  ws.forEach((w, i) => {
    lines.push(
      `### ${i + 1}. ${w.concern || ""}(${riskMeta(w.risk_level).label})`,
      w.honest_narrative ? `\n**应对策略:** ${w.honest_narrative}` : "",
      w.sample_response ? `\n**参考话术:** ${w.sample_response}` : "",
      w.resume_fix ? `\n**简历修改建议:** ${w.resume_fix}` : "",
      ""
    );
  });
  return lines.join("\n");
}

export default function InterviewPage() {
  // 持久化状态(跨页面导航保留)
  const { state: saved, updateState } = usePageState<InterviewPersist>("interview");
  const [questions, setQuestions] = useState<InterviewData | null>(saved.questions ?? null);
  const [intro, setIntro] = useState<IntroData | null>(saved.intro ?? null);
  const [weaknesses, setWeaknesses] = useState<WeaknessData[]>(saved.weaknesses ?? []);
  const [activeTab, setActiveTab] = useState<TabKey>(saved.activeTab ?? "questions");
  const [jdText, setJdText] = useState(saved.jdText ?? "");
  // 瞬时状态
  const [jdOpen, setJdOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const resume = useResumeContext();
  const hasResume = !!resume.resumeId;

  // 同步到持久化存储
  useEffect(() => { updateState({ questions }); }, [questions]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ intro }); }, [intro]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ weaknesses }); }, [weaknesses]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ activeTab }); }, [activeTab]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ jdText }); }, [jdText]); // eslint-disable-line react-hooks/exhaustive-deps

  // 卸载时中止请求、清掉提示定时器
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    };
  }, []);

  const showNotice = (msg: string) => {
    setNotice(msg);
    if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current);
    noticeTimerRef.current = setTimeout(() => setNotice(null), 4000);
  };

  const switchTab = (key: TabKey) => {
    setActiveTab(key);
    setError(null); // 切换 Tab 清除错误
  };

  /** 统一 POST;守卫已确保 resume.resumeId 存在,绝不发空 resume_id。 */
  const fetchJSON = async (path: string, extra?: Record<string, unknown>): Promise<unknown> => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_id: resume.resumeId, ...extra }),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(await readErrorDetail(res));
    return res.json();
  };

  const runGenerate = async (task: () => Promise<void>) => {
    if (!hasResume) {
      setError("请先在首页上传或选择简历");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await task();
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      setError(err instanceof Error ? err.message : "生成失败,请稍后重试");
    }
    setLoading(false);
  };

  const loadQuestions = () =>
    runGenerate(async () => {
      const jd = jdText.trim();
      const data = await fetchJSON(
        "/api/interview/questions",
        jd ? { jd_text: jd } : undefined,
      );
      setQuestions(data as InterviewData);
    });

  const loadIntro = () =>
    runGenerate(async () => {
      const data = await fetchJSON("/api/interview/intro");
      setIntro(data as IntroData);
    });

  const loadWeaknesses = () =>
    runGenerate(async () => {
      const data = await fetchJSON("/api/interview/weaknesses");
      setWeaknesses((data as { weaknesses?: WeaknessData[] }).weaknesses || []);
    });

  const copyText = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey((c) => (c === key ? null : c)), 2000);
    } catch {
      showNotice("复制失败,请手动选择文本复制");
    }
  };

  const exportPDF = async (basename: string, content: string) => {
    try {
      const res = await fetch("/api/export/pdf-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: content, filename: `${basename}_${datestamp()}.pdf` }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      triggerDownload(await res.blob(), `${basename}_${datestamp()}.pdf`);
    } catch {
      downloadMarkdown(basename, content);
      showNotice("PDF 生成失败,已改为导出 Markdown");
    }
  };

  /** 空列表时连标题一起隐藏 */
  const renderSection = (
    title: string,
    titleCls: string,
    list: Question[] | undefined,
    color: string,
  ) => {
    if (!list || list.length === 0) return null;
    return (
      <div>
        <h3 className={`font-bold mb-2 ${titleCls}`}>{title}</h3>
        {list.map((q, i) => (
          <div key={i} className="border-l-4 rounded-r-lg p-3 mb-2 bg-white" style={{ borderLeftColor: color }}>
            <p className="text-sm text-gray-800">{q.question}</p>
            {(q.technology || q.targets_entry || q.skill_targeted) && (
              <div className="flex gap-2 mt-1 flex-wrap">
                {q.technology && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{q.technology}</span>}
                {q.targets_entry && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{q.targets_entry}</span>}
                {q.skill_targeted && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{q.skill_targeted}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  const loadingHint: Record<TabKey, string> = {
    questions: "正在根据简历生成面试问题,通常需要 30~60 秒...",
    intro: "正在生成自我介绍脚本,通常需要 30~60 秒...",
    weaknesses: "正在分析简历弱点,通常需要 30~60 秒...",
  };

  const emptyHint: Record<TabKey, string> = {
    questions: "点击“生成面试问题”,获取针对性面试准备。",
    intro: "点击“生成自我介绍”,获取面试话术脚本。",
    weaknesses: "点击“分析简历弱点”,识别面试中可能被追问的问题点。",
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold mb-3">面试准备</h1>

        {/* 标签切换 */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-3" role="tablist" aria-label="面试准备内容">
          {([
            ["questions", "面试问题"],
            ["intro", "自我介绍"],
            ["weaknesses", "劣势应对"],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={activeTab === key}
              onClick={() => switchTab(key)}
              className={`flex-1 py-1.5 text-sm rounded-md transition ${
                activeTab === key ? "bg-white shadow text-gray-900 font-medium" : "text-gray-500"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* 简历守卫提示 */}
        {!hasResume && (
          <p className="text-sm text-amber-600 mb-2">
            尚未选择简历,请先
            <Link href="/" className="text-primary-600 underline mx-1">去首页上传</Link>
            或选择已有简历后再生成。
          </p>
        )}

        {/* JD 输入(可选,折叠面板,仅面试问题使用) */}
        {activeTab === "questions" && (
          <div className="mb-3">
            <button
              onClick={() => setJdOpen((o) => !o)}
              aria-expanded={jdOpen}
              className="text-sm text-gray-600 hover:text-gray-800"
            >
              {jdOpen ? "▾" : "▸"} 针对目标岗位出题(可选)
              {!jdOpen && jdText.trim() && <span className="text-xs text-green-600 ml-1">已填写 JD</span>}
            </button>
            {jdOpen && (
              <textarea
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="粘贴目标岗位 JD,问题将更贴合该岗位;留空则仅基于简历出题。"
                rows={4}
                className="mt-2 w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            )}
          </div>
        )}

        {/* 操作按钮 */}
        <div className="flex gap-2 flex-wrap">
          {activeTab === "questions" && (
            <>
              <button onClick={loadQuestions} disabled={loading || !hasResume}
                className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
                {loading ? "生成中..." : "生成面试问题"}
              </button>
              {questions && (
                <>
                  <button onClick={() => downloadMarkdown("面试问题", questionsToMarkdown(questions))}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                    导出 Markdown
                  </button>
                  <button onClick={() => exportPDF("面试问题", questionsToMarkdown(questions))}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                    导出 PDF
                  </button>
                </>
              )}
            </>
          )}
          {activeTab === "intro" && (
            <>
              <button onClick={loadIntro} disabled={loading || !hasResume}
                className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
                {loading ? "生成中..." : "生成自我介绍"}
              </button>
              {intro && (
                <>
                  <button onClick={() => downloadMarkdown("自我介绍", introToMarkdown(intro))}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                    导出 Markdown
                  </button>
                  <button onClick={() => exportPDF("自我介绍", introToMarkdown(intro))}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                    导出 PDF
                  </button>
                </>
              )}
            </>
          )}
          {activeTab === "weaknesses" && (
            <>
              <button onClick={loadWeaknesses} disabled={loading || !hasResume}
                className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
                {loading ? "分析中..." : "分析简历弱点"}
              </button>
              {weaknesses.length > 0 && (
                <>
                  <button onClick={() => downloadMarkdown("弱点分析", weaknessesToMarkdown(weaknesses))}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                    导出 Markdown
                  </button>
                  <button onClick={() => exportPDF("弱点分析", weaknessesToMarkdown(weaknesses))}
                    className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">
                    导出 PDF
                  </button>
                </>
              )}
            </>
          )}
        </div>
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
        {notice && <p className="text-sm text-amber-600 mt-2">{notice}</p>}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {/* Loading 骨架 */}
        {loading && (
          <div className="space-y-3" aria-live="polite">
            <p className="text-sm text-gray-400">{loadingHint[activeTab]}</p>
            <div className="animate-pulse space-y-3">
              <div className="h-16 bg-gray-100 rounded-lg" />
              <div className="h-16 bg-gray-100 rounded-lg" />
              <div className="h-16 bg-gray-100 rounded-lg" />
            </div>
          </div>
        )}

        {/* 面试问题 */}
        {!loading && activeTab === "questions" && (
          <div className="space-y-6" role="tabpanel">
            {questions ? (
              <>
                {questions.most_likely_questions && questions.most_likely_questions.length > 0 && (
                  <div>
                    <h3 className="font-bold text-red-600 mb-2">最可能被问到的问题</h3>
                    {questions.most_likely_questions.map((q, i) => (
                      <div key={i} className="border-l-4 border-red-500 rounded-r-lg p-3 mb-2 bg-red-50">
                        <p className="text-sm font-medium">{asText(q)}</p>
                      </div>
                    ))}
                  </div>
                )}

                {renderSection("STAR 深挖追问", "text-blue-700", questions.star_deep_dives, "#3b82f6")}
                {renderSection("技术深度追问", "text-green-700", questions.technical_follow_ups, "#22c55e")}
                {renderSection("行为面试题", "text-purple-700", questions.behavioral, "#a855f7")}
                {renderSection("压力测试题", "text-amber-700", questions.pressure_tests, "#f59e0b")}

                {questions.company_specific_tips && questions.company_specific_tips.length > 0 && (
                  <div className="bg-blue-50 rounded-lg p-4">
                    <h3 className="font-bold text-blue-700 mb-2">公司针对性建议</h3>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {questions.company_specific_tips.map((tip, i) => (
                        <li key={i}>{asText(tip)}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-gray-400 py-12">
                <p>{hasResume ? emptyHint.questions : "上传简历后点击“生成面试问题”,获取针对性面试准备。"}</p>
              </div>
            )}
          </div>
        )}

        {/* 自我介绍 */}
        {!loading && activeTab === "intro" && (
          <div className="space-y-4" role="tabpanel">
            {intro ? (
              <>
                <div className="bg-white border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-bold text-gray-800">
                      短版(约{intro.short_duration_seconds || 60}秒)
                    </h3>
                    <button
                      onClick={() => copyText("short", intro.short_version || "")}
                      className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 text-gray-600"
                    >
                      {copiedKey === "short" ? "已复制 ✓" : "复制"}
                    </button>
                  </div>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{intro.short_version}</p>
                </div>

                <div className="bg-white border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-bold text-gray-800">
                      长版(约{intro.long_duration_seconds || 180}秒)
                    </h3>
                    <button
                      onClick={() => copyText("long", intro.long_version || "")}
                      className="text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 text-gray-600"
                    >
                      {copiedKey === "long" ? "已复制 ✓" : "复制"}
                    </button>
                  </div>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{intro.long_version}</p>
                </div>

                {intro.key_messages && intro.key_messages.length > 0 && (
                  <div className="bg-blue-50 rounded-lg p-4">
                    <h3 className="font-bold text-blue-700 mb-2">核心信息点</h3>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {intro.key_messages.map((m, i) => <li key={i}>{m}</li>)}
                    </ul>
                  </div>
                )}

                {intro.delivery_tips && intro.delivery_tips.length > 0 && (
                  <div className="bg-green-50 rounded-lg p-4">
                    <h3 className="font-bold text-green-700 mb-2">表达技巧</h3>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {intro.delivery_tips.map((t, i) => <li key={i}>{t}</li>)}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-gray-400 py-12">
                <p>{hasResume ? emptyHint.intro : "上传简历后点击“生成自我介绍”,获取面试话术脚本。"}</p>
              </div>
            )}
          </div>
        )}

        {/* 劣势应对 */}
        {!loading && activeTab === "weaknesses" && (
          <div className="space-y-3" role="tabpanel">
            {weaknesses.length > 0 ? (
              weaknesses.map((w, i) => {
                const meta = riskMeta(w.risk_level);
                return (
                  <div key={i} className={`border-l-4 rounded-r-lg p-4 ${meta.card}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-semibold text-sm">{w.concern}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded-full ${meta.badge}`}>
                        {meta.label}
                      </span>
                    </div>
                    {w.honest_narrative && (
                      <p className="text-sm text-gray-700 mt-2">
                        <span className="font-medium">应对策略:</span>{w.honest_narrative}
                      </p>
                    )}
                    {w.sample_response && (
                      <div className="mt-2 bg-white rounded p-2 text-sm text-gray-800 italic">
                        &quot;{w.sample_response}&quot;
                      </div>
                    )}
                    {w.resume_fix && (
                      <p className="text-sm text-gray-700 mt-2">
                        <span className="font-medium">简历修改建议:</span>{w.resume_fix}
                      </p>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="text-center text-gray-400 py-12">
                <p>{hasResume ? emptyHint.weaknesses : "上传简历后点击“分析简历弱点”,识别面试中可能被追问的问题点。"}</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
