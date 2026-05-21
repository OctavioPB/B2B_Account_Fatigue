"use client";

// BRAND.md: dark hero, Fraunces italic key word, gold dividers, eyebrow labels.
// Two-tab layout: Business View / Engineering View.
// All diagrams are inline SVG — no external dependencies.

import { useState } from "react";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Eyebrow } from "@/components/Eyebrow";

type View = "business" | "engineering";

// ---------------------------------------------------------------------------
// Shared styles
// ---------------------------------------------------------------------------

const prose: React.CSSProperties = {
  fontFamily: "var(--fb)",
  fontSize: 14,
  color: "#374151",
  lineHeight: 1.85,
  maxWidth: 760,
};

const sectionTitle = (italic?: string) => (
  <span>
    {italic ? (
      <>
        {italic.split(" ").slice(0, -1).join(" ")}{" "}
        <em style={{ fontStyle: "italic", color: "var(--gold)" }}>
          {italic.split(" ").slice(-1)[0]}
        </em>
      </>
    ) : null}
  </span>
);

const h2: React.CSSProperties = {
  fontFamily: "'Fraunces', Georgia, serif",
  fontSize: 22,
  fontWeight: 300,
  color: "#0a1628",
  margin: "0 0 8px",
  lineHeight: 1.3,
};

const h3: React.CSSProperties = {
  fontFamily: "'Fraunces', Georgia, serif",
  fontSize: 17,
  fontWeight: 400,
  color: "#0a1628",
  margin: "0 0 6px",
};

const card: React.CSSProperties = {
  backgroundColor: "#ffffff",
  borderRadius: 10,
  boxShadow: "0 1px 4px rgba(0,51,102,0.07)",
  padding: "24px 28px",
};

const divider: React.CSSProperties = {
  height: 1,
  backgroundColor: "var(--primary-10)",
  border: "none",
  margin: "48px 0",
};

const tag = (color: string, bg: string): React.CSSProperties => ({
  display: "inline-block",
  fontFamily: "var(--fb)",
  fontSize: 9,
  letterSpacing: "2px",
  textTransform: "uppercase",
  color,
  backgroundColor: bg,
  padding: "3px 9px",
  borderRadius: 4,
  fontWeight: 600,
});

// ---------------------------------------------------------------------------
// Business View — Before / After diagram
// ---------------------------------------------------------------------------

