// BRAND.md: Chart bars — track background var(--light), fill uses data visualization
// color series. Gauge: arc SVG with corporate blue fill, Fraunces 32px score number.

interface IntentScoreGaugeProps {
  score: number;      // 0–100
  confidence: number; // 0–1
  size?: number;
}

export function IntentScoreGauge({
  score,
  confidence,
  size = 120,
}: IntentScoreGaugeProps) {
  const radius = (size - 16) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = Math.PI * radius; // half-circle arc

  // Convert score 0–100 to arc length on the top half-circle
  const filled = (score / 100) * circumference;
  const gap = circumference - filled;

  // Score color: green ≥70, orange 40–69, red <40
  const arcColor =
    score >= 70 ? "#27B97C" : score >= 40 ? "#F07020" : "#E03448";

  return (
    <div
      style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
    >
      <svg
        width={size}
        height={size / 2 + 8}
        viewBox={`0 0 ${size} ${size / 2 + 8}`}
        aria-label={`Intent score ${score} out of 100`}
        role="img"
      >
        {/* Track (background arc) */}
        <path
          d={`M 8,${cy} A ${radius},${radius} 0 0 1 ${size - 8},${cy}`}
          fill="none"
          stroke="var(--primary-10)"
          strokeWidth={8}
          strokeLinecap="round"
        />
        {/* Filled arc */}
        <path
          d={`M 8,${cy} A ${radius},${radius} 0 0 1 ${size - 8},${cy}`}
          fill="none"
          stroke={arcColor}
          strokeWidth={8}
          strokeLinecap="round"
          strokeDasharray={`${filled} ${gap}`}
        />
        {/* Score label */}
        <text
          x={cx}
          y={cy - 4}
          textAnchor="middle"
          fontFamily="'Fraunces', Georgia, serif"
          fontSize={size * 0.27}
          fontWeight={300}
          fill="var(--dark)"
        >
          {Math.round(score)}
        </text>
      </svg>
      {/* Confidence indicator */}
      <span
        style={{
          fontFamily: "var(--fb)",
          fontSize: 10,
          color: "var(--mid)",
          letterSpacing: "1px",
          textTransform: "uppercase",
        }}
      >
        {Math.round(confidence * 100)}% confidence
      </span>
    </div>
  );
}
