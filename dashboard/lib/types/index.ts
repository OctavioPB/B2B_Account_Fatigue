// Shared TypeScript types — mirror of api/models/schemas.py Pydantic contracts.

export type FatigueSeverity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ChurnRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type NBAActionType =
  | "COOLDOWN"
  | "NURTURE"
  | "RE_ENGAGE"
  | "ACCELERATE"
  | "EXEC_ESCALATION"
  | "PRICING_TRIGGER"
  | "DEAL_REVIEW";

// ---------------------------------------------------------------------------
// Scores
// ---------------------------------------------------------------------------

export interface FatigueComponent {
  name: string;
  score: number;
  weight: number;
  weighted_score: number;
  breakdown: Record<string, unknown>;
}

export interface AccountFatigueScore {
  account_domain: string;
  score: number; // 0–100
  severity: FatigueSeverity;
  components: FatigueComponent[];
  is_over_threshold: boolean;
  computed_at: string; // ISO 8601
}

export interface IntentScore {
  account_domain: string;
  intent_score: number; // 0–100
  confidence: number;   // 0–1
  computed_at: string;
}

export interface ChurnPrediction {
  account_domain: string;
  churn_probability: number; // 0–1
  risk_level: ChurnRiskLevel;
  is_high_risk: boolean;
  signal_breakdown: Record<string, unknown>;
  computed_at: string;
}

// ---------------------------------------------------------------------------
// Next Best Action
// ---------------------------------------------------------------------------

export interface NextBestAction {
  id: string;
  account_domain: string;
  action_type: NBAActionType;
  priority: number;    // 1 (highest) – 7 (lowest)
  rationale: string;
  fatigue_score: number;
  intent_score: number;
  churn_probability: number;
  is_active: boolean;
  expires_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Account
// ---------------------------------------------------------------------------

export interface AccountProfile {
  id: string;
  domain: string;
  display_name: string | null;
  industry: string | null;
  arr_usd: number | null;
  employee_count: number | null;
  committee_size: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AccountSummary {
  account: AccountProfile;
  fatigue: AccountFatigueScore | null;
  intent: IntentScore | null;
  churn: ChurnPrediction | null;
  current_nba: NextBestAction | null;
}

export interface AccountListResponse {
  items: AccountProfile[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

// ---------------------------------------------------------------------------
// Committee
// ---------------------------------------------------------------------------

export interface CommitteeMember {
  id: string;
  account_domain: string;
  email: string;
  full_name: string;
  title: string;
  role_weight: number;
  is_current: boolean;
}

// ---------------------------------------------------------------------------
// Webhooks
// ---------------------------------------------------------------------------

export interface WebhookResponse {
  id: string;
  tenant_id: string;
  target_url: string;
  description: string | null;
  event_types: string[];
  is_active: boolean;
  failure_count: number;
  last_success_at: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Signal ingestion
// ---------------------------------------------------------------------------

export type SignalType =
  | "email_open"
  | "email_click"
  | "email_reply"
  | "page_view"
  | "pricing_page_view"
  | "webinar_attend"
  | "video_view"
  | "crm_note"
  | "unsubscribe"
  | "spam_report"
  | "bounce";

export type SignalChannel = "email" | "web" | "webinar" | "crm" | "video";
