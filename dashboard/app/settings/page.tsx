"use client";

// BRAND.md: Settings page — dark hero, body sections with Eyebrow + SectionTitle,
// callout note cards (borderLeft gold) for connector status, pipeline cards for webhook list.

import { useState } from "react";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Eyebrow } from "@/components/Eyebrow";
import { useAuthStore } from "@/lib/store/auth";

const CONNECTOR_STATUS = [
  { name: "HubSpot CRM",       status: "connected", lastSync: "2 min ago" },
  { name: "Salesloft Cadences", status: "connected", lastSync: "5 min ago" },
  { name: "Zoom Webinars",      status: "connected", lastSync: "12 min ago" },
  { name: "Email Analytics",   status: "warning",   lastSync: "4 hours ago" },
  { name: "Web Tracking",      status: "connected", lastSync: "1 min ago" },
];

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  connected: { bg: "#E0F7EF", text: "#0D5C3A", dot: "#27B97C" },
  warning:   { bg: "#FEF0E6", text: "#7A3800", dot: "#F07020" },
  error:     { bg: "#FDEAEA", text: "#7A1020", dot: "#E03448" },
};

const MOCK_WEBHOOKS = [
  { id: "wh-1", target_url: "https://hooks.zapier.com/hooks/catch/abc123", event_types: ["nba.created", "fatigue.critical"], is_active: true, failure_count: 0, created_at: "2024-06-15" },
  { id: "wh-2", target_url: "https://slack-integration.example.com/harmoni", event_types: ["cooldown.set", "churn.critical"], is_active: true, failure_count: 2, created_at: "2024-06-20" },
];

const sectionDivider: React.CSSProperties = {
  height: 1, backgroundColor: "var(--primary-10)", border: "none", margin: "48px 0",
};

