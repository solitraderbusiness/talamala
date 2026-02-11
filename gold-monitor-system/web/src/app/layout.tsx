import type { Metadata } from "next";
import "./globals.css";
import TopBar from "@/components/TopBar";
import ChatWidget from "@/components/ChatWidget";

export const metadata: Metadata = {
  title: "طلاملا | Talamala",
  description: "داشبورد هوشمند بازار طلا و ارز",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="fa" dir="rtl">
      <head>
        <link
          href="https://cdn.jsdelivr.net/gh/rastikerdar/vazirmatn@v33.003/Vazirmatn-font-face.css"
          rel="stylesheet"
        />
      </head>
      <body className="font-vazir min-h-screen">
        <TopBar />
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </main>
        <ChatWidget />
      </body>
    </html>
  );
}
