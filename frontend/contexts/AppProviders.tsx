"use client";

import Sidebar from "@/components/layout/Sidebar";
import { ResumeProvider } from "@/contexts/ResumeContext";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <ResumeProvider>
      <Sidebar />
      <main className="flex-1 overflow-hidden">{children}</main>
    </ResumeProvider>
  );
}
