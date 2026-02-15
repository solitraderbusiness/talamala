"use client";

export default function OfflinePage() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center">
      <div className="mb-6 text-6xl">📡</div>
      <h1 className="mb-3 text-2xl font-bold text-gray-900 dark:text-gray-100">
        اتصال اینترنت قطع است
      </h1>
      <p className="mb-8 max-w-md text-gray-600 dark:text-gray-400">
        لطفا اتصال اینترنت خود را بررسی کرده و دوباره تلاش کنید.
      </p>
      <button
        onClick={() => window.location.reload()}
        className="btn-primary"
      >
        تلاش مجدد
      </button>
    </div>
  );
}