function BeforeAfterDiagram() {
  return (
    <svg
      viewBox="0 0 820 260"
      style={{ width: "100%", maxWidth: 820, display: "block" }}
      aria-label="Before and after diagram showing buying committee coordination"
      role="img"
    >
      {/* ---- BEFORE panel ---- */}
      <rect x="0" y="0" width="375" height="260" rx="10" fill="#FEF2F2" stroke="#FECACA" strokeWidth="1" />
      <text x="187" y="26" textAnchor="middle" fontFamily="var(--fb)" fontSize="10" fill="#9CA3AF" letterSpacing="2">BEFORE — FRAGMENTED OUTREACH</text>

      {/* Tool boxes */}
      {[
        { y: 45,  label: "Marketing\nAutomation", color: "#EF4444" },
        { y: 115, label: "Sales\nCadence",        color: "#F97316" },
        { y: 185, label: "CRM /\nOps",            color: "#8B5CF6" },
      ].map(({ y, label, color }) => (
        <g key={y}>
          <rect x="20" y={y} width="90" height="50" rx="6" fill={color} opacity="0.12" stroke={color} strokeWidth="1.2" />
          {label.split("\n").map((line, i) => (
            <text key={i} x="65" y={y + 20 + i * 14} textAnchor="middle" fontFamily="var(--fb)" fontSize="10" fill={color} fontWeight="600">
              {line}
            </text>
          ))}
        </g>
      ))}

      {/* Contact dots (committee members) */}
      {[
        { cx: 240, cy: 52,  label: "CFO" },
        { cx: 290, cy: 85,  label: "CTO" },
        { cx: 320, cy: 130, label: "VP Ops" },
        { cx: 270, cy: 165, label: "IT Dir" },
        { cx: 240, cy: 200, label: "Legal" },
      ].map(({ cx, cy, label }) => (
        <g key={label}>
          <circle cx={cx} cy={cy} r="14" fill="#F3F4F6" stroke="#D1D5DB" strokeWidth="1.2" />
          <text x={cx} y={cy + 4} textAnchor="middle" fontFamily="var(--fb)" fontSize="8" fill="#374151">{label}</text>
        </g>
      ))}

      {/* Chaotic arrows — each tool → random contacts */}
      {[
        { x1: 110, y1: 68,  x2: 225, y2: 52  },
        { x1: 110, y1: 72,  x2: 225, y2: 85  },
        { x1: 110, y1: 140, x2: 225, y2: 130 },
        { x1: 110, y1: 143, x2: 225, y2: 165 },
        { x1: 110, y1: 208, x2: 225, y2: 200 },
        { x1: 110, y1: 70,  x2: 225, y2: 165 },
        { x1: 110, y1: 210, x2: 225, y2: 85  },
      ].map((a, i) => (
        <line key={i} x1={a.x1} y1={a.y1} x2={a.x2} y2={a.y2}
          stroke="#EF4444" strokeWidth="1" strokeDasharray="3,2" opacity="0.45" />
      ))}

      {/* Conflict icon */}
      <text x="187" y="245" textAnchor="middle" fontFamily="var(--fb)" fontSize="10" fill="#EF4444">
        No coordination · duplicated outreach · fatigue invisible
      </text>

      {/* ---- DIVIDER arrow ---- */}
      <text x="403" y="112" textAnchor="middle" fontFamily="'Fraunces'" fontSize="28" fill="#C8982A" fontStyle="italic">→</text>
      <text x="403" y="140" textAnchor="middle" fontFamily="var(--fb)" fontSize="8" fill="#9CA3AF" letterSpacing="1">harmoni</text>

      {/* ---- AFTER panel ---- */}
      <rect x="430" y="0" width="375" height="260" rx="10" fill="#F0FDF4" stroke="#86EFAC" strokeWidth="1" />
      <text x="617" y="26" textAnchor="middle" fontFamily="var(--fb)" fontSize="10" fill="#9CA3AF" letterSpacing="2">AFTER — COMMITTEE INTELLIGENCE</text>

      {/* harmoni engine box */}
      <rect x="455" y="40" width="320" height="70" rx="8" fill="#003366" />
      <text x="615" y="66" textAnchor="middle" fontFamily="'Fraunces'" fontSize="13" fill="white" fontWeight="300">harmoni</text>
      <text x="615" y="83" textAnchor="middle" fontFamily="var(--fb)" fontSize="9" fill="rgba(255,255,255,0.6)" letterSpacing="1.5">ACCOUNT FATIGUE · INTENT · CHURN · NBA</text>
      <text x="615" y="100" textAnchor="middle" fontFamily="var(--fb)" fontSize="8" fill="#E8C46A">all 3 tools feed in · one committee view out</text>

      {/* Arrows from tools → harmoni */}
      <path d="M455,60 Q445,75 455,75" stroke="#22C55E" strokeWidth="1.5" fill="none" />
      <text x="449" y="72" fontFamily="var(--fb)" fontSize="8" fill="#6B7280">3 sources</text>

      {/* Committee members — organized */}
      {[
        { cx: 490, cy: 168, label: "CFO",    weight: "High" },
        { cx: 545, cy: 168, label: "CTO",    weight: "High" },
        { cx: 615, cy: 168, label: "VP Ops", weight: "Med"  },
        { cx: 685, cy: 168, label: "IT Dir", weight: "Low"  },
        { cx: 740, cy: 168, label: "Legal",  weight: "Low"  },
      ].map(({ cx, cy, label, weight }) => (
        <g key={label}>
          <circle cx={cx} cy={cy} r="16" fill="#DCFCE7" stroke="#22C55E" strokeWidth="1.2" />
          <text x={cx} y={cy + 3} textAnchor="middle" fontFamily="var(--fb)" fontSize="8" fill="#166534" fontWeight="600">{label}</text>
          <text x={cx} y={cy + 14} textAnchor="middle" fontFamily="var(--fb)" fontSize="7" fill="#9CA3AF">{weight}</text>
        </g>
      ))}

      {/* Single clean NBA output */}
      <rect x="545" y="200" width="140" height="40" rx="6" fill="#C8982A" />
      <text x="615" y="218" textAnchor="middle" fontFamily="var(--fb)" fontSize="9" fill="white" letterSpacing="1.5">NEXT BEST ACTION</text>
      <text x="615" y="232" textAnchor="middle" fontFamily="'Fraunces'" fontSize="11" fill="white" fontStyle="italic">one signal · right time</text>

      {/* Arrow from harmoni → NBA */}
      <line x1="615" y1="110" x2="615" y2="152" stroke="#22C55E" strokeWidth="1.5" markerEnd="url(#arrow-green)" />
      <line x1="615" y1="184" x2="615" y2="200" stroke="#C8982A" strokeWidth="1.5" />

      <defs>
        <marker id="arrow-green" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#22C55E" />
        </marker>
      </defs>

      <text x="617" y="252" textAnchor="middle" fontFamily="var(--fb)" fontSize="10" fill="#166534">
        Unified committee view · automated cooldowns
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Engineering View — Pipeline Architecture diagram
// ---------------------------------------------------------------------------

function PipelineDiagram() {
  const stages = [
    {
      x: 10, w: 108, label: "Signal\nSources",
      sub: ["CRM / HubSpot", "Web Analytics", "Email Events", "Webinar / Video"],
      bg: "#E0EAF4", border: "#99BBDD", text: "#003366",
    },
    {
      x: 148, w: 108, label: "Kafka CEP",
      sub: ["Schema Registry", "Avro validation", "DLQ routing", "4 topics"],
      bg: "#003366", border: "#1A4D80", text: "#ffffff",
    },
    {
      x: 286, w: 108, label: "Identity\nResolution",
      sub: ["Domain normalise", "Alias table", "CRM xref", "IP lookup"],
      bg: "#1A4D80", border: "#336699", text: "#ffffff",
    },
    {
      x: 424, w: 108, label: "Scoring\nEngine",
      sub: ["Fatigue Score", "Intent Network", "Churn Predictor", "30-min / 4-hr"],
      bg: "#336699", border: "#99BBDD", text: "#ffffff",
    },
    {
      x: 562, w: 108, label: "NBA\nOrchestrator",
      sub: ["Rules engine", "7 action types", "Priority chain", "Redis cooldown"],
      bg: "#C8982A", border: "#A67820", text: "#ffffff",
    },
    {
      x: 700, w: 108, label: "REST API\n+ Dashboard",
      sub: ["FastAPI / JWT", "Multi-tenant", "Next.js 14", "Webhooks"],
      bg: "#0a1628", border: "#1A4D80", text: "#ffffff",
    },
  ];

  return (
    <svg viewBox="0 0 820 260" style={{ width: "100%", maxWidth: 820, display: "block" }}
      aria-label="harmoni engineering pipeline architecture" role="img">
      <defs>
        <marker id="arr" markerWidth="7" markerHeight="7" refX="5" refY="3.5" orient="auto">
          <path d="M0,0 L7,3.5 L0,7 Z" fill="#99BBDD" />
        </marker>
      </defs>

      {/* Pipeline label */}
      <text x="410" y="18" textAnchor="middle" fontFamily="var(--fb)" fontSize="9" fill="#9CA3AF" letterSpacing="3">
        REAL-TIME PIPELINE
      </text>

      {stages.map((s, i) => {
        const lines = s.label.split("\n");
        return (
          <g key={i}>
            {/* Box */}
            <rect x={s.x} y="28" width={s.w} height="150" rx="8"
              fill={s.bg} stroke={s.border} strokeWidth="1.2" />

            {/* Stage title */}
            {lines.map((line, li) => (
              <text key={li} x={s.x + s.w / 2} y={50 + li * 16}
                textAnchor="middle" fontFamily="'Fraunces'" fontSize="12"
                fill={s.text} fontWeight="300">
                {line}
              </text>
            ))}

            {/* Divider */}
            <line x1={s.x + 12} y1={50 + lines.length * 16 + 4}
                  x2={s.x + s.w - 12} y2={50 + lines.length * 16 + 4}
              stroke={s.text} strokeWidth="0.5" opacity="0.25" />

            {/* Sub-labels */}
            {s.sub.map((sub, si) => (
              <text key={si} x={s.x + s.w / 2} y={76 + lines.length * 14 + si * 17}
                textAnchor="middle" fontFamily="var(--fb)" fontSize="9"
                fill={s.text} opacity="0.75">
                {sub}
              </text>
            ))}

            {/* Arrow to next */}
            {i < stages.length - 1 && (
              <line
                x1={s.x + s.w + 1} y1="103"
                x2={stages[i + 1].x - 2} y2="103"
                stroke="#99BBDD" strokeWidth="1.5"
                markerEnd="url(#arr)"
              />
            )}
          </g>
        );
      })}

      {/* Infrastructure row */}
      <text x="410" y="202" textAnchor="middle" fontFamily="var(--fb)" fontSize="9" fill="#9CA3AF" letterSpacing="3">
        INFRASTRUCTURE LAYER
      </text>

      {[
        { x: 40,  label: "PostgreSQL 15",  sub: "Account state · tenants",  fill: "#336633" },
        { x: 210, label: "Redis 7",         sub: "Cooldowns · rate limits",  fill: "#CC2200" },
        { x: 380, label: "ClickHouse",      sub: "Scoring aggregates",       fill: "#FFB200" },
        { x: 550, label: "Airflow + dbt",   sub: "Batch pipelines · SCD2",   fill: "#1A6B8A" },
        { x: 680, label: "PgBouncer",       sub: "Connection pooling",       fill: "#444466" },
      ].map((infra) => (
        <g key={infra.x}>
          <rect x={infra.x} y="210" width="118" height="42" rx="6"
            fill={infra.fill} opacity="0.12" stroke={infra.fill} strokeWidth="1" />
          <text x={infra.x + 59} y="228" textAnchor="middle"
            fontFamily="var(--fb)" fontSize="10" fill={infra.fill} fontWeight="600">
            {infra.label}
          </text>
          <text x={infra.x + 59} y="242" textAnchor="middle"
            fontFamily="var(--fb)" fontSize="8" fill="#6B7280">
            {infra.sub}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Engineering — Multi-tenant isolation diagram
// ---------------------------------------------------------------------------

function MultiTenantDiagram() {
  const tenants = [
    { label: "Tenant A\nacme-corp", schema: "tenant_acme_corp", color: "#336699" },
    { label: "Tenant B\nglobex-inc", schema: "tenant_globex_inc", color: "#1A4D80" },
    { label: "Tenant C\nstark-io",  schema: "tenant_stark_io",  color: "#003366" },
  ];

  return (
    <svg viewBox="0 0 700 190" style={{ width: "100%", maxWidth: 700, display: "block" }}
      aria-label="Multi-tenant schema isolation diagram" role="img">
      <defs>
        <marker id="arr2" markerWidth="6" markerHeight="6" refX="4" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" fill="#99BBDD" />
        </marker>
      </defs>

      {/* JWT Auth layer */}
      <rect x="260" y="8" width="180" height="44" rx="8" fill="#C8982A" />
      <text x="350" y="28" textAnchor="middle" fontFamily="var(--fb)" fontSize="11" fill="white" fontWeight="600">
        JWT Bearer Token
      </text>
      <text x="350" y="44" textAnchor="middle" fontFamily="var(--fb)" fontSize="9" fill="rgba(255,255,255,0.75)">
        sub · slug · schema · plan · rpm
      </text>

      {/* API middleware */}
      <rect x="260" y="72" width="180" height="36" rx="8" fill="#003366" />
      <text x="350" y="86" textAnchor="middle" fontFamily="var(--fb)" fontSize="10" fill="white" fontWeight="600">
        TenantContext Middleware
      </text>
      <text x="350" y="100" textAnchor="middle" fontFamily="var(--fb)" fontSize="8" fill="rgba(255,255,255,0.65)">
        validates · injects · rate-limits
      </text>

      {/* Arrow JWT → middleware */}
      <line x1="350" y1="52" x2="350" y2="72" stroke="#99BBDD" strokeWidth="1.5" markerEnd="url(#arr2)" />

      {/* Arrows middleware → schemas */}
      <line x1="260" y1="90" x2="90" y2="140" stroke="#99BBDD" strokeWidth="1.2" markerEnd="url(#arr2)" />
      <line x1="350" y1="108" x2="350" y2="138" stroke="#99BBDD" strokeWidth="1.2" markerEnd="url(#arr2)" />
      <line x1="440" y1="90" x2="610" y2="140" stroke="#99BBDD" strokeWidth="1.2" markerEnd="url(#arr2)" />

      {/* PostgreSQL schemas */}
      {tenants.map((t, i) => {
        const cx = i === 0 ? 30 : i === 1 ? 280 : 540;
        const lines = t.label.split("\n");
        return (
          <g key={i}>
            <rect x={cx} y="140" width="130" height="44" rx="8" fill={t.color} />
            {lines.map((line, li) => (
              <text key={li} x={cx + 65} y={154 + li * 14}
                textAnchor="middle" fontFamily="var(--fb)" fontSize="9"
                fill="white" fontWeight="600">{line}</text>
            ))}
            <text x={cx + 65} y="176" textAnchor="middle"
              fontFamily="var(--fb)" fontSize="7" fill="rgba(255,255,255,0.55)"
              fontStyle="italic">{t.schema}</text>
          </g>
        );
      })}

      <text x="350" y="10" textAnchor="middle" fontFamily="var(--fb)" fontSize="9" fill="#9CA3AF" letterSpacing="2">
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Business View
// ---------------------------------------------------------------------------

function BusinessView() {
  return (
    <div>
      {/* Problem */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>The problem</Eyebrow>
        <h2 style={h2}>
          B2B deals are decided by committees,{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>not individuals</em>
        </h2>
        <p style={{ ...prose, marginTop: 16 }}>
          A typical enterprise purchase involves six to ten decision-makers: a CFO, CTO, VP of Operations,
          an IT director, legal, and procurement. Each of these stakeholders has a different agenda, a
          different information threshold, and a different relationship with the vendor. Yet most commercial
          outreach tools — marketing automation platforms, sales engagement sequences, CRM workflows — treat
          each stakeholder as an isolated lead record.
        </p>
        <p style={{ ...prose, marginTop: 12 }}>
          The result is a coordination failure that plays out in three predictable ways:
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 16, marginTop: 20 }}>
          {[
            {
              label: "Outreach collision",
              desc: "Marketing sends a nurture email the same week sales sends a cold outreach to the same account. The CFO receives both, the CTO receives neither.",
              accent: "#EF4444",
            },
            {
              label: "Invisible fatigue",
              desc: "No system tracks how many touches the account has received across all channels combined. By the time engagement drops, the committee is already burned out.",
              accent: "#F97316",
            },
            {
              label: "Timing mismatch",
              desc: "A pricing conversation is triggered because one contact opened an email, without knowing that the budget holder just went dark and the CTO is on leave.",
              accent: "#8B5CF6",
            },
          ].map(({ label, desc, accent }) => (
            <div key={label} style={{ ...card, borderLeft: `3px solid ${accent}` }}>
              <h3 style={{ ...h3, color: accent, fontSize: 14 }}>{label}</h3>
              <p style={{ ...prose, fontSize: 13, marginTop: 6 }}>{desc}</p>
            </div>
          ))}
        </div>
      </section>

      <hr style={divider} />

      {/* Before / After */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>Coordination model</Eyebrow>
        <h2 style={h2}>
          From contact-level noise to{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>account-level signal</em>
        </h2>
        <p style={{ ...prose, marginTop: 12, marginBottom: 28 }}>
          harmoni sits between existing tools and the people who use them. It does not replace CRM or
          marketing automation — it reads signals from all of them and produces a single, consolidated
          view of each buying committee's health. Every recommendation is scoped to the account, not
          the contact.
        </p>
        <div style={{ ...card, padding: 28 }}>
          <BeforeAfterDiagram />
        </div>
      </section>

      <hr style={divider} />

      {/* Core capabilities */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>Core capabilities</Eyebrow>
        <h2 style={h2}>
          Three scores,{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>one recommendation</em>
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 20, marginTop: 24 }}>
          {[
            {
              score: "Account Fatigue Score",
              range: "0 – 100",
              desc: "A composite measure of collective cognitive load across the buying committee. Computed from outreach frequency, engagement decay rate, unsubscribe and spam signals, contact concentration, and recency of meaningful engagement. Refreshed every 30 minutes.",
              color: "#E03448",
              thresholds: ["LOW < 40", "MEDIUM 40–59", "HIGH 60–79", "CRITICAL ≥ 80"],
            },
            {
              score: "Intent Score",
              range: "0 – 100",
              desc: "An account-level aggregation of weak intent signals from multiple committee members: pricing page views, webinar attendance, video completion, RFP-related content. Member role weights and signal recency decay are applied before aggregation.",
              color: "#27B97C",
              thresholds: ["High ≥ 70", "Medium 40–69", "Low < 40"],
            },
            {
              score: "Churn Probability",
              range: "0 – 1",
              desc: "A binary classifier predicting deal abandonment risk in the next 30 days. Features include engagement velocity, response rate trends, stakeholder activity gaps, and signal composition changes. Recomputed every 4 hours.",
              color: "#F07020",
              thresholds: ["Critical ≥ 0.60", "High 0.35–0.59", "Medium 0.15–0.34", "Low < 0.15"],
            },
          ].map(({ score, range, desc, color, thresholds }) => (
            <div key={score} style={{ ...card, borderTop: `3px solid ${color}` }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                <h3 style={{ ...h3, fontSize: 15 }}>{score}</h3>
                <span style={tag(color, color + "18")}>{range}</span>
              </div>
              <p style={{ ...prose, fontSize: 13 }}>{desc}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 12 }}>
                {thresholds.map((t) => (
                  <span key={t} style={{ fontFamily: "var(--fb)", fontSize: 9, letterSpacing: "1px", color: "#6B7280", backgroundColor: "#F3F4F6", padding: "2px 7px", borderRadius: 3 }}>
                    {t}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>

      <hr style={divider} />

      {/* NBA actions */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>Decision engine</Eyebrow>
        <h2 style={h2}>
          Seven next best{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>action types</em>
        </h2>
        <p style={{ ...prose, marginTop: 12, marginBottom: 24 }}>
          The orchestrator applies a deterministic priority chain to the three scores and outputs exactly
          one action per account. The priority order reflects the consequences of inaction: getting a
          fatigued account wrong costs more than missing an acceleration opportunity.
        </p>
        <div style={{ ...card, overflowX: "auto" }}>
          <div style={{ height: 3, backgroundColor: "var(--gold)", margin: "-24px -28px 24px" }} />
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--fb)", fontSize: 13 }}>
            <thead>
              <tr>
                {["Priority", "Action", "Trigger condition", "Business intent"].map((h) => (
                  <th key={h} style={{ backgroundColor: "var(--primary)", color: "rgba(255,255,255,0.85)", textAlign: "left", padding: "10px 14px", fontSize: 9, letterSpacing: "2px", textTransform: "uppercase" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                { p: 1, action: "COOLDOWN",        trigger: "Fatigue ≥ 80 (CRITICAL)",                outcome: "Pause all outreach, enforce Redis cooldown lock (30 days). Protects the relationship." },
                { p: 2, action: "DEAL REVIEW",     trigger: "Fatigue ≥ 60 AND churn ≥ 0.50",          outcome: "Flag for internal sales review before further outreach. No automated actions dispatched." },
                { p: 3, action: "EXEC ESCALATION", trigger: "ARR > $500k AND intent ≥ 65",            outcome: "Route to AE for VP-to-VP or C-suite engagement. Signals strategic priority to the account." },
                { p: 4, action: "ACCELERATE",      trigger: "Fatigue ≤ 30 AND intent ≥ 75",           outcome: "Compress the evaluation cycle. Schedule executive demo, send decision-support materials." },
                { p: 5, action: "PRICING TRIGGER", trigger: "Intent ≥ 65 AND financial stakeholder active", outcome: "Surface pricing and ROI materials. Financial decision-maker has crossed the intent threshold." },
                { p: 6, action: "RE-ENGAGE",       trigger: "Engagement gap > 10 days",               outcome: "Personalised re-engagement with new angle. Used for stalled mid-funnel accounts." },
                { p: 7, action: "NURTURE",         trigger: "Default — all other cases",              outcome: "Continue educational content track. Low-pressure, committee-appropriate pacing." },
              ].map((row, i) => (
                <tr key={row.p} style={{ backgroundColor: i % 2 === 0 ? "#ffffff" : "#F9FAFB" }}>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", fontFamily: "'Fraunces'", fontSize: 16, fontWeight: 300, color: "var(--mid)" }}>{row.p}</td>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)" }}>
                    <span style={tag("var(--primary)", "var(--primary-10)")}>{row.action}</span>
                  </td>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", color: "#374151" }}>{row.trigger}</td>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", color: "var(--mid)" }}>{row.outcome}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <hr style={divider} />

      {/* Pain points */}
      <section style={{ marginBottom: 16 }}>
        <Eyebrow>Pain point mapping</Eyebrow>
        <h2 style={h2}>
          Where harmoni fits in the{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>revenue stack</em>
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 24 }}>
          {[
            {
              pain: "\"We don't know when to stop outreaching\"",
              fix: "The fatigue score gives a quantified, real-time answer per account. The COOLDOWN action enforces the pause automatically — no human judgment required in the moment.",
            },
            {
              pain: "\"Marketing and sales are stepping on each other\"",
              fix: "All signals route through the same account identity resolution layer. Every team sees the same committee health view before acting. One active NBA per account at a time.",
            },
            {
              pain: "\"We missed a hot account because of poor timing\"",
              fix: "The intent network model tracks signal velocity across the committee. When multiple members cross the intent threshold simultaneously, the system acts within 30 minutes.",
            },
            {
              pain: "\"Our data is fragmented across four tools\"",
              fix: "Kafka-based event ingestion normalises signals from any source under a canonical account key (email domain). SCD Type 2 preserves full historical state — no data is ever overwritten.",
            },
          ].map(({ pain, fix }) => (
            <div key={pain} style={{ ...card }}>
              <p style={{ fontFamily: "'Fraunces'", fontSize: 14, fontStyle: "italic", color: "#374151", marginBottom: 10, lineHeight: 1.55 }}>
                {pain}
              </p>
              <p style={{ ...prose, fontSize: 13, color: "#6B7280" }}>{fix}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Engineering View
// ---------------------------------------------------------------------------

function EngineeringView() {
  return (
    <div>
      {/* Architecture */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>System architecture</Eyebrow>
        <h2 style={h2}>
          End-to-end{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>pipeline</em>
        </h2>
        <p style={{ ...prose, marginTop: 12, marginBottom: 24 }}>
          The system is structured as a real-time event-driven pipeline (Kafka) layered on top of a
          batch scoring pipeline (Airflow + dbt). The two pipelines share the same operational database
          (PostgreSQL) and write to the same account state. The REST API layer serves both human users
          (Next.js dashboard) and machine consumers (partner webhooks with HMAC-SHA256 signatures).
        </p>
        <div style={{ ...card, padding: 28 }}>
          <PipelineDiagram />
        </div>
      </section>

      <hr style={divider} />

      {/* Data flow detail */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>Data flow</Eyebrow>
        <h2 style={h2}>
          Signal ingestion to{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>scored account</em>
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 20, marginTop: 24 }}>
          {[
            {
              step: "01",
              title: "Event ingestion — Kafka CEP",
              body: "Source connectors (CRM webhook, web pixel, email event stream, webinar webhook) produce Avro-serialised messages to four topics: harmoni.crm.contact_activity, harmoni.web.pageview, harmoni.email.engagement, harmoni.webinar.attendance. The Schema Registry enforces contract compatibility at produce time. Invalid messages route to harmoni.dlq with a structured error envelope — they are never silently dropped.",
            },
            {
              step: "02",
              title: "Account identity resolution",
              body: "The consumer pipeline runs a four-step waterfall resolver against each event: (1) explicit email domain lookup, (2) IP-to-company mapping via Clearbit, (3) CRM company-ID cross-reference, (4) alias table for known M&A relationships. Unresolved events (< 5% in production) are placed in a quarantine queue for manual review. Every resolved event carries a confidence tier: HIGH / MEDIUM / LOW.",
            },
            {
              step: "03",
              title: "Dimensional modelling — dbt / SCD Type 2",
              body: "Airflow triggers dbt hourly. The dbt project follows a strict staging → intermediate → mart layer: stg_ models clean source data, int_ models join and aggregate, fct_ models produce query-ready facts. Account and CommitteeMember dimension tables use SCD Type 2 snapshots — every org change, role change, or domain alias creates a new row with valid_from / valid_to bounds. Historical rows are never mutated.",
            },
            {
              step: "04",
              title: "Scoring pipeline",
              body: "Three independent Airflow DAGs compute scores on different cadences. The fatigue DAG (every 30 min) reads from the operational database and writes to account_fatigue_scores. The intent DAG (every 4 hr) runs the logistic regression Intent Network Model against aggregated signal features. The churn DAG (every 4 hr) runs a binary classifier against 30-day rolling features. All scores are timestamped and append-only — no score row is ever updated.",
            },
            {
              step: "05",
              title: "NBA orchestration",
              body: "The NBA DAG (hourly) reads the latest scores for every active account and applies a deterministic priority chain to select one action. Cooldown state is checked in Redis before any action is written — if a per-account or per-member cooldown is active, the action is suppressed. The output is written to next_best_actions with an expiry timestamp. Exactly one active NBA per account is maintained via the superseded_by foreign key chain.",
            },
            {
              step: "06",
              title: "API and event dispatch",
              body: "The FastAPI application serves the current account state (scores + active NBA + committee profile) via REST endpoints. All endpoints are multi-tenant: the JWT claims carry the PostgreSQL schema name, and every query is schema-prefixed before execution. Outbound webhooks are dispatched asynchronously via asyncio.gather with HMAC-SHA256 signatures. Circuit breakers (CLOSED / OPEN / HALF_OPEN) wrap all external integration calls.",
            },
          ].map(({ step, title, body }) => (
            <div key={step} style={{ ...card, position: "relative" }}>
              <div style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontSize: 44,
                fontWeight: 300,
                color: "#F1F5F9",
                position: "absolute",
                top: 12,
                right: 16,
                lineHeight: 1,
                userSelect: "none",
              }}>
                {step}
              </div>
              <h3 style={{ ...h3, paddingRight: 40 }}>{title}</h3>
              <p style={{ ...prose, fontSize: 13, marginTop: 8 }}>{body}</p>
            </div>
          ))}
        </div>
      </section>

      <hr style={divider} />

      {/* Multi-tenancy */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>Multi-tenancy</Eyebrow>
        <h2 style={h2}>
          Schema-level{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>tenant isolation</em>
        </h2>
        <p style={{ ...prose, marginTop: 12, marginBottom: 24 }}>
          Each tenant is provisioned with a dedicated PostgreSQL schema (e.g. <code style={{ fontFamily: "monospace", fontSize: 12, backgroundColor: "#F3F4F6", padding: "1px 5px", borderRadius: 3 }}>tenant_acme_corp</code>).
          The JWT payload carries the schema name as a claim. The TenantContext middleware extracts and validates
          the claim, then injects it into every downstream query via the schema search path. A tenant with a
          valid JWT for schema A cannot read data from schema B — the PostgreSQL row-level security boundary
          is enforced before application code runs.
        </p>
        <div style={{ ...card, padding: 28 }}>
          <MultiTenantDiagram />
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 24 }}>
          {[
            { label: "JWT claims", detail: "sub (tenant UUID) · slug · schema_name · plan · rate_limit_rpm · exp" },
            { label: "Rate limiting", detail: "Redis INCR + EXPIRE per (tenant_id, 60s window). Fail-open on Redis unavailability. Returns Retry-After header on 429." },
            { label: "Audit log", detail: "Every POST / PUT / PATCH / DELETE is appended to audit_log with tenant_id, client_ip, request body (sanitised). Fire-and-forget via asyncio.create_task." },
            { label: "Schema provisioning", detail: "alembic -x tenant=<schema_name> upgrade head runs per-tenant migrations. Schema creation requires the admin bearer token." },
          ].map(({ label, detail }) => (
            <div key={label} style={{ backgroundColor: "#F9FAFB", borderRadius: 8, padding: "14px 18px", borderLeft: "3px solid var(--primary-10)" }}>
              <div style={{ fontFamily: "var(--fb)", fontSize: 10, letterSpacing: "2px", textTransform: "uppercase", color: "var(--mid)", marginBottom: 4 }}>{label}</div>
              <p style={{ fontFamily: "var(--fb)", fontSize: 13, color: "#374151", margin: 0 }}>{detail}</p>
            </div>
          ))}
        </div>
      </section>

      <hr style={divider} />

      {/* Tech stack reference */}
      <section style={{ marginBottom: 52 }}>
        <Eyebrow>Technology reference</Eyebrow>
        <h2 style={h2}>
          Stack and{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>rationale</em>
        </h2>
        <div style={{ ...card, overflowX: "auto", marginTop: 24 }}>
          <div style={{ height: 3, backgroundColor: "var(--gold)", margin: "-24px -28px 24px" }} />
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--fb)", fontSize: 13 }}>
            <thead>
              <tr>
                {["Component", "Technology", "Version", "Rationale"].map((h) => (
                  <th key={h} style={{ backgroundColor: "var(--primary)", color: "rgba(255,255,255,0.85)", textAlign: "left", padding: "10px 14px", fontSize: 9, letterSpacing: "2px", textTransform: "uppercase" }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[
                { c: "Event streaming",    t: "Apache Kafka + Confluent",   v: "7.6.x",   r: "At-least-once delivery, Avro schema enforcement, DLQ routing. Schema Registry prevents silent contract breaks." },
                { c: "Workflow orch.",     t: "Apache Airflow",              v: "2.9.x",   r: "DAG-based dependency management, TaskFlow API, native scheduling. LocalExecutor for dev; CeleryExecutor planned for prod scale." },
                { c: "Data transforms",   t: "dbt Core",                    v: "1.8.x",   r: "SQL-based lineage, built-in SCD Type 2 snapshot materialisation, schema tests (not_null, unique, accepted_values)." },
                { c: "Operational DB",    t: "PostgreSQL 15",               v: "15.x",    r: "Schema-based tenant isolation, JSONB for raw signals, asyncpg for async Python access. PgBouncer for connection pooling." },
                { c: "Analytics store",   t: "ClickHouse",                  v: "24.3",    r: "Columnar storage for high-throughput aggregated scoring queries. Separate from operational DB to avoid OLTP/OLAP contention." },
                { c: "Real-time state",   t: "Redis 7",                     v: "7.x",     r: "Sub-millisecond cooldown lock reads/writes, rate limit counters (INCR + EXPIRE), session state. appendonly for durability." },
                { c: "ML / scoring",      t: "scikit-learn",                v: "1.5.x",   r: "Logistic regression for intent (interpretable, fast inference), gradient boosting for churn. joblib for model serialisation." },
                { c: "RL experiments",    t: "RLlib (isolated)",            v: "—",       r: "Behind FEATURE_RL_ORCHESTRATOR=false feature flag. Not on the production import path. Requires offline eval to graduate." },
                { c: "API framework",     t: "FastAPI + Pydantic v2",       v: "0.136.x", r: "Async-first, automatic OpenAPI generation, Pydantic v2 for validation performance. JWT via python-jose." },
                { c: "Connection pool",   t: "PgBouncer (transaction mode)","v": "—",     r: "500 concurrent API users mapped to ~25 live PostgreSQL connections. Transaction mode: connection held only during query execution." },
                { c: "Dashboard",         t: "Next.js 14 App Router",       v: "14.x",    r: "Server Components by default, Edge middleware for route protection, React Query for server state, Zustand for client state." },
                { c: "Infrastructure",    t: "Terraform + Docker Compose",  v: "—",       r: "Terraform for AWS (VPC, MSK, RDS); Docker Compose for local dev parity. All services exposed with healthchecks." },
                { c: "Observability",     t: "Prometheus + Grafana + Loki", v: "—",       r: "9-panel Grafana dashboard, 4 PagerDuty-wired alert rules (Kafka lag, DAG failure, API error rate, NBA dispatch failure)." },
              ].map((row, i) => (
                <tr key={row.c} style={{ backgroundColor: i % 2 === 0 ? "#ffffff" : "#F9FAFB" }}>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", fontWeight: 600, color: "var(--dark)", whiteSpace: "nowrap" }}>{row.c}</td>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", fontFamily: "monospace", fontSize: 12, color: "var(--primary)" }}>{row.t}</td>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", color: "var(--mid)", whiteSpace: "nowrap" }}>{row.v}</td>
                  <td style={{ padding: "10px 14px", borderBottom: "1px solid var(--primary-10)", color: "#6B7280" }}>{row.r}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <hr style={divider} />

      {/* Security */}
      <section style={{ marginBottom: 16 }}>
        <Eyebrow>Security & reliability</Eyebrow>
        <h2 style={h2}>
          OWASP ASVS Level 2{" "}
          <em style={{ fontStyle: "italic", color: "var(--gold)" }}>hardening</em>
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 16, marginTop: 24 }}>
          {[
            { label: "Security headers",  detail: "HSTS max-age=31536000, X-Content-Type-Options nosniff, X-Frame-Options DENY, CSP default-src 'none' (API) / relaxed (docs), Referrer-Policy strict-origin, Permissions-Policy. Server and X-Powered-By headers removed." },
            { label: "Circuit breakers",  detail: "CLOSED → OPEN → HALF_OPEN per integration (HubSpot, Salesloft, Slack, Clearbit, OpenAI). asyncio.Lock for state safety. Recovery timeout and success_threshold per breaker. GET /health surfaces state." },
            { label: "Audit trail",       detail: "Append-only audit_log table. PostgreSQL triggers prevent UPDATE or DELETE. Body sanitisation redacts keys matching (secret|password|token|key|credential). Max 8 KB body stored." },
            { label: "Load gates",        detail: "Locust load test: 500 concurrent users, p99 < 200ms, zero 5xx. Kafka load test: 10,000 events/min sustained, zero message loss. Both run as CI gates before any production deploy." },
          ].map(({ label, detail }) => (
            <div key={label} style={{ ...card, borderTop: "3px solid var(--primary-10)" }}>
              <h3 style={{ ...h3, fontSize: 14 }}>{label}</h3>
              <p style={{ ...prose, fontSize: 13, marginTop: 6 }}>{detail}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function InfoPage() {
  const [view, setView] = useState<View>("business");

  return (
    <div style={{ minHeight: "100vh", background: "var(--light)", display: "flex", flexDirection: "column" }}>
      <Nav title="Platform Info" />

      {/* Dark hero */}
      <section
        style={{
          backgroundColor: "#003366",
          backgroundImage: `
            linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
          padding: "56px 48px 0",
        }}
      >
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
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
            Platform{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold-light)" }}>documentation</em>
          </h1>
          <p style={{ fontFamily: "var(--fb)", fontSize: 14, color: "rgba(255,255,255,0.55)", marginTop: 14, maxWidth: 560, lineHeight: 1.8 }}>
            Two perspectives on the same system — one for revenue and product stakeholders,
            one for engineers and architects.
          </p>

          {/* Tab switcher */}
          <div style={{ display: "flex", gap: 4, marginTop: 36 }}>
            {(["business", "engineering"] as View[]).map((v) => {
              const active = view === v;
              return (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  style={{
                    fontFamily: "var(--fb)",
                    fontSize: 10,
                    letterSpacing: "2.5px",
                    textTransform: "uppercase",
                    padding: "10px 24px",
                    border: "none",
                    cursor: "pointer",
                    borderRadius: "8px 8px 0 0",
                    backgroundColor: active ? "var(--light)" : "rgba(255,255,255,0.06)",
                    color: active ? "var(--primary)" : "rgba(255,255,255,0.45)",
                    fontWeight: active ? 600 : 400,
                    transition: "all 0.15s",
                    position: "relative",
                    bottom: -1,
                  }}
                >
                  {v === "business" ? "Business view" : "Engineering view"}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      {/* Content */}
      <div style={{ flex: 1, maxWidth: 1200, margin: "0 auto", width: "100%", padding: "52px 48px" }}>
        {view === "business" ? <BusinessView /> : <EngineeringView />}
      </div>

      <Footer />
    </div>
  );
}
