"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Rocket,
  Loader2,
  CheckCircle2,
  XCircle,
  FileText,
  Link2,
  Upload,
} from "lucide-react";
import { listResumes, singleApply } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";

const DEFAULT_COVER_LETTER =
  "C:\\Users\\tirun\\OneDrive\\Desktop\\Job Applications\\April\\Cover Letters\\CoverLetter.docx";

interface ApplyResult {
  ok: boolean;
  platform: string;
  message: string;
  url: string;
  resume: string;
  timestamp: string;
}

export default function AutoApplyPage() {
  const [url, setUrl] = useState("");
  const [resumes, setResumes] = useState<string[]>([]);
  const [selectedResume, setSelectedResume] = useState("");
  const [coverLetter, setCoverLetter] = useState(DEFAULT_COVER_LETTER);
  const [applying, setApplying] = useState(false);
  const [results, setResults] = useState<ApplyResult[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    listResumes().then((list) => {
      setResumes(list);
    }).catch(console.error);
  }, []);

  const filteredResumes = filter
    ? resumes.filter((r) => r.toLowerCase().includes(filter.toLowerCase()))
    : resumes;

  async function handleApply() {
    if (!url.trim()) return;
    if (!selectedResume) return;

    setApplying(true);
    try {
      const result = await singleApply(url.trim(), selectedResume, coverLetter);
      setResults((prev) => [
        {
          ...result,
          url: url.trim(),
          resume: selectedResume,
          timestamp: new Date().toLocaleTimeString(),
        },
        ...prev,
      ]);
      if (result.ok) {
        setUrl("");
      }
    } catch (err) {
      setResults((prev) => [
        {
          ok: false,
          platform: "unknown",
          message: err instanceof Error ? err.message : "Request failed",
          url: url.trim(),
          resume: selectedResume,
          timestamp: new Date().toLocaleTimeString(),
        },
        ...prev,
      ]);
    } finally {
      setApplying(false);
    }
  }

  function detectPlatform(jobUrl: string): string {
    if (/greenhouse\.io/i.test(jobUrl)) return "greenhouse";
    if (/lever\.co/i.test(jobUrl)) return "lever";
    if (/ashbyhq\.com/i.test(jobUrl)) return "ashby";
    if (/myworkdayjobs\.com/i.test(jobUrl)) return "workday";
    if (/smartrecruiters\.com/i.test(jobUrl)) return "smartrecruiters";
    if (/workable\.com/i.test(jobUrl)) return "workable";
    if (/bamboohr\.com/i.test(jobUrl)) return "bamboohr";
    return "";
  }

  const detectedPlatform = detectPlatform(url);
  const isBrowserPlatform = ["ashby", "workable"].includes(detectedPlatform);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: "easeOut" }}
      className="space-y-6"
    >
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold gradient-text">Auto Apply</h1>
        <p className="text-sm text-text-muted mt-1">
          Paste a job link, pick your resume, and submit instantly
        </p>
      </div>

      {/* Apply Form */}
      <div className="glass-card p-6 space-y-5">
        {/* Job URL */}
        <div className="space-y-2">
          <Label className="flex items-center gap-2 text-sm font-medium">
            <Link2 className="h-4 w-4" />
            Job URL
          </Label>
          <div className="flex gap-3">
            <Input
              placeholder="https://boards.greenhouse.io/company/jobs/123456"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="flex-1"
            />
            {detectedPlatform && (
              <Badge variant="success" className="shrink-0 self-center">
                {detectedPlatform}
              </Badge>
            )}
            {url && !detectedPlatform && (
              <Badge variant="danger" className="shrink-0 self-center">
                Unknown platform
              </Badge>
            )}
          </div>
          {isBrowserPlatform && (
            <div className="text-xs mt-1 space-y-1">
              <p className="text-indigo-600">
                Opens a tab in your Chrome (with your real profile) to fill the form. You may need to solve a reCAPTCHA.
              </p>
              <p className="text-amber-600 font-medium">
                Chrome may restart briefly to enable the connection — save any unsaved work first.
              </p>
            </div>
          )}
        </div>

        {/* Resume Picker */}
        <div className="space-y-2">
          <Label className="flex items-center gap-2 text-sm font-medium">
            <FileText className="h-4 w-4" />
            Resume ({resumes.length} available)
          </Label>
          <Input
            placeholder="Search resumes..."
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="mb-2"
          />
          <div className="max-h-48 overflow-y-auto border rounded-lg divide-y divide-slate-100">
            {filteredResumes.length === 0 ? (
              <div className="p-3 text-sm text-text-muted text-center">
                {resumes.length === 0
                  ? "No resumes found. Build resumes first."
                  : "No matches"}
              </div>
            ) : (
              filteredResumes.map((name) => (
                <button
                  key={name}
                  onClick={() => setSelectedResume(name)}
                  className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                    selectedResume === name
                      ? "bg-indigo-50 text-primary-light font-medium"
                      : "hover:bg-slate-50 text-text-secondary"
                  }`}
                >
                  {name.replace(".pdf", "")}
                </button>
              ))
            )}
          </div>
          {selectedResume && (
            <p className="text-xs text-primary-light font-medium mt-1">
              Selected: {selectedResume}
            </p>
          )}
        </div>

        {/* Cover Letter */}
        <div className="space-y-2">
          <Label className="flex items-center gap-2 text-sm font-medium">
            <Upload className="h-4 w-4" />
            Cover Letter
          </Label>
          <Input
            value={coverLetter}
            onChange={(e) => setCoverLetter(e.target.value)}
          />
        </div>

        <Separator />

        {/* Apply Button */}
        <Button
          variant="primary"
          onClick={handleApply}
          disabled={applying || !url.trim() || !selectedResume || !detectedPlatform}
          className="w-full"
        >
          {applying ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Rocket className="mr-2 h-4 w-4" />
          )}
          {applying
            ? isBrowserPlatform
              ? "Browser is filling the form..."
              : "Applying..."
            : !url.trim()
            ? "Paste a job URL to start"
            : !selectedResume
            ? "Select a resume"
            : !detectedPlatform
            ? "Unsupported platform"
            : isBrowserPlatform
            ? `Apply via ${detectedPlatform} (opens browser)`
            : `Apply via ${detectedPlatform}`}
        </Button>
      </div>

      {/* Results */}
      {results.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-text-primary">Results</h2>
          {results.map((r, idx) => (
            <div key={idx} className="glass-card p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="flex items-center gap-2 min-w-0">
                  {r.ok ? (
                    <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
                  ) : (
                    <XCircle className="h-5 w-5 text-red-500 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant={r.ok ? "success" : "danger"}>
                        {r.ok ? "Submitted" : "Failed"}
                      </Badge>
                      {r.platform && (
                        <Badge variant="outline">{r.platform}</Badge>
                      )}
                      <span className="text-xs text-text-muted">{r.timestamp}</span>
                    </div>
                    <p className="text-sm text-text-secondary mt-1 truncate">{r.url}</p>
                    <p className="text-xs text-text-muted mt-0.5">Resume: {r.resume}</p>
                    {!r.ok && r.message && (
                      <p className="text-xs text-red-600 mt-1 font-mono">{r.message}</p>
                    )}
                  </div>
                </div>
                {!r.ok && r.url && (
                  <a href={r.url} target="_blank" rel="noopener noreferrer">
                    <Button className="text-xs shrink-0">Open Link</Button>
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}
