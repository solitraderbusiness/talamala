import type { Metadata } from "next";
import "./globals.css";
import { AppProvider } from "@/context/AppContext";
import TopBar from "@/components/layout/TopBar";
import MobileNav from "@/components/layout/MobileNav";

export const metadata: Metadata = {
  title: "پایش طلا | تحلیل و پایش بازار طلا",
  description: "سامانه هوشمند پایش و تحلیل بازار طلای جهانی و ایران، سکه و صندوق‌های طلا",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fa" dir="rtl">
      <body className="min-h-screen antialiased">
        <AppProvider>
          <TopBar />
          <MobileNav />
          <main className="mx-auto max-w-7xl px-4 py-4 sm:py-6">
            {children}
          </main>
        </AppProvider>
      </body>
    </html>
  );
}
