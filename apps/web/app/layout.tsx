import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Hive Codex",
  description: "Boss-mode swarm delivery control room",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
