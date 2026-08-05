import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function scoreColor(score: number | null | undefined) {
  if (!score) return "muted";
  if (score >= 8) return "success";
  if (score >= 6) return "warning";
  return "danger";
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return "N/A";
  return dateStr.slice(0, 10);
}
