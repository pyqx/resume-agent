"use client";

import type { ChatEvent } from "@/lib/types";

interface Props {
  events: ChatEvent[];
}

const EVENT_META: Record<string, { label: string; className: string }> = {
  plan_start: { label: "计划中", className: "bg-purple-100 border-purple-300 text-purple-800" },
  context_assembled: { label: "上下文就绪", className: "bg-blue-100 border-blue-300 text-blue-800" },
  plan_decision: { label: "计划决策", className: "bg-purple-100 border-purple-300 text-purple-800" },
  plan_complete: { label: "制定计划", className: "bg-purple-100 border-purple-300 text-purple-800" },
  plan_error: { label: "计划出错", className: "bg-red-100 border-red-300 text-red-800" },
  act_start: { label: "开始执行", className: "bg-indigo-100 border-indigo-300 text-indigo-800" },
  tool_call: { label: "调用工具", className: "bg-amber-100 border-amber-300 text-amber-800" },
  tool_result: { label: "工具结果", className: "bg-green-100 border-green-300 text-green-800" },
  observe_start: { label: "观察中", className: "bg-teal-100 border-teal-300 text-teal-800" },
  observe_decision: { label: "观察决策", className: "bg-teal-100 border-teal-300 text-teal-800" },
  observe_complete: { label: "观察完成", className: "bg-teal-100 border-teal-300 text-teal-800" },
  checkpoint_restored: { label: "恢复检查点", className: "bg-sky-100 border-sky-300 text-sky-800" },
  error: { label: "错误", className: "bg-red-100 border-red-300 text-red-800" },
  final: { label: "完成", className: "bg-gray-100 border-gray-300 text-gray-800" },
};

const FALLBACK_META = { label: "步骤", className: "bg-gray-100 border-gray-200 text-gray-700" };

function snippet(value: unknown, max = 160): string {
  if (value == null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "";
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

function ToolName({ name }: { name: unknown }) {
  if (!name) return null;
  return (
    <code className="font-mono font-semibold px-1 py-0.5 rounded bg-white/70 border border-black/10">
      {String(name)}
    </code>
  );
}

function EventBody({ event }: { event: ChatEvent }) {
  const data = event.data ?? {};

  switch (event.type) {
    case "plan_complete":
      return (
        <span>
          {typeof data.reasoning === "string" && data.reasoning ? (
            <span>{snippet(data.reasoning, 300)}</span>
          ) : null}
          {Array.isArray(data.tools) && data.tools.length > 0 && (
            <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
              {data.tools.map((t, i) => (
                <ToolName key={i} name={t} />
              ))}
            </span>
          )}
        </span>
      );
    case "act_start":
      return <span>并行执行 {Number(data.tool_count) || "若干"} 个工具</span>;
    case "tool_call":
      return (
        <span>
          <ToolName name={data.tool} />
          {data.params != null && (
            <span className="ml-1 opacity-75">{snippet(data.params, 120)}</span>
          )}
        </span>
      );
    case "tool_result": {
      const success = data.success !== false;
      return (
        <span>
          <span
            aria-hidden="true"
            className={`mr-1 font-bold ${success ? "text-green-700" : "text-red-700"}`}
          >
            {success ? "✓" : "✕"}
          </span>
          <span className="sr-only">{success ? "成功" : "失败"}</span>
          <ToolName name={data.tool} />
          {!success && (
            <span className="ml-1 text-red-700">
              {snippet(data.error, 160) || "执行失败"}
            </span>
          )}
          {success && data.data != null && (
            <span className="ml-1 opacity-75">{snippet(data.data, 120)}</span>
          )}
        </span>
      );
    }
    case "checkpoint_restored":
      return (
        <span>
          已从上次中断处恢复
          {typeof data.recovered_tool_calls === "number"
            ? `,找回 ${data.recovered_tool_calls} 条工具调用记录`
            : ""}
        </span>
      );
    case "plan_error":
    case "error":
      return <span>{snippet(data.error, 200) || "发生未知错误"}</span>;
    default:
      return <span className="opacity-75">{snippet(data, 120)}</span>;
  }
}

export default function ReasoningChain({ events }: Props) {
  if (events.length === 0) return null;

  return (
    // Collapsed by default — the reasoning chain is auxiliary detail.
    <details className="mt-1 mb-2">
      <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700 select-none">
        推理过程({events.length} 步)
      </summary>
      <div className="mt-2 space-y-1 max-h-60 overflow-y-auto">
        {events.map((event, i) => {
          const meta = EVENT_META[event.type] ?? FALLBACK_META;
          const isToolFailure =
            event.type === "tool_result" && event.data?.success === false;
          const className = isToolFailure
            ? "bg-red-50 border-red-300 text-red-800"
            : meta.className;
          return (
            <div key={i} className={`text-xs px-2 py-1 rounded border ${className}`}>
              <span className="font-semibold mr-1.5">{meta.label}</span>
              <EventBody event={event} />
            </div>
          );
        })}
      </div>
    </details>
  );
}
