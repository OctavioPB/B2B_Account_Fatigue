"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  token: string | null;
  tenantSlug: string | null;
  isAuthenticated: boolean;
  isDemo: boolean;
  login: (token: string, tenantSlug: string) => void;
  enterDemo: () => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      tenantSlug: null,
      isAuthenticated: false,
      isDemo: false,

      login: (token, tenantSlug) => {
        document.cookie = `harmoni_token=${token}; path=/; max-age=3600; SameSite=Strict`;
        set({ token, tenantSlug, isAuthenticated: true, isDemo: false });
      },

      enterDemo: () => {
        const demoToken = [
          btoa(JSON.stringify({ alg: "HS256", typ: "JWT" })),
          btoa(JSON.stringify({
            sub: "demo-tenant-id",
            slug: "demo",
            schema: "tenant_demo",
            plan: "growth",
            rpm: 120,
            exp: Math.floor(Date.now() / 1000) + 86400,
          })),
          "demo-signature",
        ].join(".");
        document.cookie = `harmoni_token=${demoToken}; path=/; max-age=86400; SameSite=Strict`;
        set({ token: demoToken, tenantSlug: "demo", isAuthenticated: true, isDemo: true });
      },

      logout: () => {
        document.cookie = "harmoni_token=; path=/; max-age=0";
        set({ token: null, tenantSlug: null, isAuthenticated: false, isDemo: false });
      },
    }),
    {
      name: "harmoni-auth",
      partialize: (state) => ({
        token: state.token,
        tenantSlug: state.tenantSlug,
        isAuthenticated: state.isAuthenticated,
        isDemo: state.isDemo,
      }),
    }
  )
);
