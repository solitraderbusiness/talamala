"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getMonitoringOverview,
  getMonitoringJobs,
  getRecentFailures,
  getActivityTimeline,
  getJobRuns,
  toggleJob,
  type MonitoringOverview,
  type SystemJob,
  type FailedRun,
  type ActivityEntry,
  type JobRun,
} from "@/lib/api";
import { getToken } from "@/lib/auth";
import { timeAgo, cn } from "@/lib/utils";

const CATEGORY_LABELS: Record<string, string> = {
  news_scraping: "دریافت اخبار",
  price_tracking: "پایش قیمت",
  sentiment: "تحلیل احساسات",
  calendar: "تقویم اقتصادی",
  cleanup: "پاکسازی",
  general: "عمومی",
};

const CATEGORY_COLORS: Record<string, string> = {
  news_scraping: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  price_tracking: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  sentiment: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  calendar: "bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400",
  cleanup: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400",
  general: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-400",
};

const STATUS_ICONS: Record<string, string> = {
  healthy: "\u{1F7E2}",  // green circle
  warning: "\u{26A0}\u{FE0F}",  // warning
  error: "\u{1F534}",    // red circle
  stale: "\u{1F535}",    // blue circle
};

type ActiveTab = "jobs" | "failures" | "activity";

export default function MonitoringPage() {
  const [overview, setOverview] = useState<MonitoringOverview | null>(null);
  const [jobs, setJobs] = useState<SystemJob[]>([]);
  const [failures, setFailures] = useState<FailedRun[]>([]);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("jobs");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [jobRuns, setJobRuns] = useState<JobRun[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);

  const token = getToken() || "";

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [overviewData, jobsData, failuresData, activityData] =
        await Promise.all([
          getMonitoringOverview(token),
          getMonitoringJobs(token),
          getRecentFailures(token),
          getActivityTimeline(token),
        ]);
      setOverview(overviewData);
      setJobs(jobsData || []);
      setFailures(failuresData || []);
      setActivity(activityData || []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "خطا در بارگذاری داده‌های پایش"
      );
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadData();
    // Auto-refresh every 30 seconds
    const interval = setInterval(loadData, 30000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleToggleJob = async (jobId: string) => {
    try {
      await toggleJob(token, jobId);
      await loadData();
    } catch {
      // Silently handle — will refresh on next cycle
    }
  };

  const handleViewRuns = async (jobId: string) => {
    if (expandedJobId === jobId) {
      setExpandedJobId(null);
      return;
    }
    setExpandedJobId(jobId);
    setRunsLoading(true);
    try {
      const runs = await getJobRuns(token, jobId, 20);
      setJobRuns(runs || []);
    } catch {
      setJobRuns([]);
    } finally {
      setRunsLoading(false);
    }
  };

  const filteredActivity = categoryFilter
    ? activity.filter((a) => a.job_category === categoryFilter)
    : activity;

  if (loading && !overview) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-gold-500 border-t-transparent" />
          <p className="mt-3 text-gray-500">در حال بارگذاری...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">
            پایش عملیات
          </h2>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            نظارت بر تمام فرآیندهای خودکار سیستم
          </p>
        </div>
        <button
          onClick={loadData}
          disabled={loading}
          className="btn-secondary text-sm"
        >
          {loading ? "بارگذاری..." : "بروزرسانی"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 p-4 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Section A: Health Overview Cards */}
      {overview && <HealthOverview overview={overview} />}

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200 dark:border-gray-800">
        {[
          { key: "jobs" as ActiveTab, label: "جدول وظایف" },
          { key: "failures" as ActiveTab, label: `خطاهای اخیر (${failures.length})` },
          { key: "activity" as ActiveTab, label: "تایم‌لاین فعالیت" },
        ].map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              "-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              activeTab === tab.key
                ? "border-gold-500 text-gold-700 dark:text-gold-400"
                : "border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700 dark:text-gray-400"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Section B: Jobs Table */}
      {activeTab === "jobs" && (
        <JobsTable
          jobs={jobs}
          expandedJobId={expandedJobId}
          jobRuns={jobRuns}
          runsLoading={runsLoading}
          onToggle={handleToggleJob}
          onViewRuns={handleViewRuns}
        />
      )}

      {/* Section C: Recent Failures */}
      {activeTab === "failures" && <FailuresSection failures={failures} />}

      {/* Section D: Activity Timeline */}
      {activeTab === "activity" && (
        <ActivitySection
          activity={filteredActivity}
          categoryFilter={categoryFilter}
          onCategoryChange={setCategoryFilter}
        />
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Section A: Health Overview                                            */
/* ────────────────────────────────────────────────────────────────────── */

function HealthOverview({ overview }: { overview: MonitoringOverview }) {
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
      <StatusCard
        icon={STATUS_ICONS.healthy}
        label="سالم"
        value={overview.jobs_healthy}
        color="text-emerald-600"
        bgColor="bg-emerald-50 dark:bg-emerald-900/20"
      />
      <StatusCard
        icon={STATUS_ICONS.warning}
        label="هشدار"
        value={overview.jobs_warning}
        color="text-amber-600"
        bgColor="bg-amber-50 dark:bg-amber-900/20"
      />
      <StatusCard
        icon={STATUS_ICONS.error}
        label="خطا"
        value={overview.jobs_error + overview.jobs_stale}
        color="text-red-600"
        bgColor="bg-red-50 dark:bg-red-900/20"
      />
      <StatusCard
        icon="\u{1F4CA}"
        label="اجراها (۲۴ ساعت)"
        value={overview.total_runs_24h}
        color="text-blue-600"
        bgColor="bg-blue-50 dark:bg-blue-900/20"
        subtitle={`نرخ موفقیت: ${overview.success_rate_24h}%`}
      />
      <StatusCard
        icon="\u{2699}\u{FE0F}"
        label="کل وظایف"
        value={overview.total_jobs}
        color="text-gray-600 dark:text-gray-400"
        bgColor="bg-gray-50 dark:bg-gray-800"
        subtitle={
          overview.last_check_at
            ? `آخرین بررسی: ${timeAgo(overview.last_check_at)}`
            : undefined
        }
      />
    </div>
  );
}

function StatusCard({
  icon,
  label,
  value,
  color,
  bgColor,
  subtitle,
}: {
  icon: string;
  label: string;
  value: number;
  color: string;
  bgColor: string;
  subtitle?: string;
}) {
  return (
    <div className={cn("card flex flex-col items-center p-4 text-center", bgColor)}>
      <span className="text-2xl">{icon}</span>
      <span className={cn("mt-1 text-2xl font-bold", color)}>{value}</span>
      <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
        {label}
      </span>
      {subtitle && (
        <span className="mt-1 text-[11px] text-gray-400">{subtitle}</span>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Section B: Jobs Table                                                 */
/* ────────────────────────────────────────────────────────────────────── */

function JobsTable({
  jobs,
  expandedJobId,
  jobRuns,
  runsLoading,
  onToggle,
  onViewRuns,
}: {
  jobs: SystemJob[];
  expandedJobId: string | null;
  jobRuns: JobRun[];
  runsLoading: boolean;
  onToggle: (id: string) => void;
  onViewRuns: (id: string) => void;
}) {
  if (jobs.length === 0) {
    return (
      <div className="card py-12 text-center">
        <p className="text-gray-400">هیچ وظیفه‌ای ثبت نشده است</p>
        <p className="mt-2 text-sm text-gray-400">
          وظایف به صورت خودکار پس از اولین اجرا ثبت می‌شوند
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {jobs.map((job) => (
        <div key={job.id}>
          <div
            className={cn(
              "card flex flex-col gap-3 p-4 transition-colors sm:flex-row sm:items-center sm:justify-between",
              !job.enabled && "opacity-50"
            )}
          >
            {/* Job info */}
            <div className="flex-1 space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-base">
                  {STATUS_ICONS[job.status] || STATUS_ICONS.healthy}
                </span>
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  {job.job_label_fa || job.job_name}
                </span>
                <span
                  className={cn(
                    "inline-block rounded-full px-2 py-0.5 text-[11px] font-medium",
                    CATEGORY_COLORS[job.job_category] || CATEGORY_COLORS.general
                  )}
                >
                  {CATEGORY_LABELS[job.job_category] || job.job_category}
                </span>
                {!job.enabled && (
                  <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] text-gray-500 dark:bg-gray-700 dark:text-gray-400">
                    غیرفعال
                  </span>
                )}
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                <span>
                  آخرین اجرا:{" "}
                  {job.last_run_at ? timeAgo(job.last_run_at) : "هرگز"}
                </span>
                {job.last_duration_ms != null && (
                  <span>مدت: {formatDuration(job.last_duration_ms)}</span>
                )}
                <span>پردازش: {job.items_processed ?? 0} آیتم</span>
                {job.success_rate_24h != null && (
                  <span>
                    نرخ موفقیت:{" "}
                    <span
                      className={cn(
                        job.success_rate_24h >= 90
                          ? "text-emerald-600"
                          : job.success_rate_24h >= 50
                          ? "text-amber-600"
                          : "text-red-600"
                      )}
                    >
                      {job.success_rate_24h}%
                    </span>{" "}
                    ({job.runs_24h} اجرا)
                  </span>
                )}
                {job.schedule && (
                  <span className="text-gray-400">
                    زمان‌بندی: {job.schedule}
                  </span>
                )}
              </div>
              {job.last_error && (
                <p className="mt-1 truncate text-xs text-red-500 dark:text-red-400">
                  خطا: {job.last_error.slice(0, 200)}
                </p>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2">
              <button
                onClick={() => onViewRuns(job.id)}
                className="btn-secondary text-xs"
              >
                {expandedJobId === job.id ? "بستن" : "لاگ‌ها"}
              </button>
              <button
                onClick={() => onToggle(job.id)}
                className={cn(
                  "rounded px-3 py-1 text-xs font-medium transition-colors",
                  job.enabled
                    ? "bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:hover:bg-red-900/40"
                    : "bg-emerald-50 text-emerald-600 hover:bg-emerald-100 dark:bg-emerald-900/20 dark:hover:bg-emerald-900/40"
                )}
              >
                {job.enabled ? "غیرفعال" : "فعال"}
              </button>
            </div>
          </div>

          {/* Expanded run logs */}
          {expandedJobId === job.id && (
            <div className="mr-4 mt-1 rounded-lg border border-gray-200 bg-gray-50 p-3 dark:border-gray-700 dark:bg-gray-900">
              <h4 className="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                تاریخچه اجرا ({job.job_label_fa || job.job_name})
              </h4>
              {runsLoading ? (
                <p className="py-4 text-center text-sm text-gray-400">
                  بارگذاری...
                </p>
              ) : jobRuns.length === 0 ? (
                <p className="py-4 text-center text-sm text-gray-400">
                  هیچ اجرایی ثبت نشده
                </p>
              ) : (
                <div className="max-h-64 space-y-1 overflow-y-auto">
                  {jobRuns.map((run) => (
                    <div
                      key={run.id}
                      className={cn(
                        "flex items-center justify-between rounded px-3 py-2 text-xs",
                        run.status === "success"
                          ? "bg-emerald-50 dark:bg-emerald-900/10"
                          : "bg-red-50 dark:bg-red-900/10"
                      )}
                    >
                      <div className="flex items-center gap-2">
                        <span>
                          {run.status === "success" ? "\u{2705}" : "\u{274C}"}
                        </span>
                        <span className="text-gray-600 dark:text-gray-400">
                          {timeAgo(run.started_at)}
                        </span>
                        {run.duration_ms != null && (
                          <span className="text-gray-400">
                            ({formatDuration(run.duration_ms)})
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-gray-500">
                          {run.items_processed} آیتم
                        </span>
                        {run.error_message && (
                          <span
                            className="max-w-[200px] truncate text-red-500"
                            title={run.error_message}
                          >
                            {run.error_message.slice(0, 80)}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Section C: Recent Failures                                            */
/* ────────────────────────────────────────────────────────────────────── */

function FailuresSection({ failures }: { failures: FailedRun[] }) {
  if (failures.length === 0) {
    return (
      <div className="card py-12 text-center">
        <span className="text-3xl">\u{2705}</span>
        <p className="mt-2 text-gray-500">هیچ خطایی در سابقه وجود ندارد</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {failures.map((f) => (
        <div
          key={f.id}
          className="card border-r-4 border-r-red-400 p-4 dark:border-r-red-600"
        >
          <div className="flex items-start justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm">{STATUS_ICONS.error}</span>
                <span className="font-medium text-gray-900 dark:text-gray-100">
                  {f.job_label_fa || f.job_name}
                </span>
              </div>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                {timeAgo(f.started_at)}
                {f.duration_ms != null && ` \u{2022} ${formatDuration(f.duration_ms)}`}
                {` \u{2022} ${f.items_processed} آیتم`}
              </p>
            </div>
          </div>
          {f.error_message && (
            <pre className="mt-2 max-h-32 overflow-auto rounded bg-red-50 p-2 text-xs text-red-700 dark:bg-red-900/20 dark:text-red-400">
              {f.error_message}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Section D: Activity Timeline                                          */
/* ────────────────────────────────────────────────────────────────────── */

function ActivitySection({
  activity,
  categoryFilter,
  onCategoryChange,
}: {
  activity: ActivityEntry[];
  categoryFilter: string;
  onCategoryChange: (cat: string) => void;
}) {
  return (
    <div className="space-y-3">
      {/* Category filter */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onCategoryChange("")}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-colors",
            !categoryFilter
              ? "bg-gold-500 text-white"
              : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
          )}
        >
          همه
        </button>
        {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
          <button
            key={key}
            onClick={() => onCategoryChange(key)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              categoryFilter === key
                ? "bg-gold-500 text-white"
                : "bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {activity.length === 0 ? (
        <div className="card py-12 text-center">
          <p className="text-gray-400">فعالیتی در ۲۴ ساعت اخیر ثبت نشده</p>
        </div>
      ) : (
        <div className="space-y-1">
          {activity.map((entry) => (
            <div
              key={entry.id}
              className={cn(
                "flex items-center justify-between rounded-lg px-4 py-2 text-sm",
                entry.status === "success"
                  ? "bg-emerald-50 dark:bg-emerald-900/10"
                  : "bg-red-50 dark:bg-red-900/10"
              )}
            >
              <div className="flex items-center gap-3">
                <span>
                  {entry.status === "success" ? "\u{1F7E2}" : "\u{1F534}"}
                </span>
                <span className="font-medium text-gray-800 dark:text-gray-200">
                  {entry.job_label_fa || entry.job_name}
                </span>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-[10px]",
                    CATEGORY_COLORS[entry.job_category] || CATEGORY_COLORS.general
                  )}
                >
                  {CATEGORY_LABELS[entry.job_category] || entry.job_category}
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                <span>{entry.items_processed} آیتم</span>
                {entry.duration_ms != null && (
                  <span>{formatDuration(entry.duration_ms)}</span>
                )}
                <span>{timeAgo(entry.started_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ────────────────────────────────────────────────────────────────────── */
/*  Helpers                                                               */
/* ────────────────────────────────────────────────────────────────────── */

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}
