"use client";

import { useId, useState } from "react";

export interface SectionField {
  key: string;
  label: string;
  value: string;
  /** 多行字段(如 bullets):展示为逐条列表,编辑用 textarea(每行一条) */
  multiline?: boolean;
  /** 展示态渲染为超链接 */
  link?: boolean;
  /** false 时仅展示、不进入编辑表单(默认可编辑) */
  editable?: boolean;
}

interface SectionCardProps {
  title: string;
  /** 标题下的辅助信息,如起止日期 */
  subtitle?: string;
  fields: SectionField[];
  confidence?: number;
  /** 提供时显示"编辑"按钮;保存时一次性回传全部编辑值 */
  onSave?: (values: Record<string, string>) => void;
  /** 提供时显示"删除"按钮(确认逻辑由调用方处理) */
  onDelete?: () => void;
}

function hrefOf(value: string): string {
  return /^https?:\/\//i.test(value) ? value : `https://${value}`;
}

export default function SectionCard({
  title,
  subtitle,
  fields,
  confidence,
  onSave,
  onDelete,
}: SectionCardProps) {
  const uid = useId();
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState<Record<string, string>>({});

  const editableFields = fields.filter((f) => f.editable !== false);

  const handleEdit = () => {
    setEditValues(Object.fromEntries(editableFields.map((f) => [f.key, f.value])));
    setEditing(true);
  };

  const handleSave = () => {
    onSave?.(editValues);
    setEditing(false);
  };

  const confidenceColor =
    confidence !== undefined
      ? confidence >= 0.8
        ? "bg-green-100 text-green-700"
        : confidence >= 0.5
        ? "bg-amber-100 text-amber-700"
        : "bg-red-100 text-red-700"
      : "";

  return (
    <div className="border border-gray-200 rounded-lg p-4 mb-3 hover:border-gray-300 transition">
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-gray-800 truncate">{title}</h3>
          {subtitle && <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {confidence !== undefined && (
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${confidenceColor}`}
              title="解析置信度"
            >
              {Math.round(confidence * 100)}%
            </span>
          )}
          {onSave && !editing && (
            <button
              onClick={handleEdit}
              className="text-xs text-primary-600 hover:text-primary-700"
            >
              编辑
            </button>
          )}
          {onDelete && !editing && (
            <button
              onClick={onDelete}
              className="text-xs text-red-500 hover:text-red-600"
            >
              删除
            </button>
          )}
        </div>
      </div>

      {editing ? (
        <div className="space-y-2">
          {editableFields.map((field) => {
            const inputId = `${uid}-${field.key}`;
            return (
              <div key={field.key}>
                <label htmlFor={inputId} className="text-xs text-gray-500 block mb-1">
                  {field.label}
                  {field.multiline && <span className="text-gray-400">(每行一条)</span>}
                </label>
                {field.multiline ? (
                  <textarea
                    id={inputId}
                    value={editValues[field.key] ?? ""}
                    onChange={(e) =>
                      setEditValues((v) => ({ ...v, [field.key]: e.target.value }))
                    }
                    rows={4}
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 resize-y"
                  />
                ) : (
                  <input
                    id={inputId}
                    type="text"
                    value={editValues[field.key] ?? ""}
                    onChange={(e) =>
                      setEditValues((v) => ({ ...v, [field.key]: e.target.value }))
                    }
                    className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                  />
                )}
              </div>
            );
          })}
          <div className="flex gap-2 mt-3">
            <button
              onClick={handleSave}
              className="px-3 py-1 bg-primary-600 text-white text-sm rounded hover:bg-primary-700"
            >
              保存
            </button>
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1 border border-gray-300 text-gray-600 text-sm rounded hover:bg-gray-50"
            >
              取消
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-1">
          {fields.map((field) => {
            const lines = field.multiline
              ? field.value.split("\n").map((s) => s.trim()).filter(Boolean)
              : [];
            return (
              <div key={field.key} className="text-sm">
                <span className="text-gray-500">{field.label}:</span>
                {field.multiline ? (
                  lines.length > 0 ? (
                    <ul className="mt-1 space-y-0.5 list-disc list-inside text-gray-700">
                      {lines.map((line, i) => (
                        <li key={i}>{line}</li>
                      ))}
                    </ul>
                  ) : (
                    <span>—</span>
                  )
                ) : field.link && field.value ? (
                  <a
                    href={hrefOf(field.value)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-primary-600 hover:underline break-all"
                  >
                    {field.value}
                  </a>
                ) : (
                  <span className="break-words">{field.value || "—"}</span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
