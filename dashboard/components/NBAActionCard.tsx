"use client";

// BRAND.md: Numbered pillar card — white bg, 12px border-radius, gold 3px accent bar,
// Fraunces ghosted number watermark, Jakarta body text.
// One-click dispatch button — direct CTA, not "Click here".

import type { NextBestAction, NBAActionType } from "@/lib/types";
import { FatigueScoreBadge } from "./FatigueScoreBadge";

const ACTION_META: Record<
  NBAActionType,
  { label: string; description: string; urgency: "low" | "medium" | "high" | "critical" }
> = {
  COOLDOWN:        { label: "Cooldown", description: "Pause all outreach — account fatigue is critical.", urgency: "critical" },
  DEAL_REVIEW:     { label: "Deal Review", description: "Flag for internal review — churn risk elevated.", urgency: "high" },
  EXEC_ESCALATION: { label: "Exec Escalation", description: "Route to AE / VP for executive outreach.", urgency: "high" },
  PRICING_TRIGGER: { label: "Pricing Trigger", description: "Surface pricing and ROI content now.", urgency: "medium" },
  ACCELERATE:      { label: "Accelerate", description: "High-intent — increase cadence and urgency.", urgency: "medium" },
  RE_ENGAGE:       { label: "Re-engage", description: "Personalized re-engagement sequence.", urgency: "medium" },
  NURTURE:         { label: "Nurture", description: "Low-pressure educational content sequence.", urgency: "low" },
};

const URGENCY_ACCENT: Record<string, string> = {
  critical: "#E03448",
  high:     "#F07020",
  medium:   "#C8982A",
  low:      "#27B97C",
};

interface NBAActionCardProps {
  action: NextBestAction;
  onDispatch?: (action: NextBestAction) => void;
}

export function NBAActionCard({ action, onDispatch }: NBAActionCardProps) {
  const meta = ACTION_META[action.action_type];
  const accentColor = URGENCY_ACCENT[meta.urgency];

  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        borderRadius: 12,
        boxShadow: "0 1px 4px rgba(0,51,102,0.08)",
        overflow: "hidden",
      }}
    >
      {/* BRAND.md: 3px gold accent bar (solid, no gradient) — colored by urgency */}
      <div style={{ height: 3, backgroundColor: accentColor }} />

      <div style={{ padding: "24px 28px" }}>
        {/* Priority watermark — BRAND.md ghosted Fraunces number */}
        <div
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 44,
            fontWeight: 300,
            color: "#f1f5f9",
            lineHeight: 1,
            marginBottom: 2,
            userSelect: "none",
          }}
        >
          {action.priority}
        </div>

        <div
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 16,
            fontWeight: 400,
            color: "#0a1628",
            marginBottom: 4,
          }}
        >
          {meta.label}
        </div>

        <div
          style={{
            fontFamily: "var(--fb)",
            fontSize: 12,
            color: "#475569",
            lineHeight: 1.7,
            marginBottom: 12,
          }}
        >
          {meta.description}
        </div>

        {/* Rationale */}
        <div
          style={{
            backgroundColor: "var(--light)",
            borderLeft: "3px solid var(--gold)",
            borderRadius: "0 6px 6px 0",
            padding: "10px 14px",
            fontFamily: "var(--fb)",
            fontSize: 12,
            color: "#475569",
            lineHeight: 1.65,
            marginBottom: 16,
          }}
        >
          {action.rationale}
        </div>

        {/* Score row */}
        <div
          style={{
            display: "flex",
            gap: 16,
            marginBottom: 16,
            flexWrap: "wrap",
          }}
        >
          {[
            { label: "Fatigue", value: `${Math.round(action.fatigue_score)}` },
            { label: "Intent", value: `${Math.round(action.intent_score)}` },
            { label: "Churn", value: `${Math.round(action.churn_probability * 100)}%` },
          ].map(({ label, value }) => (
            <div key={label} style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
              <span
                style={{
                  fontFamily: "'Fraunces', Georgia, serif",
                  fontSize: 22,
                  fontWeight: 300,
                  color: "var(--dark)",
                  lineHeight: 1,
                }}
              >
                {value}
              </span>
              <span
                style={{
                  fontFamily: "var(--fb)",
                  fontSize: 9,
                  letterSpacing: "2px",
                  textTransform: "uppercase",
                  color: "var(--mid)",
                }}
              >
                {label}
              </span>
            </div>
          ))}
        </div>

        {onDispatch && (
          <button
            onClick={() => onDispatch(action)}
            style={{
              display: "inline-block",
              backgroundColor: accentColor,
              color: "#ffffff",
              border: "none",
              borderRadius: 6,
              padding: "8px 18px",
              fontFamily: "var(--fb)",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "1px",
              cursor: "pointer",
              textTransform: "uppercase",
            }}
          >
            Dispatch action →
          </button>
        )}
      </div>
    </div>
  );
}
