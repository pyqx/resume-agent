"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { usePageState } from "@/contexts/PageStateContext";

// ── 与后端 SSE / compose-entry 契约对应的类型 ──────────────

interface RepoMetadata {
  url?: string;
  owner?: string;
  repo?: string;
  stars?: number;
  forks?: number;
  language?: string;
  description?: string;
  topics?: string[];
  open_issues?: number;
  updated_at?: string;
  api_status?: string;
  error?: string;
}

interface TechStack {
  detected_tools?: string[];
  top_file_extensions?: Record<string, number>;
}

interface RepoStructure {
  root_name?: string;
  tech_stack?: TechStack;
  directory_tree?: string;
  modules?: Array<{ name?: string; subdirs?: number; files?: number }>;
  file_stats?: Record<string, number>;
  has_tests?: boolean;
  has_ci?: boolean;
  has_docs?: boolean;
  error?: string;
  structure_available?: boolean;
}

interface IssueItem {
  number?: number;
  title?: string;
  labels?: string[];
  reactions?: number;
  comments?: number;
  url?: string;
  category?: string;
}

interface DeepAnalysis {
  dependencies?: {
    package_files?: string[];
    total_dependencies?: number;
    potential_issues?: unknown[];
    error?: string;
  };
  issues?: {
    total_open_issues_found?: number;
    good_first_issues?: unknown[];
    high_engagement_issues?: unknown[];
    error?: string;
    note?: string;
  };
}

interface Suggestion {
  title?: string;
  what_to_do?: string;
  why_valuable?: string;
  technical_challenges?: string;
  estimated_hours?: number | string;
  difficulty?: string;
  prerequisite_knowledge?: string | string[];
  resume_impact?: string | string[];
  recommended?: boolean;
}

interface SuggestionsResult {
  suggestions?: unknown[];
  learning_path?: unknown[];
  avoid?: unknown[];
  overall_assessment?: string;
  career_direction_used?: string;
}

interface StarEntry {
  entry_title?: string;
  background?: string;
  role?: string;
  technical_approach?: string[];
  outcomes?: string[];
  technologies_mentioned?: string[];
  is_planned?: boolean;
}

interface GithubPersist {
  repoUrl: string;
  analyzedUrl: string;
  metadata: RepoMetadata | null;
  structure: RepoStructure | null;
  deep: DeepAnalysis | null;
  suggestions: SuggestionsResult | null;
  entries: StarEntry[];
}

// ── 工具函数 ───────────────────────────────────────────────

/** 从 FastAPI 错误响应中提取中文 detail(普通请求统一走 /api 代理 + 本函数)。 */
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

/** 后端事件里的列表可能被截断并在末尾追加提示字符串,过滤出对象元素。 */
function objectItems<T extends object>(arr: unknown): T[] {
  if (!Array.isArray(arr)) return [];
  return arr.filter((x): x is T => typeof x === "object" && x !== null);
}

/** 列表里的字符串元素(含截断提示)。 */
function stringItems(arr: unknown): string[] {
  if (!Array.isArray(arr)) return [];
  return arr.filter((x): x is string => typeof x === "string");
}

function asText(v: string | string[] | undefined): string {
  if (v === undefined || v === null) return "";
  return Array.isArray(v) ? v.map(String).join("; ") : String(v);
}

const DIFF_META: Record<string, { label: string; cls: string }> = {
  beginner: { label: "入门", cls: "bg-green-100 text-green-700" },
  intermediate: { label: "中级", cls: "bg-amber-100 text-amber-700" },
  advanced: { label: "高级", cls: "bg-red-100 text-red-700" },
};

const FILE_STAT_LABELS: Record<string, string> = {
  total_files: "文件总数",
  source_files: "源码文件",
  test_files: "测试文件",
  doc_files: "文档文件",
  config_files: "配置文件",
};

function entryToMarkdown(e: StarEntry): string {
  const lines = [`## ${e.entry_title || "开源贡献"}${e.is_planned ? "(规划中)" : ""}`, ""];
  if (e.background) lines.push(`**背景**:${e.background}`, "");
  if (e.role) lines.push(`**角色**:${e.role}`, "");
  const approach = stringItems(e.technical_approach);
  if (approach.length) lines.push("**技术方案**:", ...approach.map((t) => `- ${t}`), "");
  const outcomes = stringItems(e.outcomes);
  if (outcomes.length) lines.push("**成果**:", ...outcomes.map((o) => `- ${o}`), "");
  const techs = stringItems(e.technologies_mentioned);
  if (techs.length) lines.push(`**技术栈**:${techs.join("、")}`);
  return lines.join("\n");
}

