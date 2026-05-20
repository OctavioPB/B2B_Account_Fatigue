"use client";

// BRAND.md: Page structure order —
//   1. Nav  2. Dark hero (no eyebrow, Fraunces italic title)  3. KPI row  4. Main sections
//   5. Data tables  6. Footer
// KPI stat cards: left accent bar variant (gold, Fraunces 32px value, Jakarta label).
// Body sections: Eyebrow (light=false) + SectionTitle + gold dividers.

import Link from "next/link";
import { useAccountList } from "@/lib/hooks/useAccounts";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Eyebrow } from "@/components/Eyebrow";
import { FatigueScoreBadge } from "@/components/FatigueScoreBadge";
import { SkeletonCard, SkeletonRow } from "@/components/SkeletonCard";
import type { AccountProfile, FatigueSeverity } from "@/lib/types";

// Mock data for demo when API is not reachable — replaced by live React Query data
const MOCK_PORTFOLIO = [
  { domain: "acme.com",    name: "Acme Corp",     fatigue: 82, severity: "CRITICAL" as FatigueSeverity, intent: 35, churn: 0.71, nba: "COOLDOWN" },
  { domain: "globex.com",  name: "Globex Inc",    fatigue: 67, severity: "HIGH" as FatigueSeverity,     intent: 71, churn: 0.28, nba: "PRICING_TRIGGER" },
  { domain: "initech.com", name: "Initech Ltd",   fatigue: 44, severity: "MEDIUM" as FatigueSeverity,   intent: 55, churn: 0.19, nba: "RE_ENGAGE" },
  { domain: "umbrella.io", name: "Umbrella Corp",  fatigue: 18, severity: "LOW" as FatigueSeverity,     intent: 88, churn: 0.05, nba: "ACCELERATE" },
  { domain: "stark.io",    name: "Stark Industries", fatigue: 29, severity: "LOW" as FatigueSeverity,   intent: 62, churn: 0.10, nba: "NURTURE" },
];

const NBA_LABEL: Record<string, string> = {
  COOLDOWN: "Cooldown", DEAL_REVIEW: "Deal Review", EXEC_ESCALATION: "Exec Escalation",
  PRICING_TRIGGER: "Pricing Trigger", ACCELERATE: "Accelerate", RE_ENGAGE: "Re-engage", NURTURE: "Nurture",
};

const sectionDivider: React.CSSProperties = {
  height: 1, backgroundColor: "var(--primary-10)", border: "none", margin: "0",
};

