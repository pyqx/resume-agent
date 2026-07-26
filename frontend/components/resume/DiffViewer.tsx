"use client";

import { useCallback, useEffect, useState } from "react";

interface VersionSummary {
  id: string;
  parent_id: string | null;
  name: string;
  notes: string;
  created_at: string;
  updated_at: string;
  entry_counts?: Record<string, number>;
}

interface EntryDiff {
  diff_type: "added" | "removed" | "modified";
  entry_id: string;
  section: string;
  old_entry?: Record<string, unknown> | null;
  new_entry?: Record<string, unknown> | null;
  changed_fields?: string[];
}

interface VersionDiffData {
  version_a_id: string;
  version_b_id: string;
  diffs: EntryDiff[];
}

const TYPE_LABELS: Record<string, string> = {
  added: "新增",
  removed: "删除",
  modified: "修改",
};

const SECTION_LABELS: Record<string, string> = {
  education: "教育背景",
  work_experience: "工作经历",
  project_experience: "项目经历",
  skills: "技能",
};

const FIELD_LABELS: Record<string, string> = {
  school: "学校",
  degree: "学位",
  major: "专业",
  level: "级别",
  gpa: "GPA",
  company: "公司",
  position: "职位",
  location: "地点",
  bullets: "关键成果",
  description: "描述",
  name: "名称",
  role: "角色",
  url: "链接",
  technologies: "技术栈",
  start_date: "开始时间",
  end_date: "结束时间",
  is_current: "是否至今",
  is_planned: "是否规划中",
  dates_approximate: "日期为约数",
  category: "分类",
  years: "年限",
  confidence: "置信度",
};

/** 展示这些字段作为新增/删除条目的摘要(按此顺序)。 */
const SUMMARY_FIELDS = [
  "school", "degree", "major", "gpa",
  "company", "position",
  "name", "role", "technologies",
  "level", "years",
  "start_date", "end_date",
  "bullets", "description",
];

/** 从 FastAPI 错误响应中提取中文 detail(本组件统一直接 fetch /api 代理)。 */
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

