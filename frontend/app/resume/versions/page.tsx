"use client";

import { useState, useEffect } from "react";
import Link from "next/link";

interface VersionSummary {
  id: string;
  parent_id: string | null;
  name: string;
  notes: string;
  created_at: string;
  updated_at: string;
  entry_counts: {
    education: number;
    work_experience: number;
    project_experience: number;
    skills: number;
  };
}

export default function VersionsPage() {
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [forkName, setForkName] = useState("");
  const [forking, setForking] = useState(false);

  useEffect(() => {
    fetch("/api/resume/versions")
      .then((r) => r.json())
      .then((data) => {
        setVersions(data.versions || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleFork = async () => {
    if (!forkName.trim() || selected.length === 0) return;
    setForking(true);
    try {
      const res = await fetch("/api/resume/versions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "fork",
          name: forkName,
          parent_id: selected[0],
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setVersions((v) => [
          ...v,
          {
            id: data.version_id,
            parent_id: selected[0],
            name: forkName,
            notes: "",
            created_at: data.created_at,
            updated_at: data.created_at,
            entry_counts: versions.find((x) => x.id === selected[0])?.entry_counts || {
              education: 0, work_experience: 0, project_experience: 0, skills: 0,
            },
          },
        ]);
        setForkName("");
      }
    } catch {}
    setForking(false);
  };

  const handleDelete = async (id: string) => {
    if (!confirm("确认删除此版本？")) return;
    await fetch(`/api/resume/versions/${id}`, { method: "DELETE" });
    setVersions((v) => v.filter((x) => x.id !== id));
  };

  const toggleSelect = (id: string) => {
    setSelected((s) =>
      s.includes(id) ? s.filter((x) => x !== id) : s.length < 2 ? [...s, id] : [s[1], id]
    );
  };

  if (loading) return <div className="p-8 text-gray-400">加载版本列表...</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b flex items-center justify-between">
        <h1 className="text-xl font-bold">简历版本管理</h1>
        <div className="flex gap-2">
          {selected.length === 2 && (
            <Link
              href={`/resume/versions/diff?a=${selected[0]}&b=${selected[1]}`}
              className="px-3 py-1.5 text-sm border border-primary-600 text-primary-600 rounded-lg hover:bg-primary-50"
            >
              对比选中版本
            </Link>
          )}
          {selected.length === 1 && (
            <div className="flex gap-2">
              <input
                type="text"
                value={forkName}
                onChange={(e) => setForkName(e.target.value)}
                placeholder="新版本名称..."
                className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
              <button
                onClick={handleFork}
                disabled={!forkName.trim() || forking}
                className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50"
              >
                分叉
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {versions.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            <p className="text-lg mb-2">暂无版本</p>
            <p className="text-sm">上传简历后将自动创建第一个版本。</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {versions.map((v) => (
              <div
                key={v.id}
                className={`border rounded-lg p-4 cursor-pointer transition ${
                  selected.includes(v.id)
                    ? "border-primary-500 bg-primary-50 ring-1 ring-primary-500"
                    : "border-gray-200 hover:border-gray-300"
                }`}
                onClick={() => toggleSelect(v.id)}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold text-gray-800">{v.name}</h3>
                    {v.notes && (
                      <p className="text-sm text-gray-500 mt-0.5">{v.notes}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-gray-400">
                      {new Date(v.created_at).toLocaleDateString("zh-CN")}
                    </span>
                    <Link
                      href={`/resume/${v.id}`}
                      className="text-xs text-primary-600 hover:text-primary-700"
                      onClick={(e) => e.stopPropagation()}
                    >
                      查看
                    </Link>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(v.id);
                      }}
                      className="text-xs text-red-500 hover:text-red-600"
                    >
                      删除
                    </button>
                  </div>
                </div>
                <div className="flex gap-3 mt-2">
                  <span className="text-xs text-gray-400">
                    {v.entry_counts.work_experience} 段工作 · {v.entry_counts.project_experience} 个项目 · {v.entry_counts.skills} 项技能
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
