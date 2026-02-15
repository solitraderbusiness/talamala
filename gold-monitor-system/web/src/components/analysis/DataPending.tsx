"use client";

interface DataPendingProps {
  title?: string;
  message?: string;
}

export default function DataPending({
  title = "به زودی",
  message = "داده‌های این بخش پس از اجرای اولیه سیستم نمایش داده خواهند شد.",
}: DataPendingProps) {
  return (
    <div className="card flex flex-1 flex-col items-center justify-center py-12 text-center">
      <div className="mb-3 text-4xl opacity-40">&#x23F3;</div>
      <h3 className="text-sm font-bold text-gray-500 dark:text-gray-400">
        {title}
      </h3>
      <p className="mt-1 max-w-sm text-xs text-gray-400 dark:text-gray-500">
        {message}
      </p>
    </div>
  );
}
