"use client";

import Sidebar from "@/components/layout/Sidebar";
import { ResumeProvider } from "@/contexts/ResumeContext";
import { PageStateProvider } from "@/contexts/PageStateContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ResumeProvider>
      <PageStateProvider>
        <Sidebar />
        <main className="flex-1 overflow-hidden">{children}</main>
      </PageStateProvider>
    </ResumeProvider>
  );
}
