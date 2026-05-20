import type { Config } from "tailwindcss";

// Design tokens from BRAND.md — single source of truth for all visual decisions.
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#003366",
          80: "#1A4D80",
          60: "#336699",
          30: "#99BBDD",
          10: "#E0EAF4",
        },
        gold: {
          DEFAULT: "#C8982A",
          light: "#E8C46A",
        },
        dark: "#1C1C2E",
        mid: "#6B7280",
        light: "#F4F6F9",
      },
      fontFamily: {
        display: ["Fraunces", "Georgia", "serif"],
        body: ["Plus Jakarta Sans", "sans-serif"],
      },
      fontSize: {
        label: ["10px", { letterSpacing: "3px", fontWeight: "500" }],
        eyebrow: ["9px", { letterSpacing: "4px", fontWeight: "500" }],
      },
      borderRadius: {
        card: "12px",
      },
      boxShadow: {
        card: "0 1px 4px rgba(0,51,102,0.08)",
        "card-md": "0 1px 6px rgba(0,51,102,0.09)",
      },
      maxWidth: {
        content: "1200px",
        dashboard: "1300px",
      },
    },
  },
  plugins: [],
};

export default config;
