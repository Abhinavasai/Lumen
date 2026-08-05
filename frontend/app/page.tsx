"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { motion } from "framer-motion";
import Link from "next/link";
import { Briefcase, TrendingUp, Trophy, CheckCircle2, Play, RefreshCw, FileStack, Loader2, Rocket, AlertTriangle, Send, XCircle, SkipForward } from "lucide-react";
import { getTopJobs, getStats, applyJob, dismissJob, applyAll, runPipeline, buildAllResumes, autoApply, getAutoApplyStatus, getAutoApplyProgress } from "@/lib/api";
import type { AutoApplyStatus, AutoApplyProgress } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import StatCard from "@/components/StatCard";
import JobCard from "@/components/JobCard";
import type { Job, DashboardStats } from "@/types";

export default function DashboardPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const [resumesRunning, setResumesRunning] = useState(false);
  const [autoApplyRunning, setAutoApplyRunning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [applyStatus, setApplyStatus] = useState<AutoApplyStatus | null>(null);
  const [progress, setProgress] = useState<AutoApplyProgress | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  async function loadData() {
    try {
      const [jobsData, statsData, applyStatusData] = await Promise.all([
        getTopJobs(25),
        getStats(25),
        getAutoApplyStatus().catch(() => null),
      ]);
      setJobs(jobsData);
      setStats(statsData);
      setApplyStatus(applyStatusData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadData(); }, []);

  async function handleRunPipeline() {
    setPipelineRunning(true);
    try {
      await runPipeline();
    } catch (err) {
      console.error("Pipeline error:", err);
    } finally {
      setPipelineRunning(false);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    await loadData();
    setRefreshing(false);
  }

  async function handleBuildResumes() {
    setResumesRunning(true);
    try {
      await buildAllResumes();
    } catch (err) {
      console.error("Resume build error:", err);
    } finally {
      setResumesRunning(false);
    }
  }

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const p = await getAutoApplyProgress();
        setProgress(p);
        if (!p.running) {
          stopPolling();
          setAutoApplyRunning(false);
          loadData();
        }
      } catch {
        // ignore polling errors
      }
    }, 2000);
  }, [stopPolling]);

  useEffect(() => {
    return () => stopPolling();
  }, [stopPolling]);

  useEffect(() => {
    getAutoApplyProgress()
      .then((p) => {
        if (p.running) {
          setProgress(p);
          setAutoApplyRunning(true);
          startPolling();
        }
      })
      .catch(() => {});
  }, [startPolling]);

  async function handleAutoApply() {
    setAutoApplyRunning(true);
    setProgress(null);
    try {
      await autoApply(false);
      startPolling();
    } catch (err) {
      console.error("Auto-apply error:", err);
      setAutoApplyRunning(false);
    }
  }

  async function handleApply(job: Job) {
    try {
      await applyJob(job);
      window.open(job.url, "_blank");
      setJobs((prev) => prev.filter((j) => j.source_job_id !== job.source_job_id));
    } catch (err) {
      console.error("Failed to apply:", err);
    }
  }

  async function handleDismiss(job: Job) {
    try {
      await dismissJob(job);
      setJobs((prev) => prev.filter((j) => j.source_job_id !== job.source_job_id));
    } catch (err) {
      console.error("Failed to dismiss:", err);
    }
  }

  async function handleOpenAll() {
    try {
      await applyAll(jobs);
      jobs.forEach((job) => window.open(job.url, "_blank"));
    } catch (err) {
      console.error("Failed to apply all:", err);
    }
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-9 w-48 mb-2" />
          <Skeleton className="h-5 w-80" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-28 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-px w-full" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <div className="glass-card p-6 text-center">
          <p className="text-danger-light text-sm">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="space-y-6"
    >
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold gradient-text">Dashboard</h1>
        <p className="text-sm text-text-muted mt-1">
          AI-ranked top picks from your latest pipeline run
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={handleRunPipeline} disabled={pipelineRunning}>
          {pipelineRunning ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Play className="mr-2 h-4 w-4" />
          )}
          Run Pipeline
        </Button>
        <Button onClick={handleRefresh} disabled={refreshing}>
          {refreshing ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="mr-2 h-4 w-4" />
          )}
          Refresh Results
        </Button>
        <Button onClick={handleBuildResumes} disabled={resumesRunning}>
          {resumesRunning ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <FileStack className="mr-2 h-4 w-4" />
          )}
          Build All Resumes
        </Button>
        <Button variant="primary" onClick={handleAutoApply} disabled={autoApplyRunning}>
          {autoApplyRunning ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Rocket className="mr-2 h-4 w-4" />
          )}
          Auto Apply
        </Button>
      </div>

      {/* Auto-Apply Progress */}
      {progress && (progress.running || (progress.total > 0 && progress.results?.length > 0)) && (
        <div className="glass-card p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {progress.running ? (
                <Loader2 className="h-4 w-4 animate-spin text-primary" />
              ) : (
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              )}
              <h3 className="text-sm font-semibold text-text-primary">
                {progress.running
                  ? `Applying... ${progress.current} / ${progress.total}`
                  : `Auto-Apply Complete`}
              </h3>
            </div>
            <div className="flex items-center gap-3 text-xs">
              {progress.applied > 0 && (
                <span className="flex items-center gap-1 text-emerald-600">
                  <CheckCircle2 className="h-3 w-3" /> {progress.applied}
                </span>
              )}
              {progress.failed > 0 && (
                <span className="flex items-center gap-1 text-red-600">
                  <XCircle className="h-3 w-3" /> {progress.failed}
                </span>
              )}
              {progress.skipped > 0 && (
                <span className="flex items-center gap-1 text-text-muted">
                  <SkipForward className="h-3 w-3" /> {progress.skipped}
                </span>
              )}
            </div>
          </div>

          {/* Progress bar */}
          <div className="w-full bg-slate-100 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${
                progress.running ? "bg-indigo-500" : "bg-emerald-500"
              }`}
              style={{ width: `${progress.total > 0 ? (progress.current / progress.total) * 100 : 0}%` }}
            />
          </div>

          {/* Current job */}
          {progress.running && progress.current_job && (
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <Loader2 className="h-3 w-3 animate-spin" />
              <span>
                {progress.current_job.title} @ {progress.current_job.company}
              </span>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">{progress.current_job.source}</Badge>
            </div>
          )}

          {/* Recent results (last 5) */}
          {progress.results?.length > 0 && (
            <div className="space-y-1.5 max-h-40 overflow-y-auto">
              {progress.results.slice(-5).reverse().map((r, idx) => (
                <div key={idx} className="flex items-center gap-2 text-xs">
                  {r.status === "submitted" || r.status === "dry_run" ? (
                    <CheckCircle2 className="h-3 w-3 text-emerald-500 shrink-0" />
                  ) : r.status === "skipped" ? (
                    <SkipForward className="h-3 w-3 text-slate-400 shrink-0" />
                  ) : (
                    <XCircle className="h-3 w-3 text-red-500 shrink-0" />
                  )}
                  <span className="text-text-secondary truncate">
                    {r.title} @ {r.company}
                  </span>
                  {r.error && r.status !== "skipped" && (
                    <span className="text-red-500 truncate ml-auto">{r.error.slice(0, 50)}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            title="Total Jobs"
            value={stats.total_jobs}
            icon={Briefcase}
            subtitle={`From ${Object.keys(stats.sources).length} sources`}
          />
          <StatCard
            title="Avg Score"
            value={stats.avg_score.toFixed(1)}
            icon={TrendingUp}
          />
          <StatCard
            title="Top Score"
            value={stats.top_score.toFixed(1)}
            icon={Trophy}
          />
          <StatCard
            title="Applied"
            value={stats.applied_count}
            icon={CheckCircle2}
            subtitle={stats.last_run ? `Last run: ${stats.last_run.slice(0, 10)}` : undefined}
          />
        </div>
      )}

      {/* Auto-Apply Tracker */}
      {applyStatus && applyStatus.total > 0 && (
        <Link href="/applied" className="block">
          <div className="glass-card p-4 hover:bg-slate-50 transition-colors cursor-pointer">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Send className="h-5 w-5 text-primary" />
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Auto-Apply Results</h3>
                  <div className="flex items-center gap-4 mt-1">
                    <span className="text-xs text-text-muted">
                      <span className="font-semibold text-text-primary">{applyStatus.total}</span> total
                    </span>
                    {(applyStatus.by_status.submitted ?? 0) > 0 && (
                      <span className="inline-flex items-center gap-1 text-xs">
                        <CheckCircle2 className="h-3 w-3 text-emerald-500" />
                        <span className="text-emerald-700 font-medium">{applyStatus.by_status.submitted} submitted</span>
                      </span>
                    )}
                    {((applyStatus.by_status.failed ?? 0) + (applyStatus.by_status.error ?? 0)) > 0 && (
                      <span className="inline-flex items-center gap-1 text-xs">
                        <AlertTriangle className="h-3 w-3 text-red-500" />
                        <span className="text-red-700 font-medium">
                          {(applyStatus.by_status.failed ?? 0) + (applyStatus.by_status.error ?? 0)} failed
                        </span>
                      </span>
                    )}
                  </div>
                </div>
              </div>
              <span className="text-xs text-primary-light font-medium">View details &rarr;</span>
            </div>
          </div>
        </Link>
      )}

      {/* Open All Button */}
      {jobs.length > 0 && (
        <div>
          <Button variant="primary" onClick={handleOpenAll}>
            Open all {jobs.length} jobs
          </Button>
        </div>
      )}

      <Separator />

      {/* Job List */}
      <div className="space-y-3">
        {jobs.length === 0 ? (
          <div className="glass-card p-8 text-center">
            <p className="text-text-muted text-sm">
              No top picks available. Run the pipeline to fetch and rank jobs.
            </p>
          </div>
        ) : (
          jobs.map((job) => (
            <JobCard
              key={job.source_job_id}
              job={job}
              onApply={handleApply}
              onDismiss={handleDismiss}
            />
          ))
        )}
      </div>
    </motion.div>
  );
}
