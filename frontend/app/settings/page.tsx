"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Save,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Shield,
} from "lucide-react";
import yaml from "js-yaml";
import {
  getConfig,
  updateConfig,
  getProfile,
  saveProfile,
  getBaseYaml,
  saveBaseYaml,
  saveApiKeys,
  getSetupStatus,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { AppConfig, SetupStatus } from "@/types";

interface Toast {
  message: string;
  type: "success" | "error";
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);

  // Config state
  const [keywords, setKeywords] = useState("");
  const [maxResults, setMaxResults] = useState(50);
  const [location, setLocation] = useState("");
  const [postedWithin, setPostedWithin] = useState(72);
  const [topN, setTopN] = useState(25);
  const [minScore, setMinScore] = useState(6);
  const [savingConfig, setSavingConfig] = useState(false);

  // Profile state
  const [profileContent, setProfileContent] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);

  // YAML state
  const [yamlContent, setYamlContent] = useState("");
  const [savingYaml, setSavingYaml] = useState(false);

  // API keys state
  const [azureEndpoint, setAzureEndpoint] = useState("");
  const [azureDeployment, setAzureDeployment] = useState("");
  const [azureKey, setAzureKey] = useState("");
  const [apifyToken, setApifyToken] = useState("");
  const [adzunaId, setAdzunaId] = useState("");
  const [adzunaKey, setAdzunaKey] = useState("");
  const [openaiKey, setOpenaiKey] = useState("");
  const [savingKeys, setSavingKeys] = useState(false);

  // Greenhouse state
  const [greenhouseSlugs, setGreenhouseSlugs] = useState("");
  const [savingGreenhouse, setSavingGreenhouse] = useState(false);

  // Setup status
  const [setupStatus, setSetupStatus] = useState<SetupStatus | null>(null);

  const showToast = useCallback((message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const [config, profile, yamlData, status] = await Promise.all([
          getConfig(),
          getProfile(),
          getBaseYaml(),
          getSetupStatus(),
        ]);

        // Populate config
        setKeywords(config.keywords.join("\n"));
        setMaxResults(config.filters.max_results);
        setLocation(config.filters.location);
        setPostedWithin(config.filters.posted_within_hours);
        setTopN(config.ai_ranking.top_n);
        setMinScore(config.ai_ranking.min_score);
        setGreenhouseSlugs(config.greenhouse_companies.join("\n"));

        // Azure config (non-secret)
        setAzureEndpoint(config.azure_openai.endpoint);
        setAzureDeployment(config.azure_openai.deployment);

        // Profile & YAML
        setProfileContent(profile.content);
        setYamlContent(yamlData.content);

        // Setup status
        setSetupStatus(status);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load settings");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  async function handleSaveConfig() {
    setSavingConfig(true);
    try {
      const config: Partial<AppConfig> = {
        keywords: keywords
          .split("\n")
          .map((k) => k.trim())
          .filter(Boolean),
        filters: {
          max_results: maxResults,
          location,
          posted_within_hours: postedWithin,
        },
        ai_ranking: {
          top_n: topN,
          min_score: minScore,
        },
      };
      await updateConfig(config);
      showToast("Pipeline configuration saved", "success");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to save config",
        "error"
      );
    } finally {
      setSavingConfig(false);
    }
  }

  async function handleSaveProfile() {
    setSavingProfile(true);
    try {
      await saveProfile(profileContent);
      showToast("Profile saved", "success");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to save profile",
        "error"
      );
    } finally {
      setSavingProfile(false);
    }
  }

  async function handleSaveYaml() {
    setSavingYaml(true);
    try {
      // Validate YAML
      yaml.load(yamlContent);
      await saveBaseYaml(yamlContent);
      showToast("Base resume YAML saved", "success");
    } catch (err) {
      if (err instanceof yaml.YAMLException) {
        showToast(`Invalid YAML: ${err.message}`, "error");
      } else {
        showToast(
          err instanceof Error ? err.message : "Failed to save YAML",
          "error"
        );
      }
    } finally {
      setSavingYaml(false);
    }
  }

  async function handleSaveKeys() {
    setSavingKeys(true);
    try {
      const keys: Record<string, string> = {};
      if (azureEndpoint) keys.azure_endpoint = azureEndpoint;
      if (azureDeployment) keys.azure_deployment = azureDeployment;
      if (azureKey) keys.azure_api_key = azureKey;
      if (apifyToken) keys.apify_token = apifyToken;
      if (adzunaId) keys.adzuna_id = adzunaId;
      if (adzunaKey) keys.adzuna_key = adzunaKey;
      if (openaiKey) keys.openai_key = openaiKey;
      await saveApiKeys(keys);
      showToast("API keys saved", "success");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to save API keys",
        "error"
      );
    } finally {
      setSavingKeys(false);
    }
  }

  async function handleSaveGreenhouse() {
    setSavingGreenhouse(true);
    try {
      await updateConfig({
        greenhouse_companies: greenhouseSlugs
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      showToast("Greenhouse companies saved", "success");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Failed to save greenhouse companies",
        "error"
      );
    } finally {
      setSavingGreenhouse(false);
    }
  }

  const setupItems: { label: string; key: keyof SetupStatus }[] = [
    { label: "Candidate Profile", key: "profile_exists" },
    { label: "Base Resume YAML", key: "yaml_exists" },
    { label: "Environment File", key: "env_exists" },
    { label: "Azure API Key", key: "azure_key_set" },
    { label: "Apify Token", key: "apify_token_set" },
    { label: "Adzuna App ID", key: "adzuna_id_set" },
    { label: "Azure Endpoint", key: "azure_endpoint_configured" },
    { label: "Azure Deployment", key: "azure_deployment_configured" },
  ];

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <Skeleton className="h-9 w-32 mb-2" />
          <Skeleton className="h-5 w-64" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-48 rounded-xl" />
        ))}
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
      {/* Toast */}
      {toast && (
        <div
          className={`fixed top-6 right-6 z-50 flex items-center gap-2 rounded-xl border px-4 py-3 text-sm shadow-lg transition-all ${
            toast.type === "success"
              ? "border-emerald-200 bg-emerald-50 text-success-light"
              : "border-red-200 bg-red-50 text-danger-light"
          }`}
        >
          {toast.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" />
          )}
          {toast.message}
        </div>
      )}

      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold gradient-text">Settings</h1>
        <p className="text-sm text-text-muted mt-1">
          Configure your job hunting pipeline
        </p>
      </div>

      {/* Section 1: Pipeline Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Pipeline Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="keywords">Keywords (one per line)</Label>
            <Textarea
              id="keywords"
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder={"software engineer\nfrontend developer\nfull stack"}
              className="min-h-[100px]"
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="maxResults">
                Max Jobs: {maxResults}
              </Label>
              <input
                id="maxResults"
                type="range"
                min={10}
                max={200}
                step={10}
                value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer bg-slate-200 accent-primary"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="location">Location</Label>
              <Input
                id="location"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. United States"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="postedWithin">Posted Within</Label>
              <select
                id="postedWithin"
                value={postedWithin}
                onChange={(e) => setPostedWithin(Number(e.target.value))}
                className="flex h-9 w-full rounded-[10px] bg-white border border-slate-200 px-3 text-sm text-text-primary transition-colors focus:border-primary/40 focus:ring-2 focus:ring-primary/20 focus:outline-none"
              >
                <option value={24}>Last 24 hours</option>
                <option value={48}>Last 48 hours</option>
                <option value={72}>Last 72 hours</option>
                <option value={168}>Last 7 days</option>
                <option value={336}>Last 14 days</option>
                <option value={720}>Last 30 days</option>
              </select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="topN">
                Top N Results: {topN}
              </Label>
              <input
                id="topN"
                type="range"
                min={5}
                max={100}
                step={5}
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer bg-slate-200 accent-primary"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="minScore">
                Min Score: {minScore}
              </Label>
              <input
                id="minScore"
                type="range"
                min={1}
                max={10}
                step={0.5}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full h-2 rounded-full appearance-none cursor-pointer bg-slate-200 accent-primary"
              />
            </div>
          </div>

          <Button
            variant="primary"
            onClick={handleSaveConfig}
            disabled={savingConfig}
          >
            {savingConfig ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Configuration
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Section 2: Candidate Profile */}
      <Card>
        <CardHeader>
          <CardTitle>Candidate Profile</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={profileContent}
            onChange={(e) => setProfileContent(e.target.value)}
            placeholder="Paste your candidate profile text here..."
            className="min-h-[200px] font-mono text-xs"
          />
          <Button
            variant="primary"
            onClick={handleSaveProfile}
            disabled={savingProfile}
          >
            {savingProfile ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Profile
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Section 3: Base Resume YAML */}
      <Card>
        <CardHeader>
          <CardTitle>Base Resume YAML</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={yamlContent}
            onChange={(e) => setYamlContent(e.target.value)}
            placeholder="Paste your base resume YAML here..."
            className="min-h-[200px] font-mono text-xs"
          />
          <Button
            variant="primary"
            onClick={handleSaveYaml}
            disabled={savingYaml}
          >
            {savingYaml ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save YAML
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Section 4: API Keys & Endpoints */}
      <Card>
        <CardHeader>
          <CardTitle>API Keys & Endpoints</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left Column - Azure */}
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-text-secondary">
                Azure OpenAI
              </h4>
              <div className="space-y-2">
                <Label htmlFor="azureEndpoint">Endpoint</Label>
                <Input
                  id="azureEndpoint"
                  value={azureEndpoint}
                  onChange={(e) => setAzureEndpoint(e.target.value)}
                  placeholder="https://your-resource.openai.azure.com"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="azureDeployment">Deployment</Label>
                <Input
                  id="azureDeployment"
                  value={azureDeployment}
                  onChange={(e) => setAzureDeployment(e.target.value)}
                  placeholder="gpt-4o"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="azureKey">API Key</Label>
                <Input
                  id="azureKey"
                  type="password"
                  value={azureKey}
                  onChange={(e) => setAzureKey(e.target.value)}
                  placeholder="Enter Azure API key..."
                />
              </div>
            </div>

            {/* Right Column - Other Keys */}
            <div className="space-y-4">
              <h4 className="text-sm font-medium text-text-secondary">
                Other Services
              </h4>
              <div className="space-y-2">
                <Label htmlFor="apifyToken">Apify Token</Label>
                <Input
                  id="apifyToken"
                  type="password"
                  value={apifyToken}
                  onChange={(e) => setApifyToken(e.target.value)}
                  placeholder="Enter Apify token..."
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="adzunaId">Adzuna App ID</Label>
                <Input
                  id="adzunaId"
                  value={adzunaId}
                  onChange={(e) => setAdzunaId(e.target.value)}
                  placeholder="Enter Adzuna App ID..."
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="adzunaKey">Adzuna Key</Label>
                <Input
                  id="adzunaKey"
                  type="password"
                  value={adzunaKey}
                  onChange={(e) => setAdzunaKey(e.target.value)}
                  placeholder="Enter Adzuna key..."
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="openaiKey">OpenAI Key</Label>
                <Input
                  id="openaiKey"
                  type="password"
                  value={openaiKey}
                  onChange={(e) => setOpenaiKey(e.target.value)}
                  placeholder="Enter OpenAI key..."
                />
              </div>
            </div>
          </div>

          <Button
            variant="primary"
            onClick={handleSaveKeys}
            disabled={savingKeys}
          >
            {savingKeys ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save API Keys
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Section 5: Greenhouse Companies */}
      <Card>
        <CardHeader>
          <CardTitle>Greenhouse Companies</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="greenhouse">Company slugs (one per line)</Label>
            <Textarea
              id="greenhouse"
              value={greenhouseSlugs}
              onChange={(e) => setGreenhouseSlugs(e.target.value)}
              placeholder={"stripe\nairbnb\ndatabricks"}
              className="min-h-[120px]"
            />
          </div>
          <Button
            variant="primary"
            onClick={handleSaveGreenhouse}
            disabled={savingGreenhouse}
          >
            {savingGreenhouse ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="mr-2 h-4 w-4" />
                Save Companies
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Section 6: Setup Status */}
      {setupStatus && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-primary-light" />
              Setup Status
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              {setupItems.map((item) => {
                const ok = setupStatus[item.key];
                return (
                  <div
                    key={item.key}
                    className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2.5"
                  >
                    {ok ? (
                      <CheckCircle2 className="h-4 w-4 text-success-light shrink-0" />
                    ) : (
                      <AlertCircle className="h-4 w-4 text-warning-light shrink-0" />
                    )}
                    <span className="text-xs text-text-secondary">
                      {item.label}
                    </span>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}
