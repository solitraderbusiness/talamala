'use client';

import Link from 'next/link';
import { useApp } from '@/context/AppContext';
import { cn } from '@/lib/utils';
import ModeSwitch from '@/components/ui/ModeSwitch';

export default function MobileNav() {
  const { sidebarOpen, setSidebarOpen } = useApp();

  if (!sidebarOpen) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      {/* Overlay */}
      <div className="fixed inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />

      {/* Sidebar */}
      <div className="fixed inset-y-0 right-0 w-72 bg-white shadow-xl dark:bg-gray-900">
        <div className="flex h-14 items-center justify-between border-b border-gray-200 px-4 dark:border-gray-800">
          <span className="text-sm font-bold text-gray-900 dark:text-gray-100">
            پایش طلا
          </span>
          <button
            onClick={() => setSidebarOpen(false)}
            className="text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <nav className="space-y-1 p-4">
          {[
            { href: '/', label: 'داشبورد' },
            { href: '/market/global_gold', label: 'طلای جهانی' },
            { href: '/market/iran_gold', label: 'طلای ایران' },
            { href: '/market/coin', label: 'سکه' },
            { href: '/market/gold_funds', label: 'صندوق طلا' },
            { href: '/library', label: 'کتابخانه قوانین' },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setSidebarOpen(false)}
              className="block rounded-lg px-4 py-2.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="border-t border-gray-200 p-4 dark:border-gray-800">
          <p className="mb-2 text-xs text-gray-400 dark:text-gray-500">حالت نمایش:</p>
          <ModeSwitch />
        </div>
      </div>
    </div>
  );
}
