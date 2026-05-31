"use client";

import { useState } from "react";
import { useResumeContext } from "@/contexts/ResumeContext";

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
}

export default function InterviewPage() {
  const [questions, setQuestions] = useState<InterviewData | null>(null);
  const [intro, setIntro] = useState<IntroData | null>(null);
  const [weaknesses, setWeaknesses] = useState<WeaknessData[]>([]);
  const [activeTab, setActiveTab] = useState<"questions" | "intro" | "weaknesses">("questions");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resume = useResumeContext();

  const loadQuestions = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/interview/questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_id: resume.resumeId || undefined }),
      });
      if (!res.ok) throw new Error(await res.text());
      setQuestions(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
    setLoading(false);
  };

  const loadIntro = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/interview/intro", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_id: resume.resumeId || undefined }),
      });
      if (!res.ok) throw new Error(await res.text());
      setIntro(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
    setLoading(false);
  };

  const loadWeaknesses = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/interview/weaknesses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_id: resume.resumeId || undefined }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setWeaknesses(data.weaknesses || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
    setLoading(false);
  };

  const renderQuestions = (list: Question[] | undefined, color: string) => {
    if (!list || list.length === 0) return null;
    return list.map((q, i) => (
      <div key={i} className="border-l-4 rounded-r-lg p-3 mb-2 bg-white" style={{ borderLeftColor: color }}>
        <p className="text-sm text-gray-800">{q.question}</p>
        <div className="flex gap-2 mt-1">
          {q.technology && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{q.technology}</span>}
          {q.targets_entry && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{q.targets_entry}</span>}
          {q.skill_targeted && <span className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{q.skill_targeted}</span>}
        </div>
      </div>
    ));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold mb-3">面试准备</h1>

        {/* 标签切换 */}
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1 mb-3">
          {([
            ["questions", "面试问题"],
            ["intro", "自我介绍"],
            ["weaknesses", "劣势应对"],
          ] as const).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveTab(key as typeof activeTab)}
              className={`flex-1 py-1.5 text-sm rounded-md transition ${
                activeTab === key ? "bg-white shadow text-gray-900 font-medium" : "text-gray-500"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* 操作按钮 */}
        <div className="flex gap-2">
          {activeTab === "questions" && (
            <button onClick={loadQuestions} disabled={loading}
              className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
              生成面试问题
            </button>
          )}
          {activeTab === "intro" && (
            <button onClick={loadIntro} disabled={loading}
              className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
              生成自我介绍
            </button>
          )}
          {activeTab === "weaknesses" && (
            <button onClick={loadWeaknesses} disabled={loading}
              className="px-4 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50">
              分析简历弱点
            </button>
          )}
        </div>
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {/* 面试问题 */}
        {activeTab === "questions" && (
          <div className="space-y-6">
            {questions ? (
              <>
                {questions.most_likely_questions && questions.most_likely_questions.length > 0 && (
                  <div>
                    <h3 className="font-bold text-red-600 mb-2">最可能被问到的问题</h3>
                    {questions.most_likely_questions.map((q, i) => (
                      <div key={i} className="border-l-4 border-red-500 rounded-r-lg p-3 mb-2 bg-red-50">
                        <p className="text-sm font-medium">{q}</p>
                      </div>
                    ))}
                  </div>
                )}

                <div>
                  <h3 className="font-bold text-blue-700 mb-2">STAR 深挖追问</h3>
                  {renderQuestions(questions.star_deep_dives, "#3b82f6")}
                </div>

                <div>
                  <h3 className="font-bold text-green-700 mb-2">技术深度追问</h3>
                  {renderQuestions(questions.technical_follow_ups, "#22c55e")}
                </div>

                <div>
                  <h3 className="font-bold text-purple-700 mb-2">行为面试题</h3>
                  {renderQuestions(questions.behavioral, "#a855f7")}
                </div>

                <div>
                  <h3 className="font-bold text-amber-700 mb-2">压力测试题</h3>
                  {renderQuestions(questions.pressure_tests, "#f59e0b")}
                </div>

                {questions.company_specific_tips && questions.company_specific_tips.length > 0 && (
                  <div className="bg-blue-50 rounded-lg p-4">
                    <h3 className="font-bold text-blue-700 mb-2">公司针对性建议</h3>
                    <ul className="list-disc list-inside text-sm space-y-1">
                      {questions.company_specific_tips.map((tip, i) => (
                        <li key={i}>{tip}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            ) : (
              <div className="text-center text-gray-400 py-12">
                <p>上传简历后点击"生成面试问题"，获取针对性面试准备。</p>
              </div>
            )}
          </div>
        )}

        {/* 自我介绍 */}
        {activeTab === "intro" && (
          <div className="space-y-4">
            {intro ? (
              <>
                <div className="bg-white border rounded-lg p-4">
                  <h3 className="font-bold text-gray-800 mb-2">
                    短版（约{intro.short_duration_seconds || 60}秒）
                  </h3>
                  <p className="text-sm text-gray-700 whitespace-pre-wrap">{intro.short_version}</p>
                </div>

                <div className="bg-white border rounded-lg p-4">
                  <h3 className="font-bold text-gray-800 mb-2">
                    长版（约{intro.long_duration_seconds || 180}秒）
                  </h3>
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
                <p>上传简历后点击"生成自我介绍"，获取面试话术脚本。</p>
              </div>
            )}
          </div>
        )}

        {/* 劣势应对 */}
        {activeTab === "weaknesses" && (
          <div className="space-y-3">
            {weaknesses.length > 0 ? (
              weaknesses.map((w, i) => {
                const riskLabels: Record<string, string> = { high: "高风险", medium: "中风险", low: "低风险" };
                const riskColors: Record<string, string> = {
                  high: "border-red-400 bg-red-50",
                  medium: "border-amber-400 bg-amber-50",
                  low: "border-blue-400 bg-blue-50",
                };
                const badgeColors: Record<string, string> = {
                  high: "bg-red-200 text-red-800",
                  medium: "bg-amber-200 text-amber-800",
                  low: "bg-blue-200 text-blue-800",
                };
                return (
                  <div key={i} className={`border-l-4 rounded-r-lg p-4 ${riskColors[w.risk_level || "medium"]}`}>
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-semibold text-sm">{w.concern}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded-full ${badgeColors[w.risk_level || "medium"]}`}>
                        {riskLabels[w.risk_level || "medium"]}
                      </span>
                    </div>
                    {w.honest_narrative && (
                      <p className="text-sm text-gray-700 mt-2">
                        <span className="font-medium">应对策略：</span>{w.honest_narrative}
                      </p>
                    )}
                    {w.sample_response && (
                      <div className="mt-2 bg-white rounded p-2 text-sm text-gray-800 italic">
                        "{w.sample_response}"
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="text-center text-gray-400 py-12">
                <p>上传简历后点击"分析简历弱点"，识别面试中可能被追问的问题点。</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