const STAGES = [
  { n: 1, title: "仓库元数据", desc: "基本信息与统计" },
  { n: 2, title: "目录结构", desc: "技术栈与模块划分" },
  { n: 3, title: "深度分析", desc: "依赖与 Issue 情况" },
  { n: 4, title: "改进建议", desc: "个性化贡献方向" },
  { n: 5, title: "简历条目", desc: "生成 STAR 格式条目" },
] as const;

type StageStatus = "pending" | "running" | "done";

// ── 页面组件 ───────────────────────────────────────────────

export default function GithubPage() {
  const { state: saved, updateState } = usePageState<GithubPersist>("github");
  const [repoUrl, setRepoUrl] = useState(saved.repoUrl ?? "");
  const [analyzedUrl, setAnalyzedUrl] = useState(saved.analyzedUrl ?? "");
  const [metadata, setMetadata] = useState<RepoMetadata | null>(saved.metadata ?? null);
  const [structure, setStructure] = useState<RepoStructure | null>(saved.structure ?? null);
  const [deep, setDeep] = useState<DeepAnalysis | null>(saved.deep ?? null);
  const [suggestions, setSuggestions] = useState<SuggestionsResult | null>(saved.suggestions ?? null);
  const [entries, setEntries] = useState<StarEntry[]>(saved.entries ?? []);
  // 瞬时状态
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStage, setCurrentStage] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [composingIdx, setComposingIdx] = useState<number | null>(null);
  const [composeError, setComposeError] = useState<string | null>(null);
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // 同步到持久化存储
  useEffect(() => { updateState({ repoUrl }); }, [repoUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ analyzedUrl }); }, [analyzedUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ metadata }); }, [metadata]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ structure }); }, [structure]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ deep }); }, [deep]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ suggestions }); }, [suggestions]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { updateState({ entries }); }, [entries]); // eslint-disable-line react-hooks/exhaustive-deps

  // 卸载时中止流
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const handleEvent = (type: string, data: Record<string, unknown>) => {
    switch (type) {
      case "stage":
        setCurrentStage(Number(data.stage) || null);
        break;
      case "metadata":
        setMetadata(data as RepoMetadata);
        break;
      case "structure":
        setStructure(data as RepoStructure);
        break;
      case "deep_analysis":
        setDeep(data as DeepAnalysis);
        break;
      case "suggestions":
        setSuggestions(data as SuggestionsResult);
        break;
      case "complete":
        break;
      case "error":
        // 任何阶段失败都会收到 error 事件:显示并终止 loading
        setError(String(data.error || "分析失败"));
        break;
      default:
        break;
    }
  };

  const startAnalyze = async () => {
    const url = repoUrl.trim();
    if (!url || isAnalyzing) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsAnalyzing(true);
    setCurrentStage(1);
    setError(null);
    setComposeError(null);
    setMetadata(null);
    setStructure(null);
    setDeep(null);
    setSuggestions(null);
    if (url !== analyzedUrl) setEntries([]); // 换仓库时清掉旧条目
    setAnalyzedUrl(url);

    try {
      // SSE 必须直连后端:Next.js 代理会缓冲流式响应
      const res = await fetch(`${API_BASE}/github/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ repo_url: url }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      const reader = res.body?.getReader();
      if (!reader) throw new Error("浏览器未返回可读的响应流");

      // 内联 SSE 解析:event:/data: 行、空行分帧、事件派发后复位、忽略 ":" 注释
      const decoder = new TextDecoder();
      let buffer = "";
      let eventType = "";
      let dataLines: string[] = [];

      const dispatch = () => {
        if (dataLines.length > 0) {
          try {
            const payload = JSON.parse(dataLines.join("\n"));
            if (payload && typeof payload === "object") {
              handleEvent(eventType || "message", payload as Record<string, unknown>);
            }
          } catch {
            /* 后端保证 payload 是合法 JSON;异常帧直接忽略 */
          }
        }
        eventType = "";
        dataLines = [];
      };

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (line === "") { dispatch(); continue; }   // 空行 = 一帧结束
          if (line.startsWith(":")) continue;          // 注释/心跳行
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).replace(/^ /, ""));
          }
        }
      }
      dispatch(); // 收尾:流结束时可能还有未分帧的数据
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "分析失败,请稍后重试");
      }
    } finally {
      if (!controller.signal.aborted) {
        setIsAnalyzing(false);
        setCurrentStage(null);
      }
    }
  };

  const composeEntry = async (sug: Suggestion, idx: number) => {
    if (composingIdx !== null) return;
    setComposingIdx(idx);
    setComposeError(null);
    try {
      const res = await fetch("/api/github/compose-entry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          suggestion: sug,
          repo_context: {
            metadata: {
              owner: metadata?.owner ?? "",
              repo: metadata?.repo ?? "",
              description: metadata?.description ?? "",
              language: metadata?.language ?? "",
              stars: metadata?.stars ?? 0,
            },
            tech_stack: structure?.tech_stack ?? {},
          },
        }),
      });
      if (!res.ok) throw new Error(await readErrorDetail(res));
      const entry = (await res.json()) as StarEntry;
      setEntries((prev) => [...prev, entry]);
    } catch (err) {
      setComposeError(err instanceof Error ? err.message : "简历条目生成失败,请稍后重试");
    } finally {
      setComposingIdx(null);
    }
  };

  const copyEntry = async (idx: number, entry: StarEntry) => {
    try {
      await navigator.clipboard.writeText(entryToMarkdown(entry));
      setCopiedIdx(idx);
      setTimeout(() => setCopiedIdx((c) => (c === idx ? null : c)), 2000);
    } catch {
      setComposeError("复制失败,请手动选择文本复制");
    }
  };

  const stageData: Record<number, boolean> = {
    1: !!metadata,
    2: !!structure,
    3: !!deep,
    4: !!suggestions,
    5: entries.length > 0,
  };

  const stageStatus = (n: number): StageStatus => {
    if (stageData[n]) return "done";
    if (n === 5) return composingIdx !== null ? "running" : "pending";
    if (isAnalyzing && currentStage === n) return "running";
    return "pending";
  };

  const sugList = objectItems<Suggestion>(suggestions?.suggestions);
  const learningPath = stringItems(suggestions?.learning_path);
  const avoidList = objectItems<{ direction?: string; reason?: string }>(suggestions?.avoid);

  const renderIssueList = (title: string, raw: unknown) => {
    const items = objectItems<IssueItem>(raw);
    if (items.length === 0) return null;
    return (
      <div className="mt-2">
        <p className="text-xs font-medium text-gray-600 mb-1">{title}</p>
        <ul className="space-y-1">
          {items.slice(0, 5).map((it, i) => (
            <li key={i} className="text-xs text-gray-700">
              {it.url ? (
                <a href={it.url} target="_blank" rel="noreferrer" className="text-primary-600 hover:underline">
                  #{it.number} {it.title}
                </a>
              ) : (
                <span>#{it.number} {it.title}</span>
              )}
              <span className="text-gray-400 ml-2">
                {typeof it.reactions === "number" && it.reactions > 0 ? `${it.reactions} 赞 ` : ""}
                {typeof it.comments === "number" && it.comments > 0 ? `${it.comments} 评论` : ""}
              </span>
            </li>
          ))}
        </ul>
        {items.length > 5 && <p className="text-xs text-gray-400 mt-1">等共 {items.length} 条</p>}
      </div>
    );
  };

  const statusIcon = (s: StageStatus) => {
    if (s === "running") {
      return (
        <span
          className="inline-block w-4 h-4 border-2 border-primary-600 border-t-transparent rounded-full animate-spin"
          role="status"
          aria-label="进行中"
        />
      );
    }
    if (s === "done") {
      return <span className="text-xs text-green-600 font-medium">完成 ✓</span>;
    }
    return <span className="text-xs text-gray-300">待分析</span>;
  };

  const stageCard = (n: number, body: React.ReactNode) => {
    const meta = STAGES[n - 1];
    const s = stageStatus(n);
    return (
      <div key={n} className="bg-white border border-gray-200 rounded-lg">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
          <span
            className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold shrink-0 ${
              s === "done"
                ? "bg-green-100 text-green-700"
                : s === "running"
                ? "bg-primary-50 text-primary-600"
                : "bg-gray-100 text-gray-400"
            }`}
            aria-hidden="true"
          >
            {n}
          </span>
          <h2 className="font-bold text-gray-800 text-sm">{meta.title}</h2>
          <span className="text-xs text-gray-400 hidden sm:inline">{meta.desc}</span>
          <span className="ml-auto flex items-center">{statusIcon(s)}</span>
        </div>
        <div className="px-4 py-3">{body}</div>
      </div>
    );
  };

  const pendingText = <p className="text-sm text-gray-400">等待分析...</p>;

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold mb-1">GitHub 项目分析</h1>
        <p className="text-sm text-gray-500 mb-3">
          输入仓库地址,五阶段渐进式分析,并把贡献方向写成可用的简历条目。未加载简历也可使用。
        </p>
        <div className="flex gap-3">
          <input
            type="text"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") startAnalyze(); }}
            placeholder="https://github.com/owner/repo(支持 github.com / gitlab.com / gitee.com)"
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            disabled={isAnalyzing}
          />
          <button
            onClick={startAnalyze}
            disabled={!repoUrl.trim() || isAnalyzing}
            className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition"
          >
            {isAnalyzing ? "分析中..." : "开始分析"}
          </button>
        </div>
        {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* 阶段 1:仓库元数据 */}
        {stageCard(
          1,
          metadata ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-gray-800 text-sm">
                  {metadata.owner && metadata.repo ? `${metadata.owner}/${metadata.repo}` : metadata.url || analyzedUrl}
                </span>
                {metadata.language && (
                  <span className="text-xs bg-gray-100 rounded-full px-2 py-0.5">{metadata.language}</span>
                )}
              </div>
              {metadata.description && (
                <p className="text-sm text-gray-600">{metadata.description}</p>
              )}
              {metadata.api_status === "ok" && (
                <div className="flex gap-4 text-xs text-gray-500 flex-wrap">
                  <span>Star {metadata.stars ?? 0}</span>
                  <span>Fork {metadata.forks ?? 0}</span>
                  <span>开放 Issue {metadata.open_issues ?? 0}</span>
                </div>
              )}
              {stringItems(metadata.topics).length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {stringItems(metadata.topics).map((t) => (
                    <span key={t} className="text-xs bg-blue-50 text-blue-700 rounded-full px-2 py-0.5">{t}</span>
                  ))}
                </div>
              )}
              {metadata.api_status === "rate_limited" && (
                <div className="border border-amber-300 bg-amber-50 rounded-lg px-3 py-2 text-xs text-amber-800">
                  GitHub API 已限流(匿名 60 次/小时),统计数据暂不可用(并非为 0)。
                  建议在后端配置 GITHUB_TOKEN 提升配额后重试。
                </div>
              )}
              {metadata.api_status &&
                !["ok", "rate_limited", "unavailable"].includes(metadata.api_status) && (
                  <p className="text-xs text-red-500">{metadata.error || `仓库信息获取失败(${metadata.api_status})`}</p>
                )}
              {metadata.api_status === "unavailable" && (
                <p className="text-xs text-gray-400">非 GitHub 仓库或无法获取 API 统计,后续阶段仍基于克隆代码分析。</p>
              )}
            </div>
          ) : (
            pendingText
          ),
        )}

        {/* 阶段 2:目录结构 */}
        {stageCard(
          2,
          structure ? (
            structure.error ? (
              <p className="text-sm text-red-500">结构分析失败:{structure.error}</p>
            ) : (
              <div className="space-y-3">
                {stringItems(structure.tech_stack?.detected_tools).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1.5">检测到的技术栈:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {stringItems(structure.tech_stack?.detected_tools).map((t) => (
                        <span key={t} className="text-xs bg-primary-50 text-primary-600 rounded-full px-2.5 py-1">{t}</span>
                      ))}
                    </div>
                  </div>
                )}
                <div className="flex gap-2 flex-wrap text-xs">
                  <span className={`px-2 py-0.5 rounded-full ${structure.has_tests ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-400"}`}>
                    {structure.has_tests ? "含测试" : "无测试"}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full ${structure.has_ci ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-400"}`}>
                    {structure.has_ci ? "含 CI" : "无 CI"}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full ${structure.has_docs ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-400"}`}>
                    {structure.has_docs ? "含文档" : "无文档"}
                  </span>
                  {structure.file_stats &&
                    Object.entries(structure.file_stats).map(([k, v]) => (
                      <span key={k} className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600">
                        {FILE_STAT_LABELS[k] || k}: {v}
                      </span>
                    ))}
                </div>
                {objectItems<{ name?: string; subdirs?: number; files?: number }>(structure.modules).length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1.5">顶层模块:</p>
                    <div className="flex flex-wrap gap-1.5">
                      {objectItems<{ name?: string; subdirs?: number; files?: number }>(structure.modules).map((m, i) => (
                        <span key={i} className="text-xs bg-gray-100 rounded px-2 py-1 text-gray-700">
                          {m.name}
                          <span className="text-gray-400">({m.files ?? 0} 文件)</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {structure.directory_tree && (
                  <pre className="text-xs bg-gray-50 border border-gray-100 rounded p-2 overflow-x-auto max-h-56 overflow-y-auto text-gray-600">
                    {structure.directory_tree}
                  </pre>
                )}
              </div>
            )
          ) : (
            pendingText
          ),
        )}

        {/* 阶段 3:深度分析 */}
        {stageCard(
          3,
          deep ? (
            <div className="space-y-3">
              <div>
                <p className="text-xs font-medium text-gray-600 mb-1">依赖情况</p>
                {deep.dependencies?.error ? (
                  <p className="text-xs text-red-500">依赖分析失败:{deep.dependencies.error}</p>
                ) : (
                  <div className="text-sm text-gray-700">
                    <span className="text-xs text-gray-500">
                      清单文件:{stringItems(deep.dependencies?.package_files).join("、") || "未发现"}
                      {" · "}依赖总数:{deep.dependencies?.total_dependencies ?? 0}
                    </span>
                    {stringItems(deep.dependencies?.potential_issues).length > 0 && (
                      <ul className="mt-1 space-y-0.5">
                        {stringItems(deep.dependencies?.potential_issues).map((it, i) => (
                          <li key={i} className="text-xs text-amber-700">- {it}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </div>
              <div>
                <p className="text-xs font-medium text-gray-600 mb-1">
                  开放 Issue
                  {typeof deep.issues?.total_open_issues_found === "number" &&
                    `(共 ${deep.issues.total_open_issues_found} 条)`}
                </p>
                {deep.issues?.error ? (
                  <p className="text-xs text-gray-500">{deep.issues.note || `Issue 获取失败:${deep.issues.error}`}</p>
                ) : (
                  <>
                    {renderIssueList("适合新手(good first issue):", deep.issues?.good_first_issues)}
                    {renderIssueList("高关注度:", deep.issues?.high_engagement_issues)}
                    {objectItems(deep.issues?.good_first_issues).length === 0 &&
                      objectItems(deep.issues?.high_engagement_issues).length === 0 && (
                        <p className="text-xs text-gray-400">未获取到 Issue 列表。</p>
                      )}
                  </>
                )}
              </div>
            </div>
          ) : (
            pendingText
          ),
        )}

        {/* 阶段 4:改进建议 */}
        {stageCard(
          4,
          suggestions ? (
            <div className="space-y-3">
              {suggestions.career_direction_used && (
                <p className="text-xs text-gray-500">
                  建议基于:{suggestions.career_direction_used}
                  {suggestions.career_direction_used === "general software development" &&
                    "(未加载简历,按通用软件开发方向生成;上传简历可获得更个性化的建议)"}
                </p>
              )}
              {suggestions.overall_assessment && (
                <p className="text-sm text-gray-700 bg-gray-50 rounded-lg px-3 py-2">
                  {suggestions.overall_assessment}
                </p>
              )}
              {sugList.map((sug, idx) => {
                const diff = sug.difficulty
                  ? DIFF_META[sug.difficulty] || { label: sug.difficulty, cls: "bg-gray-100 text-gray-600" }
                  : null;
                return (
                  <div key={idx} className="border border-gray-200 rounded-lg p-3">
                    <div className="flex items-center gap-2 flex-wrap mb-1.5">
                      <span className="text-sm font-medium text-gray-800">{sug.title || `方向 ${idx + 1}`}</span>
                      {diff && <span className={`text-xs px-1.5 py-0.5 rounded ${diff.cls}`}>{diff.label}</span>}
                      {sug.estimated_hours !== undefined && sug.estimated_hours !== "" && (
                        <span className="text-xs text-gray-400">
                          预估工时:{String(sug.estimated_hours)}{typeof sug.estimated_hours === "number" ? " 小时" : ""}
                        </span>
                      )}
                      {sug.recommended === false && (
                        <span className="text-xs px-1.5 py-0.5 rounded bg-gray-200 text-gray-500">不推荐</span>
                      )}
                    </div>
                    {sug.what_to_do && <p className="text-sm text-gray-700 mb-1">{sug.what_to_do}</p>}
                    {sug.why_valuable && (
                      <p className="text-xs text-gray-500 mb-1">价值:{sug.why_valuable}</p>
                    )}
                    {sug.technical_challenges && (
                      <p className="text-xs text-gray-500 mb-1">技术挑战:{sug.technical_challenges}</p>
                    )}
                    {asText(sug.prerequisite_knowledge) && (
                      <p className="text-xs text-gray-500 mb-1">前置知识:{asText(sug.prerequisite_knowledge)}</p>
                    )}
                    {asText(sug.resume_impact) && (
                      <p className="text-xs text-primary-600 mb-1">简历影响:{asText(sug.resume_impact)}</p>
                    )}
                    <button
                      onClick={() => composeEntry(sug, idx)}
                      disabled={composingIdx !== null}
                      className="mt-1.5 px-3 py-1 text-xs bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition"
                    >
                      {composingIdx === idx ? "生成中..." : "生成简历条目"}
                    </button>
                  </div>
                );
              })}
              {composeError && <p className="text-xs text-red-500">{composeError}</p>}
              {learningPath.length > 0 && (
                <div className="bg-blue-50 rounded-lg p-3">
                  <p className="text-xs font-medium text-blue-700 mb-1">学习路径</p>
                  <ul className="list-disc list-inside text-xs text-gray-700 space-y-0.5">
                    {learningPath.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
              {avoidList.length > 0 && (
                <div className="bg-red-50 rounded-lg p-3">
                  <p className="text-xs font-medium text-red-700 mb-1">建议避开</p>
                  <ul className="text-xs text-gray-700 space-y-0.5">
                    {avoidList.map((a, i) => (
                      <li key={i}>
                        <span className="font-medium">{a.direction}</span>
                        {a.reason && <span className="text-gray-500">:{a.reason}</span>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            pendingText
          ),
        )}

        {/* 阶段 5:简历条目 */}
        {stageCard(
          5,
          entries.length > 0 ? (
            <div className="space-y-3">
              {entries.map((entry, idx) => (
                <div key={idx} className="border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <span className="text-sm font-medium text-gray-800">{entry.entry_title || "开源贡献条目"}</span>
                    {entry.is_planned && (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-700">规划中</span>
                    )}
                    <button
                      onClick={() => copyEntry(idx, entry)}
                      className="ml-auto text-xs px-2 py-1 border border-gray-300 rounded hover:bg-gray-50 text-gray-600"
                    >
                      {copiedIdx === idx ? "已复制 ✓" : "复制 Markdown"}
                    </button>
                  </div>
                  {entry.background && (
                    <p className="text-sm text-gray-700 mb-1"><span className="text-gray-500">背景:</span>{entry.background}</p>
                  )}
                  {entry.role && (
                    <p className="text-sm text-gray-700 mb-1"><span className="text-gray-500">角色:</span>{entry.role}</p>
                  )}
                  {stringItems(entry.technical_approach).length > 0 && (
                    <div className="mb-1">
                      <p className="text-xs text-gray-500 mb-0.5">技术方案:</p>
                      <ul className="list-disc list-inside text-sm text-gray-700 space-y-0.5">
                        {stringItems(entry.technical_approach).map((t, i) => <li key={i}>{t}</li>)}
                      </ul>
                    </div>
                  )}
                  {stringItems(entry.outcomes).length > 0 && (
                    <div className="mb-1">
                      <p className="text-xs text-gray-500 mb-0.5">成果:</p>
                      <ul className="list-disc list-inside text-sm text-gray-700 space-y-0.5">
                        {stringItems(entry.outcomes).map((o, i) => <li key={i}>{o}</li>)}
                      </ul>
                    </div>
                  )}
                  {stringItems(entry.technologies_mentioned).length > 0 && (
                    <div className="flex flex-wrap gap-1.5 mt-1.5">
                      {stringItems(entry.technologies_mentioned).map((t) => (
                        <span key={t} className="text-xs bg-blue-50 text-blue-700 rounded-full px-2 py-0.5">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400">
              {suggestions
                ? "在上方“改进建议”中选择一条,点击“生成简历条目”,即可生成 STAR 格式的简历条目。"
                : "完成分析后,可将改进建议一键生成 STAR 格式的简历条目。"}
            </p>
          ),
        )}
      </div>
    </div>
  );
}
