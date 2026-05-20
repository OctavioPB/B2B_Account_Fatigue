"use client";

// BRAND.md: Body section structure — Eyebrow + SectionTitle + content.
// Table: BRAND.md thead primary bg, alternating rows, 1px primary-10 borders.
// Filters: Jakarta 10px uppercase labels, primary-10 bg chips.

import Link from "next/link";
import { useState } from "react";
import { useAccountList } from "@/lib/hooks/useAccounts";
import { Nav } from "@/components/Nav";
import { Footer } from "@/components/Footer";
import { Eyebrow } from "@/components/Eyebrow";
import { FatigueScoreBadge } from "@/components/FatigueScoreBadge";
import { SkeletonRow } from "@/components/SkeletonCard";
import type { FatigueSeverity } from "@/lib/types";

type SortField = "domain" | "fatigue" | "intent" | "churn";
type SortDir = "asc" | "desc";

// Stub data for demo — replaced by live API data when backend is running
const MOCK_ACCOUNTS = [
  { id: "1", domain: "acme.com",     display_name: "Acme Corp",       industry: "Technology", arr_usd: 480000, committee_size: 6, fatigue: 82, severity: "CRITICAL" as FatigueSeverity, intent: 35, churn: 0.71 },
  { id: "2", domain: "globex.com",   display_name: "Globex Inc",      industry: "Finance",    arr_usd: 320000, committee_size: 4, fatigue: 67, severity: "HIGH" as FatigueSeverity,     intent: 71, churn: 0.28 },
  { id: "3", domain: "initech.com",  display_name: "Initech Ltd",     industry: "SaaS",       arr_usd: 150000, committee_size: 3, fatigue: 44, severity: "MEDIUM" as FatigueSeverity,   intent: 55, churn: 0.19 },
  { id: "4", domain: "umbrella.io",  display_name: "Umbrella Corp",   industry: "Healthcare", arr_usd: 220000, committee_size: 5, fatigue: 18, severity: "LOW" as FatigueSeverity,      intent: 88, churn: 0.05 },
  { id: "5", domain: "stark.io",     display_name: "Stark Industries", industry: "Defense",   arr_usd: 950000, committee_size: 8, fatigue: 29, severity: "LOW" as FatigueSeverity,      intent: 62, churn: 0.10 },
  { id: "6", domain: "wayne.co",     display_name: "Wayne Enterprises", industry: "Conglomerate", arr_usd: 2100000, committee_size: 7, fatigue: 55, severity: "MEDIUM" as FatigueSeverity, intent: 77, churn: 0.22 },
];

const SEVERITY_OPTS: (FatigueSeverity | "ALL")[] = ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW"];

