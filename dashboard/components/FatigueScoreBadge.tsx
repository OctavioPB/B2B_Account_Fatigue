// BRAND.md: Status badges — semantic color system (pill, 6px dot, 10px font, 4px 12px padding).
// CRITICAL → red, HIGH → orange, MEDIUM → purple, LOW → green.

import type { FatigueSeverity } from "@/lib/types";

const SEVERITY_COLORS: Record<
  FatigueSeverity,
  { bg: string; text: string; dot: string; label: string }
> = {
  CRITICAL: { bg: "#FDEAEA", text: "#7A1020", dot: "#E03448", label: "Critical" },
  HIGH:     { bg: "#FEF0E6", text: "#7A3800", dot: "#F07020", label: "High" },
  MEDIUM:   { bg: "#F0EBF9", text: "#3D1F70", dot: "#7C4DBD", label: "Medium" },
  LOW:      { bg: "#E0F7EF", text: "#0D5C3A", dot: "#27B97C", label: "Low" },
};

interface FatigueScoreBadgeProps {
  score: number;
  severity: FatigueSeverity;
  showScore?: boolean;
}

export function FatigueScoreBadge({
  score,
  severity,
  showScore = true,
}: FatigueScoreBadgeProps) {
  const { bg, text, dot, label } = SEVERITY_COLORS[severity];

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 6,
        backgroundColor: bg,
        color: text,
        borderRadius: 20,
        padding: "4px 12px",
        fontFamily: "var(--fb)",
        fontSize: 10,
        fontWeight: 500,
        letterSpacing: "0.5px",
      }}
    >
      <span
        style={{ width: 6, height: 6, borderRadius: "50%", backgroundColor: dot, flexShrink: 0 }}
      />
      {label}
      {showScore && (
        <span style={{ fontWeight: 600, marginLeft: 2 }}>{Math.round(score)}</span>
      )}
    </span>
  );
}
