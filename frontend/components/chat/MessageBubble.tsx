"use client";

import { SSEEvent } from "@/lib/api";
import ReasoningChain from "./ReasoningChain";

interface Props {
  role: "user" | "agent";
  content: string;
  events?: SSEEvent[];
  timestamp?: number;
}

export default function MessageBubble({ role, content, events, timestamp }: Props) {
  const isAgent = role === "agent";

  return (
    <div className={`flex ${isAgent ? "justify-start" : "justify-end"} mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 ${
          isAgent
            ? "bg-gray-100 text-gray-900 rounded-tl-sm"
            : "bg-primary-600 text-white rounded-tr-sm"
        }`}
      >
        <div className="text-sm whitespace-pre-wrap">{content}</div>
        {events && events.length > 0 && <ReasoningChain events={events} />}
        {timestamp && (
          <div className={`text-xs mt-1 ${isAgent ? "text-gray-400" : "text-primary-200"}`}>
            {new Date(timestamp * 1000).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
}