/** 后端时间为 UTC 无时区字符串,解析前补 "Z";失败时回退原始串。 */
function fmtTime(value?: string): string {
  if (!value || typeof value !== "string") return "";
  let v = value.trim().replace(" ", "T");
  v = v.replace(/(\.\d{3})\d+/, "$1");
  if (v.includes("T") && !/(?:Z|[+-]\d{2}:?\d{2})$/i.test(v)) v += "Z";
  const d = new Date(v);
  if (isNaN(d.getTime())) return value.slice(0, 16);
  return `${d.toLocaleDateString("zh-CN")} ${d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
}

/** 字段值的可读渲染(数组逐项、布尔转是/否),不再 JSON.stringify 截断。 */
function fmtVal(v: unknown): string {
  if (v === null || v === undefined || v === "") return "(空)";
  if (Array.isArray(v)) return v.map((x) => String(x)).join(";") || "(空)";
  if (typeof v === "boolean") return v ? "是" : "否";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function entryTitle(section: string, entry?: Record<string, unknown> | null): string {
  if (!entry) return "";
  if (section === "education") return String(entry.school || entry.degree || "教育经历");
  if (section === "work_experience") {
    const t = [entry.position, entry.company].filter(Boolean).join(" @ ");
    return t || "工作经历";
  }
  if (section === "project_experience") return String(entry.name || "项目经历");
  if (section === "skills") return String(entry.name || "技能");
  return String(entry.id || "条目");
}

function versionLabel(v: VersionSummary): string {
  const name = v.name || v.id.slice(0, 8);
  const time = fmtTime(v.created_at);
  return time ? `${name}(${time})` : name;
}

export default function DiffViewer() {
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [versionsLoaded, setVersionsLoaded] = useState(false);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [selA, setSelA] = useState("");
  const [selB, setSelB] = useState("");
  const [diff, setDiff] = useState<VersionDiffData | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  const loadVersions = useCallback(async () => {
    setVersionsError(null);
    try {
      const res = await fetch("/api/resume/versions/");
      if (!res.ok) throw new Error(await readErrorDetail(res));
      const data: unknown = await res.json();
      const list = (data as { versions?: unknown })?.versions;
      const arr: VersionSummary[] = Array.isArray(list) ? (list as VersionSummary[]) : [];
      setVersions(arr);
      // 列表按创建时间倒序:默认 B=最新、A=次新
      if (arr.length >= 2) {
        setSelB((b) => (b && arr.some((v) => v.id === b) ? b : arr[0].id));
        setSelA((a) => (a && arr.some((v) => v.id === a) ? a : arr[1].id));
      }
    } catch (err) {
      setVersionsError(err instanceof Error ? err.message : "获取版本列表失败");
    }
    setVersionsLoaded(true);
  }, []);

  useEffect(() => {
    loadVersions();
  }, [loadVersions]);

  // 两个版本都选定且不同时自动请求 diff
  useEffect(() => {
    if (!selA || !selB || selA === selB) {
      setDiff(null);
      return;
    }
    let cancelled = false;
    (async () => {
      setDiffLoading(true);
      setDiffError(null);
      try {
        const res = await fetch(
          `/api/resume/versions/${encodeURIComponent(selB)}/diff?against=${encodeURIComponent(selA)}`,
        );
        if (!res.ok) throw new Error(await readErrorDetail(res));
        const data = (await res.json()) as VersionDiffData;
        if (!cancelled) setDiff(data);
      } catch (err) {
        if (!cancelled) {
          setDiff(null);
          setDiffError(err instanceof Error ? err.message : "计算差异失败");
        }
      }
      if (!cancelled) setDiffLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [selA, selB]);

  const cardColors: Record<string, string> = {
    added: "bg-green-50 border-green-300",
    removed: "bg-red-50 border-red-300",
    modified: "bg-amber-50 border-amber-300",
  };

  const badgeColors: Record<string, string> = {
    added: "bg-green-500 text-white",
    removed: "bg-red-500 text-white",
    modified: "bg-amber-500 text-white",
  };

  const typeIcons: Record<string, string> = {
    added: "+",
    removed: "−",
    modified: "~",
  };

  const renderEntrySummary = (entry: Record<string, unknown>, cls: string) => {
    const rows = SUMMARY_FIELDS.filter((f) => {
      const v = entry[f];
      return v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0);
    }).slice(0, 6);
    if (rows.length === 0) return null;
    return (
      <div className={`text-xs space-y-0.5 ${cls}`}>
        {rows.map((f) => (
          <div key={f}>
            <span className="text-gray-500">{FIELD_LABELS[f] || f}:</span>
            <span className="break-words">{fmtVal(entry[f])}</span>
          </div>
        ))}
      </div>
    );
  };

  const grouped = (diff?.diffs ?? []).reduce<Record<string, EntryDiff[]>>((acc, d) => {
    (acc[d.section] = acc[d.section] || []).push(d);
    return acc;
  }, {});

  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <h3 className="font-bold text-gray-800 text-sm">版本历史对比</h3>
        <button
          onClick={loadVersions}
          className="ml-auto text-xs text-primary-600 hover:text-primary-700"
        >
          刷新
        </button>
      </div>

      {versionsError && <p className="text-sm text-red-500">{versionsError}</p>}

      {versionsLoaded && !versionsError && versions.length === 0 && (
        <div className="text-sm text-gray-400 bg-white border border-dashed border-gray-300 rounded-lg p-4 text-center">
          还没有保存过版本。
          <br />
          在简历面板点「保存版本」创建第一个版本,之后即可在这里对比不同版本的差异。
        </div>
      )}

      {versions.length > 0 && (
        <>
          <div className="grid grid-cols-1 gap-2">
            <label className="text-xs text-gray-500">
              基准版本(旧,A)
              <select
                value={selA}
                onChange={(e) => setSelA(e.target.value)}
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">请选择...</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>{versionLabel(v)}</option>
                ))}
              </select>
            </label>
            <label className="text-xs text-gray-500">
              对比版本(新,B)
              <select
                value={selB}
                onChange={(e) => setSelB(e.target.value)}
                className="mt-1 w-full border border-gray-300 rounded px-2 py-1.5 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
              >
                <option value="">请选择...</option>
                {versions.map((v) => (
                  <option key={v.id} value={v.id}>{versionLabel(v)}</option>
                ))}
              </select>
            </label>
          </div>

          {versions.length === 1 && (
            <p className="text-xs text-gray-400">
              目前只有一个版本,再保存一个版本后即可对比差异。
            </p>
          )}

          {selA && selB && selA === selB && (
            <p className="text-xs text-amber-600">请选择两个不同的版本进行对比。</p>
          )}

          {diffLoading && <p className="text-sm text-gray-400">正在计算差异...</p>}
          {diffError && <p className="text-sm text-red-500">{diffError}</p>}

          {!diffLoading && !diffError && diff && diff.diffs.length === 0 && (
            <p className="text-sm text-gray-400 text-center py-4">两个版本之间没有差异。</p>
          )}

          {!diffLoading && !diffError && diff && diff.diffs.length > 0 && (
            <div className="space-y-3">
              <p className="text-xs text-gray-500">共 {diff.diffs.length} 处变更</p>
              {Object.entries(grouped).map(([section, diffs]) => (
                <div key={section}>
                  <h4 className="text-xs font-semibold text-gray-600 mb-1.5">
                    {SECTION_LABELS[section] || section}
                  </h4>
                  {diffs.map((d, i) => (
                    <div
                      key={`${d.entry_id}-${i}`}
                      className={`border rounded-lg p-3 mb-2 ${cardColors[d.diff_type] || "bg-gray-50 border-gray-300"}`}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <span
                          className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold ${badgeColors[d.diff_type] || "bg-gray-400 text-white"}`}
                          aria-hidden="true"
                        >
                          {typeIcons[d.diff_type] || "?"}
                        </span>
                        <span className="text-xs font-medium">
                          {TYPE_LABELS[d.diff_type] || d.diff_type}
                        </span>
                        <span className="text-xs text-gray-600 truncate">
                          {entryTitle(d.section, d.new_entry || d.old_entry)}
                        </span>
                      </div>

                      {/* 修改:逐字段展示 旧值 → 新值 */}
                      {d.diff_type === "modified" && (d.changed_fields?.length ?? 0) > 0 && (
                        <div className="space-y-1">
                          {(d.changed_fields ?? []).map((f) => (
                            <div key={f} className="text-xs">
                              <span className="font-medium text-gray-700">
                                {FIELD_LABELS[f] || f}:
                              </span>{" "}
                              <span className="text-red-700 line-through break-words">
                                {fmtVal(d.old_entry?.[f])}
                              </span>
                              <span className="mx-1 text-gray-400" aria-hidden="true">→</span>
                              <span className="text-green-700 break-words">
                                {fmtVal(d.new_entry?.[f])}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {d.diff_type === "added" && d.new_entry &&
                        renderEntrySummary(d.new_entry, "text-green-800")}
                      {d.diff_type === "removed" && d.old_entry &&
                        renderEntrySummary(d.old_entry, "text-red-800 line-through opacity-75")}
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
