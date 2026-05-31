"use client";

interface MatchReportProps {
  report: Record<string, unknown> | null;
  isLoading: boolean;
}

export default function MatchReportView({ report, isLoading }: MatchReportProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">正在分析岗位匹配...</div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center text-gray-400">
          <p className="text-lg mb-2">暂无匹配分析</p>
          <p className="text-sm">粘贴职位描述后点击"开始匹配"，查看您的简历与岗位的匹配情况。</p>
        </div>
      </div>
    );
  }

  const score = (report.overall_score as number) || 0;
  const mustHaveMet = (report.must_have_met as number) || 0;
  const mustHaveTotal = (report.must_have_total as number) || 0;
  const plusMet = (report.plus_met as number) || 0;
  const plusTotal = (report.plus_total as number) || 0;
  const requirements = (report.requirements as Array<Record<string, unknown>>) || [];
  const signals = (report.signals as Array<Record<string, unknown>>) || [];

  const scoreColor =
    score >= 80 ? "text-green-600" : score >= 60 ? "text-amber-600" : "text-red-600";
  const ringColor =
    score >= 80 ? "stroke-green-500" : score >= 60 ? "stroke-amber-500" : "stroke-red-500";

  return (
    <div className="overflow-y-auto h-full p-4">
      {/* 匹配得分 */}
      <div className="text-center mb-6">
        <div className="relative inline-flex items-center justify-center w-28 h-28">
          <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="#e5e7eb" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15.5" fill="none" className={ringColor} strokeWidth="3"
              strokeDasharray={`${score * 0.97} 100`} strokeLinecap="round"
            />
          </svg>
          <span className={`absolute text-2xl font-bold ${scoreColor}`}>{score}%</span>
        </div>
        <p className="text-sm text-gray-500 mt-2">综合匹配度</p>
      </div>

      {/* 摘要 */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-gray-800">{mustHaveMet}/{mustHaveTotal}</div>
          <div className="text-xs text-gray-500">必须项满足</div>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <div className="text-lg font-bold text-gray-800">{plusMet}/{plusTotal}</div>
          <div className="text-xs text-gray-500">加分项满足</div>
        </div>
      </div>

      {/* 逐条匹配详情 */}
      {requirements.length > 0 && (
        <>
          <h3 className="font-bold text-gray-800 mb-3">匹配明细</h3>
          <div className="space-y-2 mb-6">
            {requirements.map((req, i) => {
              const level = req.match_level as string;
              const label =
                level === "full" ? "满足" : level === "partial" ? "部分" : "缺失";
              const badge =
                level === "full"
                  ? "bg-green-100 text-green-700"
                  : level === "partial"
                  ? "bg-amber-100 text-amber-700"
                  : "bg-red-100 text-red-700";
              const icon =
                level === "full" ? "✅" : level === "partial" ? "⚠️" : "❌";

              return (
                <div key={i} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <span className="text-sm">{icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-sm font-medium">{String(req.criterion)}</span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${badge}`}>
                          {label}
                        </span>
                        <span className="text-xs text-gray-400">{String(req.type === "must_have" ? "必须" : "加分")}</span>
                      </div>
                      {(req.evidence as string) && (
                        <p className="text-xs text-gray-500 mt-1">
                          证据：{String(req.evidence)}
                        </p>
                      )}
                      {(req.suggestion as string) && (
                        <p className="text-xs text-primary-600 mt-1">
                          {String(req.suggestion)}
                        </p>
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
              const risk = sig.risk_level as string;
              const riskLabel =
                risk === "caution" ? "注意" : risk === "warning" ? "提醒" : "参考";
              const riskColor =
                risk === "caution"
                  ? "border-red-300 bg-red-50"
                  : risk === "warning"
                  ? "border-amber-300 bg-amber-50"
                  : "border-blue-300 bg-blue-50";

              return (
                <div key={i} className={`border rounded-lg p-3 ${riskColor}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium">&quot;{String(sig.phrase)}&quot;</span>
                    <span className="text-xs text-gray-400">[{riskLabel}]</span>
                  </div>
                  <div className="text-xs text-gray-600">{String(sig.interpretation)}</div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
