"use client";

import { useState, useEffect } from "react";

interface EntryDiff {
  diff_type: "added" | "removed" | "modified";
  entry_id: string;
  section: string;
  old_entry?: Record<string, unknown>;
  new_entry?: Record<string, unknown>;
  changed_fields?: string[];
}

interface VersionDiff {
  version_a_id: string;
  version_b_id: string;
  diffs: EntryDiff[];
}

interface Props {
  versionA: string;
  versionB: string;
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

export default function DiffViewer({ versionA, versionB }: Props) {
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!versionA || !versionB) return;
    setLoading(true);
    setError(null);

    fetch(`/api/resume/versions/${versionB}/diff?against=${versionA}`)
      .then((res) => {
        if (!res.ok) throw new Error(res.statusText);
        return res.json();
      })
      .then((data) => {
        setDiff(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err.message);
        setLoading(false);
      });
  }, [versionA, versionB]);

  if (loading) return <div className="text-gray-400 text-sm p-4">正在计算差异...</div>;
  if (error) return <div className="text-red-500 text-sm p-4">错误：{error}</div>;
  if (!diff) return null;

  if (diff.diffs.length === 0) {
    return (
      <div className="text-center text-gray-400 py-8">
        两个版本之间没有差异。
      </div>
    );
  }

  const sectionColors: Record<string, string> = {
    added: "bg-green-50 border-green-300",
    removed: "bg-red-50 border-red-300",
    modified: "bg-amber-50 border-amber-300",
  };

  const sectionIcons: Record<string, string> = {
    added: "+",
    removed: "−",
    modified: "~",
  };

  const grouped = diff.diffs.reduce<Record<string, EntryDiff[]>>((acc, d) => {
    acc[d.section] = acc[d.section] || [];
    acc[d.section].push(d);
    return acc;
  }, {});

  return (
    <div className="p-4 space-y-4">
      <h3 className="font-bold text-gray-800">
        共 {diff.diffs.length} 处变更
      </h3>

      {Object.entries(grouped).map(([section, diffs]) => (
        <div key={section}>
          <h4 className="text-sm font-semibold text-gray-600 uppercase mb-2">
            {SECTION_LABELS[section] || section}
          </h4>
          {diffs.map((d, i) => (
            <div
              key={i}
              className={`border rounded-lg p-3 mb-2 ${sectionColors[d.diff_type]}`}
            >
              <div className="flex items-center gap-2 mb-2">
                <span
                  className={`inline-flex items-center justify-center w-5 h-5 rounded-full text-xs font-bold ${
                    d.diff_type === "added"
                      ? "bg-green-500 text-white"
                      : d.diff_type === "removed"
                      ? "bg-red-500 text-white"
                      : "bg-amber-500 text-white"
                  }`}
                >
                  {sectionIcons[d.diff_type]}
                </span>
                <span className="text-xs font-medium">{TYPE_LABELS[d.diff_type]}</span>
              </div>

              {d.diff_type === "modified" && d.changed_fields && (
                <div className="text-xs text-gray-500 mb-1">
                  变更字段：{d.changed_fields.join("、")}
                </div>
              )}

              {d.old_entry && (
                <div className="text-xs text-red-700 line-through opacity-75">
                  {JSON.stringify(d.old_entry).slice(0, 200)}
                </div>
              )}
              {d.new_entry && (
                <div className="text-xs text-green-700">
                  {JSON.stringify(d.new_entry).slice(0, 200)}
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
