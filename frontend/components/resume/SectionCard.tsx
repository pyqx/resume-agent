"use client";

import { useState } from "react";

interface SectionCardProps {
  title: string;
  fields: { key: string; label: string; value: string; editable?: boolean }[];
  confidence?: number;
  onUpdate?: (key: string, value: string) => void;
  onDelete?: () => void;
}

export default function SectionCard({
  title,
  fields,
  confidence,
  onUpdate,
  onDelete,
}: SectionCardProps) {
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState<Record<string, string>>({});

  const handleEdit = () => {
    setEditValues(
      Object.fromEntries(fields.map((f) => [f.key, f.value]))
    );
    setEditing(true);
  };

  const handleSave = () => {
    if (onUpdate) {
      for (const [key, value] of Object.entries(editValues)) {
        onUpdate(key, value);
      }
    }
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
      <div className="flex items-center justify-between mb-3">
        <h3 className="font-semibold text-gray-800">{title}</h3>
        <div className="flex items-center gap-2">
          {confidence !== undefined && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${confidenceColor}`}>
              {Math.round(confidence * 100)}%
            </span>
          )}
          {onUpdate && !editing && (
            <button
              onClick={handleEdit}
              className="text-xs text-primary-600 hover:text-primary-700"
            >
              编辑
            </button>
          )}
          {onDelete && (
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
          {fields.map((field) => (
            <div key={field.key}>
              <label className="text-xs text-gray-500 block mb-1">{field.label}</label>
              <input
                type="text"
                value={editValues[field.key] || ""}
                onChange={(e) =>
                  setEditValues((v) => ({ ...v, [field.key]: e.target.value }))
                }
                className="w-full border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
              />
            </div>
          ))}
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
          {fields.map((field) => (
            <div key={field.key} className="text-sm">
              <span className="text-gray-500">{field.label}：</span>
              <span>{field.value || "—"}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
