"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { isAuthenticated, removeToken } from "@/lib/auth";
import { cn } from "@/lib/utils";

const adminNavItems = [
  { href: "/admin/monitoring", label: "پایش عملیات" },
  { href: "/admin/sources", label: "منابع خبری" },
  { href: "/admin/signal-sources", label: "منابع سیگنال" },
  { href: "/admin/data-health", label: "سلامت داده" },
  { href: "/admin/chat", label: "بینش‌های چت" },
  { href: "/admin/settings", label: "تنظیمات" },
];

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (pathname === "/admin/login") {
      setChecked(true);
      return;
    }
    if (!isAuthenticated()) {
      router.replace("/admin/login");
    } else {
      setChecked(true);
    }
  }, [pathname, router]);

  if (!checked && pathname !== "/admin/login") {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
      </div>
    );
  }

  if (pathname === "/admin/login") {
    return <>{children}</>;
  }

  function handleLogout() {
    removeToken();
    router.replace("/admin/login");
  }

  return (
    <div className="space-y-6">
      {/* Admin header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            پنل مدیریت
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            مدیریت منابع و تنظیمات سیستم
          </p>
        </div>
        <button onClick={handleLogout} className="btn-secondary text-sm">
          خروج
        </button>
      </div>

      {/* Admin tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-800">
        {adminNavItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "border-gold-500 text-gold-700 dark:text-gold-400"
                  : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
              )}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      {/* Content */}
      {children}
    </div>
  );
}
