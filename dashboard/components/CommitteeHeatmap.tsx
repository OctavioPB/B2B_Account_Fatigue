// BRAND.md: Grid layout, status badge colors for engagement density cells.
// Heatmap: committee members (rows) × signal channels (cols).
// Cell intensity uses the data visualization color series (blue family).

interface HeatmapCell {
  memberName: string;
  memberTitle: string;
  email: number;
  web: number;
  webinar: number;
  crm: number;
}

interface CommitteeHeatmapProps {
  data: HeatmapCell[];
}

const CHANNELS = ["email", "web", "webinar", "crm"] as const;

function cellColor(value: number): string {
  if (value === 0) return "#F4F6F9";
  if (value < 3)  return "#E0EAF4"; // primary-10
  if (value < 8)  return "#99BBDD"; // primary-30
  if (value < 15) return "#336699"; // primary-60
  return "#003366";                  // primary
}

function cellTextColor(value: number): string {
  return value >= 8 ? "#ffffff" : "var(--dark)";
}

export function CommitteeHeatmap({ data }: CommitteeHeatmapProps) {
  if (!data.length) {
    return (
      <div
        style={{
          backgroundColor: "var(--white)",
          borderRadius: 12,
          padding: "28px",
          textAlign: "center",
          color: "var(--mid)",
          fontFamily: "var(--fb)",
          fontSize: 13,
        }}
      >
        No committee member data available.
      </div>
    );
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontFamily: "var(--fb)",
          fontSize: 12,
        }}
        aria-label="Committee engagement heatmap"
      >
        {/* BRAND.md: thead primary bg, white text, 10px uppercase letter-spacing 2px */}
        <thead>
          <tr>
            <th
              style={{
                backgroundColor: "var(--primary)",
                color: "rgba(255,255,255,0.9)",
                textAlign: "left",
                padding: "12px 16px",
                fontSize: 10,
                letterSpacing: "2px",
                textTransform: "uppercase",
                fontWeight: 500,
                minWidth: 180,
              }}
            >
              Member
            </th>
            {CHANNELS.map((ch) => (
              <th
                key={ch}
                style={{
                  backgroundColor: "var(--primary)",
                  color: "rgba(255,255,255,0.9)",
                  textAlign: "center",
                  padding: "12px 16px",
                  fontSize: 10,
                  letterSpacing: "2px",
                  textTransform: "uppercase",
                  fontWeight: 500,
                  minWidth: 72,
                }}
              >
                {ch}
              </th>
            ))}
          </tr>
        </thead>
        {/* BRAND.md: alternating white / primary-10 rows */}
        <tbody>
          {data.map((row, i) => (
            <tr
              key={row.memberName}
              style={{
                backgroundColor: i % 2 === 0 ? "#ffffff" : "var(--primary-10)",
              }}
            >
              <td
                style={{
                  padding: "12px 16px",
                  borderBottom: "1px solid var(--primary-10)",
                }}
              >
                <div style={{ fontWeight: 600, color: "var(--dark)" }}>
                  {row.memberName}
                </div>
                <div style={{ fontSize: 11, color: "var(--mid)", marginTop: 2 }}>
                  {row.memberTitle}
                </div>
              </td>
              {CHANNELS.map((ch) => {
                const val = row[ch];
                return (
                  <td
                    key={ch}
                    style={{
                      textAlign: "center",
                      padding: "12px 16px",
                      borderBottom: "1px solid var(--primary-10)",
                      backgroundColor: cellColor(val),
                      color: cellTextColor(val),
                      fontWeight: val > 0 ? 600 : 400,
                      transition: "background-color 0.15s",
                    }}
                    title={`${row.memberName} · ${ch}: ${val} signals`}
                  >
                    {val > 0 ? val : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