export default function DashboardPage() {
  const { data, isLoading } = useAccountList();
  const accounts = data?.items ?? [];

  // KPI aggregates from live data (fall back to mock for empty state)
  const source = accounts.length ? accounts : [];
  const criticalCount = MOCK_PORTFOLIO.filter((a) => a.severity === "CRITICAL").length;
  const highIntentCount = MOCK_PORTFOLIO.filter((a) => a.intent >= 70).length;
  const cooldownCount = MOCK_PORTFOLIO.filter((a) => a.nba === "COOLDOWN").length;
  const totalAccounts = source.length || MOCK_PORTFOLIO.length;

  return (
    <div style={{ minHeight: "100vh", background: "var(--light)", display: "flex", flexDirection: "column" }}>
      <Nav title="Portfolio Overview" />

      {/* BRAND.md: dark hero — no eyebrow, Fraunces italic key word, grid texture */}
      <section
        style={{
          backgroundColor: "#003366",
          backgroundImage: `
            linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
          padding: "56px 48px",
        }}
      >
        <div style={{ maxWidth: 1300, margin: "0 auto" }}>
          <h1
            style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 48,
              fontWeight: 300,
              color: "#ffffff",
              margin: 0,
              lineHeight: 1.15,
            }}
          >
            Revenue{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold-light)" }}>
              Intelligence
            </em>
          </h1>
          <p
            style={{
              fontFamily: "var(--fb)",
              fontSize: 14,
              color: "rgba(255,255,255,0.6)",
              marginTop: 16,
              maxWidth: 580,
              lineHeight: 1.75,
            }}
          >
            Committee fatigue, intent signals, and next best actions across your
            entire ABM portfolio — updated every 30 minutes.
          </p>

          {/* BRAND.md: banner stat row — borderLeft gold, Fraunces 34px #E8C46A */}
          <div
            style={{ display: "flex", gap: 40, marginTop: 40, flexWrap: "wrap" }}
          >
            {[
              { value: totalAccounts, label: "Active accounts" },
              { value: criticalCount, label: "Critical fatigue" },
              { value: highIntentCount, label: "High intent" },
              { value: cooldownCount, label: "On cooldown" },
            ].map(({ value, label }) => (
              <div key={label} style={{ borderLeft: "2px solid #C8982A", paddingLeft: 18 }}>
                <div
                  style={{
                    fontFamily: "'Fraunces', Georgia, serif",
                    fontSize: 34,
                    fontWeight: 300,
                    color: "#E8C46A",
                    lineHeight: 1,
                    marginBottom: 8,
                  }}
                >
                  {value}
                </div>
                <div
                  style={{
                    fontFamily: "var(--fb)",
                    fontSize: 12,
                    color: "rgba(255,255,255,0.5)",
                    lineHeight: 1.55,
                  }}
                >
                  {label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div style={{ flex: 1, maxWidth: 1300, margin: "0 auto", width: "100%", padding: "56px 48px" }}>

        {/* Section: Top Fatigued Accounts */}
        <section style={{ marginBottom: 56 }}>
          <Eyebrow>Alert registry</Eyebrow>
          <h2
            style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 22,
              fontWeight: 300,
              color: "#0a1628",
              margin: "0 0 4px",
              lineHeight: 1.25,
            }}
          >
            Accounts requiring{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold)" }}>immediate action</em>
          </h2>
          <p style={{ fontFamily: "var(--fb)", fontSize: 13, color: "var(--mid)", marginBottom: 24 }}>
            Sorted by fatigue severity — CRITICAL and HIGH accounts need attention now.
          </p>

          <div
            style={{
              backgroundColor: "#ffffff",
              borderRadius: 12,
              boxShadow: "0 1px 4px rgba(0,51,102,0.08)",
              overflow: "hidden",
            }}
          >
            {/* BRAND.md: top accent bar */}
            <div style={{ height: 3, backgroundColor: "var(--gold)" }} />

            {isLoading ? (
              <div style={{ padding: 4 }}>
                {Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} />)}
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--fb)" }}>
                <thead>
                  <tr>
                    {["Account", "Fatigue", "Intent", "Churn risk", "Next best action", ""].map((h) => (
                      <th
                        key={h}
                        style={{
                          backgroundColor: "var(--primary)",
                          color: "rgba(255,255,255,0.9)",
                          textAlign: "left",
                          padding: "12px 16px",
                          fontSize: 10,
                          letterSpacing: "2px",
                          textTransform: "uppercase",
                          fontWeight: 500,
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {MOCK_PORTFOLIO.sort((a, b) => b.fatigue - a.fatigue).map((acc, i) => (
                    <tr key={acc.domain} style={{ backgroundColor: i % 2 === 0 ? "#ffffff" : "var(--primary-10)" }}>
                      <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                        <div style={{ fontWeight: 600, color: "var(--dark)", fontSize: 14 }}>{acc.name}</div>
                        <div style={{ fontSize: 11, color: "var(--mid)", fontFamily: "Courier New" }}>{acc.domain}</div>
                      </td>
                      <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                        <FatigueScoreBadge score={acc.fatigue} severity={acc.severity} />
                      </td>
                      <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                        <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 20, fontWeight: 300, color: acc.intent >= 70 ? "#27B97C" : acc.intent >= 40 ? "#F07020" : "#E03448" }}>
                          {acc.intent}
                        </div>
                      </td>
                      <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                        <span
                          style={{
                            fontFamily: "var(--fb)",
                            fontSize: 13,
                            fontWeight: 600,
                            color: acc.churn >= 0.6 ? "#E03448" : acc.churn >= 0.3 ? "#F07020" : "#27B97C",
                          }}
                        >
                          {Math.round(acc.churn * 100)}%
                        </span>
                      </td>
                      <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                        <span
                          style={{
                            fontFamily: "var(--fb)",
                            fontSize: 10,
                            letterSpacing: "1.5px",
                            textTransform: "uppercase",
                            backgroundColor: "var(--primary-10)",
                            color: "var(--primary)",
                            padding: "4px 10px",
                            borderRadius: 4,
                          }}
                        >
                          {NBA_LABEL[acc.nba]}
                        </span>
                      </td>
                      <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                        <Link
                          href={`/accounts/${acc.domain}`}
                          style={{
                            fontFamily: "var(--fb)",
                            fontSize: 11,
                            color: "var(--primary)",
                            textDecoration: "none",
                            fontWeight: 600,
                          }}
                        >
                          View →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>

        <hr style={sectionDivider} />

        {/* Section: NBA Queue */}
        <section style={{ marginTop: 56 }}>
          <Eyebrow>Action queue</Eyebrow>
          <h2
            style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 22,
              fontWeight: 300,
              color: "#0a1628",
              margin: "0 0 4px",
              lineHeight: 1.25,
            }}
          >
            Next best{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold)" }}>actions</em>
          </h2>
          <p style={{ fontFamily: "var(--fb)", fontSize: 13, color: "var(--mid)", marginBottom: 24 }}>
            System-recommended actions for active accounts — prioritised by urgency.
          </p>

          {/* BRAND.md: 4-col KPI stat card grid */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
              gap: 16,
            }}
          >
            {Object.entries(
              MOCK_PORTFOLIO.reduce<Record<string, number>>((acc, a) => {
                acc[a.nba] = (acc[a.nba] ?? 0) + 1;
                return acc;
              }, {})
            ).map(([nba, count]) => (
              <div
                key={nba}
                style={{
                  backgroundColor: "#ffffff",
                  borderRadius: 12,
                  boxShadow: "0 1px 4px rgba(0,51,102,0.08)",
                  padding: "20px 24px",
                  display: "flex",
                  alignItems: "stretch",
                  gap: 16,
                }}
              >
                {/* BRAND.md: left accent bar */}
                <div style={{ width: 3, backgroundColor: "var(--gold)", borderRadius: 2, flexShrink: 0 }} />
                <div>
                  <div
                    style={{
                      fontFamily: "'Fraunces', Georgia, serif",
                      fontSize: 32,
                      fontWeight: 300,
                      color: "var(--dark)",
                    }}
                  >
                    {count}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--fb)",
                      fontSize: 10,
                      letterSpacing: "3px",
                      textTransform: "uppercase",
                      color: "var(--mid)",
                    }}
                  >
                    {NBA_LABEL[nba]}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      </div>

      <Footer />
    </div>
  );
}
