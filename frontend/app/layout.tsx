import type { Metadata } from "next";
import "./globals.css";
import { AppProviders } from "@/contexts/AppProviders";

export const metadata: Metadata = {
  title: "简历助手",
  description: "AI驱动的智能简历顾问，深度推理引擎",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body className="flex h-dvh overflow-hidden">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
