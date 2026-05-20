"use client";

// BRAND.md: Account Detail page — dark hero, 3-col score cards (KPI left-bar variant),
// Eyebrow + SectionTitle for each content section, callout note cards (borderLeft gold),
// CommitteeHeatmap, NBAActionCard, SignalTimeline.

import { useParams } from "next/navigation";
import { useAccountSummary } from "@/lib/hooks/useAccounts";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Eyebrow } from "@/components/Eyebrow";
import { FatigueScoreBadge } from "@/components/FatigueScoreBadge";
import { IntentScoreGauge } from "@/components/IntentScoreGauge";
import { CommitteeHeatmap } from "@/components/CommitteeHeatmap";
import { NBAActionCard } from "@/components/NBAActionCard";
import { SignalTimeline, type TimelineSignal } from "@/components/SignalTimeline";
import { SkeletonCard } from "@/components/SkeletonCard";
import type { NextBestAction, FatigueSeverity } from "@/lib/types";

// Mock data for when the API isn't running
const MOCK_SUMMARY = {
  domain: "acme.com",
  displayName: "Acme Corp",
  industry: "Technology",
  arr_usd: 480000,
  committee_size: 6,
  fatigue: { score: 82, severity: "CRITICAL" as FatigueSeverity, is_over_threshold: true },
  intent: { intent_score: 35, confidence: 0.77 },
  churn: { churn_probability: 0.71, risk_level: "CRITICAL", is_high_risk: true },
  nba: {
    id: "nba-1",
    account_domain: "acme.com",
    action_type: "COOLDOWN",
    priority: 1,
    rationale: "Account fatigue is CRITICAL (82/100). All outreach paused. Churn probability at 71% — requires immediate deal review.",
    fatigue_score: 82,
    intent_score: 35,
    churn_probability: 0.71,
    is_active: true,
    expires_at: null,
    created_at: "2024-07-01T10:00:00Z",
  } as NextBestAction,
};

const MOCK_HEATMAP = [
  { memberName: "Sarah Chen",    memberTitle: "CFO",       email: 18, web: 3, webinar: 2, crm: 5 },
  { memberName: "Marcus Webb",   memberTitle: "CTO",       email: 7,  web: 12, webinar: 1, crm: 1 },
  { memberName: "Priya Sharma",  memberTitle: "VP Ops",    email: 4,  web: 6,  webinar: 4, crm: 2 },
  { memberName: "Daniel Torres", memberTitle: "IT Dir",    email: 2,  web: 9,  webinar: 0, crm: 0 },
  { memberName: "Lisa Park",     memberTitle: "Analyst",   email: 1,  web: 2,  webinar: 1, crm: 0 },
];

const MOCK_SIGNALS: TimelineSignal[] = [
  { id: "s1", signal_type: "pricing_page_view", channel: "web",     member_name: "Sarah Chen",    occurred_at: new Date(Date.now() - 3600000).toISOString() },
  { id: "s2", signal_type: "email_open",         channel: "email",   member_name: "Marcus Webb",   occurred_at: new Date(Date.now() - 7200000).toISOString() },
  { id: "s3", signal_type: "webinar_attend",     channel: "webinar", member_name: "Priya Sharma",  occurred_at: new Date(Date.now() - 86400000).toISOString() },
  { id: "s4", signal_type: "unsubscribe",        channel: "email",   member_name: "Sarah Chen",    occurred_at: new Date(Date.now() - 172800000).toISOString() },
  { id: "s5", signal_type: "page_view",          channel: "web",     member_name: "Daniel Torres", occurred_at: new Date(Date.now() - 259200000).toISOString() },
];

const sectionDivider: React.CSSProperties = {
  height: 1, backgroundColor: "var(--primary-10)", border: "none", margin: "48px 0",
};

