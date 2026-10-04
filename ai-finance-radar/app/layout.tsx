import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: '信息雷达 · SIGNAL RADAR',
  description: '自定义主题信息流、来源管理与采集流程',
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
