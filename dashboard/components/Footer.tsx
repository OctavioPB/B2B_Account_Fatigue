// BRAND.md: Footer — primary bg (#003366), flex space-between, 9px uppercase,
// left: "OPB · AUTHOR · PROJECT", right: current month + year.

export function Footer() {
  const dateLabel = new Date()
    .toLocaleDateString("en-US", { year: "numeric", month: "long" })
    .toUpperCase();

  return (
    <footer
      style={{
        backgroundColor: "var(--primary)",
        padding: "20px 48px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        fontFamily: "var(--fb)",
        fontSize: "9px",
        letterSpacing: "3px",
        textTransform: "uppercase",
        color: "rgba(255,255,255,0.4)",
      }}
    >
      <span>harmoni · Revenue Intelligence · Deal Protection</span>
      <span>{dateLabel}</span>
    </footer>
  );
}
