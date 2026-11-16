export type Verdict = "rising" | "steady" | "fading" | "insufficient";
export type Strength = "none" | "weak" | "moderate" | "strong";
export type Role = "owner" | "member" | "viewer";

export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Evidence {
  id: string;
  item_id: string;
  title: string;
  url: string;
  hn_url?: string | null;
  source: string;
  source_type: "news" | "upload";
  file_id: string | null;
  file_name: string | null;
  date: string;
  signal: number;
  relevance: number;
  quote: string;
  note: string;
  also: number;
}

export interface CompanyEvent {
  type: string;
  event: string;
  date: string | null;
  item_id: string;
  title: string;
  url: string;
  source: string;
  alias: string;
}

export interface CompanyRef {
  id: string;
  name: string;
  aliases: string[];
  events: CompanyEvent[];
}

export interface TopicBrief {
  id: string;
  name: string;
  description: string;
  verdict: Verdict;
  raw_verdict?: string;
  previous_verdict: Verdict | null;
  strength: Strength;
  score: number;
  metrics: {
    coverage_change_pct: number | null;
    recent_per_day: number;
    baseline_per_day: number;
    tone: number;
    tone_vs_subject: number;
    evidence_count: number;
    recent_count: number;
    source_count: number;
    upload_count: number;
    attention: number;
  };
  series: { date: string; score: number }[];
  volume: number[];
  summary: string;
  points: { text: string; sources: string[] }[];
  watch: string;
  validated: boolean;
  sources: string[];
  companies: CompanyRef[];
  reasons: string[];
  capped_days: string[];
}

export interface Brief {
  id?: string;
  version: number;
  workspace: { id: string; name: string; subject: string };
  date: string;
  data_through?: string;
  previous_date: string | null;
  generated_at: string;
  run_id: string;
  headline: string;
  changes: { topic_id: string; name: string; from: Verdict; to: Verdict }[];
  tally: Record<Verdict, number>;
  topics: TopicBrief[];
  evidence: Record<string, Evidence>;
  cost_usd?: number;
  method?: { recent_days: number; baseline_days: number; enter: number; exit: number };
}

export interface Topic {
  id: string;
  name: string;
  description: string;
  keywords: string[];
  position: number;
}

export interface Workspace {
  id: string;
  name: string;
  subject: string;
  subject_description: string;
  role: Role;
  is_demo: boolean;
  schedule: { enabled: boolean; time: string };
  created_at: string;
  topics?: Topic[];
  members?: number;
  latest_brief?: { date: string; tally: Partial<Record<Verdict, number>> };
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: string;
  created_at: string;
  workspace?: { id: string; name: string; subject: string };
}

export interface RunStep {
  key: string;
  status: "pending" | "running" | "done" | "failed";
  message?: string;
  started_at?: string;
  finished_at?: string;
  detail?: Record<string, unknown>;
}

export interface Run {
  id: string;
  trigger: string;
  status: "queued" | "running" | "succeeded" | "failed";
  as_of: string;
  cost_usd: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  by: string | null;
  brief_id: string | null;
  steps: RunStep[];
  error?: string;
}

export interface WFile {
  id: string;
  kind: "upload" | "brief" | "trace" | "news";
  filename: string;
  content_type: string;
  size: number;
  created_at: string;
  brief_date: string | null;
  run_id: string | null;
  parse_status: string;
  chunks: number;
  uploaded_by: string | null;
}

/** How brief components reach the outside world (app vs standalone file). */
export interface BriefLinks {
  fileHref?: (fileId: string) => string | null;
  onCompany?: (companyId: string) => void;
}
