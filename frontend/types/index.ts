export interface Job {
  id?: number;
  title: string;
  company: string;
  location: string;
  url: string;
  description: string;
  source: string;
  source_job_id: string;
  posted_at: string;
  run_date?: string;
  ai_score?: number | null;
  ai_reason?: string | null;
}

export interface AppliedJob {
  id: number;
  source_job_id: string;
  title: string;
  company: string;
  url: string;
  applied_at: string;
  platform?: string;
  status?: string;
  error?: string;
}

export interface AppConfig {
  keywords: string[];
  filters: {
    max_results: number;
    location: string;
    posted_within_hours: number;
  };
  ai_ranking: {
    top_n: number;
    min_score: number;
  };
  greenhouse_companies: string[];
  azure_openai: {
    endpoint: string;
    deployment: string;
  };
}

export interface SetupStatus {
  profile_exists: boolean;
  yaml_exists: boolean;
  env_exists: boolean;
  azure_key_set: boolean;
  apify_token_set: boolean;
  adzuna_id_set: boolean;
  azure_endpoint_configured: boolean;
  azure_deployment_configured: boolean;
}

export interface DashboardStats {
  total_jobs: number;
  avg_score: number;
  top_score: number;
  applied_count: number;
  last_run: string;
  sources: Record<string, number>;
}
