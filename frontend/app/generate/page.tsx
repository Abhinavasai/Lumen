"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { FileText, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { extractJobFields, generateResume } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";

interface FormFields {
  title: string;
  company: string;
  location: string;
  url: string;
  description: string;
}

export default function GenerateResumePage() {
  const [step, setStep] = useState<1 | 2>(1);
  const [rawDescription, setRawDescription] = useState("");
  const [fields, setFields] = useState<FormFields>({
    title: "",
    company: "",
    location: "",
    url: "",
    description: "",
  });
  const [extracting, setExtracting] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState<{
    success: boolean;
    pdf_path?: string;
    error?: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExtract() {
    if (!rawDescription.trim()) return;
    setExtracting(true);
    setError(null);
    try {
      const extracted = await extractJobFields(rawDescription);
      if (extracted.error) {
        setError(extracted.error);
        return;
      }
      setFields({
        title: extracted.title || "",
        company: extracted.company || "",
        location: extracted.location || "",
        url: extracted.url || "",
        description: rawDescription,
      });
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to extract fields");
    } finally {
      setExtracting(false);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setResult(null);
    setError(null);
    try {
      const res = await generateResume({
        title: fields.title,
        company: fields.company,
        location: fields.location,
        url: fields.url,
        description: fields.description,
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate resume");
    } finally {
      setGenerating(false);
    }
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
        <h1 className="text-3xl font-bold gradient-text">Generate Resume</h1>
        <p className="text-sm text-text-muted mt-1">
          Paste a job description to create a tailored resume
        </p>
      </div>

      {/* Step Indicator */}
      <div className="flex items-center gap-3">
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors ${
            step >= 1
              ? "bg-primary text-white"
              : "bg-slate-200 text-text-muted"
          }`}
        >
          1
        </div>
        <div
          className={`h-px flex-1 transition-colors ${
            step >= 2 ? "bg-primary" : "bg-slate-200"
          }`}
        />
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold transition-colors ${
            step >= 2
              ? "bg-primary text-white"
              : "bg-slate-200 text-text-muted"
          }`}
        >
          2
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-danger-light">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      {/* Step 1: Paste JD */}
      {step === 1 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary-light" />
              Paste Job Description
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <Textarea
              placeholder="Paste the full job description here..."
              value={rawDescription}
              onChange={(e) => setRawDescription(e.target.value)}
              className="min-h-[200px] font-mono text-xs"
            />
            <Button
              variant="primary"
              onClick={handleExtract}
              disabled={extracting || !rawDescription.trim()}
            >
              {extracting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Extracting Fields...
                </>
              ) : (
                "Extract Fields"
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Review & Generate */}
      {step === 2 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-primary-light" />
              Review & Generate
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="title">Job Title</Label>
                <Input
                  id="title"
                  value={fields.title}
                  onChange={(e) =>
                    setFields((prev) => ({ ...prev, title: e.target.value }))
                  }
                  placeholder="e.g. Senior Software Engineer"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="company">Company</Label>
                <Input
                  id="company"
                  value={fields.company}
                  onChange={(e) =>
                    setFields((prev) => ({ ...prev, company: e.target.value }))
                  }
                  placeholder="e.g. Google"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="location">Location</Label>
                <Input
                  id="location"
                  value={fields.location}
                  onChange={(e) =>
                    setFields((prev) => ({ ...prev, location: e.target.value }))
                  }
                  placeholder="e.g. San Francisco, CA"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="url">Job URL</Label>
                <Input
                  id="url"
                  value={fields.url}
                  onChange={(e) =>
                    setFields((prev) => ({ ...prev, url: e.target.value }))
                  }
                  placeholder="https://..."
                />
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <Button
                variant="ghost"
                onClick={() => setStep(1)}
              >
                Back
              </Button>
              <Button
                variant="primary"
                onClick={handleGenerate}
                disabled={generating}
              >
                {generating ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Generating Resume...
                  </>
                ) : (
                  "Generate Resume"
                )}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Result */}
      {result && (
        <Card>
          <CardContent className="pt-6">
            {result.success ? (
              <div className="flex items-start gap-3">
                <CheckCircle2 className="h-5 w-5 text-success-light shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-success-light">
                    Resume generated successfully!
                  </p>
                  {result.pdf_path && (
                    <p className="text-xs text-text-muted mt-1 font-mono">
                      Saved to: {result.pdf_path}
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="flex items-start gap-3">
                <AlertCircle className="h-5 w-5 text-danger-light shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-danger-light">
                    Resume generation failed
                  </p>
                  {result.error && (
                    <p className="text-xs text-text-muted mt-1">{result.error}</p>
                  )}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}
