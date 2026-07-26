"use client";

import { useState } from "react";

/** 与后端 /api/jd/match 契约对应的类型定义。 */
export type MatchLevel = "full" | "partial" | "none" | "error";

export interface RequirementItem {
  criterion: string;
  type: "must_have" | "plus" | string;
  match_level: MatchLevel | string;
  evidence?: string;
  suggestion?: string;
}

export interface JDSignalItem {
  phrase: string;
  interpretation: string;
  risk_level: string;
}

export interface JDRequirementsData {
  position_title?: string;
  company?: string;
  hard_requirements?: RequirementItem[];
  nice_to_have?: RequirementItem[];
  soft_signals?: JDSignalItem[];
  keyword_frequency?: Record<string, number>;
}

export interface MatchReportData {
  overall_score: number;
  must_have_met: number;
  must_have_total: number;
  plus_met: number;
  plus_total: number;
  requirements: RequirementItem[];
  signals: JDSignalItem[];
  /** 0-100 的关键词覆盖率 */
  keyword_coverage: number;
  /** 评分失败(match_level === "error")的条目数 */
  scoring_errors: number;
  /** /jd/match 附带的完整岗位解析结果 */
  jd_requirements?: JDRequirementsData;
}

interface MatchReportProps {
  report: MatchReportData;
}

/** match_level 四态映射;未知值落"未知",不再误标为"缺失"。 */
const LEVEL_META: Record<MatchLevel, { label: string; badge: string; icon: string; extra: string }> = {
  full: { label: "满足", badge: "bg-green-100 text-green-700", icon: "✅", extra: "" },
  partial: { label: "部分满足", badge: "bg-amber-100 text-amber-700", icon: "⚠️", extra: "" },
  none: { label: "缺失", badge: "bg-red-100 text-red-700", icon: "❌", extra: "" },
  error: { label: "无法评估", badge: "bg-gray-200 text-gray-500", icon: "❓", extra: "bg-gray-50 opacity-80" },
};

const UNKNOWN_LEVEL = { label: "未知", badge: "bg-gray-100 text-gray-500", icon: "❔", extra: "" };

function levelMeta(level: string) {
  return (LEVEL_META as Record<string, typeof UNKNOWN_LEVEL>)[level] ?? UNKNOWN_LEVEL;
}

const RISK_META: Record<string, { label: string; card: string }> = {
  caution: { label: "注意", card: "border-red-300 bg-red-50" },
  warning: { label: "提醒", card: "border-amber-300 bg-amber-50" },
};

export default function MatchReportView({ report }: MatchReportProps) {
  const [onlyUnmet, setOnlyUnmet] = useState(false);

  const score = Math.min(100, Math.max(0, Number(report.overall_score) || 0));
  const displayScore = Math.round(score);
  const mustHaveMet = report.must_have_met ?? 0;
  const mustHaveTotal = report.must_have_total ?? 0;
  const plusMet = report.plus_met ?? 0;
  const plusTotal = report.plus_total ?? 0;
  const requirements = report.requirements ?? [];
  const signals = report.signals ?? [];
  const keywordCoverage = Math.min(100, Math.max(0, Number(report.keyword_coverage) || 0));
  const scoringErrors = report.scoring_errors ?? 0;

  const shown = onlyUnmet
    ? requirements.filter((r) => r.match_level !== "full")
    : requirements;

  const scoreColor =
    score >= 80 ? "text-green-600" : score >= 60 ? "text-amber-600" : "text-red-600";
  const ringColor =
    score >= 80 ? "stroke-green-500" : score >= 60 ? "stroke-amber-500" : "stroke-red-500";

  return (
    <div>
      {/* 匹配得分 */}
      <div className="text-center mb-6">
        <div className="relative inline-flex items-center justify-center w-28 h-28">
          <svg
            className="w-full h-full -rotate-90"
            viewBox="0 0 36 36"
            role="img"
            aria-label={`综合匹配度 ${displayScore}%`}
          >
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e5e7eb" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15.5" fill="none" className={ringColor} strokeWidth="3"
              pathLength={100}
              strokeDasharray={`${score} 100`} strokeLinecap="round"
            />
          </svg>
          <span className={`absolute text-2xl font-bold ${scoreColor}`}>{displayScore}%</span>
        </div>
        <p className="text-sm text-gray-500 mt-2">综合匹配度</p>
      </div>

      {/* 摘要 */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-gray-800">{mustHaveMet}/{mustHaveTotal}</div>
          <div className="text-xs text-gray-500">必须项满足</div>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-gray-800">{plusMet}/{plusTotal}</div>
          <div className="text-xs text-gray-500">加分项满足</div>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-gray-800">{Math.round(keywordCoverage)}%</div>
          <div className="text-xs text-gray-500">关键词覆盖</div>
        </div>
      </div>

      {/* 评分失败提示 */}
      {scoringErrors > 0 && (
        <div className="mb-4 border border-amber-300 bg-amber-50 rounded-lg px-3 py-2 text-xs text-amber-800">
          有 {scoringErrors} 条要求评估失败(下方标记为&ldquo;无法评估&rdquo;),得分仅供参考,可稍后重新匹配。
        </div>
      )}

      {/* 逐条匹配详情 */}
      {requirements.length > 0 && (
        <>
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-bold text-gray-800">匹配明细</h3>
            <label className="flex items-center gap-1.5 text-xs text-gray-500 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={onlyUnmet}
                onChange={(e) => setOnlyUnmet(e.target.checked)}
                className="accent-blue-600"
              />
              只看未满足
            </label>
          </div>
          <div className="space-y-2 mb-6">
            {shown.length === 0 && (
              <p className="text-sm text-gray-400 py-2">所有要求均已满足 🎉</p>
            )}
            {shown.map((req, i) => {
              const meta = levelMeta(String(req.match_level));
              return (
                <div key={i} className={`border border-gray-200 rounded-lg p-3 ${meta.extra}`}>
                  <div className="flex items-start gap-2">
                    <span className="text-sm" aria-hidden="true">{meta.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1 flex-wrap">
                        <span className="text-sm font-medium">{req.criterion}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${meta.badge}`}>
                          {meta.label}
                        </span>
                        <span className="text-xs text-gray-400">
                          {req.type === "must_have" ? "必须" : "加分"}
                        </span>
                      </div>
                      {req.evidence && (
                        <p className="text-xs text-gray-500 mt-1">证据:{req.evidence}</p>
                      )}
                      {req.suggestion && (
                        <p className="text-xs text-primary-600 mt-1">{req.suggestion}</p>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* JD 隐性信号 */}
      {signals.length > 0 && (
        <>
          <h3 className="font-bold text-gray-800 mb-3">JD 隐性信号解读</h3>
          <div className="space-y-2">
            {signals.map((sig, i) => {
              const risk = RISK_META[sig.risk_level] ?? { label: "参考", card: "border-blue-300 bg-blue-50" };
              return (
                <div key={i} className={`border rounded-lg p-3 ${risk.card}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium">&quot;{sig.phrase}&quot;</span>
                    <span className="text-xs text-gray-400">[{risk.label}]</span>
                  </div>
                  <div className="text-xs text-gray-600">{sig.interpretation}</div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
