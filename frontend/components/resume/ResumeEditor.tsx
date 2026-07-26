"use client";

import { useEffect, useRef, useState } from "react";
import SectionCard from "./SectionCard";
import DiffViewer from "./DiffViewer";
import { useResumeContext } from "@/contexts/ResumeContext";
import type { Resume } from "@/lib/types";

interface ResumeEditorProps {
  resumeData: Resume | null;
  isLoading: boolean;
}

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
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** dates_approximate=true 表示原文只写了年份,只展示年并加"(约)"。 */
function fmtDate(v: string | null | undefined, approx: boolean): string {
  if (!v) return "";
  return approx ? v.slice(0, 4) : v.slice(0, 7);
}

function dateRange(e: {
  start_date: string | null;
  end_date: string | null;
  dates_approximate: boolean;
  is_current?: boolean;
}): string {
  const approx = e.dates_approximate === true;
  const start = fmtDate(e.start_date, approx);
  const end = e.is_current ? "至今" : fmtDate(e.end_date, approx);
  if (!start && !end) return "";
  return `${start || "—"} ~ ${end || "—"}${approx ? "(约)" : ""}`;
}

const splitLines = (s: string) => s.split("\n").map((t) => t.trim()).filter(Boolean);
const splitCsv = (s: string) => s.split(/[,,、]/).map((t) => t.trim()).filter(Boolean);

