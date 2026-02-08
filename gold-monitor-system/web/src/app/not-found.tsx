import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <h1 className="text-6xl font-bold text-gold-500">۴۰۴</h1>
      <h2 className="mt-4 text-xl font-semibold text-gray-700 dark:text-gray-300">
        صفحه مورد نظر یافت نشد
      </h2>
      <p className="mt-2 text-gray-500 dark:text-gray-400">
        صفحه‌ای که دنبال آن هستید وجود ندارد یا منتقل شده است.
      </p>
      <Link href="/" className="btn-primary mt-6 inline-block">
        بازگشت به داشبورد
      </Link>
    </div>
  );
}
