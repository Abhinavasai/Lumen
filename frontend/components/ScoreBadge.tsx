"use client";

import { Badge } from "@/components/ui/badge";
import { scoreColor } from "@/lib/utils";

interface ScoreBadgeProps {
  score: number | null | undefined;
}

export default function ScoreBadge({ score }: ScoreBadgeProps) {
  if (score == null) {
    return (
      <Badge variant="outline" className="text-xs">
        N/A
      </Badge>
    );
  }

  const color = scoreColor(score);
  const variant =
    color === "success"
      ? "success"
      : color === "warning"
      ? "warning"
      : color === "danger"
      ? "danger"
      : "outline";

  return (
    <Badge variant={variant} className="text-xs font-bold tabular-nums">
      {score.toFixed(1)}
    </Badge>
  );
}
