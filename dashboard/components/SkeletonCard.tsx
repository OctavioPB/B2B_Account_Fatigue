// BRAND.md: Loading skeletons — white card bg, primary-10 shimmer bars.
// Used for all data-dependent views per Sprint 9 DoD.

interface SkeletonCardProps {
  lines?: number;
  height?: number;
}

export function SkeletonCard({ lines = 3, height = 120 }: SkeletonCardProps) {
  return (
    <div
      style={{
        backgroundColor: "#ffffff",
        borderRadius: 12,
        boxShadow: "0 1px 4px rgba(0,51,102,0.08)",
        padding: "24px 28px",
        minHeight: height,
        display: "flex",
        flexDirection: "column",
        gap: 10,
      }}
      aria-busy="true"
      aria-label="Loading…"
    >
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          style={{
            height: i === 0 ? 18 : 12,
            width: i === 0 ? "60%" : `${80 - i * 10}%`,
            backgroundColor: "var(--primary-10)",
            borderRadius: 4,
            animation: "shimmer 1.4s infinite",
          }}
        />
      ))}
      <style>{`
        @keyframes shimmer {
          0%   { opacity: 1; }
          50%  { opacity: 0.45; }
          100% { opacity: 1; }
        }
      `}</style>
    </div>
  );
}

export function SkeletonRow() {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        padding: "14px 16px",
        borderBottom: "1px solid var(--primary-10)",
        alignItems: "center",
      }}
      aria-busy="true"
    >
      {[40, 20, 15, 15].map((w, i) => (
        <div
          key={i}
          style={{
            height: 12,
            flex: w,
            backgroundColor: "var(--primary-10)",
            borderRadius: 4,
            animation: "shimmer 1.4s infinite",
          }}
        />
      ))}
    </div>
  );
}