export default function AccountsPage() {
  const { data, isLoading } = useAccountList();
  const [severityFilter, setSeverityFilter] = useState<FatigueSeverity | "ALL">("ALL");
  const [sort, setSort] = useState<{ field: SortField; dir: SortDir }>({ field: "fatigue", dir: "desc" });

  const accounts = data?.items?.length ? data.items : MOCK_ACCOUNTS;

  const filtered = MOCK_ACCOUNTS
    .filter((a) => severityFilter === "ALL" || a.severity === severityFilter)
    .sort((a, b) => {
      const mul = sort.dir === "desc" ? -1 : 1;
      if (sort.field === "domain")  return mul * a.domain.localeCompare(b.domain);
      if (sort.field === "fatigue") return mul * (a.fatigue - b.fatigue);
      if (sort.field === "intent")  return mul * (a.intent - b.intent);
      if (sort.field === "churn")   return mul * (a.churn - b.churn);
      return 0;
    });

  function toggleSort(field: SortField) {
    setSort((prev) =>
      prev.field === field
        ? { field, dir: prev.dir === "desc" ? "asc" : "desc" }
        : { field, dir: "desc" }
    );
  }

  const sortIndicator = (field: SortField) =>
    sort.field === field ? (sort.dir === "desc" ? " ↓" : " ↑") : "";

  return (
    <div style={{ minHeight: "100vh", background: "var(--light)", display: "flex", flexDirection: "column" }}>
      <Nav title="Accounts" />

      {/* BRAND.md: dark hero */}
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
            Account{" "}
            <em style={{ fontStyle: "italic", color: "var(--gold-light)" }}>portfolio</em>
          </h1>
          <p
            style={{
              fontFamily: "var(--fb)",
              fontSize: 13,
              color: "rgba(255,255,255,0.55)",
              marginTop: 12,
              lineHeight: 1.7,
            }}
          >
            {filtered.length} accounts · sorted by {sort.field}
          </p>
        </div>
      </section>

      <div style={{ flex: 1, maxWidth: 1300, margin: "0 auto", width: "100%", padding: "40px 48px" }}>

        {/* Filters */}
        <section style={{ marginBottom: 28 }}>
          <Eyebrow>Filter by severity</Eyebrow>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {SEVERITY_OPTS.map((sev) => {
              const active = severityFilter === sev;
              return (
                <button
                  key={sev}
                  onClick={() => setSeverityFilter(sev)}
                  style={{
                    fontFamily: "var(--fb)",
                    fontSize: 9,
                    letterSpacing: "2px",
                    textTransform: "uppercase",
                    padding: "5px 14px",
                    borderRadius: 20,
                    border: `1px solid ${active ? "var(--primary)" : "var(--primary-10)"}`,
                    backgroundColor: active ? "var(--primary)" : "#ffffff",
                    color: active ? "#ffffff" : "var(--mid)",
                    cursor: "pointer",
                    transition: "all 0.15s",
                  }}
                >
                  {sev === "ALL" ? "All" : sev.charAt(0) + sev.slice(1).toLowerCase()}
                </button>
              );
            })}
          </div>
        </section>

        {/* Table */}
        <div
          style={{
            backgroundColor: "#ffffff",
            borderRadius: 12,
            boxShadow: "0 1px 4px rgba(0,51,102,0.08)",
            overflow: "hidden",
          }}
        >
          <div style={{ height: 3, backgroundColor: "var(--gold)" }} />

          {isLoading ? (
            <div style={{ padding: 4 }}>
              {Array.from({ length: 6 }).map((_, i) => <SkeletonRow key={i} />)}
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "var(--fb)" }}>
              <thead>
                <tr>
                  {(
                    [
                      { key: "domain", label: "Account" },
                      { key: "fatigue", label: "Fatigue" },
                      { key: "intent", label: "Intent" },
                      { key: "churn", label: "Churn" },
                      { key: null, label: "Industry" },
                      { key: null, label: "ARR" },
                      { key: null, label: "Committee" },
                      { key: null, label: "" },
                    ] as { key: SortField | null; label: string }[]
                  ).map(({ key, label }) => (
                    <th
                      key={label}
                      onClick={key ? () => toggleSort(key) : undefined}
                      style={{
                        backgroundColor: "var(--primary)",
                        color: "rgba(255,255,255,0.9)",
                        textAlign: "left",
                        padding: "12px 16px",
                        fontSize: 10,
                        letterSpacing: "2px",
                        textTransform: "uppercase",
                        fontWeight: 500,
                        cursor: key ? "pointer" : "default",
                        userSelect: "none",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {label}{key ? sortIndicator(key) : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((acc, i) => (
                  <tr key={acc.domain} style={{ backgroundColor: i % 2 === 0 ? "#ffffff" : "var(--primary-10)" }}>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                      <div style={{ fontWeight: 600, color: "var(--dark)" }}>{acc.display_name}</div>
                      <div style={{ fontFamily: "Courier New", fontSize: 11, color: "var(--mid)" }}>{acc.domain}</div>
                    </td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                      <FatigueScoreBadge score={acc.fatigue} severity={acc.severity} />
                    </td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                      <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 20, fontWeight: 300, color: acc.intent >= 70 ? "#27B97C" : acc.intent >= 40 ? "#F07020" : "#E03448" }}>
                        {acc.intent}
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                      <span style={{ fontWeight: 600, fontSize: 13, color: acc.churn >= 0.6 ? "#E03448" : acc.churn >= 0.3 ? "#F07020" : "#27B97C" }}>
                        {Math.round(acc.churn * 100)}%
                      </span>
                    </td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)", color: "var(--mid)", fontSize: 13 }}>{acc.industry}</td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)", fontSize: 13 }}>
                      ${(acc.arr_usd / 1000).toFixed(0)}k
                    </td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)", fontSize: 13, color: "var(--mid)" }}>
                      {acc.committee_size} members
                    </td>
                    <td style={{ padding: "12px 16px", borderBottom: "1px solid var(--primary-10)" }}>
                      <Link
                        href={`/accounts/${acc.domain}`}
                        style={{ fontFamily: "var(--fb)", fontSize: 11, color: "var(--primary)", textDecoration: "none", fontWeight: 600 }}
                      >
                        Detail →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <Footer />
    </div>
  );
}
