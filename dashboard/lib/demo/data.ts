// Synthetic demo data — used when isDemo=true in the auth store.
// All companies, names, and figures are fictional and for presentation only.

import type {
  AccountProfile,
  AccountSummary,
  AccountFatigueScore,
  IntentScore,
  ChurnPrediction,
  NextBestAction,
  AccountListResponse,
  FatigueSeverity,
  NBAActionType,
} from "@/lib/types";
import type { TimelineSignal } from "@/components/SignalTimeline";

export interface HeatmapRow {
  memberName: string;
  memberTitle: string;
  email: number;
  web: number;
  webinar: number;
  crm: number;
}

export interface DemoAccountFull {
  profile: AccountProfile;
  summary: AccountSummary;
  heatmap: HeatmapRow[];
  signals: TimelineSignal[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const H = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString();
const D = (d: number) => new Date(Date.now() - d * 86_400_000).toISOString();

function fatigue(
  domain: string,
  score: number,
  severity: FatigueSeverity,
): AccountFatigueScore {
  return {
    account_domain: domain,
    score,
    severity,
    is_over_threshold: score >= 60,
    computed_at: H(0.5),
    components: [
      { name: "Outreach frequency",   score: Math.round(score * 0.30), weight: 0.30, weighted_score: Math.round(score * 0.30 * 0.30), breakdown: {} },
      { name: "Engagement decay",     score: Math.round(score * 0.25), weight: 0.25, weighted_score: Math.round(score * 0.25 * 0.25), breakdown: {} },
      { name: "Negative signals",     score: Math.round(score * 0.20), weight: 0.20, weighted_score: Math.round(score * 0.20 * 0.20), breakdown: {} },
      { name: "Contact concentration",score: Math.round(score * 0.15), weight: 0.15, weighted_score: Math.round(score * 0.15 * 0.15), breakdown: {} },
      { name: "Recency gap",          score: Math.round(score * 0.10), weight: 0.10, weighted_score: Math.round(score * 0.10 * 0.10), breakdown: {} },
    ],
  };
}

function intent(domain: string, score: number): IntentScore {
  return { account_domain: domain, intent_score: score, confidence: 0.74 + (score % 20) / 100, computed_at: H(1) };
}

function churn(domain: string, prob: number): ChurnPrediction {
  const risk = prob >= 0.6 ? "CRITICAL" : prob >= 0.35 ? "HIGH" : prob >= 0.15 ? "MEDIUM" : "LOW";
  return { account_domain: domain, churn_probability: prob, risk_level: risk, is_high_risk: prob >= 0.35, signal_breakdown: {}, computed_at: H(1) };
}

function nba(
  domain: string,
  type: NBAActionType,
  priority: number,
  rationale: string,
  f: number, i: number, c: number,
): NextBestAction {
  return {
    id: `nba-${domain}`,
    account_domain: domain,
    action_type: type,
    priority,
    rationale,
    fatigue_score: f,
    intent_score: i,
    churn_probability: c,
    is_active: true,
    expires_at: D(-2),
    created_at: H(4),
  };
}

function profile(
  domain: string, name: string, industry: string,
  arr: number, employees: number, committee: number,
): AccountProfile {
  return {
    id: `demo-${domain}`,
    domain,
    display_name: name,
    industry,
    arr_usd: arr,
    employee_count: employees,
    committee_size: committee,
    is_active: true,
    created_at: D(180),
    updated_at: H(1),
  };
}

// ---------------------------------------------------------------------------
// Account definitions
// ---------------------------------------------------------------------------

const ACCOUNTS: DemoAccountFull[] = [

  // 1 — CRITICAL fatigue → COOLDOWN
  {
    profile: profile("acme.com", "Acme Corp", "Enterprise SaaS", 480_000, 1200, 6),
    summary: {
      account: profile("acme.com", "Acme Corp", "Enterprise SaaS", 480_000, 1200, 6),
      fatigue: fatigue("acme.com", 82, "CRITICAL"),
      intent:  intent("acme.com", 35),
      churn:   churn("acme.com", 0.71),
      current_nba: nba("acme.com", "COOLDOWN", 1,
        "Fatigue score CRITICAL (82/100). CFO Sarah Chen unsubscribed 3 days ago. All outreach paused — churn probability at 71%.",
        82, 35, 0.71),
    },
    heatmap: [
      { memberName: "Sarah Chen",    memberTitle: "CFO",          email: 18, web: 3,  webinar: 2, crm: 5 },
      { memberName: "Marcus Webb",   memberTitle: "CTO",          email: 7,  web: 12, webinar: 1, crm: 1 },
      { memberName: "Priya Sharma",  memberTitle: "VP Operations",email: 4,  web: 6,  webinar: 4, crm: 2 },
      { memberName: "Daniel Torres", memberTitle: "IT Director",  email: 2,  web: 9,  webinar: 0, crm: 0 },
      { memberName: "Lisa Park",     memberTitle: "Analyst",      email: 1,  web: 2,  webinar: 1, crm: 0 },
      { memberName: "Tom Bauer",     memberTitle: "Procurement",  email: 3,  web: 1,  webinar: 0, crm: 1 },
    ],
    signals: [
      { id: "a1s1", signal_type: "unsubscribe",       channel: "email",   member_name: "Sarah Chen",    occurred_at: D(3) },
      { id: "a1s2", signal_type: "pricing_page_view", channel: "web",     member_name: "Marcus Webb",   occurred_at: H(3) },
      { id: "a1s3", signal_type: "email_open",        channel: "email",   member_name: "Priya Sharma",  occurred_at: H(6) },
      { id: "a1s4", signal_type: "webinar_attend",    channel: "webinar", member_name: "Daniel Torres", occurred_at: D(5) },
      { id: "a1s5", signal_type: "email_open",        channel: "email",   member_name: "Tom Bauer",     occurred_at: D(7) },
    ],
  },

  // 2 — HIGH fatigue + HIGH intent → PRICING_TRIGGER
  {
    profile: profile("globex.com", "Globex Inc", "Financial Services", 320_000, 840, 4),
    summary: {
      account: profile("globex.com", "Globex Inc", "Financial Services", 320_000, 840, 4),
      fatigue: fatigue("globex.com", 67, "HIGH"),
      intent:  intent("globex.com", 71),
      churn:   churn("globex.com", 0.28),
      current_nba: nba("globex.com", "PRICING_TRIGGER", 2,
        "High intent (71) with elevated fatigue (67). CFO and VP of Finance both viewed ROI calculator twice this week — send pricing proposal now.",
        67, 71, 0.28),
    },
    heatmap: [
      { memberName: "Rachel Kim",   memberTitle: "CFO",           email: 9,  web: 14, webinar: 3, crm: 4 },
      { memberName: "James Okafor", memberTitle: "VP Finance",    email: 6,  web: 11, webinar: 2, crm: 3 },
      { memberName: "Nina Patel",   memberTitle: "Head of IT",    email: 3,  web: 7,  webinar: 1, crm: 0 },
      { memberName: "Owen Clarke",  memberTitle: "Compliance Dir",email: 1,  web: 3,  webinar: 0, crm: 2 },
    ],
    signals: [
      { id: "a2s1", signal_type: "pricing_page_view", channel: "web",   member_name: "Rachel Kim",   occurred_at: H(2) },
      { id: "a2s2", signal_type: "pricing_page_view", channel: "web",   member_name: "James Okafor", occurred_at: H(5) },
      { id: "a2s3", signal_type: "email_reply",       channel: "email", member_name: "Rachel Kim",   occurred_at: D(1) },
      { id: "a2s4", signal_type: "page_view",         channel: "web",   member_name: "Nina Patel",   occurred_at: D(2) },
      { id: "a2s5", signal_type: "crm_note",          channel: "crm",   member_name: "James Okafor", occurred_at: D(4) },
    ],
  },

  // 3 — MEDIUM fatigue → RE_ENGAGE
  {
    profile: profile("initech.com", "Initech Ltd", "B2B SaaS", 150_000, 340, 3),
    summary: {
      account: profile("initech.com", "Initech Ltd", "B2B SaaS", 150_000, 340, 3),
      fatigue: fatigue("initech.com", 44, "MEDIUM"),
      intent:  intent("initech.com", 55),
      churn:   churn("initech.com", 0.19),
      current_nba: nba("initech.com", "RE_ENGAGE", 4,
        "Engagement stalled for 11 days. CTO last opened an email 2 weeks ago. Send personalized re-engagement with product update.",
        44, 55, 0.19),
    },
    heatmap: [
      { memberName: "Greg Lyman",  memberTitle: "CTO",         email: 5, web: 8, webinar: 2, crm: 1 },
      { memberName: "Ally Huang",  memberTitle: "Head of Eng", email: 3, web: 5, webinar: 1, crm: 0 },
      { memberName: "Sam Reeves",  memberTitle: "COO",         email: 2, web: 3, webinar: 0, crm: 2 },
    ],
    signals: [
      { id: "a3s1", signal_type: "email_open",  channel: "email", member_name: "Greg Lyman", occurred_at: D(14) },
      { id: "a3s2", signal_type: "page_view",   channel: "web",   member_name: "Ally Huang", occurred_at: D(11) },
      { id: "a3s3", signal_type: "email_click", channel: "email", member_name: "Sam Reeves", occurred_at: D(16) },
    ],
  },

  // 4 — LOW fatigue + VERY HIGH intent → ACCELERATE
  {
    profile: profile("umbrella.io", "Umbrella Corp", "Healthcare Tech", 220_000, 610, 5),
    summary: {
      account: profile("umbrella.io", "Umbrella Corp", "Healthcare Tech", 220_000, 610, 5),
      fatigue: fatigue("umbrella.io", 18, "LOW"),
      intent:  intent("umbrella.io", 88),
      churn:   churn("umbrella.io", 0.05),
      current_nba: nba("umbrella.io", "ACCELERATE", 3,
        "Intent score spiking (88). All 5 committee members active this week. Compress evaluation timeline — propose executive kickoff.",
        18, 88, 0.05),
    },
    heatmap: [
      { memberName: "Alice Mercer",  memberTitle: "CEO",           email: 4, web: 16, webinar: 5, crm: 6 },
      { memberName: "Ben Nakamura",  memberTitle: "CTO",           email: 3, web: 14, webinar: 3, crm: 2 },
      { memberName: "Clara Diaz",    memberTitle: "CFO",           email: 5, web: 10, webinar: 4, crm: 4 },
      { memberName: "David Osei",    memberTitle: "Head of Infra", email: 2, web: 9,  webinar: 2, crm: 1 },
      { memberName: "Emma Walsh",    memberTitle: "Compliance",    email: 1, web: 6,  webinar: 3, crm: 2 },
    ],
    signals: [
      { id: "a4s1", signal_type: "pricing_page_view", channel: "web",     member_name: "Alice Mercer", occurred_at: H(1) },
      { id: "a4s2", signal_type: "webinar_attend",    channel: "webinar", member_name: "Ben Nakamura", occurred_at: H(2) },
      { id: "a4s3", signal_type: "email_reply",       channel: "email",   member_name: "Clara Diaz",   occurred_at: H(4) },
      { id: "a4s4", signal_type: "page_view",         channel: "web",     member_name: "David Osei",   occurred_at: H(6) },
      { id: "a4s5", signal_type: "video_view",        channel: "video",   member_name: "Emma Walsh",   occurred_at: H(8) },
    ],
  },

  // 5 — LOW fatigue + MEDIUM intent → NURTURE
  {
    profile: profile("stark.io", "Stark Industries", "Aerospace & Defense", 950_000, 3400, 8),
    summary: {
      account: profile("stark.io", "Stark Industries", "Aerospace & Defense", 950_000, 3400, 8),
      fatigue: fatigue("stark.io", 29, "LOW"),
      intent:  intent("stark.io", 62),
      churn:   churn("stark.io", 0.10),
      current_nba: nba("stark.io", "NURTURE", 6,
        "Large strategic account, long evaluation cycle expected. Committee is engaged but not ready to buy. Send thought leadership content on compliance automation.",
        29, 62, 0.10),
    },
    heatmap: [
      { memberName: "Tony Marsh",    memberTitle: "CTO",              email: 3, web: 7,  webinar: 2, crm: 3 },
      { memberName: "Pepper Lin",    memberTitle: "COO",              email: 2, web: 5,  webinar: 1, crm: 2 },
      { memberName: "Rhodes Carter", memberTitle: "VP Security",      email: 1, web: 4,  webinar: 3, crm: 1 },
      { memberName: "Happy Hicks",   memberTitle: "Dir IT",           email: 2, web: 3,  webinar: 1, crm: 0 },
      { memberName: "Maya Stern",    memberTitle: "Head of Finance",  email: 1, web: 2,  webinar: 0, crm: 1 },
      { memberName: "Cole Barton",   memberTitle: "Procurement",      email: 0, web: 1,  webinar: 0, crm: 2 },
      { memberName: "Jess Vance",    memberTitle: "Risk & Compliance",email: 1, web: 2,  webinar: 1, crm: 0 },
      { memberName: "Drew Park",     memberTitle: "Analyst",          email: 0, web: 1,  webinar: 0, crm: 0 },
    ],
    signals: [
      { id: "a5s1", signal_type: "webinar_attend", channel: "webinar", member_name: "Rhodes Carter", occurred_at: D(2) },
      { id: "a5s2", signal_type: "email_open",     channel: "email",   member_name: "Tony Marsh",    occurred_at: D(4) },
      { id: "a5s3", signal_type: "page_view",      channel: "web",     member_name: "Pepper Lin",    occurred_at: D(6) },
    ],
  },

  // 6 — MEDIUM fatigue + HIGH intent → EXEC_ESCALATION
  {
    profile: profile("wayne.co", "Wayne Enterprises", "Conglomerate", 2_100_000, 8200, 7),
    summary: {
      account: profile("wayne.co", "Wayne Enterprises", "Conglomerate", 2_100_000, 8200, 7),
      fatigue: fatigue("wayne.co", 55, "MEDIUM"),
      intent:  intent("wayne.co", 77),
      churn:   churn("wayne.co", 0.22),
      current_nba: nba("wayne.co", "EXEC_ESCALATION", 2,
        "Strategic $2.1M opportunity. CEO and CFO engaged, VP Legal now active. Escalate to AE for executive-to-executive outreach — deal is at inflection.",
        55, 77, 0.22),
    },
    heatmap: [
      { memberName: "Bruce Harper",  memberTitle: "CEO",              email: 6,  web: 12, webinar: 4, crm: 8 },
      { memberName: "Lucie Fox",     memberTitle: "CFO",              email: 7,  web: 10, webinar: 3, crm: 6 },
      { memberName: "Alfred Reed",   memberTitle: "VP Legal",         email: 4,  web: 8,  webinar: 2, crm: 4 },
      { memberName: "Dick Grayson",  memberTitle: "Head of Security", email: 3,  web: 6,  webinar: 1, crm: 2 },
      { memberName: "Barbara Quinn", memberTitle: "CTO",              email: 2,  web: 9,  webinar: 2, crm: 1 },
      { memberName: "Tim Drake",     memberTitle: "IT Manager",       email: 1,  web: 4,  webinar: 1, crm: 0 },
      { memberName: "Cassandra Wu",  memberTitle: "Procurement",      email: 2,  web: 2,  webinar: 0, crm: 3 },
    ],
    signals: [
      { id: "a6s1", signal_type: "pricing_page_view", channel: "web",   member_name: "Lucie Fox",     occurred_at: H(2) },
      { id: "a6s2", signal_type: "email_reply",       channel: "email", member_name: "Bruce Harper",  occurred_at: H(6) },
      { id: "a6s3", signal_type: "page_view",         channel: "web",   member_name: "Alfred Reed",   occurred_at: D(1) },
      { id: "a6s4", signal_type: "crm_note",          channel: "crm",   member_name: "Lucie Fox",     occurred_at: D(2) },
      { id: "a6s5", signal_type: "video_view",        channel: "video", member_name: "Dick Grayson",  occurred_at: D(3) },
      { id: "a6s6", signal_type: "webinar_attend",    channel: "webinar",member_name: "Barbara Quinn",occurred_at: D(5) },
    ],
  },

  // 7 — HIGH fatigue + LOW intent → DEAL_REVIEW
  {
    profile: profile("veridian.com", "Veridian Dynamics", "Pharmaceuticals", 780_000, 2100, 5),
    summary: {
      account: profile("veridian.com", "Veridian Dynamics", "Pharmaceuticals", 780_000, 2100, 5),
      fatigue: fatigue("veridian.com", 74, "HIGH"),
      intent:  intent("veridian.com", 22),
      churn:   churn("veridian.com", 0.58),
      current_nba: nba("veridian.com", "DEAL_REVIEW", 1,
        "High fatigue (74) combined with sharply declining intent (22 from 61 two weeks ago). CTO went silent. Internal deal review required before any outreach.",
        74, 22, 0.58),
    },
    heatmap: [
      { memberName: "Carol Reeves",  memberTitle: "CTO",           email: 14, web: 5,  webinar: 2, crm: 3 },
      { memberName: "James Holden",  memberTitle: "CFO",           email: 9,  web: 3,  webinar: 0, crm: 2 },
      { memberName: "Naomi Nagata",  memberTitle: "VP Science",    email: 7,  web: 4,  webinar: 3, crm: 1 },
      { memberName: "Amos Burton",   memberTitle: "Head of Ops",   email: 4,  web: 2,  webinar: 0, crm: 0 },
      { memberName: "Bobbie Draper", memberTitle: "Security Dir",  email: 2,  web: 1,  webinar: 0, crm: 0 },
    ],
    signals: [
      { id: "a7s1", signal_type: "email_open",  channel: "email", member_name: "Carol Reeves", occurred_at: D(10) },
      { id: "a7s2", signal_type: "email_open",  channel: "email", member_name: "James Holden", occurred_at: D(12) },
      { id: "a7s3", signal_type: "bounce",      channel: "email", member_name: "Carol Reeves", occurred_at: D(8) },
    ],
  },

  // 8 — LOW fatigue + HIGH intent → ACCELERATE
  {
    profile: profile("meridian.io", "Meridian Health", "Digital Health", 130_000, 280, 4),
    summary: {
      account: profile("meridian.io", "Meridian Health", "Digital Health", 130_000, 280, 4),
      fatigue: fatigue("meridian.io", 14, "LOW"),
      intent:  intent("meridian.io", 81),
      churn:   churn("meridian.io", 0.07),
      current_nba: nba("meridian.io", "ACCELERATE", 3,
        "High intent (81) and very low fatigue — committee is warm and receptive. Two members viewed case studies today. Move to product demo this week.",
        14, 81, 0.07),
    },
    heatmap: [
      { memberName: "Aria Santos",   memberTitle: "CEO",         email: 2, web: 11, webinar: 4, crm: 3 },
      { memberName: "Leo Marsh",     memberTitle: "CTO",         email: 3, web: 9,  webinar: 3, crm: 1 },
      { memberName: "Iris Tanaka",   memberTitle: "Head of Data",email: 1, web: 7,  webinar: 2, crm: 0 },
      { memberName: "Sam Ortega",    memberTitle: "CFO",         email: 2, web: 5,  webinar: 1, crm: 2 },
    ],
    signals: [
      { id: "a8s1", signal_type: "page_view",   channel: "web",     member_name: "Aria Santos", occurred_at: H(1) },
      { id: "a8s2", signal_type: "video_view",  channel: "video",   member_name: "Leo Marsh",   occurred_at: H(3) },
      { id: "a8s3", signal_type: "email_click", channel: "email",   member_name: "Iris Tanaka", occurred_at: H(5) },
      { id: "a8s4", signal_type: "webinar_attend",channel:"webinar",member_name: "Sam Ortega",  occurred_at: D(1) },
    ],
  },

  // 9 — CRITICAL fatigue → COOLDOWN (second)
  {
    profile: profile("quantum-labs.io", "Quantum Labs", "Deep Tech", 200_000, 520, 4),
    summary: {
      account: profile("quantum-labs.io", "Quantum Labs", "Deep Tech", 200_000, 520, 4),
      fatigue: fatigue("quantum-labs.io", 91, "CRITICAL"),
      intent:  intent("quantum-labs.io", 18),
      churn:   churn("quantum-labs.io", 0.80),
      current_nba: nba("quantum-labs.io", "COOLDOWN", 1,
        "Fatigue at 91/100 — highest in portfolio. Two spam reports filed. 30-day cooldown enforced. No outreach until score drops below 50.",
        91, 18, 0.80),
    },
    heatmap: [
      { memberName: "Victor Reyes",  memberTitle: "CTO",       email: 22, web: 4,  webinar: 1, crm: 2 },
      { memberName: "Zara Ahmed",    memberTitle: "CEO",       email: 15, web: 3,  webinar: 0, crm: 1 },
      { memberName: "Kurt Voss",     memberTitle: "VP Eng",    email: 8,  web: 2,  webinar: 0, crm: 0 },
      { memberName: "Mina Lee",      memberTitle: "Analyst",   email: 3,  web: 1,  webinar: 0, crm: 0 },
    ],
    signals: [
      { id: "a9s1", signal_type: "spam_report", channel: "email", member_name: "Victor Reyes", occurred_at: D(1) },
      { id: "a9s2", signal_type: "unsubscribe", channel: "email", member_name: "Zara Ahmed",   occurred_at: D(2) },
      { id: "a9s3", signal_type: "email_open",  channel: "email", member_name: "Kurt Voss",    occurred_at: D(6) },
    ],
  },

  // 10 — MEDIUM fatigue + MEDIUM intent → NURTURE (second)
  {
    profile: profile("syntex.ai", "Syntex AI", "AI & ML Platform", 420_000, 680, 4),
    summary: {
      account: profile("syntex.ai", "Syntex AI", "AI & ML Platform", 420_000, 680, 4),
      fatigue: fatigue("syntex.ai", 38, "MEDIUM"),
      intent:  intent("syntex.ai", 58),
      churn:   churn("syntex.ai", 0.16),
      current_nba: nba("syntex.ai", "NURTURE", 5,
        "Account is in steady evaluation — no urgency signals yet. Continue educational nurture track focused on MLOps cost reduction.",
        38, 58, 0.16),
    },
    heatmap: [
      { memberName: "Rajan Mehta",   memberTitle: "CTO",          email: 4, web: 8, webinar: 3, crm: 2 },
      { memberName: "Sofia Kaur",    memberTitle: "Head of AI",   email: 3, web: 6, webinar: 2, crm: 0 },
      { memberName: "Noah Levi",     memberTitle: "VP Eng",       email: 2, web: 5, webinar: 1, crm: 1 },
      { memberName: "Amara Cole",    memberTitle: "Product Lead", email: 1, web: 3, webinar: 1, crm: 0 },
    ],
    signals: [
      { id: "a10s1", signal_type: "webinar_attend", channel: "webinar", member_name: "Rajan Mehta", occurred_at: D(3) },
      { id: "a10s2", signal_type: "email_click",    channel: "email",   member_name: "Sofia Kaur",  occurred_at: D(5) },
      { id: "a10s3", signal_type: "page_view",      channel: "web",     member_name: "Noah Levi",   occurred_at: D(7) },
    ],
  },

  // 11 — LOW fatigue + HIGH intent → PRICING_TRIGGER (second)
  {
    profile: profile("orbital.io", "Orbital Systems", "Aerospace", 1_200_000, 1800, 6),
    summary: {
      account: profile("orbital.io", "Orbital Systems", "Aerospace", 1_200_000, 1800, 6),
      fatigue: fatigue("orbital.io", 22, "LOW"),
      intent:  intent("orbital.io", 76),
      churn:   churn("orbital.io", 0.08),
      current_nba: nba("orbital.io", "PRICING_TRIGGER", 2,
        "High-value $1.2M opportunity. VP Finance visited pricing page 4 times this week. CFO reply-rate is 60%. Send custom ROI analysis now.",
        22, 76, 0.08),
    },
    heatmap: [
      { memberName: "Kenji Tanaka",  memberTitle: "CEO",         email: 3, web: 9,  webinar: 3, crm: 4 },
      { memberName: "Layla Hassan",  memberTitle: "CFO",         email: 5, web: 13, webinar: 2, crm: 6 },
      { memberName: "Max Brandt",    memberTitle: "VP Finance",  email: 4, web: 16, webinar: 1, crm: 3 },
      { memberName: "Suki Watanabe", memberTitle: "CTO",         email: 2, web: 8,  webinar: 2, crm: 1 },
      { memberName: "Carlos Lima",   memberTitle: "Procurement", email: 1, web: 4,  webinar: 0, crm: 2 },
      { memberName: "Petra Novak",   memberTitle: "Legal Dir",   email: 1, web: 3,  webinar: 0, crm: 1 },
    ],
    signals: [
      { id: "a11s1", signal_type: "pricing_page_view", channel: "web",   member_name: "Max Brandt",    occurred_at: H(1) },
      { id: "a11s2", signal_type: "pricing_page_view", channel: "web",   member_name: "Layla Hassan",  occurred_at: H(4) },
      { id: "a11s3", signal_type: "email_reply",       channel: "email", member_name: "Layla Hassan",  occurred_at: D(1) },
      { id: "a11s4", signal_type: "crm_note",          channel: "crm",   member_name: "Kenji Tanaka",  occurred_at: D(2) },
      { id: "a11s5", signal_type: "video_view",        channel: "video", member_name: "Suki Watanabe", occurred_at: D(3) },
    ],
  },

  // 12 — HIGH fatigue + MEDIUM intent → RE_ENGAGE (second)
  {
    profile: profile("cascade.com", "Cascade Retail", "Retail Tech", 290_000, 960, 4),
    summary: {
      account: profile("cascade.com", "Cascade Retail", "Retail Tech", 290_000, 960, 4),
      fatigue: fatigue("cascade.com", 61, "HIGH"),
      intent:  intent("cascade.com", 47),
      churn:   churn("cascade.com", 0.34),
      current_nba: nba("cascade.com", "RE_ENGAGE", 3,
        "Engagement dropped after heavy Q4 outreach. Take a 10-day pause then re-engage with holiday-season case study — personalized to VP of Retail Ops.",
        61, 47, 0.34),
    },
    heatmap: [
      { memberName: "Fiona Graves",  memberTitle: "VP Retail Ops",email: 11, web: 7, webinar: 1, crm: 2 },
      { memberName: "Damian Moore",  memberTitle: "CTO",          email: 8,  web: 5, webinar: 2, crm: 1 },
      { memberName: "Helen Cross",   memberTitle: "CFO",          email: 6,  web: 4, webinar: 0, crm: 3 },
      { memberName: "Ethan Brooks",  memberTitle: "IT Director",  email: 3,  web: 3, webinar: 1, crm: 0 },
    ],
    signals: [
      { id: "a12s1", signal_type: "email_open",  channel: "email", member_name: "Fiona Graves",  occurred_at: D(8) },
      { id: "a12s2", signal_type: "email_open",  channel: "email", member_name: "Helen Cross",    occurred_at: D(9) },
      { id: "a12s3", signal_type: "page_view",   channel: "web",   member_name: "Damian Moore",   occurred_at: D(11) },
    ],
  },
];

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

export const DEMO_BY_DOMAIN: Record<string, DemoAccountFull> =
  Object.fromEntries(ACCOUNTS.map((a) => [a.profile.domain, a]));

export const DEMO_ACCOUNT_LIST: AccountListResponse = {
  items: ACCOUNTS.map((a) => a.profile),
  total: ACCOUNTS.length,
  page: 1,
  page_size: 50,
  has_next: false,
};
