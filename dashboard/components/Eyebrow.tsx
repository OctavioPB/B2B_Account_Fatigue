// BRAND.md: Gold eyebrow label with 24px horizontal line before text.
// light={true} when sitting on dark navy; default for white/var(--light) backgrounds.

interface EyebrowProps {
  children: React.ReactNode;
  light?: boolean;
}

export function Eyebrow({ children, light = false }: EyebrowProps) {
  const color = light ? "var(--gold-light)" : "var(--gold)";
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 8,
        fontSize: 9,
        fontFamily: "var(--fb)",
        fontWeight: 500,
        letterSpacing: "4px",
        textTransform: "uppercase",
        color,
        marginBottom: 10,
      }}
    >
      <div
        style={{ width: 24, height: 1, flexShrink: 0, backgroundColor: color }}
      />
      {children}
    </div>
  );
}
