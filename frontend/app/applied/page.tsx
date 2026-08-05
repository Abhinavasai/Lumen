"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { ExternalLink, Info, AlertTriangle, CheckCircle2, Eye } from "lucide-react";
import { getAutoApplyResults } from "@/lib/api";
import type { AutoApplyResult } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { formatDate } from "@/lib/utils";

type StatusFilter = "all" | "failed" | "submitted" | "dry_run";

function statusBadge(status?: string) {
  switch (status) {
    case "submitted":
      return <Badge variant="success">Submitted</Badge>;
    case "failed":
    case "error":
      return <Badge variant="danger">Failed</Badge>;
    case "dry_run":
      return <Badge variant="warning">Dry Run</Badge>;
    default:
      return <Badge variant="outline">{status || "unknown"}</Badge>;
  }
}

export default function AppliedJobsPage() {
  const [jobs, setJobs] = useState<AutoApplyResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    async function load() {
      try {
        const data = await getAutoApplyResults();
        setJobs(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load applied jobs");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const submitted = jobs.filter((j) => j.status === "submitted");
  const failed = jobs.filter((j) => j.status === "failed" || j.status === "error");
  const dryRuns = jobs.filter((j) => j.status === "dry_run");

  const displayed =
    filter === "failed"
      ? failed
      : filter === "submitted"
      ? submitted
      : filter === "dry_run"
      ? dryRuns
      : jobs;

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-9 w-44 mb-2" />
          <Skeleton className="h-5 w-64" />
        </div>
        <Skeleton className="h-64 rounded-xl" />
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
      <div className="flex items-center gap-3">
        <h1 className="text-3xl font-bold gradient-text">Applied Jobs</h1>
        <Badge variant="default">{jobs.length}</Badge>
      </div>

      {/* Stats Row */}
      {jobs.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <button
            onClick={() => setFilter("all")}
            className={`glass-card p-4 text-center transition-all cursor-pointer ${
              filter === "all" ? "ring-2 ring-indigo-300" : "hover:bg-slate-50"
            }`}
          >
            <div className="text-2xl font-bold text-text-primary">{jobs.length}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Total</div>
          </button>
          <button
            onClick={() => setFilter("submitted")}
            className={`glass-card p-4 text-center transition-all cursor-pointer ${
              filter === "submitted" ? "ring-2 ring-emerald-300" : "hover:bg-slate-50"
            }`}
          >
            <div className="text-2xl font-bold text-success-light">{submitted.length}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Submitted</div>
          </button>
          <button
            onClick={() => setFilter("failed")}
            className={`glass-card p-4 text-center transition-all cursor-pointer ${
              filter === "failed" ? "ring-2 ring-red-300" : "hover:bg-slate-50"
            }`}
          >
            <div className="text-2xl font-bold text-danger-light">{failed.length}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Failed</div>
          </button>
          <button
            onClick={() => setFilter("dry_run")}
            className={`glass-card p-4 text-center transition-all cursor-pointer ${
              filter === "dry_run" ? "ring-2 ring-amber-300" : "hover:bg-slate-50"
            }`}
          >
            <div className="text-2xl font-bold text-warning-light">{dryRuns.length}</div>
            <div className="text-xs text-text-muted uppercase tracking-wider">Dry Runs</div>
          </button>
        </div>
      )}

      {/* Failed Banner */}
      {failed.length > 0 && (filter === "all" || filter === "failed") && (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-red-50 border border-red-200">
          <AlertTriangle className="h-5 w-5 text-danger-light shrink-0" />
          <p className="text-sm text-danger-light">
            <span className="font-semibold">{failed.length} job(s) failed auto-apply.</span>{" "}
            Click &quot;Apply Manually&quot; to open the job posting.
          </p>
        </div>
      )}

      <Separator />

      {/* Job List */}
      {displayed.length === 0 ? (
        <div className="glass-card p-8 text-center">
          <Info className="h-8 w-8 text-text-muted mx-auto mb-3" />
          <p className="text-text-muted text-sm">
            {filter === "all"
              ? "No applied jobs yet. Run Auto Apply from the Dashboard."
              : `No ${filter === "failed" ? "failed" : filter === "submitted" ? "submitted" : "dry run"} jobs.`}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {displayed.map((job) => (
            <div key={job.source_job_id} className="glass-card p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    {statusBadge(job.status)}
                    {job.platform && (
                      <Badge variant="outline">{job.platform}</Badge>
                    )}
                    <span className="text-xs text-text-muted">
                      {formatDate(job.applied_at)}
                    </span>
                  </div>
                  <h3 className="font-semibold text-text-primary mt-1.5 truncate">
                    {job.title}
                  </h3>
                  <p className="text-sm text-text-secondary">{job.company}</p>
                  {job.error && (
                    <div className="mt-2 p-2.5 rounded-lg bg-red-50 border border-red-100">
                      <p className="text-xs text-danger-light font-mono">{job.error}</p>
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {(job.status === "failed" || job.status === "error") && job.url ? (
                    <a href={job.url} target="_blank" rel="noopener noreferrer">
                      <Button variant="primary" className="text-xs">
                        Apply Manually
                        <ExternalLink className="ml-1.5 h-3 w-3" />
                      </Button>
                    </a>
                  ) : job.url ? (
                    <a href={job.url} target="_blank" rel="noopener noreferrer">
                      <Button className="text-xs">
                        <Eye className="mr-1.5 h-3 w-3" />
                        View
                      </Button>
                    </a>
                  ) : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
