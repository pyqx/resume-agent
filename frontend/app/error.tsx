"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Keep the stack in the console for debugging.
    console.error("页面渲染出错:", error);
  }, [error]);

  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <p className="text-4xl mb-4" aria-hidden="true">
          ⚠️
        </p>
        <h2 className="text-lg font-semibold text-gray-900 mb-2">页面出错了</h2>
        <p className="text-sm text-gray-500 mb-1">
          抱歉,页面渲染时发生异常。您可以点击下方按钮重试,或刷新页面。
        </p>
        {error?.message && (
          <p className="text-xs text-gray-400 mb-4 break-words">{error.message}</p>
        )}
        <button
          onClick={reset}
          className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition"
        >
          重试
        </button>
      </div>
    </div>
  );
}
