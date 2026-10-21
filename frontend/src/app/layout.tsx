import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "메일 가드 랩 | 프롬프트 인젝션 모델 비교",
  description: "이메일 프롬프트 인젝션 탐지 모델의 로컬 평가 실험실"
};
export default function RootLayout({children}: Readonly<{children: React.ReactNode}>) {
  return <html lang="ko"><body>{children}</body></html>;
}
