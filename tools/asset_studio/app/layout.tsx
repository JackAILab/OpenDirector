import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VisualAgent 直播制作画布",
  description: "面向直播视频生产的中文资产画布，统一管理参考元素、Agent 对话与多轨时间线。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
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
