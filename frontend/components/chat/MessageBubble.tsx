"use client";

import ReactMarkdown from "react-markdown";
import type { ChatMessage } from "@/lib/types";
import ReasoningChain from "./ReasoningChain";

type Props = ChatMessage;

export default function MessageBubble({ role, content, events, timestamp, isError }: Props) {
  const isAgent = role === "agent";

  const bubbleClass = isAgent
    ? isError
      ? "bg-red-50 border border-red-200 text-red-800 rounded-tl-sm"
      : "bg-gray-100 text-gray-900 rounded-tl-sm"
    : "bg-primary-600 text-white rounded-tr-sm";

  return (
    <div className={`flex ${isAgent ? "justify-start" : "justify-end"} mb-4`}>
      <div className={`max-w-[80%] rounded-2xl px-4 py-3 ${bubbleClass}`}>
        {events && events.length > 0 && <ReasoningChain events={events} />}
        {content &&
          (isAgent ? (
            <div className="markdown-body text-sm">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          ) : (
            <div className="text-sm whitespace-pre-wrap break-words">{content}</div>
          ))}
        {timestamp ? (
          <div
            className={`text-xs mt-1 ${
              isAgent ? "text-gray-400" : "text-primary-200"
            }`}
          >
            {new Date(timestamp * 1000).toLocaleTimeString("zh-CN")}
          </div>
        ) : null}
      </div>
    </div>
  );
}
