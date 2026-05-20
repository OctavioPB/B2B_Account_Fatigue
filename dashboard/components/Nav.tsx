"use client";

// BRAND.md: Sticky nav — rgba(0,51,102,.97) bg, blur(12px), 52px height.
// OPB monogram uses inline styles per BRAND.md spec.
// Nav links use navLink / navLinkActive inline spread pattern.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/store/auth";

const NAV_LINKS: { href: string; label: string }[] = [
  { href: "/dashboard", label: "Portfolio" },
  { href: "/accounts", label: "Accounts" },
  { href: "/settings", label: "Settings" },
];

const navLink: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "rgba(255,255,255,0.45)",
  cursor: "pointer",
  fontFamily: "var(--fb)",
  fontSize: "9px",
  letterSpacing: "2px",
  textTransform: "uppercase",
  padding: "5px 8px",
  borderRadius: "6px",
  transition: "color 0.15s",
  textDecoration: "none",
};

const navLinkActive: React.CSSProperties = {
  color: "var(--gold-light)",
  backgroundColor: "rgba(201,168,76,0.12)",
};

const logoutBtn: React.CSSProperties = {
  background: "none",
  border: "1px solid rgba(255,255,255,0.2)",
  borderRadius: "6px",
  color: "rgba(255,255,255,0.5)",
  cursor: "pointer",
  fontFamily: "var(--fb)",
  fontSize: "9px",
  letterSpacing: "2px",
  textTransform: "uppercase",
  padding: "5px 10px",
};

export function Nav({ title = "harmoni" }: { title?: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const logout = useAuthStore((s) => s.logout);

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        height: 52,
        backgroundColor: "rgba(0,51,102,0.97)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        padding: "0 40px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
      }}
    >
      {/* OPB Monogram — BRAND.md: inline styles, not Tailwind */}
      <Link href="/dashboard" style={{ textDecoration: "none" }}>
        <span>
          <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 20, fontWeight: 300, color: "#ffffff" }}>
            h
          </span>
          <em style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 20, fontWeight: 300, fontStyle: "italic", color: "var(--gold-light)" }}>
            armoni
          </em>
        </span>
      </Link>

      {/* Center-right: app title */}
      <span
        style={{
          position: "absolute",
          left: "50%",
          transform: "translateX(-50%)",
          fontFamily: "var(--fb)",
          fontSize: "9px",
          letterSpacing: "3px",
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.4)",
        }}
      >
        {title}
      </span>

      {/* Right cluster: nav links + logout */}
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        {NAV_LINKS.map(({ href, label }) => {
          const isActive = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              style={isActive ? { ...navLink, ...navLinkActive } : navLink}
            >
              {label}
            </Link>
          );
        })}
        <button style={logoutBtn} onClick={handleLogout}>
          Sign out
        </button>
      </div>
    </nav>
  );
}
