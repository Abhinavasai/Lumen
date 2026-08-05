"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import ScoreBadge from "@/components/ScoreBadge";
import { formatDate } from "@/lib/utils";
import { ExternalLink, Check, X, MapPin, Building2, Calendar } from "lucide-react";
import type { Job } from "@/types";

interface JobCardProps {
  job: Job;
  showScore?: boolean;
  onApply?: (job: Job) => void;
  onDismiss?: (job: Job) => void;
}

export default function JobCard({ job, showScore = true, onApply, onDismiss }: JobCardProps) {
  return (
    <Card className="p-5 transition-all hover:border-primary/20">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-text-primary truncate">
              {job.title}
            </h3>
            {showScore && <ScoreBadge score={job.ai_score} />}
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted mt-1.5">
            <span className="flex items-center gap-1">
              <Building2 className="h-3 w-3" />
              {job.company}
            </span>
            <span className="flex items-center gap-1">
              <MapPin className="h-3 w-3" />
              {job.location || "Remote"}
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {formatDate(job.posted_at)}
            </span>
            <span className="text-text-muted/50">
              {job.source}
            </span>
          </div>

          {job.ai_reason && (
            <p className="text-xs text-text-secondary mt-2 line-clamp-2">
              {job.ai_reason}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => window.open(job.url, "_blank")}
            title="Open job listing"
          >
            <ExternalLink className="h-4 w-4" />
          </Button>

          {onApply && (
            <Button
              variant="success"
              size="icon"
              onClick={() => onApply(job)}
              title="Mark as applied"
            >
              <Check className="h-4 w-4" />
            </Button>
          )}

          {onDismiss && (
            <Button
              variant="danger"
              size="icon"
              onClick={() => onDismiss(job)}
              title="Dismiss"
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </Card>
  );
}
