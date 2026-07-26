"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/types";
import MessageBubble from "./MessageBubble";

interface Props {
  onSendMessage: (message: string) => void | Promise<void>;
  onStop: () => void;
  isStreaming: boolean;
  messages: ChatMessage[];
}

// text-sm line-height is 20px; cap the textarea at 6 lines + vertical padding.
const LINE_HEIGHT = 20;
const MAX_TEXTAREA_HEIGHT = LINE_HEIGHT * 6 + 16;
/** Within this distance of the bottom we consider the user "at the bottom". */
const NEAR_BOTTOM_PX = 80;

export default function ChatPanel({ onSendMessage, onStop, isStreaming, messages }: Props) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const nearBottomRef = useRef(true);
  const composingRef = useRef(false);

  // Auto-grow the textarea with its content, up to 6 lines.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [input]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    nearBottomRef.current =
      el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  }, []);

  // Follow new messages only when the user is already near the bottom, so
  // scrolling up to read history is never hijacked.
  useEffect(() => {
    if (nearBottomRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isStreaming]);

  const handleSend = () => {
    if (!input.trim() || isStreaming) return;
    const msg = input.trim();
    setInput("");
    void onSendMessage(msg);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Never send mid-IME-composition (Chinese input confirms with Enter).
    if (composingRef.current || e.nativeEvent.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* 消息列表 */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-2"
      >
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-8">
            <p className="text-lg mb-2">简历助手</p>
            <p className="text-sm">
              上传简历、粘贴职位描述,或者让我帮您从零开始创建一份简历。
            </p>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} {...msg} />
        ))}
        {isStreaming && (
          <div className="flex justify-start mb-4" aria-live="polite" role="status">
            <span className="sr-only">正在生成回复...</span>
            <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
              <div className="flex gap-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div
                  className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0.1s" }}
                />
                <div
                  className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: "0.2s" }}
                />
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* 输入区 */}
      <div className="border-t p-4">
        <div className="flex gap-2 items-end">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            onCompositionStart={() => {
              composingRef.current = true;
            }}
            onCompositionEnd={() => {
              composingRef.current = false;
            }}
            placeholder="在此输入你的问题..."
            aria-label="聊天输入框"
            className="flex-1 resize-none overflow-y-auto rounded-lg border border-gray-300 px-4 py-2 text-sm leading-5 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            rows={2}
          />
          {isStreaming ? (
            <button
              onClick={onStop}
              className="px-4 py-2 border border-red-300 text-red-600 rounded-lg hover:bg-red-50 transition shrink-0"
            >
              停止生成
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition shrink-0"
            >
              发送
            </button>
          )}
        </div>
        <p className="mt-1.5 text-xs text-gray-400">
          Enter 发送,Shift+Enter 换行
        </p>
      </div>
    </div>
  );
}
