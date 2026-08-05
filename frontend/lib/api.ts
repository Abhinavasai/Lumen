import type { Job, AppliedJob, AppConfig, SetupStatus, DashboardStats } from "@/types";

const BASE = "/api";

async function fetchJSON<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(url, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json();
}

export async function getTopJobs(topN: number): Promise<Job[]> {
  return fetchJSON(`${BASE}/jobs?top_n=${topN}`);
}

export async function getAllJobs(): Promise<Job[]> {
  return fetchJSON(`${BASE}/jobs`);
}

export async function getAppliedJobs(): Promise<AppliedJob[]> {
  return fetchJSON(`${BASE}/applied`);
}

export async function getStats(topN?: number): Promise<DashboardStats> {
  const params = topN ? `?top_n=${topN}` : "";
  return fetchJSON(`${BASE}/stats${params}`);
}

export async function applyJob(job: Job): Promise<void> {
  await fetchJSON(`${BASE}/apply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(job),
  });
}

export async function dismissJob(job: Job): Promise<void> {
  await fetchJSON(`${BASE}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(job),
  });
}

export async function applyAll(jobs: Job[]): Promise<void> {
  await fetchJSON(`${BASE}/apply-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(jobs),
  });
}

export async function runPipeline(): Promise<{ message: string }> {
  return fetchJSON(`${BASE}/pipeline/run`, { method: "POST" });
}

export async function autoApply(dryRun: boolean = false, source?: string): Promise<{ message: string }> {
  const params = new URLSearchParams();
  if (dryRun) params.set("dry_run", "true");
  if (source) params.set("source", source);
  const qs = params.toString();
  return fetchJSON(`${BASE}/auto-apply${qs ? `?${qs}` : ""}`, { method: "POST" });
}

export interface AutoApplyResult {
  source_job_id: string;
  title: string;
  company: string;
  url: string;
  applied_at: string;
  platform?: string;
  status?: string;
  error?: string;
}

export async function getAutoApplyResults(status?: string): Promise<AutoApplyResult[]> {
  const params = status ? `?status=${status}` : "";
  return fetchJSON(`${BASE}/auto-apply/results${params}`);
}

export interface AutoApplyStatus {
  total: number;
  by_status: Record<string, number>;
  by_platform: Record<string, number>;
}

export async function getAutoApplyStatus(): Promise<AutoApplyStatus> {
  return fetchJSON(`${BASE}/auto-apply/status`);
}

export interface AutoApplyProgress {
  running: boolean;
  started_at?: string;
  finished_at?: string;
  dry_run?: boolean;
  current: number;
  total: number;
  current_job: { title: string; company: string; source: string } | null;
  applied: number;
  skipped: number;
  failed: number;
  results: Array<{
    title: string;
    company: string;
    source: string;
    status: string;
    error: string;
  }>;
}

export async function getAutoApplyProgress(): Promise<AutoApplyProgress> {
  return fetchJSON(`${BASE}/auto-apply/progress`);
}

export async function listResumes(): Promise<string[]> {
  return fetchJSON(`${BASE}/resumes/list`);
}

export async function singleApply(url: string, resumeName: string, coverLetterPath?: string, dryRun?: boolean): Promise<{
  ok: boolean;
  platform: string;
  message: string;
}> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5 * 60 * 1000);
  try {
    return await fetchJSON(`${BASE}/auto-apply/single`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url,
        resume_name: resumeName,
        cover_letter_path: coverLetterPath || "",
        dry_run: dryRun || false,
      }),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function buildAllResumes(): Promise<{ message: string }> {
  return fetchJSON(`${BASE}/resumes/build-all`, { method: "POST" });
}

export async function generateResume(job: {
  title: string;
  company: string;
  location: string;
  url: string;
  description: string;
}): Promise<{ success: boolean; pdf_path?: string; error?: string; stdout?: string }> {
  return fetchJSON(`${BASE}/resumes/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(job),
  });
}

export async function extractJobFields(description: string): Promise<{
  title: string;
  company: string;
  location: string;
  url: string;
  error?: string;
}> {
  return fetchJSON(`${BASE}/extract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ description }),
  });
}

export async function getConfig(): Promise<AppConfig> {
  return fetchJSON(`${BASE}/config`);
}

export async function updateConfig(config: Partial<AppConfig>): Promise<void> {
  await fetchJSON(`${BASE}/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
}

export async function getSetupStatus(): Promise<SetupStatus> {
  return fetchJSON(`${BASE}/setup/status`);
}

export async function getProfile(): Promise<{ content: string }> {
  return fetchJSON(`${BASE}/profile`);
}

export async function saveProfile(content: string): Promise<void> {
  await fetchJSON(`${BASE}/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export async function getBaseYaml(): Promise<{ content: string }> {
  return fetchJSON(`${BASE}/yaml`);
}

export async function saveBaseYaml(content: string): Promise<void> {
  await fetchJSON(`${BASE}/yaml`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
}

export async function saveApiKeys(keys: Record<string, string>): Promise<void> {
  await fetchJSON(`${BASE}/keys`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(keys),
  });
}
