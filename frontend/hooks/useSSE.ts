"use client";

import { useState, useRef, useCallback } from "react";
import { streamChat, SSEEvent } from "@/lib/api";

interface UseSSEReturn {
  events: SSEEvent[];
  isStreaming: boolean;
  streamingText: string;
  error: string | null;
  sendMessage: (message: string, sessionId?: string) => Promise<string>;
  clearEvents: () => void;
}

export function useSSE(): UseSSEReturn {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (message: string, sessionId?: string): Promise<string> => {
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const controller = new AbortController();
    abortRef.current = controller;

    setIsStreaming(true);
    setError(null);
    setStreamingText("");

    const newEvents: SSEEvent[] = [];
    let finalResponse = "";

    try {
      for await (const event of streamChat(message, sessionId)) {
        if (controller.signal.aborted) break;
        newEvents.push(event);
        setEvents([...newEvents]);

        // Extract streaming text from plan_complete events
        if (event.type === "plan_complete") {
          const data = event.data as { raw_response?: string };
          if (data?.raw_response) {
            // Try to extract message from JSON response for "respond" actions
            try {
              const parsed = JSON.parse(data.raw_response);
              if (parsed.action === "respond" && parsed.message) {
                setStreamingText(parsed.message);
                finalResponse = parsed.message;
              } else if (parsed.reasoning) {
                setStreamingText("思考中: " + parsed.reasoning);
              }
            } catch {
              setStreamingText(data.raw_response.slice(0, 200));
            }
          }
        }

        // Capture final response
        if (event.type === "final") {
          const data = event.data as { response?: string };
          if (data?.response) {
            finalResponse = data.response;
            setStreamingText(data.response);
          }
        }
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : "流式传输失败");
      }
    } finally {
      setIsStreaming(false);
    }

    return finalResponse;
  }, []);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setStreamingText("");
    setError(null);
  }, []);

  return { events, isStreaming, streamingText, error, sendMessage, clearEvents };
}
