"use client";

// BRAND.md: Dark hero section (primary navy + grid texture) for the login cover.
// Fraunces italic title — "Revenue Intelligence" with italic key word.
// KPI stat card pattern for the form container (white, card shadow, gold accent bar).

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuthStore } from "@/lib/store/auth";

export default function LoginPage() {
  const router = useRouter();
  const params = useSearchParams();
  const login = useAuthStore((s) => s.login);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // In dev: accept any non-empty credentials and issue a mock token.
      // In production: POST to /auth/token and receive a real JWT.
      if (!email || !password) {
        throw new Error("Email and password are required.");
      }

      // Mock JWT — replace with real API call in production
      const mockToken = [
        btoa(JSON.stringify({ alg: "HS256", typ: "JWT" })),
        btoa(
          JSON.stringify({
            sub: "11111111-1111-1111-1111-111111111111",
            slug: email.split("@")[1]?.split(".")[0] ?? "demo",
            schema: "tenant_demo",
            plan: "growth",
            rpm: 60,
            exp: Math.floor(Date.now() / 1000) + 3600,
          })
        ),
        "demo-signature",
      ].join(".");

      login(mockToken, email.split("@")[1]?.split(".")[0] ?? "demo");

      const next = params.get("next") ?? "/dashboard";
      router.push(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ minHeight: "100vh", backgroundColor: "var(--primary)", display: "flex", flexDirection: "column" }}>
      {/* BRAND.md: dark hero — primary navy + grid texture */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundImage: `
            linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
          padding: "48px 24px",
        }}
      >
        <div style={{ width: "100%", maxWidth: 420 }}>
          {/* Logo */}
          <div style={{ textAlign: "center", marginBottom: 40 }}>
            <span>
              <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 32, fontWeight: 300, color: "#ffffff" }}>
                h
              </span>
              <em style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 32, fontWeight: 300, fontStyle: "italic", color: "var(--gold-light)" }}>
                armoni
              </em>
            </span>
            <p
              style={{
                fontFamily: "var(--fb)",
                fontSize: 11,
                letterSpacing: "3px",
                textTransform: "uppercase",
                color: "rgba(255,255,255,0.4)",
                marginTop: 8,
              }}
            >
              Revenue Intelligence
            </p>
          </div>

          {/* Login card — BRAND.md: white, border-radius 12, card shadow, gold accent bar */}
          <div
            style={{
              backgroundColor: "#ffffff",
              borderRadius: 12,
              boxShadow: "0 4px 24px rgba(0,0,0,0.2)",
              overflow: "hidden",
            }}
          >
            <div style={{ height: 3, backgroundColor: "var(--gold)" }} />
            <div style={{ padding: "32px 36px" }}>
              <h1
                style={{
                  fontFamily: "'Fraunces', Georgia, serif",
                  fontSize: 22,
                  fontWeight: 300,
                  color: "#0a1628",
                  marginBottom: 24,
                }}
              >
                Sign in to your{" "}
                <em style={{ fontStyle: "italic", color: "var(--gold)" }}>workspace</em>
              </h1>

              <form onSubmit={handleSubmit} noValidate>
                <div style={{ marginBottom: 16 }}>
                  <label
                    htmlFor="email"
                    style={{
                      display: "block",
                      fontFamily: "var(--fb)",
                      fontSize: 10,
                      letterSpacing: "2px",
                      textTransform: "uppercase",
                      color: "var(--mid)",
                      marginBottom: 6,
                    }}
                  >
                    Work email
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    autoComplete="email"
                    required
                    style={{
                      width: "100%",
                      border: "1px solid var(--primary-10)",
                      borderRadius: 6,
                      padding: "10px 14px",
                      fontFamily: "var(--fb)",
                      fontSize: 14,
                      color: "var(--dark)",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                </div>

                <div style={{ marginBottom: 24 }}>
                  <label
                    htmlFor="password"
                    style={{
                      display: "block",
                      fontFamily: "var(--fb)",
                      fontSize: 10,
                      letterSpacing: "2px",
                      textTransform: "uppercase",
                      color: "var(--mid)",
                      marginBottom: 6,
                    }}
                  >
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                    required
                    style={{
                      width: "100%",
                      border: "1px solid var(--primary-10)",
                      borderRadius: 6,
                      padding: "10px 14px",
                      fontFamily: "var(--fb)",
                      fontSize: 14,
                      color: "var(--dark)",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                </div>

                {error && (
                  <div
                    style={{
                      backgroundColor: "#FDEAEA",
                      color: "#7A1020",
                      borderRadius: 6,
                      padding: "10px 14px",
                      fontFamily: "var(--fb)",
                      fontSize: 13,
                      marginBottom: 16,
                    }}
                    role="alert"
                  >
                    {error}
                  </div>
                )}

                <button
                  type="submit"
                  disabled={loading}
                  style={{
                    width: "100%",
                    backgroundColor: "var(--primary)",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: 6,
                    padding: "12px",
                    fontFamily: "var(--fb)",
                    fontSize: 11,
                    fontWeight: 600,
                    letterSpacing: "2px",
                    textTransform: "uppercase",
                    cursor: loading ? "not-allowed" : "pointer",
                    opacity: loading ? 0.7 : 1,
                  }}
                >
                  {loading ? "Signing in…" : "Sign in →"}
                </button>
              </form>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
