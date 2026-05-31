"use client";

import SectionCard from "./SectionCard";

interface ResumeEditorProps {
  resumeData: Record<string, unknown> | null;
  isLoading: boolean;
}

export default function ResumeEditor({ resumeData, isLoading }: ResumeEditorProps) {
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

  const pi = resumeData.personal_info as Record<string, unknown> || {};
  const education = resumeData.education as Array<Record<string, unknown>> || [];
  const work = resumeData.work_experience as Array<Record<string, unknown>> || [];
  const projects = resumeData.project_experience as Array<Record<string, unknown>> || [];
  const skills = resumeData.skills as Array<Record<string, unknown>> || [];

  return (
    <div className="overflow-y-auto h-full p-4">
      {/* 个人信息 */}
      <SectionCard
        title="个人信息"
        fields={[
          { key: "full_name", label: "姓名", value: String(pi.full_name || "") },
          { key: "email", label: "邮箱", value: String(pi.email || "") },
          { key: "phone", label: "电话", value: String(pi.phone || "") },
          { key: "location", label: "所在地", value: String(pi.location || "") },
          { key: "summary", label: "个人概述", value: String(pi.summary || "").slice(0, 100) },
        ]}
      />

      {/* 教育背景 */}
      <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">教育背景</h2>
      {education.map((edu, i) => (
        <SectionCard
          key={i}
          title={String(edu.school || "教育经历")}
          fields={[
            { key: "degree", label: "学位", value: String(edu.degree || "") },
            { key: "major", label: "专业", value: String(edu.major || "") },
            { key: "school", label: "学校", value: String(edu.school || "") },
          ]}
          confidence={edu.confidence as number}
        />
      ))}
      {education.length === 0 && (
        <p className="text-sm text-gray-400">暂无教育经历</p>
      )}

      {/* 工作经历 */}
      <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">工作经历</h2>
      {work.map((w, i) => (
        <SectionCard
          key={i}
          title={`${w.position || "职位"} @ ${w.company || "公司"}`}
          fields={[
            { key: "company", label: "公司", value: String(w.company || "") },
            { key: "position", label: "职位", value: String(w.position || "") },
            {
              key: "bullets",
              label: "关键成果",
              value: Array.isArray(w.bullets) ? (w.bullets as string[]).join("; ") : "",
            },
          ]}
          confidence={w.confidence as number}
        />
      ))}
      {work.length === 0 && (
        <p className="text-sm text-gray-400">暂无工作经历</p>
      )}

      {/* 项目经历 */}
      <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">项目经历</h2>
      {projects.map((p, i) => (
        <SectionCard
          key={i}
          title={String(p.name || "项目")}
          fields={[
            { key: "name", label: "项目名称", value: String(p.name || "") },
            { key: "role", label: "角色", value: String(p.role || "") },
            {
              key: "technologies",
              label: "技术栈",
              value: Array.isArray(p.technologies) ? (p.technologies as string[]).join(", ") : "",
            },
          ]}
          confidence={p.confidence as number}
        />
      ))}
      {projects.length === 0 && (
        <p className="text-sm text-gray-400">暂无项目经历</p>
      )}

      {/* 技能 */}
      <h2 className="text-lg font-bold text-gray-800 mt-6 mb-3">技能</h2>
      <div className="flex flex-wrap gap-2">
        {skills.map((s, i) => (
          <span
            key={i}
            className="px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-sm"
          >
            {String(s.name || "")}
          </span>
        ))}
      </div>
      {skills.length === 0 && (
        <p className="text-sm text-gray-400">暂无技能标签</p>
      )}
    </div>
  );
}
