"use client";

import { SSEEvent } from "@/lib/api";

interface Props {
  events: SSEEvent[];
}

const STEP_COLORS: Record<string, string> = {
  context_assembled: "bg-blue-100 border-blue-300 text-blue-800",
  plan_start: "bg-purple-100 border-purple-300 text-purple-800",
  plan_decision: "bg-purple-100 border-purple-300 text-purple-800",
  plan_complete: "bg-purple-100 border-purple-300 text-purple-800",
  plan_error: "bg-red-100 border-red-300 text-red-800",
  tool_call: "bg-amber-100 border-amber-300 text-amber-800",
  tool_result: "bg-green-100 border-green-300 text-green-800",
  observe_start: "bg-teal-100 border-teal-300 text-teal-800",
  observe_decision: "bg-teal-100 border-teal-300 text-teal-800",
  observe_complete: "bg-teal-100 border-teal-300 text-teal-800",
  final: "bg-gray-100 border-gray-300 text-gray-800",
};

export default function ReasoningChain({ events }: Props) {
  if (events.length === 0) return null;

  return (
    <details className="mt-2">
      <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-700">
        查看推理链 ({events.length} 步)
      </summary>
      <div className="mt-2 space-y-1 max-h-60 overflow-y-auto">
        {events.map((event, i) => {
          const colorClass = STEP_COLORS[event.type] || "bg-gray-100 border-gray-200";
          return (
            <div
              key={i}
              className={`text-xs px-2 py-1 rounded border ${colorClass}`}
            >
              <span className="font-mono font-semibold">{event.type}</span>
              {"data" in event && (
                <span className="ml-2 opacity-75">
                  {JSON.stringify(event.data).slice(0, 100)}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}