export default function AccountDetailPage() {
  const params = useParams<{ domain: string }>();
  const domain = decodeURIComponent(params.domain ?? "");

  const { data: summary, isLoading } = useAccountSummary(domain);

  // Use live data or fall back to mock
  const fatigue = summary?.fatigue ?? { ...MOCK_SUMMARY.fatigue, account_domain: domain, components: [], computed_at: new Date().toISOString() };
  const intent  = summary?.intent  ?? { account_domain: domain, ...MOCK_SUMMARY.intent, computed_at: new Date().toISOString() };
  const churn   = summary?.churn   ?? { account_domain: domain, ...MOCK_SUMMARY.churn, signal_breakdown: {}, computed_at: new Date().toISOString() };
  const nba     = summary?.current_nba ?? MOCK_SUMMARY.nba;
  const account = summary?.account ?? { id: "mock", domain, display_name: domain.split(".")[0].toUpperCase(), industry: "Technology", arr_usd: 480000, committee_size: 6, is_active: true, created_at: "", updated_at: "" };

  return (
    <div style={{ minHeight: "100vh", background: "var(--light)", display: "flex", flexDirection: "column" }}>
      <Nav title="Account Detail" />

      {/* BRAND.md: dark hero — no eyebrow */}
      <section
        style={{
          backgroundColor: "#003366",
          backgroundImage: `
            linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
          padding: "48px 48px 40px",
        }}
      >
        <div style={{ maxWidth: 1300, margin: "0 auto" }}>
          <p
            style={{
              fontFamily: "var(--fb)",
              fontSize: 11,
              letterSpacing: "3px",
              textTransform: "uppercase",
              color: "rgba(255,255,255,0.4)",
              marginBottom: 8,
              fontFamily: "Courier New",
            } as React.CSSProperties}
          >
            {domain}
          </p>
          <h1
            style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 40,
              fontWeight: 300,
              color: "#ffffff",
              margin: 0,
              lineHeight: 1.2,
            }}
          >
            {account.display_name ?? domain}{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold-light)" }}>
              {account.industry ?? ""}
            </em>
          </h1>
          <div style={{ display: "flex", gap: 24, marginTop: 16, flexWrap: "wrap" }}>
            {account.arr_usd && (
              <span style={{ fontFamily: "var(--fb)", fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
                ARR ${(account.arr_usd / 1000).toFixed(0)}k
              </span>
            )}
            <span style={{ fontFamily: "var(--fb)", fontSize: 12, color: "rgba(255,255,255,0.5)" }}>
              {account.committee_size} committee members
            </span>
          </div>
        </div>
      </section>

      <div style={{ flex: 1, maxWidth: 1300, margin: "0 auto", width: "100%", padding: "40px 48px" }}>

        {/* Score summary row */}
        {isLoading ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 40 }}>
            {Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 16, marginBottom: 40 }}>
            {/* Fatigue card */}
            <div style={{ backgroundColor: "#ffffff", borderRadius: 12, boxShadow: "0 1px 4px rgba(0,51,102,0.08)", padding: "20px 24px", display: "flex", gap: 14 }}>
              <div style={{ width: 3, backgroundColor: "var(--gold)", borderRadius: 2, flexShrink: 0 }} />
              <div>
                <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 32, fontWeight: 300, color: "var(--dark)" }}>
                  {Math.round(fatigue.score)}
                </div>
                <div style={{ fontFamily: "var(--fb)", fontSize: 10, letterSpacing: "3px", textTransform: "uppercase", color: "var(--mid)", marginBottom: 8 }}>
                  Fatigue score
                </div>
                <FatigueScoreBadge score={fatigue.score} severity={fatigue.severity} showScore={false} />
              </div>
            </div>

            {/* Intent gauge */}
            <div style={{ backgroundColor: "#ffffff", borderRadius: 12, boxShadow: "0 1px 4px rgba(0,51,102,0.08)", padding: "20px 24px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <IntentScoreGauge score={intent.intent_score} confidence={intent.confidence} size={110} />
            </div>

            {/* Churn card */}
            <div style={{ backgroundColor: "#ffffff", borderRadius: 12, boxShadow: "0 1px 4px rgba(0,51,102,0.08)", padding: "20px 24px", display: "flex", gap: 14 }}>
              <div style={{ width: 3, backgroundColor: churn.is_high_risk ? "#E03448" : "#27B97C", borderRadius: 2, flexShrink: 0 }} />
              <div>
                <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 32, fontWeight: 300, color: churn.is_high_risk ? "#E03448" : "#27B97C" }}>
                  {Math.round(churn.churn_probability * 100)}%
                </div>
                <div style={{ fontFamily: "var(--fb)", fontSize: 10, letterSpacing: "3px", textTransform: "uppercase", color: "var(--mid)" }}>
                  Churn probability
                </div>
                <div style={{ marginTop: 8, fontFamily: "var(--fb)", fontSize: 11, color: churn.is_high_risk ? "#E03448" : "#27B97C", fontWeight: 600 }}>
                  {churn.risk_level} risk
                </div>
              </div>
            </div>
          </div>
        )}

        <hr style={sectionDivider} />

        {/* NBA + Timeline columns */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 32, marginBottom: 48 }}>
          <div>
            <Eyebrow>Recommended action</Eyebrow>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 20px", lineHeight: 1.25 }}>
              Next best{" "}
              <em style={{ fontStyle: "italic", color: "var(--gold)" }}>action</em>
            </h2>
            {isLoading ? <SkeletonCard height={200} /> : nba ? <NBAActionCard action={nba} /> : (
              <div style={{ padding: 24, color: "var(--mid)", fontFamily: "var(--fb)", fontSize: 13 }}>No active recommendation.</div>
            )}
          </div>

          <div>
            <Eyebrow>Signal feed</Eyebrow>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 20px", lineHeight: 1.25 }}>
              Recent{" "}
              <em style={{ fontStyle: "italic", color: "var(--gold)" }}>signals</em>
            </h2>
            <SignalTimeline signals={MOCK_SIGNALS} maxItems={5} />
          </div>
        </div>

        <hr style={sectionDivider} />

        {/* Committee heatmap */}
        <section style={{ marginBottom: 48 }}>
          <Eyebrow>Buying committee</Eyebrow>
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 4px", lineHeight: 1.25 }}>
            Engagement{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold)" }}>heatmap</em>
          </h2>
          <p style={{ fontFamily: "var(--fb)", fontSize: 13, color: "var(--mid)", marginBottom: 20 }}>
            Signal count per committee member × channel over the last 30 days.
          </p>
          <div style={{ backgroundColor: "#ffffff", borderRadius: 12, boxShadow: "0 1px 4px rgba(0,51,102,0.08)", overflow: "hidden" }}>
            <div style={{ height: 3, backgroundColor: "var(--gold)" }} />
            <CommitteeHeatmap data={MOCK_HEATMAP} />
          </div>
        </section>

        {/* Fatigue components breakdown */}
        {fatigue.components && fatigue.components.length > 0 && (
          <>
            <hr style={sectionDivider} />
            <section style={{ marginBottom: 48 }}>
              <Eyebrow>Fatigue breakdown</Eyebrow>
              <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 20px", lineHeight: 1.25 }}>
                Component{" "}
                <em style={{ fontStyle: "italic", color: "var(--gold)" }}>analysis</em>
              </h2>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {fatigue.components.map((comp) => (
                  <div
                    key={comp.name}
                    style={{
                      backgroundColor: "#ffffff",
                      borderRadius: 10,
                      padding: "16px 20px",
                      boxShadow: "0 1px 3px rgba(0,51,102,0.07)",
                      borderLeft: "3px solid var(--gold)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                      <span style={{ fontFamily: "var(--fb)", fontSize: 12, fontWeight: 600, color: "#0a1628", textTransform: "capitalize" }}>
                        {comp.name.replace(/_/g, " ")}
                      </span>
                      <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 18, fontWeight: 300, color: "var(--dark)" }}>
                        {Math.round(comp.score)}
                      </span>
                    </div>
                    {/* BRAND.md: chart bar — track light, fill semantic color */}
                    <div style={{ height: 6, backgroundColor: "var(--light)", borderRadius: 4, overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${comp.score}%`,
                          backgroundColor: comp.score >= 70 ? "#E03448" : comp.score >= 40 ? "#F07020" : "#27B97C",
                          borderRadius: 4,
                          transition: "width 0.4s",
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        )}
      </div>

      <Footer />
    </div>
  );
}
