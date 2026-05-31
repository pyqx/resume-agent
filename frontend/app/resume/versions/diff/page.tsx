"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import DiffViewer from "@/components/resume/DiffViewer";

function DiffContent() {
  const params = useSearchParams();
  const versionA = params.get("a") || "";
  const versionB = params.get("b") || "";

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold">版本对比</h1>
        <p className="text-sm text-gray-500 mt-1">
          对比 <code className="bg-gray-100 px-1 rounded">{versionA.slice(0, 8)}</code> →{" "}
          <code className="bg-gray-100 px-1 rounded">{versionB.slice(0, 8)}</code>
        </p>
      </div>
      <div className="flex-1 overflow-y-auto">
        <DiffViewer versionA={versionA} versionB={versionB} />
      </div>
    </div>
  );
}

export default function DiffPage() {
  return (
    <Suspense fallback={<div className="p-8 text-gray-400">加载中...</div>}>
      <DiffContent />
    </Suspense>
  );
}
