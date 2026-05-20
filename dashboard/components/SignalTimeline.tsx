// BRAND.md: Callout note cards — left-border 3px gold variant for chronological events.
// Jakarta 12.5px body, gold label, section divider between entries.

import { formatDistanceToNow } from "date-fns";

export interface TimelineSignal {
  id: string;
  signal_type: string;
  channel: string;
  member_name?: string;
  occurred_at: string;
}

const CHANNEL_COLOR: Record<string, string> = {
  email:   "#003366",
  web:     "#27B97C",
  webinar: "#7C4DBD",
  crm:     "#F07020",
  video:   "#E05080",
};

interface SignalTimelineProps {
  signals: TimelineSignal[];
  maxItems?: number;
}

function formatSignalType(t: string): string {
  return t.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function SignalTimeline({ signals, maxItems = 10 }: SignalTimelineProps) {
  const visible = signals.slice(0, maxItems);

  if (!visible.length) {
    return (
      <div
        style={{
          padding: "24px",
          textAlign: "center",
          color: "var(--mid)",
          fontFamily: "var(--fb)",
          fontSize: 13,
        }}
      >
        No signals recorded yet.
      </div>
    );
  }

  return (
    <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 12 }}>
      {visible.map((signal) => {
        const channelColor = CHANNEL_COLOR[signal.channel] ?? "#003366";
        const timeAgo = (() => {
          try {
            return formatDistanceToNow(new Date(signal.occurred_at), { addSuffix: true });
          } catch {
            return signal.occurred_at;
          }
        })();

        return (
          <li
            key={signal.id}
            style={{
              backgroundColor: "#ffffff",
              borderRadius: 10,
              padding: "14px 16px",
              boxShadow: "0 1px 3px rgba(0,51,102,0.07)",
              borderLeft: "3px solid var(--gold)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: 12,
            }}
          >
            <div>
              {/* BRAND.md: archNote label — 9px uppercase gold, letter-spacing 1.5px */}
              <div
                style={{
                  fontFamily: "var(--fb)",
                  fontSize: 9,
                  fontWeight: 700,
                  letterSpacing: "1.5px",
                  textTransform: "uppercase",
                  color: "#C8982A",
                  marginBottom: 5,
                }}
              >
                {formatSignalType(signal.signal_type)}
              </div>
              <div
                style={{
                  fontFamily: "var(--fb)",
                  fontSize: 12.5,
                  color: "#475569",
                  lineHeight: 1.65,
                }}
              >
                {signal.member_name ?? "Unknown member"}{" "}
                <span
                  style={{
                    display: "inline-block",
                    backgroundColor: channelColor,
                    color: "#ffffff",
                    borderRadius: 4,
                    padding: "1px 6px",
                    fontSize: 9,
                    fontWeight: 700,
                    letterSpacing: "1.5px",
                    textTransform: "uppercase",
                    marginLeft: 4,
                  }}
                >
                  {signal.channel}
                </span>
              </div>
            </div>
            <div
              style={{
                fontFamily: "var(--fb)",
                fontSize: 11,
                color: "var(--mid)",
                whiteSpace: "nowrap",
                marginTop: 2,
              }}
            >
              {timeAgo}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