export default function SettingsPage() {
  const tenantSlug = useAuthStore((s) => s.tenantSlug);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookEvents, setWebhookEvents] = useState<string[]>([]);
  const [registeredMsg, setRegisteredMsg] = useState<string | null>(null);

  const EVENT_OPTS = ["nba.created", "fatigue.critical", "fatigue.high", "cooldown.set", "churn.critical", "signal.ingested"];

  function toggleEvent(ev: string) {
    setWebhookEvents((prev) =>
      prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]
    );
  }

  function handleRegister(e: React.FormEvent) {
    e.preventDefault();
    if (!webhookUrl || webhookEvents.length === 0) return;
    setRegisteredMsg(`Webhook registered for ${webhookUrl}`);
    setWebhookUrl("");
    setWebhookEvents([]);
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--light)", display: "flex", flexDirection: "column" }}>
      <Nav title="Settings" />

      {/* BRAND.md: dark hero — no eyebrow */}
      <section
        style={{
          backgroundColor: "#003366",
          backgroundImage: `
            linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
          padding: "48px 48px 40px",
        }}
      >
        <div style={{ maxWidth: 1300, margin: "0 auto" }}>
          <h1
            style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 40,
              fontWeight: 300,
              color: "#ffffff",
              margin: 0,
              lineHeight: 1.2,
            }}
          >
            Workspace{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold-light)" }}>settings</em>
          </h1>
          {tenantSlug && (
            <p style={{ fontFamily: "var(--fb)", fontSize: 12, color: "rgba(255,255,255,0.45)", marginTop: 12, letterSpacing: "1.5px" }}>
              Tenant: <span style={{ color: "rgba(255,255,255,0.7)", fontFamily: "Courier New" }}>{tenantSlug}</span>
            </p>
          )}
        </div>
      </section>

      <div style={{ flex: 1, maxWidth: 1300, margin: "0 auto", width: "100%", padding: "40px 48px" }}>

        {/* Section: Connector status */}
        <section style={{ marginBottom: 48 }}>
          <Eyebrow>Data connectors</Eyebrow>
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 4px", lineHeight: 1.25 }}>
            Source{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold)" }}>integrations</em>
          </h2>
          <p style={{ fontFamily: "var(--fb)", fontSize: 13, color: "var(--mid)", marginBottom: 20 }}>
            Real-time signal sources feeding the CEP pipeline.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 12 }}>
            {CONNECTOR_STATUS.map((conn) => {
              const colors = STATUS_COLORS[conn.status];
              return (
                <div
                  key={conn.name}
                  style={{
                    backgroundColor: "#ffffff",
                    borderRadius: 10,
                    padding: "16px 20px",
                    boxShadow: "0 1px 3px rgba(0,51,102,0.07)",
                    borderLeft: "3px solid var(--gold)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                  }}
                >
                  <div>
                    <div style={{ fontFamily: "var(--fb)", fontSize: 13, fontWeight: 600, color: "#0a1628", marginBottom: 4 }}>
                      {conn.name}
                    </div>
                    <div style={{ fontFamily: "var(--fb)", fontSize: 11, color: "var(--mid)" }}>
                      Last sync: {conn.lastSync}
                    </div>
                  </div>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 5,
                      backgroundColor: colors.bg,
                      color: colors.text,
                      borderRadius: 20,
                      padding: "3px 10px",
                      fontSize: 9,
                      fontFamily: "var(--fb)",
                      fontWeight: 600,
                      letterSpacing: "1px",
                      textTransform: "uppercase",
                    }}
                  >
                    <span style={{ width: 5, height: 5, borderRadius: "50%", backgroundColor: colors.dot }} />
                    {conn.status}
                  </span>
                </div>
              );
            })}
          </div>
        </section>

        <hr style={sectionDivider} />

        {/* Section: Webhook registrations */}
        <section style={{ marginBottom: 48 }}>
          <Eyebrow>Webhook dispatch</Eyebrow>
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 4px", lineHeight: 1.25 }}>
            Outbound{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold)" }}>webhooks</em>
          </h2>
          <p style={{ fontFamily: "var(--fb)", fontSize: 13, color: "var(--mid)", marginBottom: 24 }}>
            Register HTTPS endpoints to receive NBA events in real time. Payloads are HMAC-SHA256 signed.
          </p>

          {/* Existing webhooks */}
          {MOCK_WEBHOOKS.length > 0 && (
            <div style={{ marginBottom: 28, display: "flex", flexDirection: "column", gap: 10 }}>
              {MOCK_WEBHOOKS.map((wh) => (
                <div
                  key={wh.id}
                  style={{
                    backgroundColor: "#ffffff",
                    borderRadius: 10,
                    padding: "16px 20px",
                    boxShadow: "0 1px 3px rgba(0,51,102,0.07)",
                    borderLeft: "3px solid var(--gold)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: 12,
                  }}
                >
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontFamily: "Courier New", fontSize: 12, color: "var(--dark)", marginBottom: 6, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {wh.target_url}
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {wh.event_types.map((ev) => (
                        <span
                          key={ev}
                          style={{
                            backgroundColor: "var(--primary-10)",
                            color: "var(--primary)",
                            borderRadius: 4,
                            padding: "2px 8px",
                            fontSize: 9,
                            fontFamily: "var(--fb)",
                            fontWeight: 700,
                            letterSpacing: "1px",
                            textTransform: "uppercase",
                          }}
                        >
                          {ev}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexShrink: 0 }}>
                    {wh.failure_count > 0 && (
                      <span style={{ fontFamily: "var(--fb)", fontSize: 11, color: "#F07020" }}>
                        {wh.failure_count} failures
                      </span>
                    )}
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 4,
                        backgroundColor: "#E0F7EF",
                        color: "#0D5C3A",
                        borderRadius: 20,
                        padding: "3px 10px",
                        fontSize: 9,
                        fontFamily: "var(--fb)",
                        fontWeight: 600,
                        letterSpacing: "1px",
                        textTransform: "uppercase",
                      }}
                    >
                      <span style={{ width: 5, height: 5, borderRadius: "50%", backgroundColor: "#27B97C" }} />
                      Active
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Register form */}
          <div
            style={{
              backgroundColor: "#ffffff",
              borderRadius: 12,
              boxShadow: "0 1px 4px rgba(0,51,102,0.08)",
              overflow: "hidden",
            }}
          >
            <div style={{ height: 3, backgroundColor: "var(--gold)" }} />
            <div style={{ padding: "28px 32px" }}>
              <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 17, fontWeight: 400, color: "#0a1628", marginBottom: 20 }}>
                Register a new webhook
              </div>
              <form onSubmit={handleRegister}>
                <div style={{ marginBottom: 16 }}>
                  <label
                    htmlFor="webhook-url"
                    style={{ display: "block", fontFamily: "var(--fb)", fontSize: 10, letterSpacing: "2px", textTransform: "uppercase", color: "var(--mid)", marginBottom: 6 }}
                  >
                    Target URL (HTTPS required)
                  </label>
                  <input
                    id="webhook-url"
                    type="url"
                    value={webhookUrl}
                    onChange={(e) => setWebhookUrl(e.target.value)}
                    placeholder="https://hooks.example.com/harmoni"
                    style={{
                      width: "100%",
                      border: "1px solid var(--primary-10)",
                      borderRadius: 6,
                      padding: "10px 14px",
                      fontFamily: "Courier New",
                      fontSize: 13,
                      color: "var(--dark)",
                      boxSizing: "border-box",
                      outline: "none",
                    }}
                  />
                </div>

                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontFamily: "var(--fb)", fontSize: 10, letterSpacing: "2px", textTransform: "uppercase", color: "var(--mid)", marginBottom: 10 }}>
                    Subscribe to events
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {EVENT_OPTS.map((ev) => {
                      const selected = webhookEvents.includes(ev);
                      return (
                        <button
                          key={ev}
                          type="button"
                          onClick={() => toggleEvent(ev)}
                          style={{
                            fontFamily: "var(--fb)",
                            fontSize: 9,
                            letterSpacing: "1.5px",
                            textTransform: "uppercase",
                            padding: "5px 12px",
                            borderRadius: 4,
                            border: `1px solid ${selected ? "var(--primary)" : "var(--primary-10)"}`,
                            backgroundColor: selected ? "var(--primary)" : "#ffffff",
                            color: selected ? "#ffffff" : "var(--mid)",
                            cursor: "pointer",
                          }}
                        >
                          {ev}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {registeredMsg && (
                  <div
                    style={{
                      backgroundColor: "#E0F7EF",
                      color: "#0D5C3A",
                      borderRadius: 6,
                      padding: "10px 14px",
                      fontFamily: "var(--fb)",
                      fontSize: 13,
                      marginBottom: 16,
                    }}
                    role="status"
                  >
                    {registeredMsg}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={!webhookUrl || webhookEvents.length === 0}
                  style={{
                    backgroundColor: "var(--primary)",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: 6,
                    padding: "10px 22px",
                    fontFamily: "var(--fb)",
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: "2px",
                    textTransform: "uppercase",
                    cursor: !webhookUrl || webhookEvents.length === 0 ? "not-allowed" : "pointer",
                    opacity: !webhookUrl || webhookEvents.length === 0 ? 0.5 : 1,
                  }}
                >
                  Register webhook →
                </button>
              </form>
            </div>
          </div>
        </section>

        <hr style={sectionDivider} />

        {/* Section: Tenant info */}
        <section style={{ marginBottom: 48 }}>
          <Eyebrow>Tenant config</Eyebrow>
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: "#0a1628", margin: "0 0 20px", lineHeight: 1.25 }}>
            Workspace{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold)" }}>configuration</em>
          </h2>

          <div
            style={{
              backgroundColor: "#ffffff",
              borderRadius: 10,
              padding: "20px 24px",
              boxShadow: "0 1px 3px rgba(0,51,102,0.07)",
              borderLeft: "3px solid var(--gold)",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
              gap: 20,
            }}
          >
            {[
              { label: "Tenant", value: tenantSlug ?? "—" },
              { label: "Plan", value: "Growth" },
              { label: "Rate limit", value: "60 req/min" },
              { label: "Schema isolation", value: "PostgreSQL" },
            ].map(({ label, value }) => (
              <div key={label}>
                <div style={{ fontFamily: "var(--fb)", fontSize: 9, letterSpacing: "2px", textTransform: "uppercase", color: "var(--mid)", marginBottom: 4 }}>
                  {label}
                </div>
                <div style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 16, fontWeight: 400, color: "#0a1628" }}>
                  {value}
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