export default function ResumeEditor({ resumeData, isLoading }: ResumeEditorProps) {
  const { resumeId, updateEntry, deleteEntry } = useResumeContext();
  const [showHistory, setShowHistory] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ text: string; isError: boolean } | null>(null);
  const msgTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    return () => {
      if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
    };
  }, []);

  const flash = (text: string, isError = false) => {
    setMsg({ text, isError });
    if (msgTimerRef.current) clearTimeout(msgTimerRef.current);
    msgTimerRef.current = setTimeout(() => setMsg(null), 4000);
  };

  const saveEntry = async (entryId: string, updates: Record<string, unknown>) => {
    try {
      await updateEntry(entryId, updates);
      flash("已保存修改");
    } catch (err) {
      flash(err instanceof Error ? err.message : "保存失败,请稍后重试", true);
    }
  };

  const removeEntry = async (entryId: string, label: string) => {
    if (!window.confirm(`确定删除「${label}」?此操作不可撤销。`)) return;
    try {
      await deleteEntry(entryId);
      flash("已删除条目");
    } catch (err) {
      flash(err instanceof Error ? err.message : "删除失败,请稍后重试", true);
    }
  };

  const fetchMarkdownText = async (): Promise<string> => {
    const res = await fetch("/api/export/markdown", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_id: resumeId }),
    });
    if (!res.ok) throw new Error(await readErrorDetail(res));
    return res.text();
  };

  const exportMarkdown = async () => {
    if (busy) return;
    setBusy("md");
    try {
      const text = await fetchMarkdownText();
      triggerDownload(
        new Blob([text], { type: "text/markdown;charset=utf-8" }),
        `简历_${datestamp()}.md`,
      );
    } catch (err) {
      flash(err instanceof Error ? err.message : "导出失败,请稍后重试", true);
    }
    setBusy(null);
  };

  const exportPDF = async () => {
    if (busy) return;
    setBusy("pdf");
    try {
      const text = await fetchMarkdownText();
      const res = await fetch("/api/export/pdf-text", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, filename: `简历_${datestamp()}.pdf` }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      triggerDownload(await res.blob(), `简历_${datestamp()}.pdf`);
    } catch (err) {
      flash(err instanceof Error ? err.message : "PDF 导出失败,请稍后重试", true);
    }
    setBusy(null);
  };

  const saveVersion = async () => {
    if (busy) return;
    const name = window.prompt("版本名称(例如:投递后端岗 v1)");
    if (name === null) return;
    const trimmed = name.trim();
    if (!trimmed) {
      flash("版本名称不能为空", true);
      return;
    }
    setBusy("version");
    try {
      const res = await fetch("/api/resume/versions/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: trimmed, notes: "", resume_id: resumeId }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      flash(`已保存版本「${trimmed}」`);
    } catch (err) {
      flash(err instanceof Error ? err.message : "保存版本失败,请稍后重试", true);
    }
    setBusy(null);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-400">加载中...</div>
      </div>
    );
  }

  if (!resumeData) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center text-gray-400">
          <p className="text-lg mb-2">暂无简历</p>
          <p className="text-sm">上传 PDF、DOCX 或 Markdown 文件开始使用。</p>
        </div>
      </div>
    );
  }

  const pi = resumeData.personal_info;
  const education = resumeData.education ?? [];
  const work = resumeData.work_experience ?? [];
  const projects = resumeData.project_experience ?? [];
  const skills = resumeData.skills ?? [];

  return (
    <div className="flex flex-col h-full">
      {/* 工具栏 */}
      <div className="flex items-center gap-2 flex-wrap px-4 py-3 border-b">
        <span className="text-sm font-semibold text-gray-800 mr-auto">简历面板</span>
        <button
          onClick={exportMarkdown}
          disabled={!resumeId || busy !== null}
          className="px-2.5 py-1 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition"
        >
          {busy === "md" ? "导出中..." : "导出 Markdown"}
        </button>
        <button
          onClick={exportPDF}
          disabled={!resumeId || busy !== null}
          className="px-2.5 py-1 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition"
        >
          {busy === "pdf" ? "导出中..." : "导出 PDF"}
        </button>
        <button
          onClick={saveVersion}
          disabled={!resumeId || busy !== null}
          className="px-2.5 py-1 text-xs border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition"
        >
          {busy === "version" ? "保存中..." : "保存版本"}
        </button>
        <button
          onClick={() => setShowHistory((v) => !v)}
          aria-expanded={showHistory}
          className={`px-2.5 py-1 text-xs border rounded-lg transition ${
            showHistory
              ? "border-primary-600 text-primary-600 bg-primary-50"
              : "border-gray-300 hover:bg-gray-50"
          }`}
        >
          版本历史
        </button>
      </div>

      {msg && (
        <div
          className={`px-4 py-2 text-xs border-b ${
            msg.isError ? "bg-red-50 text-red-600" : "bg-green-50 text-green-700"
          }`}
        >
          {msg.text}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {showHistory && (
          <div className="border-b bg-gray-50">
            <DiffViewer />
          </div>
        )}

        <div className="p-4">
          {/* 个人信息(无条目 id,仅展示) */}
          <SectionCard
            title="个人信息"
            fields={[
              { key: "full_name", label: "姓名", value: String(pi?.full_name || "") },
              { key: "email", label: "邮箱", value: String(pi?.email || "") },
              { key: "phone", label: "电话", value: String(pi?.phone || "") },
              { key: "location", label: "所在地", value: String(pi?.location || "") },
              ...(pi?.github ? [{ key: "github", label: "GitHub", value: String(pi.github), link: true }] : []),
              ...(pi?.linkedin ? [{ key: "linkedin", label: "LinkedIn", value: String(pi.linkedin), link: true }] : []),
              ...(pi?.website ? [{ key: "website", label: "个人网站", value: String(pi.website), link: true }] : []),
              { key: "summary", label: "个人概述", value: String(pi?.summary || "") },
            ]}
          />

          {/* 教育背景 */}
          <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">教育背景</h2>
          {education.map((edu) => (
            <SectionCard
              key={edu.id}
              title={String(edu.school || "教育经历")}
              subtitle={dateRange(edu)}
              fields={[
                { key: "school", label: "学校", value: String(edu.school || "") },
                { key: "degree", label: "学位", value: String(edu.degree || "") },
                { key: "major", label: "专业", value: String(edu.major || "") },
                { key: "gpa", label: "GPA", value: String(edu.gpa || "") },
              ]}
              confidence={edu.confidence}
              onSave={(v) =>
                saveEntry(edu.id, {
                  school: v.school ?? "",
                  degree: v.degree ?? "",
                  major: v.major ?? "",
                  gpa: v.gpa ?? "",
                })
              }
              onDelete={() => removeEntry(edu.id, edu.school || "教育经历")}
            />
          ))}
          {education.length === 0 && <p className="text-sm text-gray-400">暂无教育经历</p>}

          {/* 工作经历 */}
          <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">工作经历</h2>
          {work.map((w) => (
            <SectionCard
              key={w.id}
              title={`${w.position || "职位"} @ ${w.company || "公司"}`}
              subtitle={dateRange(w)}
              fields={[
                { key: "company", label: "公司", value: String(w.company || "") },
                { key: "position", label: "职位", value: String(w.position || "") },
                { key: "location", label: "地点", value: String(w.location || "") },
                {
                  key: "bullets",
                  label: "关键成果",
                  value: Array.isArray(w.bullets) ? w.bullets.join("\n") : "",
                  multiline: true,
                },
              ]}
              confidence={w.confidence}
              onSave={(v) =>
                saveEntry(w.id, {
                  company: v.company ?? "",
                  position: v.position ?? "",
                  location: v.location ?? "",
                  bullets: splitLines(v.bullets ?? ""),
                })
              }
              onDelete={() =>
                removeEntry(w.id, `${w.position || "职位"} @ ${w.company || "公司"}`)
              }
            />
          ))}
          {work.length === 0 && <p className="text-sm text-gray-400">暂无工作经历</p>}

          {/* 项目经历 */}
          <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">项目经历</h2>
          {projects.map((p) => (
            <SectionCard
              key={p.id}
              title={`${p.name || "项目"}${p.is_planned ? "(规划中)" : ""}`}
              subtitle={dateRange(p)}
              fields={[
                { key: "name", label: "项目名称", value: String(p.name || "") },
                { key: "role", label: "角色", value: String(p.role || "") },
                {
                  key: "technologies",
                  label: "技术栈",
                  value: Array.isArray(p.technologies) ? p.technologies.join(", ") : "",
                },
                { key: "url", label: "链接", value: String(p.url || ""), link: true },
                {
                  key: "bullets",
                  label: "项目亮点",
                  value: Array.isArray(p.bullets) ? p.bullets.join("\n") : "",
                  multiline: true,
                },
              ]}
              confidence={p.confidence}
              onSave={(v) =>
                saveEntry(p.id, {
                  name: v.name ?? "",
                  role: v.role ?? "",
                  url: v.url ?? "",
                  technologies: splitCsv(v.technologies ?? ""),
                  bullets: splitLines(v.bullets ?? ""),
                })
              }
              onDelete={() => removeEntry(p.id, p.name || "项目经历")}
            />
          ))}
          {projects.length === 0 && <p className="text-sm text-gray-400">暂无项目经历</p>}

          {/* 技能 */}
          <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">技能</h2>
          <div className="flex flex-wrap gap-2">
            {skills.map((s) => {
              const years =
                typeof s.years === "number" && s.years > 0
                  ? Number.isInteger(s.years)
                    ? `${s.years} 年`
                    : `${s.years.toFixed(1)} 年`
                  : "";
              const extra = [s.level, years].filter(Boolean).join(" · ");
              return (
                <span
                  key={s.id}
                  className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm"
                >
                  {String(s.name || "")}
                  {extra && <span className="text-xs text-blue-500 ml-1">({extra})</span>}
                </span>
              );
            })}
          </div>
          {skills.length === 0 && <p className="text-sm text-gray-400">暂无技能标签</p>}
        </div>
      </div>
    </div>
  );
}
